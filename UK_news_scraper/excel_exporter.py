from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dedupe import dedupe_news_items, normalize_title
from .models import NewsItem, ParliamentBriefing
from .translation_cache import load_translations, save_translations


HEADERS = ("編號", "部會", "新聞日期", "單位分類", "新聞標題", "新聞連結")
MATCH_HEADERS = HEADERS + ("命中觀測領域", "命中關鍵字")
PARLIAMENT_HEADERS = (
    "資料日期",
    "國家",
    "機關",
    "院別",
    "資料來源類型",
    "發布單位",
    "主題分類",
    "文件類型",
    "標題",
    "摘要",
    "識別碼",
    "網頁連結",
    "PDF連結",
    "抓取來源",
)
PARLIAMENT_MATCH_HEADERS = PARLIAMENT_HEADERS + ("命中觀測領域", "命中關鍵字")
TITLE_COLUMN = 5
MATCH_FILL = PatternFill("solid", fgColor="FFFF00")
SECTION_FILL = PatternFill("solid", fgColor="BDD7EE")
DEFAULT_TRANSLATION_CONCURRENCY = 4


def export_news(
    all_items: list[NewsItem],
    filtered_items: list[NewsItem],
    output_path: str | Path,
    parliament_items: list[ParliamentBriefing] | None = None,
    filtered_parliament_items: list[ParliamentBriefing] | None = None,
) -> Path:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    title_translations = _translate_titles([*all_items, *filtered_items])
    parliament_items = parliament_items or []
    filtered_parliament_items = filtered_parliament_items or []
    parliament_translations = _translate_texts(
        [
            text
            for item in parliament_items
            for text in (item.title, item.summary)
            if text
        ],
        content_label="國會標題或摘要",
    )

    wb = Workbook()
    ws_all = wb.active
    ws_all.title = "全部新聞"
    _write_sheet(ws_all, all_items, include_matches=False, title_translations=title_translations)

    ws_filtered = wb.create_sheet("已初步篩選工作表")
    _write_filtered_sheet(
        ws_filtered,
        filtered_items,
        filtered_parliament_items,
        title_translations,
        parliament_translations,
    )

    ws_parliament = wb.create_sheet("國會研究資料")
    _write_parliament_sheet(ws_parliament, parliament_items, parliament_translations)

    _style_sheet(ws_all)
    _style_filtered_sheet(ws_filtered)
    _style_parliament_sheet(ws_parliament)

    temporary_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
    try:
        wb.save(temporary_path)
        verification_workbook = load_workbook(temporary_path, read_only=True, data_only=True)
        required_sheets = {"全部新聞", "已初步篩選工作表", "國會研究資料"}
        if not required_sheets.issubset(verification_workbook.sheetnames):
            raise RuntimeError("Excel 暫存檔缺少必要工作表")
        verification_workbook.close()
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def _write_parliament_sheet(
    ws,
    items: list[ParliamentBriefing],
    translations: dict[str, str],
    include_matches: bool = False,
) -> None:
    ws.append(PARLIAMENT_MATCH_HEADERS if include_matches else PARLIAMENT_HEADERS)
    for item in sorted(items, key=lambda briefing: (briefing.published_at, briefing.publisher), reverse=True):
        english_row_number = ws.max_row + 1
        row = [
            item.date_text,
            "United Kingdom",
            "UK Parliament",
            item.chamber,
            "Research Briefing",
            item.publisher,
            "、".join(item.topics),
            item.document_type,
            item.title,
            item.summary,
            item.identifier,
            item.webpage_url,
            item.pdf_url,
            item.fetched_from,
        ]
        if include_matches:
            row.extend(
                [
                    "、".join(item.matched_topics),
                    "、".join(item.matched_keywords),
                ]
            )
        ws.append(row)

        chinese_row_number = ws.max_row + 1
        translation_row = [""] * len(PARLIAMENT_HEADERS)
        translation_row[8] = translations.get(item.title, "")
        translation_row[9] = translations.get(item.summary, "")
        ws.append(translation_row)

        if item.matched_keywords:
            _fill_rows(ws, english_row_number, chinese_row_number, MATCH_FILL)

        merged_columns = [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14]
        if include_matches:
            merged_columns.extend((15, 16))
        for column in merged_columns:
            ws.merge_cells(
                start_row=english_row_number,
                start_column=column,
                end_row=chinese_row_number,
                end_column=column,
            )

        for column in (12, 13):
            cell = ws.cell(row=english_row_number, column=column)
            if cell.value:
                cell.hyperlink = cell.value
                cell.style = "Hyperlink"


def _style_parliament_sheet(ws) -> None:
    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = (14, 16, 18, 18, 20, 46, 36, 20, 56, 80, 18, 72, 72, 72)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (7, 9, 10, 14))
        if row[0].row % 2 == 1:
            for column in (9, 10):
                row[column - 1].font = Font(color="666666")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _write_filtered_sheet(
    ws,
    news_items: list[NewsItem],
    parliament_items: list[ParliamentBriefing],
    title_translations: dict[str, str],
    parliament_translations: dict[str, str],
) -> None:
    ws.append(["新聞稿"])
    _style_section_row(ws, ws.max_row)
    _write_sheet(
        ws,
        news_items,
        include_matches=True,
        title_translations=title_translations,
    )
    ws.append([])
    ws.append(["研究"])
    _style_section_row(ws, ws.max_row)
    _write_parliament_sheet(
        ws,
        parliament_items,
        parliament_translations,
        include_matches=True,
    )


def _style_filtered_sheet(ws) -> None:
    news_header_row = 2
    research_header_row = next(
        row[0].row + 1
        for row in ws.iter_rows()
        if row[0].value == "研究"
    )
    for row_number in (news_header_row, research_header_row):
        for cell in ws[row_number]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9EAF7")
            cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = (14, 38, 18, 24, 80, 72, 36, 60, 56, 80, 18, 72, 72, 72, 28, 60)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A3"


def _style_section_row(ws, row_number: int) -> None:
    cell = ws.cell(row=row_number, column=1)
    cell.font = Font(bold=True)
    cell.fill = SECTION_FILL


def _write_sheet(
    ws,
    items: list[NewsItem],
    include_matches: bool,
    title_translations: dict[str, str],
) -> None:
    ws.append(MATCH_HEADERS if include_matches else HEADERS)
    export_items = _dedupe_for_export(items)
    for index, item in enumerate(
        sorted(export_items, key=lambda news: (news.agency, news.published_at, news.title.casefold())),
        start=1,
    ):
        english_row_number = ws.max_row + 1
        row = [
            index,
            item.agency,
            item.date_text,
            item.unit_category,
            item.title,
            item.link,
        ]
        if include_matches:
            row.extend(
                [
                    "、".join(item.matched_topics),
                    "、".join(item.matched_keywords),
                ]
            )
        ws.append(row)

        chinese_row_number = ws.max_row + 1
        translation_row = [""] * ws.max_column
        translation_row[TITLE_COLUMN - 1] = title_translations.get(item.title, "")
        ws.append(translation_row)

        if item.matched_keywords:
            _fill_rows(ws, english_row_number, chinese_row_number, MATCH_FILL)

        for column in _merged_columns(include_matches):
            ws.merge_cells(
                start_row=english_row_number,
                start_column=column,
                end_row=chinese_row_number,
                end_column=column,
            )

        link_cell = ws.cell(row=english_row_number, column=6)
        if item.link:
            link_cell.hyperlink = item.link
            link_cell.style = "Hyperlink"


def _translate_titles(items: list[NewsItem]) -> dict[str, str]:
    unique_titles = list(dict.fromkeys(item.title for item in items if item.title))
    return _translate_texts(unique_titles, content_label="新聞標題")


def _translate_texts(texts: list[str], content_label: str) -> dict[str, str]:
    unique_titles = list(dict.fromkeys(text for text in texts if text))
    if not unique_titles:
        return {}

    cached = load_translations()
    translations = {
        title: cached[title]
        for title in unique_titles
        if cached.get(title)
    }
    missing = [title for title in unique_titles if title not in translations]
    if not missing:
        return translations

    translated = _translate_uncached_texts(missing, content_label)
    translations.update(translated)
    save_translations(translated)
    return translations


def _translate_uncached_texts(unique_titles: list[str], content_label: str) -> dict[str, str]:
    try:
        from googletrans import Translator
    except ImportError:
        print(f"[warn] 尚未安裝 googletrans，將改用 deep-translator 作為{content_label}翻譯備援。")
        return _translate_titles_with_deep_translator(unique_titles)

    return asyncio.run(_translate_titles_async(unique_titles, Translator, content_label))


async def _translate_titles_async(
    unique_titles: list[str],
    translator_class,
    content_label: str,
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(_translation_concurrency())

    async with translator_class() as translator:
        async def translate_one(title: str) -> tuple[str, str]:
            translated_title = ""
            async with semaphore:
                try:
                    translated = await translator.translate(title, src="en", dest="zh-tw")
                except Exception as exc:
                    print(f"[warn] googletrans {content_label}翻譯失敗，改用 deep-translator：{title} ({exc})")
                else:
                    translated_title = translated.text
            return title, translated_title

        results = await asyncio.gather(*(translate_one(title) for title in unique_titles))
    return {
        title: _translation_or_fallback(title, translated_title)
        for title, translated_title in results
    }


def _translation_concurrency() -> int:
    configured = os.environ.get("UK_NEWS_TRANSLATION_CONCURRENCY")
    if not configured:
        return DEFAULT_TRANSLATION_CONCURRENCY
    try:
        return max(1, int(configured))
    except ValueError:
        print(
            "[warn] UK_NEWS_TRANSLATION_CONCURRENCY 必須是整數，"
            f"改用預設值 {DEFAULT_TRANSLATION_CONCURRENCY}。"
        )
        return DEFAULT_TRANSLATION_CONCURRENCY


def _translation_or_fallback(title: str, translated_title: str) -> str:
    if translated_title and _normalize_title(translated_title) != _normalize_title(title):
        return translated_title
    return (
        _translate_with_deep_translator(title)
        or _translate_election_statement_title(title)
        or translated_title
    )


def _translate_titles_with_deep_translator(unique_titles: list[str]) -> dict[str, str]:
    return {
        title: _translate_with_deep_translator(title) or _translate_election_statement_title(title)
        for title in unique_titles
    }


def _translate_with_deep_translator(title: str) -> str:
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("[warn] 尚未安裝 deep-translator，無法執行備援翻譯。請先執行：pip install -r requirement.txt")
        return ""

    try:
        translated_title = GoogleTranslator(source="en", target="zh-TW").translate(title)
    except Exception as exc:
        print(f"[warn] deep-translator 標題翻譯失敗：{title} ({exc})")
        return ""

    if translated_title and _normalize_title(translated_title) != _normalize_title(title):
        return translated_title
    return ""


def _translate_election_statement_title(title: str) -> str:
    match = re.fullmatch(
        r"Post count statement\s*[-–]\s*(\d{4})\s+(.+?)\s+election",
        title,
        flags=re.IGNORECASE,
    )
    if match:
        year, election_name = match.groups()
        return f"計票後聲明 - {year} 年{_translate_election_name(election_name)}選舉"

    match = re.fullmatch(r"Post poll statement\s*[-–]\s*(.+)", title, flags=re.IGNORECASE)
    if match:
        return f"投票後聲明 - {_translate_month_year(match.group(1))}"

    return ""


def _translate_election_name(name: str) -> str:
    known_names = {
        "scottish parliament": "蘇格蘭議會",
        "senedd": "參議院",
    }
    return known_names.get(name.casefold(), name)


def _translate_month_year(value: str) -> str:
    months = {
        "january": "1 月",
        "february": "2 月",
        "march": "3 月",
        "april": "4 月",
        "may": "5 月",
        "june": "6 月",
        "july": "7 月",
        "august": "8 月",
        "september": "9 月",
        "october": "10 月",
        "november": "11 月",
        "december": "12 月",
    }
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", value.strip())
    if not match:
        return value
    month, year = match.groups()
    return f"{year} 年 {months.get(month.casefold(), month)}"


def _dedupe_for_export(items: list[NewsItem]) -> list[NewsItem]:
    return dedupe_news_items(items)


def _normalize_title(value: str) -> str:
    return normalize_title(value)


def _fill_rows(ws, start_row: int, end_row: int, fill: PatternFill) -> None:
    for row in ws.iter_rows(min_row=start_row, max_row=end_row, max_col=ws.max_column):
        for cell in row:
            cell.fill = fill


def _merged_columns(include_matches: bool) -> tuple[int, ...]:
    if include_matches:
        return (1, 2, 3, 4, 6, 7, 8)
    return (1, 2, 3, 4, 6)


def _style_sheet(ws) -> None:
    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    widths = {
        1: 8,
        2: 38,
        3: 14,
        4: 24,
        5: 80,
        6: 72,
        7: 28,
        8: 60,
    }
    for idx, width in widths.items():
        if idx <= ws.max_column:
            ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=cell.column == TITLE_COLUMN)
        if row[TITLE_COLUMN - 1].row % 2 == 1:
            row[TITLE_COLUMN - 1].font = Font(color="666666")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
