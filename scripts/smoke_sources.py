from __future__ import annotations

import subprocess


SOURCES = {
    "GOV.UK": "https://www.gov.uk/search/news-and-communications",
    "UK Parliament": "https://commonslibrary.parliament.uk/feed/",
    "DSIT": "https://www.gov.uk/government/organisations/department-for-science-innovation-and-technology",
}


def main() -> int:
    failed = False
    for name, url in SOURCES.items():
        try:
            completed = subprocess.run(
                ["curl", "-LfsS", "--max-time", "25", "--range", "0-4095", url],
                capture_output=True,
                check=True,
            )
            if not completed.stdout:
                raise ValueError("empty response")
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            failed = True
            print(f"::warning::{name} smoke test failed: {exc}")
        else:
            print(f"{name}: ok ({len(completed.stdout)} sample bytes)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
