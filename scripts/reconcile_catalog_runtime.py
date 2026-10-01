"""Hold audited endpoints which fail in the selected actual runtime transports.

Writes only resumable per-source audit rows. Catalog adoption remains a separate
step, so parser replay cannot silently stand in for successful live collection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.audit_source_catalog import write_json  # noqa: E402


def reconcile(
    output: Path, source_id: str, *, python_evidence: Path | None = None, rust_evidence: Path | None = None,
    runtimes: tuple[str, ...] = ("python", "rust"),
) -> None:
    if not runtimes or len(set(runtimes)) != len(runtimes) or set(runtimes) - {"python", "rust"}:
        raise ValueError("runtimes 必須明確指定 python、rust 或兩者，不能重複")
    evidence_files = {
        "python": python_evidence or output / "live-all/failed-python-diagnostics.json",
        "rust": rust_evidence or output / "live-all/failed-rust-diagnostics.json",
    }
    read_runtimes = set(runtimes)
    if python_evidence is not None:
        read_runtimes.add("python")
    if rust_evidence is not None:
        read_runtimes.add("rust")
    proof = {}
    for runtime in sorted(read_runtimes):
        path = evidence_files[runtime]
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = [row for row in payload["health"] if row["source"] == source_id]
        if len(rows) != 1:
            raise ValueError(f"{runtime} 未有此來源的唯一抓取紀錄：{source_id}")
        if runtime in runtimes and rows[0]["success"] is not False:
            raise ValueError(f"{runtime} 未有此來源的明確抓取失敗：{source_id}")
        proof[runtime] = {"evidence_file": str(path), "health": rows[0]}
    cached = output / "sources" / f"{hashlib.sha256(source_id.encode()).hexdigest()}.json"
    row = json.loads(cached.read_text(encoding="utf-8"))
    review = row.get("review") or row.get("previous_review")
    if not review:
        raise ValueError(f"未有先前查核發布端點：{source_id}")
    descriptions = []
    labels = {"python": "Python", "rust": "Rust"}
    for runtime in runtimes:
        evidence = proof[runtime]
        failed_codes = sorted({endpoint["status_code"] for endpoint in evidence["health"]["endpoints"]
                               if endpoint["url"] == review["endpoint"] and (
                                   endpoint["status_code"] == 0 or endpoint["status_code"] >= 400
                               )})
        if not failed_codes:
            raise ValueError(f"{runtime} 未證實已查核端點讀取失敗：{source_id}")
        failure = "連線失敗" if failed_codes == [0] else "HTTP 讀取失敗"
        descriptions.append(f"{labels[runtime]} {failure}（HTTP {','.join(map(str, failed_codes))}）")
    for runtime in sorted(read_runtimes - set(runtimes)):
        health = proof[runtime]["health"]
        success_codes = sorted({endpoint["status_code"] for endpoint in health["endpoints"]
                                if endpoint["url"] == review["endpoint"] and 200 <= endpoint["status_code"] < 300})
        if health["success"] is True and success_codes:
            descriptions.append(f"{labels[runtime]} 備援成功（HTTP {','.join(map(str, success_codes))}）")
    if "review" in row:
        row["previous_review"] = row.pop("review")
    row.update(
        outcome="network_or_access_error",
        reason="；".join(descriptions) + "；保留機關，暫停選取，待抓取恢復",
        runtime_verification=proof, failed_runtimes=list(runtimes),
    )
    write_json(cached, row)
    print(f"held={source_id}; audit_row={cached}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "新聞放置區/source-audit")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--python-evidence", type=Path, help="實際 Python 執行結果（須含 health）")
    parser.add_argument("--rust-evidence", type=Path, help="實際 Rust 執行結果（須含 health）")
    parser.add_argument("--runtimes", default="python,rust", help="須確認失敗的執行版本，預設 python,rust")
    args = parser.parse_args()
    reconcile(
        args.output_dir, args.source_id, python_evidence=args.python_evidence, rust_evidence=args.rust_evidence,
        runtimes=tuple(runtime.strip() for runtime in args.runtimes.split(",")),
    )


if __name__ == "__main__":
    main()
