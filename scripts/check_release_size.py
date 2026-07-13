from __future__ import annotations

import argparse
from pathlib import Path


MIB = 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release asset size budgets.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-file-mib", type=int, required=True)
    parser.add_argument("--max-total-mib", type=int, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    files = sorted(path for path in args.root.rglob("*") if path.is_file())
    if not files:
        parser.error(f"no release files found under {args.root}")

    total_bytes = sum(path.stat().st_size for path in files)
    oversized = [path for path in files if path.stat().st_size > args.max_file_mib * MIB]
    lines = [
        f"file_limit_mib={args.max_file_mib}",
        f"total_limit_mib={args.max_total_mib}",
        f"total_bytes={total_bytes}",
        f"total_mib={total_bytes / MIB:.2f}",
        "",
    ]
    lines.extend(
        f"{path.stat().st_size}\t{path.stat().st_size / MIB:.2f} MiB\t{path.relative_to(args.root)}"
        for path in files
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if oversized:
        names = ", ".join(str(path.relative_to(args.root)) for path in oversized)
        raise RuntimeError(f"release files exceed {args.max_file_mib} MiB: {names}")
    if total_bytes > args.max_total_mib * MIB:
        raise RuntimeError(
            f"release total is {total_bytes / MIB:.2f} MiB; limit is {args.max_total_mib} MiB"
        )
    print(f"release size budget passed: {total_bytes / MIB:.2f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
