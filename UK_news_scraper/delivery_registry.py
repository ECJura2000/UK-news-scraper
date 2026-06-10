from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .runtime_lock import exclusive_lock


DEFAULT_REGISTRY = Path.home() / ".codex" / "automations" / "uk" / "sent_run_ids.json"


def claim_delivery(summary_path: str | Path, registry_path: str | Path = DEFAULT_REGISTRY) -> dict:
    summary = _read_json(Path(summary_path))
    delivery_id = summary["delivery_id"]
    registry_path = Path(registry_path)
    with exclusive_lock(registry_path.with_suffix(".lock"), wait_seconds=10):
        registry = _read_json(registry_path, default={})
        legacy_record = registry.get(summary["run_id"])
        if legacy_record:
            return {
                "claimed": False,
                "delivery_id": delivery_id,
                "existing": legacy_record,
                "reason": "legacy run_id already sent",
            }
        existing = registry.get(delivery_id)
        if existing and existing.get("state") in {"claimed", "sent"}:
            return {"claimed": False, "delivery_id": delivery_id, "existing": existing}
        registry[delivery_id] = {
            "state": "claimed",
            "run_id": summary["run_id"],
            "status": summary["status"],
            "data_fingerprint": summary["data_fingerprint"],
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "excel_path": summary["output_file"],
        }
        _atomic_write_json(registry_path, registry)
    return {"claimed": True, "delivery_id": delivery_id}


def complete_delivery(
    delivery_id: str,
    message_id: str,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> dict:
    registry_path = Path(registry_path)
    with exclusive_lock(registry_path.with_suffix(".lock"), wait_seconds=10):
        registry = _read_json(registry_path, default={})
        record = registry.get(delivery_id)
        if not record or record.get("state") != "claimed":
            raise ValueError(f"delivery 尚未 claim：{delivery_id}")
        record.update(
            {
                "state": "sent",
                "message_id": message_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _atomic_write_json(registry_path, registry)
    return record


def release_delivery(
    delivery_id: str,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> bool:
    registry_path = Path(registry_path)
    with exclusive_lock(registry_path.with_suffix(".lock"), wait_seconds=10):
        registry = _read_json(registry_path, default={})
        record = registry.get(delivery_id)
        if not record or record.get("state") != "claimed":
            return False
        del registry[delivery_id]
        _atomic_write_json(registry_path, registry)
    return True


def delivery_status(
    delivery_id: str | None = None,
    state: str | None = None,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> dict:
    registry = _read_json(Path(registry_path), default={})
    if delivery_id:
        return {
            "delivery_id": delivery_id,
            "record": registry.get(delivery_id),
        }
    records = {
        key: value
        for key, value in registry.items()
        if not state or value.get("state") == state
    }
    return {"count": len(records), "records": records}


def recover_claim(
    delivery_id: str,
    confirmed: bool,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> dict:
    if not confirmed:
        raise ValueError("recover 需要明確確認：--confirm-release")
    released = release_delivery(delivery_id, registry_path)
    return {"delivery_id": delivery_id, "released": released}


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="原子管理 UK 新聞郵件 delivery claim。")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    subparsers = parser.add_subparsers(dest="command", required=True)
    claim = subparsers.add_parser("claim")
    claim.add_argument("--summary", required=True)
    complete = subparsers.add_parser("complete")
    complete.add_argument("--delivery-id", required=True)
    complete.add_argument("--message-id", required=True)
    release = subparsers.add_parser("release")
    release.add_argument("--delivery-id", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--delivery-id")
    status.add_argument("--state", choices=("claimed", "sent"))
    recover = subparsers.add_parser("recover")
    recover.add_argument("--delivery-id", required=True)
    recover.add_argument("--confirm-release", action="store_true")
    args = parser.parse_args()

    if args.command == "claim":
        result = claim_delivery(args.summary, args.registry)
    elif args.command == "complete":
        result = complete_delivery(args.delivery_id, args.message_id, args.registry)
    elif args.command == "release":
        result = {"released": release_delivery(args.delivery_id, args.registry)}
    elif args.command == "status":
        result = delivery_status(args.delivery_id, args.state, args.registry)
    else:
        result = recover_claim(args.delivery_id, args.confirm_release, args.registry)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
