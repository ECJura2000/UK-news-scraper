"""Refresh the reviewable GOV.UK organisation snapshot from its public API.

This script deliberately does not run during a scrape. Review the generated
diff before committing because government organisations change over time.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


API = "https://www.gov.uk/api/organisations"
OUTPUT = Path(__file__).resolve().parent.parent / "UK_news_scraper" / "data" / "source_catalog.json"
EXISTING_SLUGS = {
    "department-for-business-innovation-science-and-trade",
    "department-for-culture-media-and-sport",
    "ai-safety-institute",
    "competition-and-markets-authority",
    "intellectual-property-office",
    "government-digital-service",
    "cabinet-office",
    "information-commissioner-s-office",
    "ofcom",
    "national-cyber-security-centre",
    "the-electoral-commission",
    "national-protective-security-authority",
    "uk-research-and-innovation",
}
SCOTLAND_DIRECTORY = "https://www.gov.scot/publications/national-public-bodies-directory/"
WALES_DIRECTORY = "https://www.gov.wales/organisations"
NI_BODIES = "https://www.publicappointmentsni.org/list-bodies-we-regulate"
NI_DEPARTMENTS = "https://www.nidirect.gov.uk/contacts/government-departments-in-northern-ireland"
NI_FINANCE_DIRECTORY = "https://www.finance-ni.gov.uk/articles/list-bodies-which-public-procurement-policy-statement-applies"
# The Finance directory blocks automated reads on some networks. These additional
# names were reviewed against its public list on 2026-09-25; keep them visible as
# directory-only until an independent publication page has been verified.
NI_FINANCE_EXTRAS = (
    "Public Prosecution Service for Northern Ireland",
    "Attorney General for Northern Ireland",
    "Commissioner for Public Appointments for Northern Ireland",
    "Commissioner for Survivors of Institutional Childhood Abuse",
    "Community Relations Council",
    "Driver and Vehicle Agency",
    "Education Training Inspectorate",
    "Equality Commission for Northern Ireland",
    "Exceptional Circumstances Body",
    "Fiscal Council",
    "Forensic Science Northern Ireland",
    "Forest Service",
    "Legal Services Agency Northern Ireland",
    "Northern Ireland Courts and Tribunals Service",
    "Northern Ireland Environment Agency",
    "Northern Ireland Prison Service",
    "Northern Ireland Prisoner Ombudsman",
    "Northern Ireland Statistics and Research Agency",
    "Planning Appeals and Water Appeals Commission",
    "Police Service of Northern Ireland",
    "Victims and Survivors Service Ltd",
    "Victims’ Payment Board",
    "Youth Justice Agency",
)
EW_COURTS = "https://www.judiciary.uk/structure-of-courts-and-tribunals-system/"
SCOTLAND_COURTS = "https://www.scotcourts.gov.uk/courts-and-tribunals/"
WALES_TRIBUNALS = "https://www.gov.wales/welsh-tribunals/about-us"
DIRECTORY_ONLY_SLUGS = {"bbc"}  # BBC is outside the project's permitted scraping sources.


def _slug(name: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in name).split())


def _directory_entry(prefix: str, name: str, jurisdiction: str, kind: str, homepage: str, provenance: str) -> dict:
    return {
        "id": f"{prefix}:{_slug(name)}", "name_en": name, "name_zh": "",
        "jurisdiction": jurisdiction, "kind": kind, "homepage": homepage,
        "status": "directory_only", "adapter": "", "slug": "", "feed": "",
        "provenance": provenance, "reason": "尚未驗證獨立官方發布頁",
    }


def _page(number: int) -> dict:
    url = API if number == 1 else f"{API}?page={number}"
    request = Request(url, headers={"User-Agent": "UK-news-scraper/source-catalog"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def collect_govuk() -> list[dict]:
    first = _page(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = [first, *pool.map(_page, range(2, first["pages"] + 1))]
    records = []
    for page in pages:
        for value in page["results"]:
            details = value.get("details") or {}
            slug = details.get("slug")
            if not slug or slug in EXISTING_SLUGS or details.get("govuk_status") == "closed":
                continue
            homepage = value.get("web_url", "")
            if not homepage.startswith("https://www.gov.uk/government/organisations/"):
                continue
            is_live = details.get("govuk_status") == "live" and slug not in DIRECTORY_ONLY_SLUGS
            records.append({
                "id": f"govuk:{slug}",
                "name_en": value["title"],
                "name_zh": "",
                "jurisdiction": "UK",
                "kind": value.get("format", "Other"),
                "homepage": homepage,
                "status": "searchable" if is_live else "directory_only",
                "adapter": "govuk_search" if is_live else "",
                "slug": slug,
                "provenance": API,
                "reason": "" if is_live else ("依專案設定不抓 BBC" if slug in DIRECTORY_ONLY_SLUGS else "GOV.UK 未標記為可發布來源"),
            })
    return sorted(records, key=lambda row: row["id"])


def _html(url: str) -> BeautifulSoup:
    request = Request(url, headers={"User-Agent": "UK-news-scraper/source-catalog"})
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read()
    except Exception:
        from curl_cffi import requests as browser_requests

        response = browser_requests.get(url, impersonate="chrome120", timeout=20)
        response.raise_for_status()
        content = response.content
    return BeautifulSoup(content, "html.parser")


def collect_scotland() -> list[dict]:
    root = _html(SCOTLAND_DIRECTORY)
    sections = {
        urljoin(SCOTLAND_DIRECTORY, anchor["href"]): anchor.get_text(" ", strip=True)
        for anchor in root.select('a[href*="national-public-bodies-directory/pages/"]')
        if anchor.get_text(" ", strip=True)
        not in {"Introduction", "Notes", "Public sector organisations outwith Ministerial or Parliamentary responsibility"}
    }
    records = {}
    for url, kind in sections.items():
        page = _html(url)
        for heading in page.select("h3"):
            name = heading.get_text(" ", strip=True)
            if not name:
                continue
            homepage = ""
            for sibling in heading.next_siblings:
                if getattr(sibling, "name", None) == "h3":
                    break
                for anchor in getattr(sibling, "select", lambda _: [])('a[href^="http"]'):
                    homepage = anchor["href"]
                    break
                if homepage:
                    break
            slug = _slug(name)
            records[slug] = {
                "id": f"scotland:{slug}",
                "name_en": name,
                "name_zh": "",
                "jurisdiction": "Scotland",
                "kind": kind,
                "homepage": homepage or url,
                "status": "directory_only",
                "adapter": "",
                "slug": "",
                "provenance": url,
                "reason": "尚未驗證獨立官方發布頁",
            }
    return sorted(records.values(), key=lambda row: row["id"])


def collect_wales() -> list[dict]:
    page = _html(WALES_DIRECTORY)
    records = []
    for row in page.select("li.index-list__item"):
        anchor = row.select_one(".index-list__title a[href]")
        if anchor is None:
            continue
        kind = row.select_one(".index-list__type")
        kind_text = kind.get_text(" ", strip=True) if kind else "Other"
        if kind_text == "Local government":
            continue
        name = anchor.get_text(" ", strip=True)
        slug = anchor["href"].strip("/").replace("/", "-")
        records.append({
            "id": f"wales:{slug}", "name_en": name, "name_zh": "",
            "jurisdiction": "Wales", "kind": kind_text,
            "homepage": urljoin(WALES_DIRECTORY, anchor["href"]),
            "status": "directory_only", "adapter": "", "slug": "",
            "provenance": WALES_DIRECTORY,
            "reason": "尚未驗證獨立官方發布頁",
        })
    if len(records) < 150:
        raise RuntimeError("威爾斯官方目錄筆數異常，停止更新")
    return sorted(records, key=lambda row: row["id"])


def collect_northern_ireland() -> list[dict]:
    records: dict[str, dict] = {}
    for anchor in _html(NI_DEPARTMENTS).select("article li a[href]"):
        name = anchor.get_text(" ", strip=True)
        if name.startswith("Department") or name == "The Executive Office":
            row = _directory_entry("ni", name, "Northern Ireland", "Government department", urljoin(NI_DEPARTMENTS, anchor["href"]), NI_DEPARTMENTS)
            records[row["id"]] = row
    page = _html(NI_BODIES)
    for group in page.select("main .content ul"):
        for li in group.find_all("li", recursive=False):
            name = li.contents[0].get_text(" ", strip=True) if getattr(li.contents[0], "get_text", None) else str(li.contents[0]).strip()
            if not name or name.endswith(":"):
                continue
            row = _directory_entry("ni", name, "Northern Ireland", "Public body", NI_BODIES, NI_BODIES)
            records.setdefault(row["id"], row)
            for child in li.select("li"):
                child_name = child.get_text(" ", strip=True)
                child_row = _directory_entry("ni", child_name, "Northern Ireland", "Public body", NI_BODIES, NI_BODIES)
                records.setdefault(child_row["id"], child_row)
    for name in NI_FINANCE_EXTRAS:
        row = _directory_entry("ni", name, "Northern Ireland", "Public body", NI_FINANCE_DIRECTORY, NI_FINANCE_DIRECTORY)
        records.setdefault(row["id"], row)
    if len(records) < 80:
        raise RuntimeError("北愛爾蘭官方目錄筆數異常，停止更新")
    return sorted(records.values(), key=lambda row: row["id"])


def collect_courts() -> list[dict]:
    records: dict[str, dict] = {}
    page = _html(EW_COURTS)
    for anchor in page.select("main .organogram a[href]"):
        name = anchor.get_text(" ", strip=True)
        if not name:
            continue
        row = _directory_entry("court-ew", name, "UK" if "Supreme Court" in name else "England and Wales", "Court or tribunal", urljoin(EW_COURTS, anchor["href"]), EW_COURTS)
        if row["id"] in records:
            row["id"] += "-" + _slug(anchor["href"].rstrip("/").split("/")[-2])
        records[row["id"]] = row
    for name, url in (
        ("Court of Session", "https://www.scotcourts.gov.uk/courts-and-tribunals/the-supreme-courts/the-court-of-session/"),
        ("High Court of Justiciary", "https://www.scotcourts.gov.uk/courts-and-tribunals/the-supreme-courts/the-high-court-of-justiciary/"),
        ("Sheriff Appeal Court", "https://www.scotcourts.gov.uk/courts-and-tribunals/appeals-courts/"),
        ("Sheriff Courts", "https://www.scotcourts.gov.uk/courts-and-tribunals/sheriff-and-justice-of-the-peace-courts/"),
        ("Justice of the Peace Courts", "https://www.scotcourts.gov.uk/courts-and-tribunals/sheriff-and-justice-of-the-peace-courts/"),
        ("Scottish Tribunals", "https://www.scotcourts.gov.uk/courts-and-tribunals/scottish-tribunals/"),
        ("Upper Tribunal for Scotland", "https://www.scotcourts.gov.uk/courts-and-tribunals/scottish-tribunals/"),
        ("First-tier Tribunal for Scotland", "https://www.scotcourts.gov.uk/courts-and-tribunals/scottish-tribunals/"),
    ):
        row = _directory_entry("court-scotland", name, "Scotland", "Court or tribunal", url, SCOTLAND_COURTS)
        records[row["id"]] = row
    for name in ("Adjudication Panel for Wales", "Agricultural Land Tribunal for Wales", "Mental Health Review Tribunal for Wales", "Education Tribunal for Wales", "Residential Property Tribunal Wales", "Welsh Language Tribunal"):
        row = _directory_entry("court-wales", name, "Wales", "Tribunal", WALES_TRIBUNALS, WALES_TRIBUNALS)
        records[row["id"]] = row
    for name in ("Court of Appeal in Northern Ireland", "High Court of Justice in Northern Ireland", "Crown Court in Northern Ireland", "County Court in Northern Ireland", "Magistrates' Courts in Northern Ireland", "Northern Ireland Tribunal Service"):
        provenance = "https://www.judiciaryni.uk/files/judiciaryni/media-files/Court%20Structure%20in%20Northern%20Ireland_1.pdf"
        row = _directory_entry("court-ni", name, "Northern Ireland", "Court or tribunal", "https://www.judiciaryni.uk/", provenance)
        records[row["id"]] = row
    records["court-ew:find-case-law"] = {
        **_directory_entry("court-ew", "The National Archives Find Case Law", "England and Wales", "Official case-law directory", "https://caselaw.nationalarchives.gov.uk/courts-and-tribunals", "https://caselaw.nationalarchives.gov.uk/when-you-need-permission"),
        "id": "court-ew:find-case-law",
        "reason": "大量程式查詢與分析須先取得授權；目前僅提供官方連結",
    }
    records["court-ew:united-kingdom-supreme-court"].update(
        homepage="https://www.supremecourt.uk/news/latest-judgments",
        provenance="https://www.supremecourt.uk/news/latest-judgments",
        reason="官方判決頁僅列近期個案；尚未驗證完整日期查詢介面",
    )
    for name, identifier, jurisdiction, homepage, feed, provenance in (
        ("Courts and Tribunals Judiciary judgments", "court-ew:judgments", "England and Wales", "https://www.judiciary.uk/judgments/", "https://www.judiciary.uk/judgments/feed/", "https://www.judiciary.uk/rss-feeds/"),
        ("Courts and Tribunals Judiciary announcements", "court-ew:announcements", "England and Wales", "https://www.judiciary.uk/announcements/", "https://www.judiciary.uk/announcements/feed/", "https://www.judiciary.uk/rss-feeds/"),
        ("Scottish Courts and Tribunals Service judgments", "court-scotland:judgments", "Scotland", "https://www.scotcourts.gov.uk/judgments/", "https://api.pa.web.scotcourts.gov.uk/web/rss/Judgments", "https://www.scotcourts.gov.uk/rss-feeds/"),
    ):
        row = _directory_entry("court", name, jurisdiction, "Official judicial publication", homepage, provenance)
        row.update(id=identifier, status="searchable", adapter="feed", feed=feed, reason="")
        records[identifier] = row
    if len(records) < 35:
        raise RuntimeError("法院官方目錄筆數異常，停止更新")
    return sorted(records.values(), key=lambda row: row["id"])


def main() -> None:
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"sources": []}
    manual = [row for row in existing["sources"] if not row["id"].startswith(("govuk:", "scotland:", "wales:", "ni:", "court-"))]
    payload = {
        "schema_version": 1,
        "as_of": date.today().isoformat(),
        "sources": sorted([*collect_govuk(), *collect_scotland(), *collect_wales(), *collect_northern_ireland(), *collect_courts(), *manual], key=lambda row: row["id"]),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"catalog: {len(payload['sources'])} sources; review {OUTPUT}")


if __name__ == "__main__":
    main()
