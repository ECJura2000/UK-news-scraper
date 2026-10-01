"""Audit every directory-only source, with resumable per-source HTTP evidence.

Advertised RSS/Atom feeds, dated HTML indexes and GOV.UK search records are
candidates for production-parser verification. Shared directories must identify
the individual body first; a parsable sample post is not a publication channel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from UK_news_scraper.catalog_html import parse_news_index  # noqa: E402
from UK_news_scraper.models import Agency  # noqa: E402
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper  # noqa: E402
from UK_news_scraper.source_catalog import GOVUK_LINKS  # noqa: E402
from UK_news_scraper.source_review import (  # noqa: E402
    apply_review_state,
    load_assessments,
    load_exclusions,
    load_overrides,
)

CATALOG = ROOT / "UK_news_scraper/data/source_catalog.json"
OVERRIDES = CATALOG.with_name("source_catalog_overrides.json")
SINCE = datetime(1990, 1, 1, tzinfo=UTC)
NEWS = re.compile(r"\b(news|newsroom|press|media|publications|judgments|decisions|latest)\b", re.I)
SOCIAL = {"facebook.com", "twitter.com", "x.com", "youtube.com", "linkedin.com", "instagram.com"}
SHARED_PUBLISHERS = {
    "gov.uk", "gov.wales", "gov.scot", "nidirect.gov.uk", "nationalarchives.gov.uk",
    "judiciary.uk", "scotcourts.gov.uk", "judiciaryni.uk", "publicappointmentsni.org",
}
RELATED_PUBLISHERS = {
    "ukri.org": ("UKRI", "UK Research and Innovation"),
    "audit.scot": ("scotland:audit-scotland", "Audit Scotland"),
    "dhcw.nhs.wales": ("wales:digital-health-and-care-wales", "Digital Health and Care Wales"),
    "awttc.nhs.wales": ("", "All Wales Therapeutics and Toxicology Centre"),
    "scotcourts.gov.uk": ("court-scotland:judgments", "Scottish Courts and Tribunals Service judgments"),
    "futuregenerations.wales": (
        "wales:future-generations-commissioner-wales", "Future Generations Commissioner for Wales"
    ),
}
# Primary official pages reviewed when an older directory URL no longer works.
OFFICIAL_DISCOVERY_PAGES = {
    "scotland:convener-of-school-closure-review-panels": [
        "https://www.mygov.scot/organisations/school-closure-review-panels"
    ],
    "scotland:parole-board-for-scotland": ["https://www.mygov.scot/organisations/parole-board-for-scotland"],
    "scotland:nhs-dumfries-galloway": ["https://www.nhsdg.co.uk/"],
    "govuk:financial-remedies-court": ["https://www.judiciary.uk/guidance-and-resources/financial-remedies-guide-2026/"],
    "govuk:research-england": ["https://www.ukri.org/councils/research-england/news/"],
    "scotland:accounts-commission-for-scotland": ["https://audit.scot/accounts-commission"],
    "scotland:scottish-courts-and-tribunals-service": ["https://www.scotcourts.gov.uk/rss-feeds/"],
}
SCOPED_PARENT_INDEXES = {
    "govuk:research-england": "https://www.ukri.org/councils/research-england/news/",
    "scotland:accounts-commission-for-scotland": "https://audit.scot/accounts-commission",
}
OFFICIAL_IDENTITY_AUTHORITIES: dict[str, str] = {}
OFFICIAL_IDENTITY_CONTACTS: dict[str, list[str]] = {}
SCTS = "scotland:scottish-courts-and-tribunals-service"
SCTS_NEWS_FEED = "https://api.pa.web.scotcourts.gov.uk/web/rss/NewsArticles"


def body_advertised_feeds(identifier: str, page: str, soup: BeautifulSoup) -> list[str]:
    """One verified SCTS page advertises its news URL as plain text, not a link."""
    if (identifier == SCTS and page.rstrip("/") == "https://www.scotcourts.gov.uk/rss-feeds"
            and SCTS_NEWS_FEED in soup.get_text(" ", strip=True)):
        return [SCTS_NEWS_FEED]
    return []


def identity_publication_scope(identifier: str, root: str, base: str) -> str:
    if (root in OFFICIAL_IDENTITY_CONTACTS.get(identifier, []) and host(base) not in SHARED_PUBLISHERS
            and host(base) not in RELATED_PUBLISHERS and not host(base).endswith("-ni.gov.uk")):
        # A named body's own contact page identifies its whole independent site;
        # departmental/subsidiary pages retain the reviewed nested path boundary.
        return urljoin(base, "/")
    return publication_scope(root, base)


def scoped_parent_index(identifier: str, endpoint: str) -> bool:
    """Only body-specific URLs may override a shared publisher's broad scope."""
    expected = SCOPED_PARENT_INDEXES.get(identifier)
    return expected is not None and endpoint.rstrip("/") == expected.rstrip("/")


def load_identity_map(path: Path, sources: list[dict]) -> dict[str, list[str]]:
    """Accept exact NI identities endorsed by a successfully read official list.

    Directory/contact evidence only supplies discovery starting points. Every
    proposed publication endpoint still undergoes normal transport/parser gates.
    """
    from scripts.discover_catalog_identities import contact_entries, identity_key

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("matches"), list):
        raise ValueError("不支援的官方機關身分對照格式")
    entries = {source["id"]: source for source in sources}
    authorities = {item["url"] for item in payload.get("requests", []) if item.get("http_status") == 200}
    store = FetchStore(path.parent / "http")
    result = {}
    for item in payload["matches"]:
        identifier = item["id"]
        entry = entries.get(identifier)
        if not entry or not identifier.startswith("ni:") or identifier in result:
            raise ValueError(f"機關身分對照的 ID 不在範圍或重複：{identifier}")
        if identity_key(entry["name_en"]) != identity_key(item.get("matched_name", "")):
            raise ValueError(f"官方對照機關名稱不符：{identifier}")
        authority = item.get("authority_url", "")
        if not authority.startswith("https://") or not (
            host(authority) == "gov.uk" or host(authority) == "nidirect.gov.uk"
            or host(authority).endswith("-ni.gov.uk")
        ):
            raise ValueError(f"機關身分對照缺少官方證據網址：{identifier}")
        evidence = item.get("contact_evidence", {})
        if authority not in authorities and not (
            evidence.get("url") == authority and evidence.get("http_status") == 200
        ):
            raise ValueError(f"機關身分對照尚未讀取官方證據：{identifier}")
        # Check the actual official page's matching link. Neither website_urls
        # nor contact_url in a local mapping can independently inject a host.
        checked, body = store.get(authority)
        if checked["http_status"] != 200:
            raise ValueError(f"官方機關對照證據讀取失敗：{identifier}")
        contact = item.get("contact_url", "")
        if contact == authority and host(authority) == "gov.uk":
            heading = BeautifulSoup(body, "html.parser").select_one("h1")
            if not heading or identity_key(heading.get_text()) != identity_key(entry["name_en"]):
                raise ValueError(f"官方機關標題不符：{identifier}")
        elif not any(
            candidate["contact_url"] == contact and identity_key(candidate["name_en"]) == identity_key(entry["name_en"])
            for candidate in contact_entries(body, authority)
        ):
            raise ValueError(f"官方目錄未列出此機關的網址：{identifier}")
        # A sponsoring department's whole site is evidence of identity, not the
        # subsidiary's publication scope. Only its exact endorsed link is visited.
        result[identifier] = [contact]
        OFFICIAL_IDENTITY_AUTHORITIES[identifier] = authority
        OFFICIAL_IDENTITY_CONTACTS[identifier] = [contact]
    return result


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def same_site(left: str, right: str) -> bool:
    a, b = host(left), host(right)
    return bool(a and b and (a == b or a.endswith(f".{b}") or b.endswith(f".{a}")))


def publication_scope(requested_homepage: str, final_homepage: str) -> str:
    """An official host root remains a root when it serves an index file."""
    if host(requested_homepage) == host(final_homepage) and urlparse(requested_homepage).path in {"", "/"}:
        return urljoin(final_homepage, "/")
    # A subsidiary's nested homepage never gains its parent's full site scope.
    return final_homepage


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def audit_targets(sources: list[dict]) -> list[dict]:
    """A fresh audit must also recheck sources enabled by an earlier review."""
    targets = []
    for source in sources:
        if source["status"] != "directory_only" and not source.get("review_status"):
            continue
        entry = dict(source)
        if source.get("authority_url"):
            entry["homepage"] = source["authority_url"]
        targets.append(entry)
    return targets


class FetchStore:
    def __init__(self, directory: Path, retry_errors: bool = False):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.guard = threading.Lock()
        self.locks: dict[str, threading.Lock] = {}
        self.hosts: dict[str, threading.Semaphore] = {}
        self.retry_errors = retry_errors
        self.retried: set[str] = set()

    def get(self, url: str) -> tuple[dict, bytes]:
        url = url.strip()
        if urlparse(url).scheme not in {"http", "https"}:
            return {"url": url, "http_status": 0, "error": "非 HTTP 網址"}, b""
        key = hashlib.sha256(url.encode()).hexdigest()
        with self.guard:
            lock = self.locks.setdefault(key, threading.Lock())
            semaphore = self.hosts.setdefault(host(url), threading.Semaphore(2))
        with lock:
            metadata = self.directory / f"{key}.json"
            body_path = self.directory / f"{key}.body"
            if metadata.exists() and body_path.exists():
                cached = json.loads(metadata.read_text())
                failed = cached["http_status"] in {0, 403, 429} or cached["http_status"] >= 500
                if not (self.retry_errors and failed and key not in self.retried):
                    return cached, body_path.read_bytes()
                self.retried.add(key)
            evidence = {"url": url, "checked_at": datetime.now(UTC).isoformat(), "http_status": 0}
            content = b""
            with semaphore:
                try:
                    with requests.get(
                        url,
                        headers={"User-Agent": "UK-news-scraper/official-source-review"},
                        timeout=(6, 15),
                        stream=True,
                    ) as response:
                        evidence.update(
                            http_status=response.status_code,
                            final_url=response.url,
                            content_type=response.headers.get("Content-Type", ""),
                        )
                        chunks = []
                        size = 0
                        for chunk in response.iter_content(65536):
                            size += len(chunk)
                            if size > 8 * 1024 * 1024:
                                raise ValueError("回應超過 8 MiB 查核上限")
                            chunks.append(chunk)
                        content = b"".join(chunks)
                except (requests.RequestException, ValueError) as exc:
                    evidence["error"] = f"{type(exc).__name__}: {exc}"
                if self.retry_errors and (evidence["http_status"] == 403 or evidence.get("error")):
                    try:
                        from curl_cffi import requests as browser_requests

                        response = browser_requests.get(url, impersonate="chrome120", timeout=15)
                        if response.status_code == 200 and len(response.content) <= 8 * 1024 * 1024:
                            content = response.content
                            evidence.update(http_status=200, final_url=response.url, backend="browser_tls",
                                            content_type=response.headers.get("Content-Type", ""))
                            evidence.pop("error", None)
                    except Exception as exc:
                        evidence["fallback_error"] = f"{type(exc).__name__}: {exc}"
            evidence["response_sha256"] = hashlib.sha256(content).hexdigest()
            body_path.write_bytes(content)
            write_json(metadata, evidence)
            return evidence, content


def advertised_feeds(soup: BeautifulSoup, base: str) -> list[str]:
    urls = []
    for node in soup.select("link[href], a[href]"):
        href = str(node.get("href", "")).strip()
        media = str(node.get("type", "")).lower()
        label = node.get_text(" ", strip=True).lower()
        if (node.name == "link" and ("rss" in media or "atom" in media)) or (
            node.name == "a" and (re.search(r"\b(rss|atom)\b", label) or re.search(r"/(feed|rss)(/|[.?]|$)", href))
        ):
            urls.append(urljoin(base, href))
    return list(dict.fromkeys(urls))[:6]


def independent_sites(soup: BeautifulSoup, base: str, name: str, shared: bool) -> list[str]:
    urls = []
    target = normalized(name)
    for node in soup.select("a[href]"):
        definition = node.find_parent("dd")
        term = definition.find_previous_sibling("dt") if definition else None
        metadata_website = (
            host(base) == "mygov.scot" and urlparse(base).path.startswith("/organisations/")
            and node.find_parent("main") is not None and term is not None
            and normalized(term.get_text()) in {"web", "website"}
        )
        if node.find_parent(["footer", "nav"]) or (node.find_parent("header") and not metadata_website):
            continue
        url = urljoin(base, str(node.get("href", "")).strip())
        if urlparse(url).scheme not in {"http", "https"} or host(url) in SOCIAL:
            continue
        label = normalized(node.get_text(" ", strip=True))
        exact_name = label == target
        website_link = bool(re.search(r"\b(website|visit|www)\b", label))
        # Individual mygov organisation pages label the canonical website in
        # a definition list; the anchor itself is just the bare domain.
        website_link = website_link or metadata_website
        context_match = False
        if shared and website_link:
            parent = node.find_parent("li")
            heading = node.find_previous(["h2", "h3", "h4"])
            context_match = (parent is not None and target in normalized(parent.get_text(" ", strip=True))) or (
                heading is not None and normalized(heading.get_text(" ", strip=True)) == target
            )
        eligible = exact_name or context_match if shared else exact_name or (
            website_link and (host(base) in SHARED_PUBLISHERS or host(base) == "mygov.scot")
        )
        if eligible and (not same_site(url, base) or (shared and exact_name and url != base)):
            urls.append(url)
    return list(dict.fromkeys(urls))[:3]


def news_pages(soup: BeautifulSoup, base: str) -> list[str]:
    urls = []
    for node in soup.select("a[href]"):
        url = urljoin(base, str(node.get("href", "")).strip())
        label = node.get_text(" ", strip=True)
        path = urlparse(url).path
        is_news_index = bool(re.search(r"/(news|newsroom|press-releases)(/|$)", path, re.I))
        if same_site(url, base) and (NEWS.search(label) or is_news_index) and len(label) < 60:
            exact_label = normalized(label) in {"news", "latest news", "newsroom", "press releases", "view all news"}
            # A navigation index precedes incidental articles mentioning media.
            urls.append((0 if exact_label else 1 if is_news_index else 2, url))
    return list(dict.fromkeys(url for _, url in sorted(urls, key=lambda x: x[0])))[:3]


def scoped_welsh_index(url: str) -> bool:
    parsed = urlparse(url)
    return host(url) == "gov.wales" and (
        re.fullmatch(r"/node/\d+/latest-external-org-content/?", parsed.path) is not None
        or any(re.fullmatch(r"field_external_organisations\[\d+\]", key) for key in parse_qs(parsed.query))
    )


def welsh_scope_proof(entry: dict, homepage: str, endpoint: str, soup: BeautifulSoup) -> dict | None:
    """Match a shared publisher's organisation identity, not just its URL shape."""
    parsed = urlparse(endpoint)
    query = parse_qs(parsed.query)
    if re.fullmatch(r"/node/\d+/latest-external-org-content/?", parsed.path):
        labels = [node.get_text(" ", strip=True) for node in soup.select(".breadcrumb a[href]")
                  if urlparse(urljoin(endpoint, node["href"])).path == urlparse(homepage).path]
        method = "organisation breadcrumb links back to reviewed homepage"
    else:
        scopes = [(key, values) for key, values in query.items()
                  if re.fullmatch(r"field_external_organisations\[\d+\]", key)]
        if len(scopes) != 1 or scopes[0][1] != [re.search(r"\d+", scopes[0][0]).group()]:
            return None
        key, values = scopes[0]
        labels = [node.parent.get_text(" ", strip=True) for node in soup.select("input[checked]")
                  if node.get("name") == key and node.get("value") == values[0]]
        method = "single selected organisation filter matches reviewed name"
    if normalized(entry["name_en"]) not in [normalized(label) for label in labels]:
        return None
    return {"scope_verified": True, "scope_name": entry["name_en"], "scope_homepage": homepage,
            "scope_endpoint": endpoint, "scope_method": method}


def verify_feed(
    entry: dict, homepage: str, endpoint: str, evidence: dict, body: bytes, scope: str | None = None
) -> dict | None:
    if evidence["http_status"] != 200 or any(urlparse(url).scheme != "https" for url in (homepage, endpoint)):
        return None
    document = feedparser.parse(body)
    if not document.get("version") or not document.entries:
        return None
    if not feed_is_attributable(entry, scope or homepage, endpoint, document):
        return None
    agency = Agency(entry["name_zh"] or entry["name_en"], entry["name_en"], entry["id"], homepage)
    scraper = AgencyFeedScraper(agency)
    now = datetime.now(UTC)
    items = []
    for record in document.entries:
        item = scraper._entry_to_news_item(record, endpoint, SINCE)
        # WordPress's default first post can be valid RSS without constituting
        # any published agency material (observed on the former MEXE website).
        placeholder = item and normalized(item.title) == "hello world" and (
            "welcome to wordpress" in normalized(item.summary)
        )
        if item and not placeholder and item.published_at < now and same_site(item.link, homepage):
            items.append(item)
    if not items:
        return None
    return {
        "id": entry["id"], "adapter": "feed", "homepage": homepage,
        "authority_url": entry["homepage"].strip(), "endpoint": endpoint,
        "verification": {
            **evidence, "parsed_count": len(items), "parser": "AgencyFeedScraper._entry_to_news_item",
            "oldest_published_at": min(x.published_at for x in items).isoformat(),
            "newest_published_at": max(x.published_at for x in items).isoformat(),
            "sample_link": items[0].link,
            "coverage": "RSS snapshot; historical completeness is not guaranteed",
        },
    }


def feed_is_attributable(entry: dict, homepage: str, endpoint: str, document: dict) -> bool:
    """A site-wide footer feed cannot be attributed to every body on that site."""
    base, feed = urlparse(homepage), urlparse(endpoint)
    title = normalized(document.get("feed", {}).get("title", ""))
    name = normalized(entry["name_en"])
    if entry["id"] == SCTS and host(homepage) == "scotcourts.gov.uk" and endpoint == SCTS_NEWS_FEED:
        return True
    if name and name in title:
        return True
    if host(homepage) in RELATED_PUBLISHERS and name != normalized(RELATED_PUBLISHERS[host(homepage)][1]):
        return bool(base.path.strip("/")) and feed.path.startswith(base.path.rstrip("/") + "/")
    if entry["id"].startswith("govuk:") and host(homepage) == "gov.uk":
        slug = entry["id"].split(":", 1)[1]
        query = parse_qs(feed.query)
        return feed.path == f"/government/organisations/{slug}.atom" or any(
            slug in values for key, values in query.items() if key in {"organisations", "filter_organisations"}
        )
    if host(homepage) in SHARED_PUBLISHERS:
        return bool(base.path.strip("/")) and feed.path.startswith(base.path.rstrip("/") + "/")
    return base.path in {"", "/"} or feed.path.startswith(base.path.rstrip("/") + "/")


def verify_govuk(entry: dict, evidence: dict, body: bytes) -> dict | None:
    if evidence["http_status"] != 200:
        return None
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload.get("results"), list):
        return None
    records = []
    for value in payload["results"]:
        link = urljoin("https://www.gov.uk", str(value.get("link", "")))
        decision = any(word in str(value.get("format", "")) for word in ("decision", "judgment"))
        if host(link) != "gov.uk" or not (any(x in link for x in GOVUK_LINKS) or decision):
            continue
        try:
            published = datetime.fromisoformat(str(value.get("public_timestamp", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if published.tzinfo and SINCE <= published < datetime.now(UTC) and value.get("title"):
            records.append((value, published, link))
    if not records:
        return None
    return {
        "id": entry["id"], "adapter": "govuk_search", "homepage": entry["homepage"],
        "authority_url": entry["homepage"], "endpoint": evidence["url"],
        "verification": {
            **evidence, "parsed_count": len(records), "parser": "dated GOV.UK official search records",
            "newest_published_at": max(x[1] for x in records).isoformat(),
            "sample_link": records[0][2],
        },
    }


def audit_entry(entry: dict, store: FetchStore, shared_urls: set[str]) -> dict:
    row = {"id": entry["id"], "name_en": entry["name_en"], "original_reason": entry["reason"], "requests": []}
    if entry["id"] in {"govuk:bbc", "court-ew:find-case-law"}:
        evidence, _ = store.get(entry.get("provenance") or entry["homepage"])
        row["requests"].append(evidence)
        row.update(outcome="policy_excluded" if entry["id"] == "govuk:bbc" else "permission_required",
                   reason=entry["reason"])
        return row

    def get(url: str) -> tuple[dict, bytes]:
        # Older official directories advertise HTTP even where the same path
        # serves HTTPS. Verify the secure URL before adopting it.
        if urlparse(url.strip()).scheme == "http":
            secure = "https://" + url.strip()[len("http://"):]
            evidence, body = store.get(secure)
            row["requests"].append(evidence)
            if evidence["http_status"] == 200 and urlparse(evidence.get("final_url", secure)).scheme == "https":
                return evidence, body
        evidence, body = store.get(url)
        row["requests"].append(evidence)
        return evidence, body

    def authority_url() -> str:
        if entry["id"] in OFFICIAL_IDENTITY_AUTHORITIES:
            return OFFICIAL_IDENTITY_AUTHORITIES[entry["id"]]
        discovery = OFFICIAL_DISCOVERY_PAGES.get(entry["id"], [])
        return next((x["url"] for x in row["requests"] if x["url"] in discovery and x["http_status"] == 200),
                    entry["homepage"])

    if entry["id"].startswith("govuk:"):
        query = urlencode({"filter_organisations": entry["id"].split(":", 1)[1], "count": 100,
                           "order": "-public_timestamp", "fields": "title,link,description,public_timestamp,format"})
        evidence, body = get(f"https://www.gov.uk/api/search.json?{query}")
        review = verify_govuk(entry, evidence, body)
        if review:
            row.update(outcome="verified", review=review)
            return row

    roots = [entry["homepage"], *OFFICIAL_DISCOVERY_PAGES.get(entry["id"], [])]
    scopes = {}
    related = set()
    candidates = []
    news_candidates = []
    attributable_news = []
    for root in roots:
        evidence, body = get(root)
        if evidence["http_status"] != 200:
            continue
        base = evidence.get("final_url", root)
        soup = BeautifulSoup(body, "html.parser")
        shared = root in shared_urls or root == entry.get("provenance") or (
            "/national-public-bodies-directory/" in urlparse(root).path
        )
        independent = independent_sites(soup, base, entry["name_en"], shared)
        if not shared and host(base) not in SHARED_PUBLISHERS:
            independent.insert(0, urljoin(base, "/"))
        for official in independent:
            if official not in roots and len(roots) < 4:
                roots.append(official)
        if shared:
            continue
        scope = scopes.setdefault(host(base), identity_publication_scope(entry["id"], root, base))
        publisher = RELATED_PUBLISHERS.get(host(base))
        if publisher and normalized(entry["name_en"]) != normalized(publisher[1]) and publisher[0]:
            related.add(publisher[0])
        # Redirects from an individual directory record remain attributable;
        # feed entries must also stay on that discovered official site.
        feeds = advertised_feeds(soup, base) + body_advertised_feeds(entry["id"], base, soup)
        pages = news_pages(soup, base)
        if scoped_parent_index(entry["id"], base):
            pages.insert(0, base)
        for page in pages:
            news_candidates.append(page)
            page_evidence, page_body = get(page)
            if page_evidence["http_status"] == 200:
                page = page_evidence["url"]
                page_soup = BeautifulSoup(page_body, "html.parser")
                feeds.extend(advertised_feeds(page_soup, page))
                scoped_index = urlparse(scope).path in {"", "/"} or urlparse(page).path.startswith(
                    urlparse(scope).path.rstrip("/") + "/"
                )
                known_parent = publisher and normalized(entry["name_en"]) != normalized(publisher[1])
                welsh_scope = welsh_scope_proof(entry, base, page, page_soup) if scoped_welsh_index(page) else None
                attributable = (host(base) not in SHARED_PUBLISHERS and scoped_index and not known_parent) or (
                    not shared and welsh_scope is not None
                ) or (
                    scoped_parent_index(entry["id"], page)
                ) or (
                    entry["id"] == "court-ew:united-kingdom-supreme-court"
                    and host(page) == "supremecourt.uk" and urlparse(page).path == "/news"
                )
                if attributable:
                    attributable_news.append(page)
                    agency = Agency(entry["name_zh"] or entry["name_en"], entry["name_en"], entry["id"], base)
                    found = parse_news_index(str(page_soup), agency, page, SINCE, datetime.now(UTC))
                    if found and all(urlparse(url).scheme == "https" for url in (base, page)):
                        row.setdefault("html_reviews", []).append({
                            "id": entry["id"], "adapter": "html_news", "homepage": base,
                            "authority_url": authority_url(), "endpoint": page,
                            "verification": {
                                **page_evidence, "parsed_count": len(found), "parser": "parse_news_index",
                                **(welsh_scope or {}),
                                "newest_published_at": max(x.published_at for x in found).isoformat(),
                                "sample_link": found[0].link,
                                "coverage": "Single official index; historical completeness is not guaranteed",
                            },
                        })
        for endpoint in dict.fromkeys(feeds):
            candidates.append(endpoint)
            feed_evidence, feed_body = get(endpoint)
            review = verify_feed(entry, base, feed_evidence["url"], feed_evidence, feed_body, scope)
            if review:
                review["authority_url"] = authority_url()
                row.update(outcome="verified", review=review)
                return row
    row["feed_candidates"] = list(dict.fromkeys(candidates))
    row["news_candidates"] = list(dict.fromkeys(news_candidates))
    row["attributable_news_candidates"] = list(dict.fromkeys(attributable_news))
    failures = [x for x in row["requests"] if x["http_status"] != 200 or x.get("error")]
    if row.get("html_reviews"):
        row.update(outcome="verified", review=row["html_reviews"][0])
    elif entry["id"] == "govuk:financial-remedies-court" and any(
        x["http_status"] == 200 and host(x["url"]) == "judiciary.uk" for x in row["requests"]
    ):
        row.update(outcome="covered_by_parent", reason="已確認司法機關的正式發布頁；GOV.UK 舊機關網址失效",
                   parent_sources=["court-ew:announcements", "court-ew:judgments"])
    elif related:
        row.update(outcome="covered_by_parent", reason="官方連結指向共用或後續機關的發布管道；未確認此名稱的獨立範圍",
                   parent_sources=sorted(related))
    elif entry["id"].startswith("court-ew:") and any(host(url) == "judiciary.uk" for url in candidates):
        row.update(outcome="covered_by_parent", reason="機關頁提供司法機關共用 RSS；由既有法院公告／判決來源收錄",
                   parent_sources=["court-ew:announcements", "court-ew:judgments"])
    elif attributable_news:
        row.update(outcome="html_adapter_required", reason="已找到官方發布頁；尚需日期與逐筆解析器驗證")
    elif candidates:
        row.update(outcome="feed_validation_failed", reason="已發現 feed，但未取得可解析且可歸屬此機關的有日期資料")
    elif failures:
        row.update(outcome="network_or_access_error", reason="連線、HTTP 或存取限制使發布管道未能確認")
    else:
        row.update(outcome="no_verified_endpoint", reason="已查核官方頁及其發布連結，未發現可驗證的獨立發布管道")
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "新聞放置區/source-audit")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply-verified", action="store_true")
    parser.add_argument("--recheck-results", action="store_true", help="重新判讀已保存的官方 HTTP 證據")
    parser.add_argument("--source-id", action="append", default=[], help="重新查核指定來源，其餘沿用已保存結果")
    parser.add_argument("--retry-errors", action="store_true", help="重新連線曾逾時或被阻擋的官方頁")
    parser.add_argument("--identity-map", type=Path, help="使用已讀取的官方 NI 聯絡名錄機關對照")
    args = parser.parse_args()
    if not 1 <= args.workers <= 32 or (args.limit is not None and args.limit < 1):
        parser.error("workers 須為 1 至 32，limit 須大於 0")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline = args.output_dir / "baseline.json"
    if not baseline.exists():
        write_json(baseline, json.loads(CATALOG.read_text()))
    sources = json.loads(baseline.read_text())["sources"]
    if args.identity_map:
        for identifier, authorities in load_identity_map(args.identity_map, sources).items():
            OFFICIAL_DISCOVERY_PAGES[identifier] = list(dict.fromkeys([
                *OFFICIAL_DISCOVERY_PAGES.get(identifier, []), *authorities,
            ]))
    targets = audit_targets(sources)
    if args.limit:
        targets = targets[:args.limit]
    counts = Counter(x["homepage"] for x in sources)
    shared_urls = {url for url, count in counts.items() if count > 1}
    results_dir = args.output_dir / "sources"
    results_dir.mkdir(exist_ok=True)
    if set(args.source_id) - {entry["id"] for entry in targets}:
        parser.error("指定 ID 不在本次僅列名或已有查核紀錄的來源範圍")
    store = FetchStore(args.output_dir / "http", retry_errors=args.retry_errors)
    results = []
    pending = []
    for entry in targets:
        path = results_dir / f"{hashlib.sha256(entry['id'].encode()).hexdigest()}.json"
        old = json.loads(path.read_text()) if path.exists() else None
        retry = args.retry_errors and old is not None and old["outcome"] not in {
            "verified", "permission_required", "policy_excluded"
        } and any(x["http_status"] in {0, 403, 429} or x["http_status"] >= 500 for x in old.get("requests", []))
        recheck = entry["id"] in args.source_id or retry or (args.recheck_results and not args.source_id)
        if old is not None and not recheck:
            results.append(old)
        else:
            pending.append((entry, path))
    print(f"targets={len(targets)} resumed={len(results)} pending={len(pending)}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_entry, entry, store, shared_urls): (entry, path) for entry, path in pending}
        for future in as_completed(futures):
            entry, path = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"id": entry["id"], "name_en": entry["name_en"], "outcome": "audit_error",
                       "reason": f"{type(exc).__name__}: {exc}", "requests": []}
            write_json(path, row)
            results.append(row)
            if len(results) % 25 == 0 or len(results) == len(targets):
                outcomes = dict(Counter(x["outcome"] for x in results))
                print(f"completed={len(results)}/{len(targets)} outcomes={outcomes}", flush=True)
    results.sort(key=lambda x: x["id"])
    payload = {"schema_version": 1, "completed_at": datetime.now(UTC).isoformat(), "target_count": len(targets),
               "completed_count": len(results), "outcomes": dict(Counter(x["outcome"] for x in results)),
               "sources": results}
    write_json(args.output_dir / "audit.json", payload)
    report = ["# 官方來源查核", "", f"共查核 {len(results)} / {len(targets)} 筆僅列名來源。", "",
              "| ID | 機關 | 結果 | 原因或發布端點 |", "| --- | --- | --- | --- |"]
    for row in results:
        detail = row["review"]["endpoint"] if row["outcome"] == "verified" else row.get("reason", "")
        report.append("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ")
                      for x in (row["id"], row["name_en"], row["outcome"], detail)) + " |")
    (args.output_dir / "audit.md").write_text("\n".join(report) + "\n")
    if args.apply_verified:
        reviews = {x["id"]: x for x in load_overrides(OVERRIDES)}
        assessments = {x["id"]: x for x in load_assessments(OVERRIDES)}
        exclusions = load_exclusions(OVERRIDES)
        excluded_ids = {x["id"] for x in exclusions}
        for row in results:
            if row["id"] in excluded_ids:
                continue
            reviews.pop(row["id"], None)
            assessments.pop(row["id"], None)
            if row["outcome"] != "verified":
                assessments[row["id"]] = {
                    "id": row["id"], "outcome": row["outcome"], "reason": row["reason"],
                    "checked_at": payload["completed_at"], "parent_sources": row.get("parent_sources", []),
                    "alternative_sources": row.get("alternative_sources", []),
                }
        reviews.update({x["id"]: x["review"] for x in results
                        if x["outcome"] == "verified" and x["id"] not in excluded_ids})
        current = json.loads(CATALOG.read_text())
        current["sources"] = apply_review_state(
            current["sources"], list(reviews.values()), list(assessments.values()), exclusions,
        )
        write_json(OVERRIDES, {"schema_version": 1, "reviews": sorted(reviews.values(), key=lambda x: x["id"]),
                               "assessments": sorted(assessments.values(), key=lambda x: x["id"]),
                               "exclusions": exclusions})
        write_json(CATALOG, current)
        print(f"applied_verified={len(reviews)}", flush=True)


if __name__ == "__main__":
    main()
