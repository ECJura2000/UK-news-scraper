from datetime import UTC, datetime
from pathlib import Path

import feedparser
import pytest

from UK_news_scraper.catalog_html import content_type_for_link, index_date, parse_news_index
from UK_news_scraper.models import Agency
from UK_news_scraper.scrapers.ministry import registry

SINCE = datetime(2026, 9, 20, tzinfo=UTC)
UNTIL = datetime(2026, 9, 30, tzinfo=UTC)
AGENCY = Agency("官方機關", "Official Agency", "catalog:test", "https://official.example/",
                news_pages=("https://official.example/news",))


def test_explicit_card_dates_and_title_links_preserve_attribution():
    body = (Path(__file__).parent / "fixtures/catalog_explicit_dates.html").read_text()
    items = parse_news_index(body, AGENCY, AGENCY.news_pages[0], SINCE, UNTIL)
    assert len(items) == 16
    assert {item.link.rsplit("/", 1)[1] for item in items} == {
        "metadata", "meta", "environment", "views", "listing", "semantic",
        "cover", "skills", "divi", "health", "transport", "grampian", "ordinal", "standards", "water", "ambulance"
    }
    assert next(item for item in items if item.link.endswith("semantic")).published_at == (
        datetime(2026, 9, 29, 11, tzinfo=UTC)
    )


def test_historical_query_reports_missing_coverage_without_false_layout_failure(monkeypatch):
    monkeypatch.setattr(registry, "catalog_adapter", lambda _: "html_news")
    monkeypatch.setattr(registry, "get_text", lambda _: (
        '<article><h3><a href="/news/recent">Official recent policy announcement</a></h3>'
        '<time datetime="2026-09-25"></time></article>'
    ))
    scraper = registry.AgencyFeedScraper(AGENCY, datetime(2026, 2, 1, tzinfo=UTC))
    assert scraper.fetch(datetime(2026, 1, 1, tzinfo=UTC)) == []
    assert len(scraper.source_warnings) == 1
    assert "期間可能不完整" in scraper.source_warnings[0]


@pytest.mark.parametrize("kind,expected", [
    ("text", "Official <news> announcement & guidance"),
    ("html", "Official announcement & guidance"),
])
def test_atom_title_content_type_preserves_literal_text(kind, expected):
    xml = f'''<feed xmlns="http://www.w3.org/2005/Atom"><id>f</id><title>Official</title>
      <updated>2026-09-25T00:00:00Z</updated><entry><id>one</id>
      <title type="{kind}">Official &lt;news&gt; announcement &amp; guidance</title>
      <link href="https://official.example/news/one"/><updated>2026-09-25T00:00:00Z</updated>
      </entry></feed>'''
    entry = feedparser.parse(xml).entries[0]
    item = registry.AgencyFeedScraper(AGENCY, UNTIL)._entry_to_news_item(entry, "feed", SINCE)
    assert item.title == expected


@pytest.mark.parametrize("host,expected", [
    ("www.slab.org.uk", "legal-aid"), ("www.mwcscot.org.uk", "mental-health"),
    ("www.foodstandards.gov.scot", "food-safety")
])
def test_host_specific_publication_fields_do_not_apply_to_unrelated_sites(host, expected):
    body = (Path(__file__).parent / "fixtures/catalog_host_dates.html").read_text()
    agency = Agency("Official", "Official", "catalog:test", f"https://{host}/")
    items = parse_news_index(body, agency, f"https://{host}/news", datetime(2026, 9, 1, tzinfo=UTC), UNTIL)
    assert [item.link for item in items] == [f"https://{host}/news/{expected}"]
    assert not parse_news_index(body, AGENCY, AGENCY.news_pages[0], SINCE, UNTIL)


def test_feed_content_supplies_missing_summary_but_preserves_explicit_summary():
    body = (Path(__file__).parent / "fixtures/catalog_content_feed.xml").read_bytes()
    entries = feedparser.parse(body).entries
    scraper = registry.AgencyFeedScraper(AGENCY, UNTIL)
    summaries = [scraper._entry_to_news_item(entry, "feed", SINCE).summary for entry in entries]
    assert summaries == ["The Board's official update is published.", "Short official summary"]


def test_tayside_sibling_dates_and_summaries_are_bound_to_each_headline():
    body = (Path(__file__).parent / "fixtures/catalog_tayside.html").read_text()
    page = "https://www.nhstayside.scot.nhs.uk/News/index.htm"
    agency = Agency("Official", "Official", "catalog:test", page)
    items = parse_news_index(body, agency, page, SINCE, UNTIL)
    assert [(item.published_at.day, item.summary) for item in items] == [
        (25, "First summary"), (24, "Second summary with reference to 11 September 2026")
    ]
    assert not parse_news_index(body, AGENCY, AGENCY.news_pages[0], SINCE, UNTIL)


@pytest.mark.parametrize("host,expected,day", [
    ("www.ombudsman.wales", "ombudsman", 29),
    ("www.uksbs.co.uk", "business", 28),
    ("www.oscr.org.uk", "charity", 29),
    ("www.foi.scot", "foi", 25),
    ("www.pirc.scot", "pirc", 26),
])
def test_reviewed_index_fields_bind_date_and_headline_to_the_same_card(host, expected, day):
    body = (Path(__file__).parent / "fixtures/catalog_reviewed_indexes.html").read_text()
    page = f"https://{host}/news"
    agency = Agency("Official", "Official", "catalog:test", page)
    items = parse_news_index(body, agency, page, SINCE, UNTIL)
    assert [(item.link.rsplit("/", 1)[1], item.published_at.day) for item in items] == [(expected, day)]


@pytest.mark.parametrize("host,path,expected", [
    ("www.ukri.org", "/councils/research-england/news/", "research-england"),
    ("audit.scot", "/accounts-commission", "accounts"),
])
def test_shared_publisher_rules_require_an_explicit_body_scoped_index(host, path, expected):
    body = (Path(__file__).parent / "fixtures/catalog_reviewed_indexes.html").read_text()
    page = f"https://{host}{path}"
    agency = Agency("Official", "Official", "catalog:test", page)
    items = parse_news_index(body, agency, page, SINCE, UNTIL)
    assert [item.link.rsplit("/", 1)[1] for item in items] == [expected]
    unrelated = parse_news_index(body, agency, f"https://{host}/news/", SINCE, UNTIL)
    assert not unrelated


@pytest.mark.parametrize("host,path,expected,day", [
    ("www.cvsni.org", "/news/", "victims", 18),
    ("www.publichealth.hscni.net", "/news", "health", 25),
    ("www.stmarys-belfast.ac.uk", "/about-us/news/", "university", 29),
])
def test_ni_indexes_require_explicit_year_and_exclude_detail_related_cards(host, path, expected, day):
    body = (Path(__file__).parent / "fixtures/catalog_ni_indexes.html").read_text()
    page = f"https://{host}{path}"
    agency = Agency("Official", "Official", "catalog:test", page)
    items = parse_news_index(body, agency, page, datetime(2026, 9, 1, tzinfo=UTC), UNTIL)
    assert [(item.link.rsplit("/", 1)[1], item.published_at.day) for item in items] == [(expected, day)]
    assert not parse_news_index(body, agency, f"https://{host}/news/detail", SINCE, UNTIL)


@pytest.mark.parametrize("value,expected", [
    ("Tue, 29 Sep 2026 10:00:00 +0200", datetime(2026, 9, 29, 8, tzinfo=UTC)),
    ("Tue, 29 Sep 2026 10:00:00", datetime(2026, 9, 29, 10, tzinfo=UTC)),
    ("29 September", None),
    ("31 September 2026", None),
])
def test_index_dates_use_explicit_year_and_normalize_timezone_without_guessing(value, expected):
    assert index_date(value) == expected


@pytest.mark.parametrize("path", ["judgments/official-case", "judicial-decision/official-case"])
def test_catalog_court_publications_retain_judgment_type(path):
    assert content_type_for_link(f"https://official.example/{path}") == "judgment"


def test_supreme_court_news_cards_filter_period_duplicate_and_rolling_collection():
    page = "https://supremecourt.uk/news"
    agency = Agency("Official", "Official", "catalog:test", page)
    body = '''
      <a href="/news/announcement"><div class="line-clamp-2">Supreme Court official announcement</div>
        <p>29 September 2026</p></a>
      <a href="/news/announcement"><div class="line-clamp-2">Duplicate official announcement</div>
        <p>29 September 2026</p></a>
      <a href="/news/future"><div class="line-clamp-2">Announcement after requested period</div>
        <p>30 September 2026</p></a>
      <a href="/news/old"><div class="line-clamp-2">Announcement before requested period</div>
        <p>19 September 2026</p></a>
      <a href="/news/invalid"><div class="line-clamp-2">Announcement with invalid date field</div>
        <p>31 September 2026</p></a>
      <a href="/news/latest-judgments"><div class="line-clamp-2">Rolling latest judgments collection</div>
        <p>29 September 2026</p></a>
    '''
    items = parse_news_index(body, agency, page, SINCE, UNTIL)
    assert [(item.link, item.title) for item in items] == [
        ("https://supremecourt.uk/news/announcement", "Supreme Court official announcement")
    ]
