from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from UK_news_scraper import __version__  # noqa: E402


PLATFORM_LABELS = {
    "linux": "Linux-x86_64",
    "macos": "macOS",
    "windows": "Windows",
}


def package(platform_name: str) -> Path:
    label = PLATFORM_LABELS[platform_name]
    dist_dir = PROJECT_DIR / "dist"
    release_root = dist_dir / "release"
    folder_name = f"UKNewsScraper-{__version__}-{label}"
    release_dir = release_root / folder_name
    archive = release_root / f"{folder_name}.zip"

    if release_dir.exists():
        shutil.rmtree(release_dir)
    if archive.exists():
        archive.unlink()
    release_dir.mkdir(parents=True, exist_ok=True)

    if platform_name == "windows":
        required = (
            dist_dir / "UKNewsScraper.exe",
            dist_dir / "UKNewsScraper_protected.exe",
            PROJECT_DIR / "run_windows.bat",
            PROJECT_DIR / "run_windows_protected.bat",
        )
    else:
        required = (
            dist_dir / "UKNewsScraper",
            dist_dir / "UKNewsScraper_protected",
        )

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing release files: {missing}")

    for source in required:
        shutil.copy2(source, release_dir / source.name)

    if platform_name == "windows":
        instructions = """UK News Scraper Windows portable edition

Python is not required.

Recommended: double-click run_windows.bat and enter a date range.
You may also run UKNewsScraper.exe directly from Command Prompt or PowerShell.
The protected edition is optional and uses the existing 30-day trial/password behavior.
"""
    else:
        executable = "./UKNewsScraper"
        instructions = f"""UK News Scraper {label} portable edition

Python is not required.

1. Open a terminal in this folder.
2. Run: chmod +x UKNewsScraper UKNewsScraper_protected
3. Run: {executable}

Examples:
  {executable} 30
  {executable} 20160501～20160515

The protected edition is optional and uses the existing 30-day trial/password behavior.
"""
    (release_dir / "README.txt").write_text(instructions, encoding="utf-8")

    created = Path(
        shutil.make_archive(
            str(release_root / folder_name),
            "zip",
            root_dir=release_root,
            base_dir=folder_name,
        )
    )
    print(created)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Create portable UK News Scraper release archives.")
    parser.add_argument("platform", choices=tuple(PLATFORM_LABELS))
    args = parser.parse_args()
    package(args.platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
