from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock


_CACHE_LOCK = Lock()


def cache_path() -> Path:
    configured = os.environ.get("UK_NEWS_TRANSLATION_CACHE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "uk_news_scraper" / "translations.json"


def load_translations() -> dict[str, str]:
    path = cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(source): str(translation)
        for source, translation in payload.items()
        if source and translation
    }


def save_translations(translations: dict[str, str]) -> None:
    if not translations:
        return
    path = cache_path()
    with _CACHE_LOCK:
        existing = load_translations()
        existing.update(
            {
                source: translation
                for source, translation in translations.items()
                if source and translation
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
