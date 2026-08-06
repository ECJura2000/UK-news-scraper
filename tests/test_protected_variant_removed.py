from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_protected_runtime_entrypoints_are_removed():
    removed = (
        "UKNewsScraper_protected.spec",
        "run_scraper_protected.py",
        "run_windows_protected.bat",
    )
    assert all(not (ROOT / name).exists() for name in removed)


def test_build_and_runtime_sources_do_not_restore_protected_mode():
    files = (
        ROOT / "UK_news_scraper" / "main.py",
        ROOT / "scripts" / "package_release.py",
        ROOT / ".github" / "workflows" / "release.yml",
        ROOT / ".github" / "workflows" / "test.yml",
        ROOT / "build_linux.sh",
        ROOT / "build_macos.sh",
        ROOT / "build_windows.bat",
    )
    forbidden = ("UKNewsScraper_protected", "UK_NEWS_RUN_PASSWORD", "--protected")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(value in text for value in forbidden), path
