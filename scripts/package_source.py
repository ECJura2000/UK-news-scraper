from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from UK_news_scraper import __version__ as python_version  # noqa: E402


def release_version() -> str:
    if value := os.environ.get("UK_NEWS_RELEASE_VERSION"):
        return value
    cargo = ROOT / "Cargo.toml"
    if cargo.exists():
        with cargo.open("rb") as source:
            return str(tomllib.load(source)["workspace"]["package"]["version"])
    return python_version

REQUIRED_SOURCE_FILES = {
    "AGENTS.md",
    "AI_START_HERE.md",
    "README.md",
    "requirement-lock.txt",
}
FORBIDDEN_DIRECTORIES = {".git", ".venv", "新聞放置區"}
FORBIDDEN_FILENAMES = {"sent_run_ids.json"}


def create_source_archive(
    repo_root: Path,
    output_dir: Path,
    *,
    ref: str = "HEAD",
    version: str | None = None,
) -> Path:
    version = version or release_version()
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"UKNewsScraper-{version}-Source.zip"
    prefix = f"UKNewsScraper-{version}-Source/"

    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "archive",
            "--format=zip",
            f"--prefix={prefix}",
            f"--output={archive}",
            ref,
        ],
        check=True,
    )

    with ZipFile(archive) as bundle:
        names = bundle.namelist()
    try:
        _validate_archive(names, prefix)
    except RuntimeError:
        archive.unlink(missing_ok=True)
        raise
    return archive


def _validate_archive(names: list[str], prefix: str) -> None:
    if not names or any(not name.startswith(prefix) for name in names):
        raise RuntimeError("source archive has an invalid root directory")

    relative_names = {name.removeprefix(prefix) for name in names}
    missing = REQUIRED_SOURCE_FILES - relative_names
    if missing:
        raise RuntimeError(f"source archive is missing required files: {sorted(missing)}")

    for relative_name in relative_names:
        path = PurePosixPath(relative_name)
        if FORBIDDEN_DIRECTORIES.intersection(path.parts):
            raise RuntimeError(f"source archive contains a private directory: {relative_name}")
        if path.name in FORBIDDEN_FILENAMES:
            raise RuntimeError(f"source archive contains delivery state: {relative_name}")
        if relative_name.endswith((".run.json", ".xlsx")):
            raise RuntimeError(f"source archive contains generated output: {relative_name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package tracked UK News Scraper source files.",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "release")
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    archive = create_source_archive(args.repo_root, args.output_dir, ref=args.ref)
    print(archive)


if __name__ == "__main__":
    main()
