"""Find missing NI publication identities from the official nidirect contact list.

Only exact organisation-name matches (with spelled-out HSC and optional acronym)
are accepted. Contact URLs are evidence, never proof that a news feed is usable.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.audit_source_catalog import CATALOG, FetchStore, host, write_json  # noqa: E402


def identity_key(value: str) -> str:
    value = re.sub(r"\(([^)]*)\)", lambda match: " " if (
        match[1].isupper() or match[1].casefold() == "northern ireland"
    ) else match[0], value).casefold()
    value = re.sub(r"\bhsc\b", "health and social care", value)
    value = value.replace("&", " and ")
    return " ".join(re.findall(r"\w+", value))


def contact_entries(body: bytes, base: str) -> list[dict]:
    soup = BeautifulSoup(body, "html.parser")
    selector = "main .view-content li a[href]" if host(base) == "nidirect.gov.uk" else "main a[href]"
    return [{"name_en": node.get_text(" ", strip=True), "contact_url": urljoin(base, node["href"]),
             "authority_url": base}
            for node in soup.select(selector) if not node.find_parent(["footer", "nav"])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "新聞放置區/source-audit")
    args = parser.parse_args()
    store = FetchStore(args.output_dir / "http", retry_errors=True)
    urls = [f"https://www.nidirect.gov.uk/contacts/letter/{letter}" for letter in string.ascii_lowercase]
    urls += [f"https://www.{department}-ni.gov.uk/" for department in (
        "health", "education", "economy", "communities", "justice", "finance", "infrastructure", "daera",
    )]
    urls.append("https://www.executiveoffice-ni.gov.uk/")

    def fetch(url: str) -> tuple[dict, list[dict]]:
        evidence, body = store.get(url)
        return evidence, contact_entries(body, url) if evidence["http_status"] == 200 else []

    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = list(pool.map(fetch, urls))
    contacts = [entry for _, entries in pages for entry in entries]
    sources = json.loads(CATALOG.read_text(encoding="utf-8"))["sources"]
    # GOV.UK's verified inventory supplies additional exact organisation names,
    # including acronyms absent from nidirect's public-facing contact labels.
    contacts += [{"name_en": source["name_en"], "contact_url": source.get("authority_url") or source["homepage"],
                  "authority_url": source.get("authority_url") or source["homepage"]}
                 for source in sources if source["id"].startswith("govuk:")
                 and ("northern ireland" in source["name_en"].casefold()
                      or source["id"] == "govuk:labour-relations-agency")]
    targets = [source for source in sources if source["id"].startswith("ni:")
               and source["status"] == "directory_only"]
    mappings, unresolved = [], []
    for source in targets:
        matches = [item for item in contacts if identity_key(item["name_en"]) == identity_key(source["name_en"])]
        unique = {item["contact_url"]: item for item in matches}
        if unique:
            # Exact-name official records may differ only in contact/website URLs.
            # Retain all authorities, preferring a direct website over GOV.UK metadata.
            ordered = sorted(unique.values(), key=lambda item: (
                host(item["contact_url"]) in {"gov.uk", "nidirect.gov.uk"}
            ))
            item = ordered[0]
            evidence, body = store.get(item["contact_url"])
            soup = BeautifulSoup(body, "html.parser")
            external = []
            if host(item["contact_url"]) == "nidirect.gov.uk":
                for node in soup.select("main a[href]"):
                    link = urljoin(item["contact_url"], node["href"])
                    if node.find_parent(["footer", "nav"]) or not link.startswith(("http://", "https://")):
                        continue
                    if host(link) != "nidirect.gov.uk" and re.search(r"\b(website|web|www)\b", node.get_text(), re.I):
                        external.append(link)
            mappings.append({
                "id": source["id"], "name_en": source["name_en"], "matched_name": item["name_en"],
                "authority_url": item["authority_url"], "contact_url": item["contact_url"],
                "website_urls": list(dict.fromkeys(external)) if external else [item["contact_url"]],
                "contact_evidence": evidence, "official_records": ordered,
            })
        else:
            unresolved.append({"id": source["id"], "name_en": source["name_en"],
                               "reason": "官方聯絡目錄未有唯一同名機關"})
    write_json(args.output_dir / "ni-identity-discovery.json", {
        "schema_version": 1, "directory_count": len(contacts), "targets": len(targets),
        "matches": mappings, "unresolved": unresolved, "requests": [evidence for evidence, _ in pages],
    })
    print(f"official_contacts={len(contacts)}; NI_targets={len(targets)}; matches={len(mappings)}")


if __name__ == "__main__":
    main()
