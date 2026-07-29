from __future__ import annotations

import subprocess
from zipfile import ZipFile

import pytest

from scripts.package_source import create_source_archive


def test_source_archive_contains_only_tracked_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    tracked_files = {
        "AGENTS.md": "agent rules",
        "AI_START_HERE.md": "AI setup",
        "README.md": "read me",
        "requirement-lock.txt": "requests==1",
        "tracked.txt": "tracked",
    }
    for name, content in tracked_files.items():
        (repo / name).write_text(content, encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked", encoding="utf-8")
    subprocess.run(["git", "-C", repo, "add", *tracked_files], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )

    archive = create_source_archive(
        repo,
        tmp_path / "release",
        version="9.9.9",
    )

    with ZipFile(archive) as bundle:
        assert "UKNewsScraper-9.9.9-Source/untracked.txt" not in bundle.namelist()
        assert "UKNewsScraper-9.9.9-Source/AI_START_HERE.md" in bundle.namelist()
        assert (
            bundle.read("UKNewsScraper-9.9.9-Source/tracked.txt").decode("utf-8")
            == "tracked"
        )


def test_source_archive_rejects_generated_workbook(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    for name in (
        "AGENTS.md",
        "AI_START_HERE.md",
        "README.md",
        "requirement-lock.txt",
        "report.xlsx",
    ):
        (repo / name).write_text(name, encoding="utf-8")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )

    with pytest.raises(RuntimeError, match="generated output"):
        create_source_archive(
            repo,
            tmp_path / "release",
            version="9.9.9",
        )
    assert not (tmp_path / "release" / "UKNewsScraper-9.9.9-Source.zip").exists()
