"""Official source adapters preserve partial data and source-specific fallbacks."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from UK_news_scraper.errors import DownloadError
from UK_news_scraper.models import Agency, NewsItem
from UK_news_scraper.scrapers.ministry import registry

SINCE = datetime(2026, 9, 14, tzinfo=UTC)


def _agency(short_name="Test", **overrides):
    values = dict(
        name_zh="測試機關",
        name_en="Official Test Agency",
        short_name=short_name,
        homepage="https://official.example/",
        feeds=(),
        news_pages=(),
        official_pages=(),
    )
    values.update(overrides)
    return Agency(**values)


def _entry(title="Official digital policy announcement", link="https://official.example/news/one"):
    return SimpleNamespace(title=title, link=link, published="2026-09-20T00:00:00Z", summary="Digital policy update")


def _item(short_name="Test"):
    return NewsItem(
        "Agency",
        "Agency",
        short_name,
        "Official digital policy announcement",
        "https://official.example/news/one",
        SINCE,
    )


def test_feed_failure_keeps_official_html_and_warning(monkeypatch):
    agency = _agency(
        feeds=("https://official.example/feed",),
        news_pages=("https://official.example/news",),
        official_pages=("https://official.example/guidance/one",),
    )
    scraper = registry.AgencyFeedScraper(agency)
    monkeypatch.setattr(registry, "discover_feed_urls", lambda _url: [])
    monkeypatch.setattr(registry, "parse_feed", lambda _url: (_ for _ in ()).throw(OSError("feed offline")))
    pages = {
        "https://official.example/news": (
            "<article><h2><a href='/news/one'>Official digital policy announcement</a></h2>"
            "<time datetime='2026-09-20'></time></article>"
        ),
        "https://official.example/guidance/one": (
            "<h1>New official digital guidance published</h1><time datetime='2026-09-20'></time><p>Guidance summary</p>"
        ),
    }
    monkeypatch.setattr(registry, "get_text", pages.__getitem__)

    items = scraper.fetch(SINCE)

    assert {item.content_type for item in items} == {"news", "guidance"}
    assert scraper.source_warnings and "RSS/Atom" in scraper.source_warnings[0]
    assert all(item.link.startswith("https://official.example/") for item in items)


def test_feed_filters_old_external_and_duplicate_entries(monkeypatch):
    agency = _agency(
        feeds=("https://official.example/feed",),
        link_include_patterns=("/government/news/",),
    )
    scraper = registry.AgencyFeedScraper(agency)
    old = SimpleNamespace(
        title="Older policy", link="https://official.example/government/news/old", published="2026-09-01"
    )
    external = _entry(link="https://external.example/story")
    current = _entry(link="https://official.example/government/news/one")
    monkeypatch.setattr(registry, "parse_feed", lambda _url: SimpleNamespace(entries=[old, external, current, current]))

    items = scraper.fetch(SINCE)
    assert len(items) == 1
    assert items[0].content_type == "news"


def test_all_failed_sources_raise_without_hiding_source_error(monkeypatch):
    scraper = registry.AgencyFeedScraper(_agency(feeds=("https://official.example/feed",)))
    monkeypatch.setattr(registry, "parse_feed", lambda _url: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(DownloadError, match="所有來源"):
        scraper.fetch(SINCE)


def test_npsa_ordered_fallback_uses_search_only_after_official_and_html_fail(monkeypatch):
    scraper = registry.AgencyFeedScraper(
        _agency(
            "NPSA", official_pages=("https://official.example/blog",), news_pages=("https://official.example/news",)
        )
    )
    steps = []
    monkeypatch.setattr(scraper, "_fetch_official_pages", lambda _since: (steps.append("official") or [], 1, 1))
    monkeypatch.setattr(scraper, "_fetch_html_news_pages", lambda _since: (steps.append("html") or [], 1, 1))
    monkeypatch.setattr(
        scraper, "_fetch_google_news_fallback", lambda _since: steps.append("fallback") or [_item("NPSA")]
    )
    assert scraper.fetch(SINCE)
    assert steps == ["official", "html", "fallback"]


@pytest.mark.parametrize(
    ("source", "html", "expected"),
    [
        (
            "Electoral Commission",
            "<article class='c-teaser'><a href='/news/one'>"
            "<span class='c-teaser__title'>Election digital services update</span></a>"
            "<time datetime='2026-09-20'></time><p class='c-teaser__desc'>New services</p></article>",
            "Election digital services update",
        ),
        (
            "NPSA",
            "<div class='views-row'><h2><a href='/blog/one'>Technology guidance updated</a></h2>"
            "<p>Blog publish date is 20/09/2026</p></div>",
            "Technology guidance updated",
        ),
        (
            "Ofcom",
            "<a href='/news/one'>Online platforms safety update Published: 20 September 2026</a>",
            "Online platforms safety update",
        ),
    ],
)
def test_source_specific_html_adapters_preserve_official_urls(source, html, expected):
    scraper = registry.AgencyFeedScraper(_agency(source))
    items = scraper._extract_html_news_items(BeautifulSoup(html, "html.parser"), "https://official.example/news", SINCE)
    assert items and expected in items[0].title
    assert items[0].link.startswith("https://official.example/")


def test_official_page_excludes_external_and_undated_links():
    scraper = registry.AgencyFeedScraper(_agency())
    html = """<section>
      <article><h2><a href='/guidance/one'>Digital safety guidance published</a></h2>
      <time datetime='2026-09-20'></time></article>
      <article><h2><a href='https://external.example/one'>External technology announcement</a></h2>
      <time datetime='2026-09-20'></time></article>
      <article><h2><a href='/guidance/old'>Undated policy announcement</a></h2></article>
    </section>"""
    items = scraper._extract_official_page_items(
        BeautifulSoup(html, "html.parser"), "https://official.example/news", SINCE
    )
    assert [item.link for item in items] == ["https://official.example/guidance/one"]


@pytest.mark.parametrize(
    "markup",
    [
        '<meta property="article:published_time" content="2026-09-20">',
        '<script type="application/ld+json">{"datePublished":"2026-09-20"}</script>',
        '<script type="application/ld+json">[{"dateCreated":"2026-09-20"}]</script>',
        "<p>Updated: 20 September 2026</p>",
    ],
)
def test_official_metadata_dates_accept_supported_formats(markup):
    assert registry._date_from_html(BeautifulSoup(markup, "html.parser")).date().isoformat() == "2026-09-20"


def test_official_metadata_skips_invalid_json_and_uses_description():
    markup = (
        '<script type="application/ld+json">{invalid</script>'
        '<script type="application/ld+json">[null,{"dateModified":"2026-09-20"}]</script>'
        '<meta name="description" content="Official digital policy summary">'
    )
    soup = BeautifulSoup(markup, "html.parser")
    assert registry._date_from_html(soup).date().isoformat() == "2026-09-20"
    assert registry._summary_from_html(soup) == "Official digital policy summary"
    assert registry._content_type_for_link("https://official.example/research/study") == "report"
    assert registry._content_type_for_link("https://official.example/publication/one") == "publication"


def test_google_news_fallback_filters_unrelated_election_titles(monkeypatch):
    scraper = registry.AgencyFeedScraper(_agency("Electoral Commission"))
    entries = [
        _entry("Search criteria - Electoral Commission", "https://news.google.com/rss/articles/criteria"),
        _entry("Election digital services update - Electoral Commission", "https://news.google.com/rss/articles/news"),
        _entry("Election digital services update - Electoral Commission", "https://news.google.com/rss/articles/news"),
    ]
    monkeypatch.setattr(registry, "parse_feed", lambda _url: SimpleNamespace(entries=entries))
    items = scraper._fetch_google_news_fallback(SINCE)
    assert len(items) == 1
    assert items[0].title == "Election digital services update"


def test_generic_page_read_error_isolated_from_healthy_official_page(monkeypatch):
    scraper = registry.AgencyFeedScraper(
        _agency(
            news_pages=("https://official.example/news",), official_pages=("https://official.example/guidance/one",)
        )
    )
    monkeypatch.setattr(registry, "discover_feed_urls", lambda _url: [])

    def get_page(url):
        if url.endswith("/news"):
            raise OSError("offline")
        return "<h1>Official digital guidance published</h1><time datetime='2026-09-20'></time>"

    monkeypatch.setattr(registry, "get_text", get_page)
    items = scraper.fetch(SINCE)
    assert len(items) == 1
    assert items[0].content_type == "guidance"
