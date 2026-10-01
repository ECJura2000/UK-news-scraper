"""Conservative, dated HTML news cards shared by audit and production."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Agency, NewsItem
from .scrapers.ministry.utils.text import clean_text

INDEX_RULES = {
    "cvsni.org": ("article", "a.no-underline[href]", "h2", "p.italic"),
    "publichealth.hscni.net": (".node--type-news", "h3 a[href]", "h3 a[href]", ".node--type-news > p strong"),
    "stmarys-belfast.ac.uk": ("a.news-item", ":self", "h4", ".text-pale-sky"),
    "ukri.org": (".category-research-england", "a[href]", ".entry-title", ".post-summary__date"),
    "audit.scot": (".ac-latest-news > div", "h3 a[href]", "h3 a[href]", "time"),
    "portonbiopharma.com": ("a.post-item-inner", ":self", "h3", ".post-date"),
    "prosecutioninspectorate.scot": (".news-landing", "h2 a[href]", "h2 a[href]", ".article-date"),
    "hmfsi.scot": (".publication-list-item", "h2 a[href]", "h2 a[href]", ".meta-date"),
    "hmics.scot": (".article-landing-list-item", "h2 a[href]", "h2 a[href]", ".meta-date"),
    "oscr.org.uk": (".news-item", "a[href]", "h3", ".date"),
    "fuelpovertypanel.scot": ("li.ds_category-item", "h3 a[href]", "h3 a[href]", ".publishedDate"),
    "qmscotland.co.uk": (".featured-article", "a[href]", "h2", ".date"),
    "ombudsman.wales": (".newslist-item", "a.newslist-item-link", "a.newslist-item-link", ".newslist-item-date"),
    "uksbs.co.uk": (".card", ".content a[href]", ".content h3", "p.article-date"),
    "consumer.scot": ("article", "a.news-item__link", ".news-item__title", ".news-item__link-date"),
    "crownestatescotland.com": (
        ".views-view-responsive-grid__item", "a[href]", "a[href]", ".views-field-localgov-news-date"
    ),
    "nhshighland.scot.nhs.uk": (".featured-article, .article", "a[href]", ".article__title", ".article__detail"),
    "pirc.scot": (".publication-item", "a.publication-item--heading", "h3", ".publication-item--date"),
    "scottishcanals.co.uk": (".entry-card", "h2 a[href]", "h2 a[href]", "dd.entry-card-meta-value"),
    "housingregulator.gov.scot": ("a.signpost--news", ":self", "h2", ".signpost__date"),
    "southofscotlandenterprise.com": (".items .item", "a[href]", "h3", "a > p"),
    "foi.scot": (".intro_desc > p", "a[href]", "a[href]", ":prefix"),
}


def content_type_for_link(link: str, title: str = "", context: str = "") -> str:
    value = " ".join((link, title, context)).casefold()
    path = urlparse(link).path.casefold()
    if "/judgment" in path or "/judicial-decision" in path:
        return "judgment"
    if "/guidance/" in path or "/collection/" in path or "guidance" in value:
        return "guidance"
    if "/report" in path or "/research/" in path or "report" in value or "research" in value:
        return "report"
    if "/publication" in path or "/consultation" in path or "publication" in value or "consultation" in value:
        return "publication"
    return "news"


def index_date(text: str) -> datetime | None:
    value = text.strip()
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\bSept\b", "Sep", value)
    value = re.sub(r"^(\d{1,2})(?:st|nd|rd|th)(?=\s)", r"\1", value)
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(T.*)", value)
    if match:
        year, month, day, suffix = match.groups()
        value = f"{year}-{int(month):02d}-{int(day):02d}{suffix}"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        pass
    for pattern in (
        "%d %B %Y", "%B %d, %Y", "%d %b %Y", "%d %b, %Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M"
    ):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def parse_news_index(
    html: str, agency: Agency, page_url: str, since: datetime, until: datetime | None
) -> list[NewsItem]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    base_host = urlparse(page_url).hostname
    cards = soup.select(
        "article, li, .search-result, .card, .views-row, .news-listing, "
        ".newsResult__item, .news-list__item, a.list__item, a.homepage-panel-link, "
        ".news-result, .card-body, .featuredItemContent, .contentContainer"
    )
    host = (base_host or "").removeprefix("www.")
    rule = INDEX_RULES.get(host)
    restricted_indexes = {
        "cvsni.org": "/news", "publichealth.hscni.net": "/news", "stmarys-belfast.ac.uk": "/about-us/news",
    }
    if host in restricted_indexes and urlparse(page_url).path.rstrip("/") != restricted_indexes[host]:
        return []
    if host == "ukri.org" and urlparse(page_url).path.rstrip("/") != "/councils/research-england/news":
        return []
    if host == "audit.scot" and urlparse(page_url).path.rstrip("/") != "/accounts-commission":
        rule = None
    rule_cards = set()
    if rule:
        selected = soup.select(rule[0])
        rule_cards = {id(card) for card in selected}
        if host == "ukri.org":
            # The shared publisher can show other councils in related cards.
            # This council index only admits its explicit category marker.
            cards = selected
        else:
            cards.extend(selected)
    if host == "slab.org.uk":
        cards.extend(parent for anchor in soup.select("a.page-listing-link[href]")
                     if isinstance(parent := anchor.parent, Tag))
    if host == "mwcscot.org.uk":
        cards.extend(soup.select(".sp-content"))
    if host == "foodstandards.gov.scot":
        cards.extend(soup.select("a.grid-card[href]"))
    for card in cards:
        anchor = next((node for selector in (
            "h2 a[href]", "h3 a[href]", "h4 a[href]", ".views-field-title a[href]", "a[href]"
        ) if (node := card.select_one(selector)) is not None), None)
        title_node = anchor
        matched_rule = rule is not None and id(card) in rule_cards
        if matched_rule and rule is not None:
            anchor = card if rule[1] == ":self" else card.select_one(rule[1])
            title_node = card.select_one(rule[2])
        structured_anchor = card.select_one(
            "a.stretched-link[href], a.card-link[href], a.newsResult__cta[href], a.link--cover[href], a.cover[href]"
        )
        structured_title = card.select_one(
            ".card-title, .newsResult__itemTitle, .news-list__title, .card-main h3.title"
        )
        if matched_rule:
            pass
        elif structured_anchor is not None and structured_title is not None:
            anchor, title_node = structured_anchor, structured_title
        elif card.name == "a":
            anchor, title_node = card, card.select_one("h2, h3")
        elif "contentContainer" in (card.get("class") or ()):
            title_node = card.select_one("h2")
        elif host == "slab.org.uk" and (slab_link := card.select_one("a.page-listing-link[href]")) is not None:
            anchor, title_node = slab_link, card.select_one("h2")
        elif host == "mwcscot.org.uk" and "sp-content" in (card.get("class") or ()):
            anchor, title_node = card.select_one("a.slink[href]"), card.select_one("h3")
        time = card.select_one("time")
        date_text = ""
        if matched_rule and rule is not None:
            if rule[3] == ":prefix":
                date_text = card.get_text(" ", strip=True).split(" - ", 1)[0]
            else:
                for date_node in card.select(rule[3]):
                    candidate = date_node.get_text(" ", strip=True)
                    if host == "ukri.org":
                        candidate = re.sub(r"^Pinned\s+article from\s+", "", candidate)
                    if index_date(candidate):
                        date_text = candidate
                        break
        elif time is not None:
            date_text = str(time.get("datetime", "")) or time.get_text(" ", strip=True)
        else:
            semantic_date = card.select_one('span[property="dc:date"][content]')
            if semantic_date is not None:
                date_text = str(semantic_date.get("content", ""))
            for label in card.select("dl.ds_metadata dt"):
                value = label.find_next_sibling("dd")
                if label.get_text(" ", strip=True).casefold() == "date" and value is not None:
                    date_text = value.get_text(" ", strip=True)
                    break
            if not date_text:
                values = card.select(
                    ".ds_news-item__meta p, .PubDate p, .card-text small, .newsResult__date, "
                    ".post-meta .published, .news-list__date, .listing-item p, "
                    ".updated, .homepage-panel-footer small, .news-result p.date, "
                    ".card-body p.article-date, .featuredItemContent span.date, "
                    ".card-meta p.date, .contentContainer p.date, p.pub-date"
                )
                if host == "slab.org.uk":
                    values.extend(card.select("p.date-display"))
                if host == "mwcscot.org.uk":
                    values.extend(card.select("p.meek"))
                if host == "foodstandards.gov.scot":
                    values.extend(card.select(".grid-card-info date"))
                if values:
                    for value in reversed(values):
                        raw = value.get_text(" ", strip=True)
                        if "updated" in (value.get("class") or ()) and not raw.startswith("Published:"):
                            continue
                        candidate = re.sub(r"^Published:\s*", "", raw)
                        if index_date(candidate):
                            date_text = candidate
                            break
        if anchor is None or title_node is None or not date_text:
            continue
        title = clean_text(title_node.get_text(" ", strip=True))
        link = urljoin(page_url, str(anchor.get("href", "")))
        published = index_date(date_text)
        if (
            len(title) < 12 or not published or published < since or (until is not None and published >= until)
            or urlparse(link).hostname != base_host or urlparse(link).path.lower().endswith(".pdf")
            or link == page_url or link in seen
        ):
            continue
        seen.add(link)
        items.append(NewsItem(
            agency=agency.display_name, agency_en=agency.name_en, unit_category=agency.short_name,
            title=title, link=link, published_at=published, source_feed=page_url,
            content_type=content_type_for_link(link, title, card.get_text(" ", strip=True)),
        ))
    if host == "nhstayside.scot.nhs.uk":
        for intro in soup.select(".news-short-article > .news-short-article-intro"):
            sibling_date = intro.find_previous_sibling()
            anchor = intro.select_one("a[href]")
            if (anchor is None or sibling_date is None
                or "news-short-article-date" not in (sibling_date.get("class") or ())):
                continue
            published = index_date(sibling_date.get_text(" ", strip=True))
            title = clean_text(anchor.get_text(" ", strip=True))
            link = urljoin(page_url, str(anchor.get("href", "")))
            if (len(title) < 12 or published is None or published < since
                or (until is not None and published >= until) or urlparse(link).hostname != base_host
                or urlparse(link).path.lower().endswith(".pdf") or link in seen):
                continue
            seen.add(link)
            summary_node = intro.find_next_sibling()
            summary = clean_text(summary_node.get_text(" ", strip=True)) if (
                summary_node is not None and "news-short-article-text" in (summary_node.get("class") or ())
            ) else ""
            items.append(NewsItem(
                agency=agency.display_name, agency_en=agency.name_en, unit_category=agency.short_name,
                title=title, link=link, published_at=published, source_feed=page_url, summary=summary,
                content_type=content_type_for_link(link, title, summary),
            ))
    if (urlparse(page_url).hostname or "").removeprefix("www.") == "supremecourt.uk":
        for anchor in soup.select('a[href^="/news/"]'):
            link = urljoin(page_url, str(anchor.get("href", "")))
            heading = anchor.select_one('[class*="line-clamp-2"]')
            date = re.search(r"\b\d{1,2} [A-Za-z]+ \d{4}\b", anchor.get_text(" ", strip=True))
            if heading is None or date is None or urlparse(link).path == "/news/latest-judgments":
                continue
            title = clean_text(heading.get_text(" ", strip=True))
            published = index_date(date.group())
            if (len(title) < 12 or not published or published < since
                or (until is not None and published >= until) or link in seen):
                continue
            seen.add(link)
            items.append(NewsItem(
                agency=agency.display_name, agency_en=agency.name_en, unit_category=agency.short_name,
                title=title, link=link, published_at=published, source_feed=page_url,
                content_type=content_type_for_link(link, title, anchor.get_text(" ", strip=True)),
            ))
    return items
