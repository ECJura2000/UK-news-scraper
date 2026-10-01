from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import feedparser
import pytest
from bs4 import BeautifulSoup

from scripts import audit_source_catalog as audit
from scripts import refresh_source_catalog as refresh
from UK_news_scraper.catalog_html import index_date, parse_news_index
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry.registry import AgencyFeedScraper
from UK_news_scraper.source_review import apply_assessments, apply_exclusions, apply_overrides, apply_review_state

HTML = (Path(__file__).parent / "fixtures/catalog_news_index.html").read_text()
SINCE = datetime(2026, 9, 24, tzinfo=UTC)
UNTIL = datetime(2026, 9, 26, tzinfo=UTC)


def review():
    return {
        "id": "govuk:test", "homepage": "https://official.example/", "adapter": "feed",
        "endpoint": "https://official.example/feed/", "authority_url": "https://www.gov.uk/test",
        "verification": {"http_status": 200, "parsed_count": 2,
                         "response_sha256": "a" * 64, "checked_at": "2026-09-30T01:00:00+00:00",
                         "production_parser_verified": True, "python_rust_parity": True},
    }


def entry():
    return {"id": "govuk:test", "name_en": "Official Test Agency", "homepage": "https://www.gov.uk/test",
            "status": "directory_only", "adapter": "", "reason": "尚未驗證", "name_zh": ""}


def exclusion():
    return {
        "id": "govuk:test", "outcome": "covered_by_parent", "reason": "共用主管機關发布管道",
        "checked_at": "2026-09-30T01:00:00+00:00", "authority_url": "https://official.example/",
        "replacement_sources": ["govuk:parent"], "original_source": entry(),
    }


def test_exclusions_prevent_reappearance_and_override_retained_reviews():
    old = entry()
    removed = exclusion()
    assert apply_review_state([old], [review()], [], [removed]) == []
    assert apply_review_state([], [review()], [], [removed]) == []
    assert old == entry()
    assert removed["original_source"] == entry()


def test_orphaned_reviews_fail_closed_unless_their_id_was_explicitly_excluded():
    with pytest.raises(ValueError, match="不在名錄"):
        apply_review_state([], [review()], [], [])
    hold = {"id": "govuk:missing", "outcome": "network_or_access_error", "reason": "逾時",
            "checked_at": "2026-09-30T01:00:00+00:00"}
    with pytest.raises(ValueError, match="不在名錄"):
        apply_review_state([], [], [hold], [exclusion()])


def test_refresh_does_not_revive_removed_channels_or_fail_on_their_old_reviews(monkeypatch, tmp_path):
    catalog = tmp_path / "source_catalog.json"
    audit.write_json(catalog, {"schema_version": 1, "sources": [entry()]})
    audit.write_json(catalog.with_name("source_catalog_overrides.json"), {
        "schema_version": 1, "reviews": [review()], "exclusions": [exclusion()],
        "assessments": [{"id": "govuk:test", "outcome": "covered_by_parent", "reason": "共用",
                         "checked_at": "2026-09-30T01:00:00+00:00"}],
    })
    monkeypatch.setattr(refresh, "OUTPUT", catalog)
    monkeypatch.setattr(refresh, "collect_govuk", lambda: [entry()])
    for collector in ("collect_scotland", "collect_wales", "collect_northern_ireland", "collect_courts"):
        monkeypatch.setattr(refresh, collector, list)
    refresh.main()
    refresh.main()
    assert refresh.json.loads(catalog.read_text())["sources"] == []
    monkeypatch.setattr(refresh, "collect_govuk", list)
    refresh.main()
    assert refresh.json.loads(catalog.read_text())["sources"] == []


def test_refresh_preserves_existing_catalog_when_nonexcluded_review_goes_missing(monkeypatch, tmp_path):
    catalog = tmp_path / "source_catalog.json"
    audit.write_json(catalog, {"schema_version": 1, "sources": [entry()]})
    audit.write_json(catalog.with_name("source_catalog_overrides.json"), {
        "schema_version": 1, "reviews": [review()],
    })
    previous = catalog.read_bytes()
    monkeypatch.setattr(refresh, "OUTPUT", catalog)
    for collector in (
        "collect_govuk", "collect_scotland", "collect_wales", "collect_northern_ireland", "collect_courts",
    ):
        monkeypatch.setattr(refresh, collector, list)
    with pytest.raises(ValueError, match="不在名錄"):
        refresh.main()
    assert catalog.read_bytes() == previous


def test_incomplete_exclusions_cannot_silently_delete_sources():
    for changes in ({"original_source": {}}, {"replacement_sources": []}, {"replacement_sources": ["govuk:test"]},
                    {"authority_url": ""}, {"outcome": "network_or_access_error"}, {"checked_at": "2026-09-30"}):
        item = {**exclusion(), **changes}
        with pytest.raises(ValueError):
            apply_exclusions([entry()], [item])
    with pytest.raises(ValueError, match="重複"):
        apply_exclusions([entry()], [exclusion(), exclusion()])


def test_adopting_old_audit_results_keeps_exclusions_and_cannot_revive_source(monkeypatch, tmp_path):
    catalog = tmp_path / "source_catalog.json"
    overrides = catalog.with_name("source_catalog_overrides.json")
    output = tmp_path / "audit"
    audit.write_json(catalog, {"schema_version": 1, "sources": []})
    audit.write_json(overrides, {"schema_version": 1, "reviews": [], "assessments": [],
                               "exclusions": [exclusion()]})
    audit.write_json(output / "baseline.json", {"schema_version": 1, "sources": [entry()]})
    cached = output / "sources" / f"{audit.hashlib.sha256(b'govuk:test').hexdigest()}.json"
    audit.write_json(cached, {"id": "govuk:test", "name_en": "Test", "outcome": "verified", "review": review()})
    monkeypatch.setattr(audit, "CATALOG", catalog)
    monkeypatch.setattr(audit, "OVERRIDES", overrides)
    monkeypatch.setattr(refresh.sys, "argv", ["audit", "--output-dir", str(output), "--apply-verified"])
    audit.main()
    assert audit.json.loads(catalog.read_text())["sources"] == []
    state = audit.json.loads(overrides.read_text())
    assert state["exclusions"] == [exclusion()]
    assert state["reviews"] == []


def test_removal_plan_keeps_access_failures_and_licensing_holds():
    from scripts.cleanup_source_catalog import plan_removals

    sources = [{**entry(), "id": identifier} for identifier in ("govuk:test", "govuk:access", "govuk:licensed")]
    rows = [
        {"id": "govuk:test", "outcome": "available_as_other_source", "reason": "同一機關",
         "alternative_sources": ["govuk:parent"]},
        {"id": "govuk:access", "outcome": "network_or_access_error", "reason": "403"},
        {"id": "govuk:licensed", "outcome": "permission_required", "reason": "需授權"},
    ]
    result = plan_removals(sources, rows, "2026-09-30T01:00:00+00:00", {"govuk:parent"})
    assert [item["id"] for item in result] == ["govuk:test"]
    assert result[0]["original_source"] == sources[0]
    with pytest.raises(ValueError, match="替代管道"):
        plan_removals(sources, rows, "2026-09-30T01:00:00+00:00", set())


@pytest.mark.parametrize("identifier", [
    "govuk:research-england", "scotland:accounts-commission-for-scotland",
    "scotland:scottish-courts-and-tribunals-service",
])
def test_cleanup_never_removes_identified_body_scoped_channels_as_shared_parent(identifier):
    from scripts.cleanup_source_catalog import plan_removals

    source = {**entry(), "id": identifier}
    row = {"id": identifier, "outcome": "covered_by_parent", "reason": "舊共用路由判讀",
           "parent_sources": ["parent"]}
    assert plan_removals([source], [row], "2026-10-01T01:00:00+00:00", {"parent"}) == []


def test_shared_parent_exception_requires_exact_body_id_and_scoped_url():
    assert audit.scoped_parent_index("govuk:research-england", "https://www.ukri.org/councils/research-england/news/")
    assert audit.scoped_parent_index("scotland:accounts-commission-for-scotland", "https://audit.scot/accounts-commission")
    for identifier, endpoint in (
        ("govuk:research-england", "https://www.ukri.org/news/"),
        ("govuk:research-england", "https://www.ukri.org/councils/other/news/"),
        ("govuk:research-england", "https://www.ukri.org/councils/research-england/news/?all=true"),
        ("govuk:other-body", "https://www.ukri.org/councils/research-england/news/"),
        ("scotland:accounts-commission-for-scotland", "https://audit.scot/news"),
        ("scotland:audit-scotland", "https://audit.scot/accounts-commission"),
    ):
        assert not audit.scoped_parent_index(identifier, endpoint)


def test_official_contact_identity_matching_keeps_board_and_subordinate_scope():
    from scripts.discover_catalog_identities import contact_entries, identity_key

    assert identity_key("Belfast HSC Trust (BHSCT)") == identity_key("Belfast Health and Social Care Trust")
    assert identity_key("Agency (NI)") == identity_key("Agency")
    assert identity_key("Commission (Lay Member)") != identity_key("Commission")
    assert identity_key("Observatory Board of Governors") != identity_key("Observatory")
    entries = contact_entries(b'<main><nav><a href="https://other.example">Other</a></nav>'
                              b'<div class="view-content"><li><a href="/contacts/agency">Agency</a></li></div></main>',
                              "https://www.nidirect.gov.uk/contacts/letter/a")
    assert entries == [{"name_en": "Agency", "contact_url": "https://www.nidirect.gov.uk/contacts/agency",
                        "authority_url": "https://www.nidirect.gov.uk/contacts/letter/a"}]


def test_identity_map_rechecks_matching_official_anchor_and_ignores_injected_website(monkeypatch, tmp_path):
    authority = "https://www.nidirect.gov.uk/contacts/letter/o"
    contact = "https://official.example/contact"
    item = {"id": "ni:test", "matched_name": entry()["name_en"], "authority_url": authority,
            "contact_url": contact, "website_urls": ["https://unrelated.example/"]}
    path = tmp_path / "mapping.json"
    payload = {"schema_version": 1, "matches": [item], "requests": [{"url": authority, "http_status": 200}]}
    audit.write_json(path, payload)

    class Store:
        def __init__(self, _):
            pass

        def get(self, url):
            assert url == authority
            body = f'<main><div class="view-content"><li><a href="{contact}">{entry()["name_en"]}</a></li></div></main>'
            return {"url": authority, "http_status": 200}, body.encode()

    monkeypatch.setattr(audit, "FetchStore", Store)
    monkeypatch.setattr(audit, "OFFICIAL_IDENTITY_CONTACTS", {})
    monkeypatch.setattr(audit, "OFFICIAL_IDENTITY_AUTHORITIES", {})
    assert audit.load_identity_map(path, [{**entry(), "id": "ni:test"}]) == {"ni:test": [contact]}
    assert audit.identity_publication_scope("ni:test", contact, contact) == "https://official.example/"
    item["contact_url"] = "https://unrelated.example/"
    audit.write_json(path, payload)
    with pytest.raises(ValueError, match="未列出此機關"):
        audit.load_identity_map(path, [{**entry(), "id": "ni:test"}])


def test_identity_scope_never_expands_a_departmental_body_contact_to_whole_parent(monkeypatch):
    contact = "https://www.justice-ni.gov.uk/contacts/body"
    monkeypatch.setattr(audit, "OFFICIAL_IDENTITY_CONTACTS", {"ni:body": [contact]})
    assert audit.identity_publication_scope("ni:body", contact, contact) == contact


def test_scts_plain_text_feed_requires_exact_body_and_official_advertising_page():
    soup = BeautifulSoup(f'<main>All news articles: {audit.SCTS_NEWS_FEED}</main>', "html.parser")
    page = "https://www.scotcourts.gov.uk/rss-feeds/"
    assert audit.body_advertised_feeds(audit.SCTS, page, soup) == [audit.SCTS_NEWS_FEED]
    assert audit.body_advertised_feeds("court-scotland:court-of-session", page, soup) == []
    assert audit.body_advertised_feeds(audit.SCTS, "https://other.example/rss-feeds", soup) == []
    assert audit.body_advertised_feeds(audit.SCTS, page, BeautifulSoup("No RSS", "html.parser")) == []


def test_repeated_cleanup_plan_retains_the_original_recovery_records(monkeypatch, tmp_path):
    from scripts import cleanup_source_catalog as cleanup

    catalog = tmp_path / "catalog.json"
    overrides = tmp_path / "overrides.json"
    audit_file = tmp_path / "audit.json"
    plan = tmp_path / "plan.json"
    audit.write_json(catalog, {"schema_version": 1, "sources": []})
    audit.write_json(overrides, {"schema_version": 1, "reviews": [], "exclusions": [exclusion()]})
    audit.write_json(audit_file, {"schema_version": 1, "sources": []})
    monkeypatch.setattr(cleanup, "CATALOG", catalog)
    monkeypatch.setattr(cleanup, "OVERRIDES", overrides)
    monkeypatch.setattr(refresh.sys, "argv", ["cleanup", "--audit", str(audit_file), "--plan", str(plan)])
    cleanup.main()
    cleanup.main()
    assert audit.json.loads(plan.read_text())["exclusions"] == [exclusion()]


def test_explicit_remove_disabled_keeps_runtime_and_permission_backups_and_survives_refresh(monkeypatch, tmp_path):
    from scripts import cleanup_source_catalog as cleanup

    held = {**entry(), "id": "govuk:runtime-held", "reason": "Python/Rust 連線失敗", "authority_url": "https://official.example/"}
    licensed = {**entry(), "id": "court-ew:find-case-law", "reason": "需授權", "authority_url": "https://caselaw.nationalarchives.gov.uk/"}
    enabled = {**entry(), "id": "govuk:enabled", "status": "searchable", "adapter": "govuk_search"}
    sources = [held, licensed, enabled]
    assessments = [{"id": source["id"], "outcome": outcome, "reason": source["reason"],
                    "checked_at": "2026-10-01T01:00:00+00:00"}
                   for source, outcome in ((held, "network_or_access_error"), (licensed, "permission_required"))]
    catalog, overrides, plan = (tmp_path / name for name in (
        "source_catalog.json", "source_catalog_overrides.json", "plan.json",
    ))
    audit.write_json(catalog, {"schema_version": 1, "sources": sources})
    audit.write_json(overrides, {"schema_version": 1, "reviews": [], "assessments": assessments,
                               "exclusions": [exclusion()]})
    monkeypatch.setattr(cleanup, "CATALOG", catalog)
    monkeypatch.setattr(cleanup, "OVERRIDES", overrides)
    monkeypatch.setattr(refresh.sys, "argv", ["cleanup", "--remove-disabled", "--plan", str(plan)])
    cleanup.main()
    generated = audit.json.loads(plan.read_text())["exclusions"]
    backup_catalog = plan.with_suffix(".catalog-before-removal.json").read_bytes()
    backup_state = plan.with_suffix(".overrides-before-removal.json").read_bytes()
    assert len(generated) == 3
    assert {item["id"] for item in generated if item["outcome"] == "user_requested_removal"} == {
        held["id"], licensed["id"],
    }
    monkeypatch.setattr(refresh.sys, "argv", ["cleanup", "--apply", "--plan", str(plan)])
    cleanup.main()
    saved = overrides.read_bytes()
    cleanup.main()
    assert overrides.read_bytes() == saved
    monkeypatch.setattr(refresh.sys, "argv", ["cleanup", "--remove-disabled", "--plan", str(plan)])
    cleanup.main()
    assert plan.with_suffix(".catalog-before-removal.json").read_bytes() == backup_catalog
    assert plan.with_suffix(".overrides-before-removal.json").read_bytes() == backup_state
    state = audit.json.loads(saved)
    assert state["assessments"] == assessments
    for original in (held, licensed):
        backup = next(item for item in state["exclusions"] if item["id"] == original["id"])
        assert backup["original_source"] == original
        assert backup["original_reason"] == original["reason"]
        assert backup["original_status"] == "directory_only"
        assert backup["authority_url"] == original["authority_url"]
    monkeypatch.setattr(refresh, "OUTPUT", catalog)
    monkeypatch.setattr(refresh, "collect_govuk", lambda: sources)
    for collector in ("collect_scotland", "collect_wales", "collect_northern_ireland", "collect_courts"):
        monkeypatch.setattr(refresh, collector, list)
    refresh.main()
    refresh.main()
    assert audit.json.loads(catalog.read_text())["sources"] == [enabled]


def test_user_requested_removal_cannot_target_searchable_sources_or_misstate_original_reason():
    from scripts.cleanup_source_catalog import plan_disabled_removals

    assert plan_disabled_removals([{**entry(), "status": "searchable"}], "2026-10-01T01:00:00+00:00") == []
    item = plan_disabled_removals([entry()], "2026-10-01T01:00:00+00:00")[0]
    assert apply_exclusions([entry()], [item]) == []
    item["original_reason"] = "已裁撤"
    with pytest.raises(ValueError, match="原僅列名狀態與原因"):
        apply_exclusions([entry()], [item])


def test_unverified_results_cannot_enable_a_source():
    for changes in ({"http_status": 403}, {"parsed_count": 0}, {"response_sha256": ""},
                    {"checked_at": "2026-09-30T01:00:00"}, {"python_rust_parity": False},
                    {"production_parser_verified": False}):
        item = review()
        item["verification"].update(changes)
        with pytest.raises(ValueError):
            apply_overrides([entry()], [item])
    with pytest.raises(ValueError):
        apply_overrides([entry()], [review(), review()])
    with pytest.raises(ValueError):
        apply_overrides([], [review()])


def test_refresh_preserves_reviewed_endpoint_and_original_input(monkeypatch, tmp_path):
    catalog = tmp_path / "source_catalog.json"
    overrides = catalog.with_name("source_catalog_overrides.json")
    audit.write_json(catalog, {"schema_version": 1, "sources": [entry()]})
    audit.write_json(overrides, {"schema_version": 1, "reviews": [review()]})
    monkeypatch.setattr(refresh, "OUTPUT", catalog)
    monkeypatch.setattr(refresh, "collect_govuk", lambda: [entry()])
    for collector in ("collect_scotland", "collect_wales", "collect_northern_ireland", "collect_courts"):
        monkeypatch.setattr(refresh, collector, list)
    refresh.main()
    refresh.main()
    assert refresh.json.loads(catalog.read_text())["sources"][0]["feed"] == review()["endpoint"]
    original = entry()
    apply_overrides([original], [review()])
    assert original["status"] == "directory_only"


def test_project_policy_and_permission_require_separate_review():
    for identifier in ("govuk:bbc", "court-ew:find-case-law"):
        source, checked = entry(), review()
        source["id"] = checked["id"] = identifier
        with pytest.raises(ValueError, match="專案設定或授權"):
            apply_overrides([source], [checked])


def test_shared_publisher_feed_is_not_attributed_to_each_body():
    document = {"feed": {"title": "All government news"}}
    assert not audit.feed_is_attributable(entry(), "https://www.gov.uk/test",
                                         "https://www.gov.uk/search/news-and-communications.atom", document)
    court = {"id": "court-ew:admiralty-court", "name_en": "Admiralty Court"}
    assert not audit.feed_is_attributable(court, "https://www.judiciary.uk/courts/admiralty/",
                                         "https://www.judiciary.uk/feed/", document)
    assert audit.feed_is_attributable(entry(), "https://official.example/",
                                     "https://official.example/feed/", document)


def test_shared_directory_does_not_assign_another_bodys_website():
    soup = BeautifulSoup('<h3>First Body</h3><a href="https://first.example/">Website</a>'
                         '<h3>Second Body</h3><a href="https://second.example/">Website</a>', "html.parser")
    assert audit.independent_sites(soup, "https://directory.example/", "Second Body", True) == [
        "https://second.example/"
    ]


def test_mygov_individual_organisation_website_uses_metadata_label():
    soup = BeautifulSoup('<main><header><dl><dt>Web</dt><dd><a href="https://scrp.scot/">scrp.scot/</a></dd>'
                         '<dt>Social</dt><dd><a href="https://other.example/">other.example/</a></dd></dl></header></main>',
                         "html.parser")
    assert audit.independent_sites(soup, "https://www.mygov.scot/organisations/school-closure-review-panels",
                                    "Convener of School Closure Review Panels", False) == ["https://scrp.scot/"]


def test_own_site_generic_partner_website_is_not_new_agency_identity():
    soup = BeautifulSoup('<a href="https://partner.example/">Visit website</a>', "html.parser")
    assert audit.independent_sites(soup, "https://official.example/", "Official Agency", False) == []


def test_news_navigation_precedes_incidental_media_articles():
    soup = BeautifulSoup('<a href="/social-media">Food on social media</a>'
                         '<a href="/media-guide">Media guide</a>'
                         '<a href="/publications">Publications</a>'
                         '<a href="/about-us/newsroom">Newsroom</a>'
                         '<a href="/News/index.htm">News</a>', "html.parser")
    urls = audit.news_pages(soup, "https://official.example/")
    assert urls[:2] == ["https://official.example/about-us/newsroom", "https://official.example/News/index.htm"]


def test_catalog_html_filters_dates_foreign_links_and_index_metadata():
    agency = Agency("官方機關", "Official Agency", "test", "https://official.example/")
    items = parse_news_index(HTML, agency, "https://official.example/news", SINCE, UNTIL)
    assert [(x.link, x.content_type) for x in items] == [
        ("https://official.example/news/digital-policy", "publication"),
        ("https://official.example/reports/ai", "report"),
    ]


def test_reviewed_govuk_feed_uses_feed_and_filters_untrusted_and_future_records(monkeypatch):
    agency = Agency("官方機關", "Official Agency", "govuk:test", "https://official.example/",
                    feeds=("https://official.example/feed/",))
    feed = feedparser.parse('''<rss version="2.0"><channel><title>Official</title>
      <item><title>Published policy update</title><link>https://official.example/news</link>
      <pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item>
      <item><title>Foreign policy update</title><link>https://unrelated.example/news</link>
      <pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate></item>
      <item><title>Future policy update</title><link>https://official.example/future</link>
      <pubDate>Sat, 26 Sep 2026 00:00:00 GMT</pubDate></item>
      </channel></rss>''')
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.catalog_adapter", lambda _: "feed")
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.parse_feed", lambda _: feed)
    scraper = AgencyFeedScraper(agency, UNTIL)
    assert [x.link for x in scraper.fetch(SINCE)] == ["https://official.example/news"]
    assert any("期間可能不完整" in x for x in scraper.source_warnings)


def test_html_source_does_not_discover_unreviewed_sitewide_rss(monkeypatch):
    agency = Agency("官方機關", "Official Agency", "govuk:test", "https://official.example/",
                    news_pages=("https://official.example/news",))
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.catalog_adapter", lambda _: "html_news")
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_text", lambda _: HTML)
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.get_json",
                        lambda _: pytest.fail("HTML source incorrectly routed to GOV.UK Search"))
    monkeypatch.setattr("UK_news_scraper.scrapers.ministry.registry.discover_feed_urls",
                        lambda _: pytest.fail("Unreviewed RSS discovery"))
    assert len(AgencyFeedScraper(agency, UNTIL).fetch(SINCE)) == 2


def test_empty_or_invalid_feed_is_not_promoted():
    evidence = deepcopy(review()["verification"])
    assert audit.verify_feed(entry(), "https://official.example/", "https://official.example/feed",
                             evidence, b"<html><title>News</title></html>") is None


def test_default_wordpress_post_does_not_validate_publication_channel():
    xml = b'''<rss version="2.0"><channel><title>Official Test Agency</title>
      <item><title>Hello world!</title><link>https://official.example/?p=1</link>
      <pubDate>Mon, 13 Dec 2021 22:58:04 GMT</pubDate>
      <description>Welcome to WordPress. This is your first post.</description></item>
      </channel></rss>'''
    assert audit.verify_feed(entry(), "https://official.example/", "https://official.example/feed",
                             deepcopy(review()["verification"]), xml) is None


def test_fresh_audit_rechecks_reviewed_searchable_sources_with_authority():
    source = {**entry(), "status": "searchable", "review_status": "verified",
              "homepage": "https://official.example/", "authority_url": "https://www.gov.uk/test"}
    original = deepcopy(source)
    existing = {**entry(), "id": "govuk:existing", "status": "searchable"}
    targets = audit.audit_targets([source, existing, entry()])
    assert [x["id"] for x in targets] == [source["id"], entry()["id"]]
    assert targets[0]["homepage"] == source["authority_url"]
    assert source == original


def test_http_or_foreign_feed_cannot_bypass_review_gate():
    for field, url in (("homepage", "http://official.example/"),
                       ("endpoint", "http://official.example/feed/"),
                       ("endpoint", "https://unrelated.example/feed/")):
        checked = review()
        checked[field] = url
        with pytest.raises(ValueError):
            apply_overrides([entry()], [checked])


@pytest.mark.parametrize("adapter", ["feed", "html_news"])
def test_http_discovery_adopts_only_successfully_fetched_https(adapter):
    source = {**entry(), "id": "ni:test", "homepage": "http://official.example/"}
    xml = b'''<rss version="2.0"><channel><title>Official Test Agency</title>
      <item><title>Health update</title><link>https://official.example/news/health</link>
      <pubDate>25 September 2026</pubDate></item></channel></rss>'''

    class Store:
        def get(self, url):
            assert url.startswith("https://")
            if url.endswith("/feed"):
                body = xml
            elif url.endswith("/news"):
                body = HTML.encode()
            else:
                body = (b'<link type="application/rss+xml" href="http://official.example/feed">'
                        if adapter == "feed" else b'<a href="http://official.example/news">News</a>')
            return {"url": url, "http_status": 200, "final_url": url}, body

    result = audit.audit_entry(source, Store(), set())
    assert result["outcome"] == "verified"
    assert result["review"]["homepage"] == "https://official.example/"
    assert result["review"]["endpoint"] == "https://official.example/" + ("feed" if adapter == "feed" else "news")


def test_reviewed_holds_preserve_specific_reason_and_do_not_enable_source():
    source = apply_overrides([entry()], [review()])[0]
    hold = {"id": source["id"], "outcome": "parser_verification_failed", "reason": "解析結果不一致",
            "checked_at": "2026-09-30T01:00:00+00:00"}
    result = apply_assessments([source], [hold])[0]
    assert result["status"] == "directory_only"
    assert result["adapter"] == ""
    assert result["reason"] == "解析結果不一致"
    assert "verification" not in result


def test_welsh_organisation_index_scope_excludes_unfiltered_global_news():
    assert audit.scoped_welsh_index("https://www.gov.wales/node/5256/latest-external-org-content")
    assert audit.scoped_welsh_index("https://www.gov.wales/publications?field_external_organisations%5B5256%5D=5256")
    assert not audit.scoped_welsh_index("https://www.gov.wales/news")


def test_welsh_scope_requires_selected_identity_not_any_visible_org_name():
    source = {**entry(), "name_en": "Target Body"}
    homepage = "https://www.gov.wales/target-body"
    endpoint = "https://www.gov.wales/publications?field_external_organisations%5B123%5D=123"
    soup = BeautifulSoup('<label><input name="field_external_organisations[123]" value="123" checked>'
                         'Other Body</label><label><input name="field_external_organisations[456]" value="456">'
                         'Target Body</label>', "html.parser")
    assert audit.welsh_scope_proof(source, homepage, endpoint, soup) is None
    soup = BeautifulSoup('<nav class="breadcrumb"><a href="/other-body">Target Body</a></nav>', "html.parser")
    assert audit.welsh_scope_proof(source, homepage, "https://www.gov.wales/node/123/latest-external-org-content",
                                  soup) is None
    soup = BeautifulSoup('<nav class="breadcrumb"><a href="/target-body">Target Body</a></nav>', "html.parser")
    assert audit.welsh_scope_proof(source, homepage, "https://www.gov.wales/node/123/latest-external-org-content",
                                  soup)["scope_verified"]


def test_supreme_court_dated_news_does_not_count_rolling_judgment_collection():
    html = '''<a href="/news/latest-judgments"><div>22 September 2026</div>
      <div class="line-clamp-2">Latest judgments</div></a>
      <a href="/news/practice-note"><div>Practice notes • 25 September 2026</div>
      <div class="line-clamp-2">Updated court practice note</div></a>'''
    agency = Agency("最高法院", "United Kingdom Supreme Court", "court-ew:united-kingdom-supreme-court",
                    "https://www.supremecourt.uk/")
    result = parse_news_index(html, agency, "https://www.supremecourt.uk/news", SINCE, UNTIL)
    assert [item.link for item in result] == ["https://www.supremecourt.uk/news/practice-note"]


def test_related_publishers_do_not_assign_a_parents_entire_feed_to_a_child():
    body = {"id": "govuk:research-england", "name_en": "Research England"}
    assert not audit.feed_is_attributable(body, "https://www.ukri.org/", "https://www.ukri.org/news/feed/",
                                         {"feed": {"title": "UKRI News"}})


def test_root_index_redirect_preserves_root_scope_without_broadening_subsidiary():
    assert audit.publication_scope("https://official.example/", "https://official.example/index.htm") == (
        "https://official.example/"
    )
    assert audit.publication_scope("https://official.example/body/", "https://official.example/body/index.htm") == (
        "https://official.example/body/index.htm"
    )
    assert audit.publication_scope("https://old.example/", "https://parent.example/child/") == (
        "https://parent.example/child/"
    )


def test_single_directory_record_is_still_shared_when_homepage_is_its_provenance():
    source = {**entry(), "id": "scotland:committee", "name_en": "Specific Committee",
              "homepage": "https://directory.example/bodies", "provenance": "https://directory.example/bodies"}

    class Store:
        def get(self, url):
            return {"url": url, "http_status": 200, "final_url": url}, (
                b'<h3>Other Committee</h3><a href="https://other.example/">Website</a>'
            )

    result = audit.audit_entry(source, Store(), set())
    assert result["outcome"] == "no_verified_endpoint"
    assert len(result["requests"]) == 1


def test_name_crosswalk_keeps_separate_education_departments_distinct():
    assert audit.normalized("Department of Education") != audit.normalized("Department for Education")


def test_plain_feed_title_preserves_ampersand():
    agency = Agency("官方機關", "Official", "test", "https://official.example/")
    xml = '''<rss version="2.0"><channel><title>Official</title><link>https://official.example/</link>
      <description>News</description><item><title>Health in D&#038;G</title>
      <link>https://official.example/news/health</link><pubDate>25 September 2026</pubDate></item>
      </channel></rss>'''
    entry = feedparser.parse(xml).entries[0]
    item = AgencyFeedScraper(agency, UNTIL)._entry_to_news_item(entry, agency.homepage, SINCE)
    assert item is not None
    assert item.title == "Health in D&G"
    assert item.published_at == datetime(2026, 9, 25, tzinfo=UTC)


def test_unpadded_minute_precision_official_datetime():
    assert index_date("2025-12-4T10:36Z") == datetime(2025, 12, 4, 10, 36, tzinfo=UTC)
    assert index_date("2025-02-31T10:36Z") is None
