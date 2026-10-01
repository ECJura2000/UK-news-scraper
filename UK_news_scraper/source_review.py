"""Preserve reviewed publication endpoints across directory refreshes."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse


def validate_override(review: dict[str, Any]) -> None:
    """A directory flag alone is insufficient evidence to enable a source."""
    if not isinstance(review.get("id"), str) or not review["id"]:
        raise ValueError("查核結果缺少來源 ID")
    if review.get("adapter") not in {"feed", "govuk_search", "html_news"}:
        raise ValueError("查核結果包含不支援的抓取方式")
    for field in ("homepage", "authority_url", "endpoint"):
        url = urlparse(str(review.get(field, "")))
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError(f"查核結果缺少有效的 {field}")
        if field in {"homepage", "endpoint"} and url.scheme != "https":
            raise ValueError("開放來源必須使用已驗證的 HTTPS 首頁與發布端點")
    if review["adapter"] == "govuk_search" and (
        not review["id"].startswith("govuk:")
        or urlparse(review["endpoint"]).hostname != "www.gov.uk"
        or urlparse(review["endpoint"]).path != "/api/search.json"
        or parse_qs(urlparse(review["endpoint"]).query).get("filter_organisations") != [review["id"].split(":", 1)[1]]
    ):
        raise ValueError("GOV.UK 查核結果必須使用官方搜尋端點")
    if review["adapter"] == "html_news" and (
        urlparse(review["endpoint"]).hostname != urlparse(review["homepage"]).hostname
    ):
        raise ValueError("官方 HTML 發布頁必須屬於已確認的機關網站")
    if review["adapter"] == "feed":
        homepage_host = urlparse(review["homepage"]).hostname.removeprefix("www.")
        endpoint_host = urlparse(review["endpoint"]).hostname.removeprefix("www.")
        if not (homepage_host == endpoint_host or endpoint_host.endswith("." + homepage_host)
                or homepage_host.endswith("." + endpoint_host)):
            raise ValueError("官方 feed 必須屬於已確認的機關網站")
    evidence = review.get("verification", {})
    if not isinstance(evidence, dict) or evidence.get("http_status") != 200 or (
        not isinstance(evidence.get("parsed_count"), int) or evidence["parsed_count"] < 1
    ):
        raise ValueError("查核結果沒有成功解析的官方資料")
    if (review["adapter"] == "html_news" and urlparse(review["homepage"]).hostname.removeprefix("www.") == "gov.wales"
            and (evidence.get("scope_verified") is not True or evidence.get("scope_endpoint") != review["endpoint"]
                 or evidence.get("scope_homepage") != review["homepage"])):
        raise ValueError("共用發布頁缺少個別機關範圍的驗證證據")
    if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("response_sha256", ""))):
        raise ValueError("查核結果缺少回應雜湊")
    if evidence.get("production_parser_verified") is not True:
        raise ValueError("查核結果尚未通過生產解析器驗證")
    if review["adapter"] in {"feed", "html_news"} and evidence.get("python_rust_parity") is not True:
        raise ValueError("查核結果尚未通過 Python/Rust 解析一致性驗證")
    checked = datetime.fromisoformat(str(evidence.get("checked_at", "")))
    if checked.tzinfo is None:
        raise ValueError("查核時間必須包含時區")


def apply_overrides(sources: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply validated, ID-specific reviews; refuse orphaned or duplicate records."""
    entries = {entry["id"]: dict(entry) for entry in sources}
    if len(entries) != len(sources):
        raise ValueError("來源名錄 ID 重複")
    seen: set[str] = set()
    for review in reviews:
        validate_override(review)
        identifier = review["id"]
        if identifier in seen or identifier not in entries:
            raise ValueError(f"查核 ID 重複或不在名錄：{identifier}")
        seen.add(identifier)
        entry = entries[identifier]
        if identifier == "govuk:bbc" or identifier == "court-ew:find-case-law":
            raise ValueError(f"此來源須另行處理專案設定或授權：{identifier}")
        entry.update(
            homepage=review["homepage"],
            status="searchable",
            adapter=review["adapter"],
            feed=review["endpoint"] if review["adapter"] == "feed" else "",
            news_page=review["endpoint"] if review["adapter"] == "html_news" else "",
            reason="",
            verification=review["verification"],
            authority_url=review["authority_url"],
            review_status="verified", review_checked_at=review["verification"]["checked_at"],
            parent_sources=[], alternative_sources=[],
        )
    return sorted(entries.values(), key=lambda entry: entry["id"])


def load_overrides(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("reviews"), list):
        raise ValueError("不支援的來源查核結果格式")
    return cast(list[dict[str, Any]], payload["reviews"])


def apply_assessments(sources: list[dict[str, Any]], assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep reviewed holds visible instead of relabelling them as never reviewed."""
    entries = {entry["id"]: dict(entry) for entry in sources}
    seen: set[str] = set()
    allowed = {
        "covered_by_parent", "no_verified_endpoint", "html_adapter_required", "network_or_access_error",
        "permission_required", "policy_excluded", "parser_verification_failed", "audit_error",
        "available_as_other_source", "feed_validation_failed",
    }
    for assessment in assessments:
        identifier = assessment["id"]
        if identifier in seen or identifier not in entries:
            raise ValueError(f"來源查核 ID 重複或不在名錄：{identifier}")
        if assessment.get("outcome") not in allowed or not assessment.get("reason"):
            raise ValueError(f"來源查核原因不完整：{identifier}")
        checked = datetime.fromisoformat(assessment["checked_at"])
        if checked.tzinfo is None:
            raise ValueError("來源查核時間必須包含時區")
        seen.add(identifier)
        entries[identifier].update(
            status="directory_only", adapter="", feed="", news_page="", reason=assessment["reason"],
            review_status=assessment["outcome"], review_checked_at=assessment["checked_at"],
            parent_sources=assessment.get("parent_sources", []),
            alternative_sources=assessment.get("alternative_sources", []),
        )
        entries[identifier].pop("verification", None)
    return sorted(entries.values(), key=lambda entry: entry["id"])


def load_assessments(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("assessments", []), list):
        raise ValueError("不支援的來源查核判讀格式")
    return cast(list[dict[str, Any]], payload.get("assessments", []))


def load_exclusions(path: Path) -> list[dict[str, Any]]:
    """Removed channels remain reviewable and can be restored deliberately."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("exclusions", []), list):
        raise ValueError("不支援的來源排除紀錄格式")
    return cast(list[dict[str, Any]], payload.get("exclusions", []))


def apply_exclusions(sources: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suppress reviewed channels even when an upstream directory relists them."""
    seen: set[str] = set()
    for exclusion in exclusions:
        identifier = exclusion.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("來源排除 ID 缺少或重複")
        if exclusion.get("outcome") not in {
            "covered_by_parent", "available_as_other_source", "policy_excluded", "obsolete_source",
            "user_requested_removal",
        } or not exclusion.get("reason"):
            raise ValueError(f"來源排除原因不完整：{identifier}")
        original = exclusion.get("original_source")
        if not isinstance(original, dict) or original.get("id") != identifier or not original.get("name_en"):
            raise ValueError(f"來源排除缺少可復原的原始紀錄：{identifier}")
        if exclusion["outcome"] == "user_requested_removal" and (
            original.get("status") != "directory_only" or exclusion.get("original_status") != "directory_only"
            or exclusion.get("original_reason") != original.get("reason", "")
        ):
            raise ValueError(f"使用者指定刪除必須保留原僅列名狀態與原因：{identifier}")
        checked = datetime.fromisoformat(str(exclusion.get("checked_at", "")))
        if checked.tzinfo is None:
            raise ValueError("來源排除時間必須包含時區")
        authority = urlparse(str(exclusion.get("authority_url", "")))
        if authority.scheme not in {"http", "https"} or not authority.netloc:
            raise ValueError(f"來源排除缺少證據網址：{identifier}")
        replacements = exclusion.get("replacement_sources", [])
        if (not isinstance(replacements, list) or any(not isinstance(x, str) or not x for x in replacements)
                or identifier in replacements):
            raise ValueError(f"來源排除的替代 ID 無效：{identifier}")
        if exclusion["outcome"] in {"covered_by_parent", "available_as_other_source"} and not replacements:
            raise ValueError(f"共用或重複來源缺少替代管道：{identifier}")
        seen.add(identifier)
    identifiers = [source["id"] for source in sources]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("來源名錄 ID 重複")
    return [dict(source) for source in sources if source["id"] not in seen]


def apply_review_state(
    sources: list[dict[str, Any]], reviews: list[dict[str, Any]],
    assessments: list[dict[str, Any]], exclusions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Exclusions take precedence; unrelated orphaned reviews still fail closed."""
    current = apply_exclusions(sources, exclusions)
    excluded = {item["id"] for item in exclusions}
    current = apply_assessments(current, [item for item in assessments if item["id"] not in excluded])
    return apply_overrides(current, [item for item in reviews if item["id"] not in excluded])
