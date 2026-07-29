from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .calendar_utils import CalendarMode, excel_number_format
from .dedupe import dedupe_news_items, normalize_title
from .models import NewsItem, ParliamentBriefing
from .profiles import (
    FilterProfile,
    KeywordStrength,
    default_profile,
    profile_hash,
)
from .translation_cache import load_translations, save_translations


HEADERS = ("編號", "部會", "新聞日期", "單位分類", "新聞標題", "新聞連結")
MATCH_HEADERS = HEADERS + (
    "命中觀測領域",
    "命中關鍵字",
    "相關性",
    "分數",
    "核心關聯詞",
    "一般關聯詞",
    "輔助關聯詞",
)
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
PARLIAMENT_MATCH_HEADERS = PARLIAMENT_HEADERS + (
    "命中觀測領域",
    "命中關鍵字",
    "相關性",
    "分數",
    "核心關聯詞",
    "一般關聯詞",
    "輔助關聯詞",
)
TITLE_COLUMN = 5
RELEVANCE_FILLS = {
    "高": PatternFill("solid", fgColor="FFD966"),
    "中": PatternFill("solid", fgColor="FFE699"),
    "低": PatternFill("solid", fgColor="FFF2CC"),
}
SECTION_FILL = PatternFill("solid", fgColor="BDD7EE")
STRENGTH_FILLS = {
    KeywordStrength.CORE.value: PatternFill("solid", fgColor="E6A817"),
    KeywordStrength.GENERAL.value: PatternFill("solid", fgColor="F2C94C"),
    KeywordStrength.SUPPORTING.value: PatternFill("solid", fgColor="FFF1B8"),
}
DEFAULT_TRANSLATION_CONCURRENCY = 4
MANUAL_TITLE_TRANSLATIONS = {
    "Building more resilient CNI: what industry pen testers told us": "打造更具韌性的關鍵國家基礎設施：產業滲透測試人員的回饋",
    "Cyber Shield: The path to an agentic AI future for cyber defence": "Cyber Shield：邁向具代理式 AI 的網路防禦未來",
}


@dataclass(frozen=True)
class ExportOptions:
    calendar_mode: CalendarMode = CalendarMode.GREGORIAN
    profile: FilterProfile | None = None


def export_news(
    all_items: list[NewsItem],
    filtered_items: list[NewsItem],
    output_path: str | Path,
    parliament_items: list[ParliamentBriefing] | None = None,
    filtered_parliament_items: list[ParliamentBriefing] | None = None,
    export_options: ExportOptions | None = None,
) -> Path:
    options = export_options or ExportOptions()
    profile = options.profile or default_profile()
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    title_translations = _translate_titles([*all_items, *filtered_items])
    _ensure_translations_present(title_translations, [*all_items, *filtered_items])
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
    _write_sheet(
        ws_all,
        all_items,
        include_matches=False,
        title_translations=title_translations,
        calendar_mode=options.calendar_mode,
    )

    ws_filtered = wb.create_sheet("已初步篩選工作表")
    _write_filtered_sheet(
        ws_filtered,
        filtered_items,
        filtered_parliament_items,
        title_translations,
        parliament_translations,
        options.calendar_mode,
    )

    ws_parliament = wb.create_sheet("國會研究資料")
    _write_parliament_sheet(
        ws_parliament,
        parliament_items,
        parliament_translations,
        calendar_mode=options.calendar_mode,
    )

    ws_settings = wb.create_sheet("篩選設定")
    _write_settings_sheet(ws_settings, profile, options.calendar_mode)

    _style_sheet(ws_all)
    _style_filtered_sheet(ws_filtered)
    _style_parliament_sheet(ws_parliament)
    _style_settings_sheet(ws_settings)

    temporary_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
    try:
        wb.save(temporary_path)
        verification_workbook = load_workbook(temporary_path, read_only=True, data_only=True)
        required_sheets = {"全部新聞", "已初步篩選工作表", "國會研究資料", "篩選設定"}
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
    calendar_mode: CalendarMode = CalendarMode.GREGORIAN,
) -> None:
    ws.append(PARLIAMENT_MATCH_HEADERS if include_matches else PARLIAMENT_HEADERS)
    for item in sorted(items, key=lambda briefing: (briefing.published_at, briefing.publisher), reverse=True):
        english_row_number = ws.max_row + 1
        row = [
            item.published_at.date(),
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
                    item.relevance_level,
                    item.relevance_score,
                    "、".join(item.core_matched_keywords),
                    "、".join(item.general_matched_keywords),
                    "、".join(item.supporting_matched_keywords),
                ]
            )
        ws.append(row)
        ws.cell(english_row_number, 1).number_format = excel_number_format(calendar_mode)

        chinese_row_number = ws.max_row + 1
        translation_row = [""] * len(PARLIAMENT_HEADERS)
        translation_row[8] = translations.get(item.title, "")
        translation_row[9] = translations.get(item.summary, "")
        ws.append(translation_row)

        title_fill = _strongest_keyword_fill(item.title_keyword_strengths, item.relevance_level)
        summary_fill = _strongest_keyword_fill(item.summary_keyword_strengths, item.relevance_level)
        if item.title_matched_keywords:
            ws.cell(english_row_number, 9).fill = title_fill
        if item.summary_matched_keywords:
            ws.cell(english_row_number, 10).fill = summary_fill
        if include_matches and item.matched_keywords:
            relevance_fill = _relevance_fill(item.relevance_level)
            for column in (15, 16, 17, 18):
                ws.cell(english_row_number, column).fill = relevance_fill
            for column, strength in (
                (19, KeywordStrength.CORE),
                (20, KeywordStrength.GENERAL),
                (21, KeywordStrength.SUPPORTING),
            ):
                if ws.cell(english_row_number, column).value:
                    ws.cell(english_row_number, column).fill = STRENGTH_FILLS[strength.value]

        merged_columns = [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14]
        if include_matches:
            merged_columns.extend((15, 16, 17, 18, 19, 20, 21))
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
    widths = (14, 16, 18, 18, 20, 46, 36, 20, 56, 80, 18, 72, 72, 72, 28, 60, 12, 10, 36, 36, 36)
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
    calendar_mode: CalendarMode,
) -> None:
    ws.append(["新聞稿"])
    _style_section_row(ws, ws.max_row)
    _write_sheet(
        ws,
        news_items,
        include_matches=True,
        title_translations=title_translations,
        calendar_mode=calendar_mode,
    )
    ws.append([])
    ws.append(["研究"])
    _style_section_row(ws, ws.max_row)
    _write_parliament_sheet(
        ws,
        parliament_items,
        parliament_translations,
        include_matches=True,
        calendar_mode=calendar_mode,
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
    widths = (14, 38, 18, 24, 80, 72, 36, 60, 12, 10, 36, 36, 36, 72, 28, 60, 12, 10, 36, 36, 36)
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
    calendar_mode: CalendarMode = CalendarMode.GREGORIAN,
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
            item.published_at.date(),
            item.unit_category,
            item.title,
            item.link,
        ]
        if include_matches:
            row.extend(
                [
                    "、".join(item.matched_topics),
                    "、".join(item.matched_keywords),
                    item.relevance_level,
                    item.relevance_score,
                    "、".join(item.core_matched_keywords),
                    "、".join(item.general_matched_keywords),
                    "、".join(item.supporting_matched_keywords),
                ]
            )
        ws.append(row)
        ws.cell(english_row_number, 3).number_format = excel_number_format(calendar_mode)

        chinese_row_number = ws.max_row + 1
        translation_row = [""] * ws.max_column
        translation_row[TITLE_COLUMN - 1] = title_translations.get(item.title, "")
        ws.append(translation_row)

        title_fill = _strongest_keyword_fill(item.title_keyword_strengths, item.relevance_level)
        if item.title_matched_keywords:
            ws.cell(english_row_number, TITLE_COLUMN).fill = title_fill
            ws.cell(chinese_row_number, TITLE_COLUMN).fill = title_fill
        if include_matches and item.matched_keywords:
            relevance_fill = _relevance_fill(item.relevance_level)
            for column in (7, 8, 9, 10):
                ws.cell(english_row_number, column).fill = relevance_fill
            for column, strength in (
                (11, KeywordStrength.CORE),
                (12, KeywordStrength.GENERAL),
                (13, KeywordStrength.SUPPORTING),
            ):
                if ws.cell(english_row_number, column).value:
                    ws.cell(english_row_number, column).fill = STRENGTH_FILLS[strength.value]
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


def _relevance_fill(level: str) -> PatternFill:
    return RELEVANCE_FILLS.get(level, RELEVANCE_FILLS["低"])


def _strongest_keyword_fill(strengths: dict[str, str], fallback_level: str) -> PatternFill:
    for strength in (
        KeywordStrength.CORE.value,
        KeywordStrength.GENERAL.value,
        KeywordStrength.SUPPORTING.value,
    ):
        if strength in strengths.values():
            return STRENGTH_FILLS[strength]
    return _relevance_fill(fallback_level)


def _write_settings_sheet(
    ws,
    profile: FilterProfile,
    calendar_mode: CalendarMode,
) -> None:
    ws.append(["UK 新聞篩選設定", "值"])
    rows = (
        ("設定檔 ID", profile.profile_id),
        ("設定檔名稱", profile.name),
        ("設定檔版本", profile.version),
        ("設定檔雜湊", profile_hash(profile)),
        ("最低納入分數", profile.minimum_score),
        ("Excel 日期紀年", calendar_mode.value),
        ("選用來源", "、".join(profile.selected_sources)),
    )
    for row in rows:
        ws.append(row)
    ws.append([])
    ws.append(["主題", "關鍵詞", "強度", "標題分數", "摘要分數"])
    weights = {
        KeywordStrength.CORE: (6, 4),
        KeywordStrength.GENERAL: (4, 3),
        KeywordStrength.SUPPORTING: (2, 1),
    }
    for topic in profile.topics:
        for keyword in topic.keywords:
            title_score, summary_score = weights[keyword.strength]
            ws.append([topic.name, keyword.phrase, keyword.strength.label, title_score, summary_score])
            ws.cell(ws.max_row, 3).fill = STRENGTH_FILLS[keyword.strength.value]
    ws.sheet_properties.tabColor = "E6A817"


def _style_settings_sheet(ws) -> None:
    for row_number in (1, 10):
        for cell in ws[row_number]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="14213D")
            cell.alignment = Alignment(horizontal="center", vertical="center")
    for index, width in enumerate((28, 72, 16, 14, 14), start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A11"


def _translate_titles(items: list[NewsItem]) -> dict[str, str]:
    unique_titles = list(dict.fromkeys(item.title for item in items if item.title))
    return _translate_texts(unique_titles, content_label="新聞標題")


def _ensure_translations_present(translations: dict[str, str], items: list[NewsItem]) -> None:
    untranslated = [
        item.title
        for item in items
        if item.title
        and _normalize_title(translations.get(item.title, "")) == _normalize_title(item.title)
    ]
    if untranslated:
        sample = "；".join(dict.fromkeys(untranslated))
        print(f"[warn] 新聞標題翻譯失敗或未變更，將保留原文：{sample}")


def _translate_texts(texts: list[str], content_label: str) -> dict[str, str]:
    unique_titles = list(dict.fromkeys(text for text in texts if text))
    if not unique_titles:
        return {}

    cached = load_translations()
    translations: dict[str, str] = {}
    for title in unique_titles:
        cached_translation = cached.get(title, "")
        resolved = _translation_or_fallback(title, cached_translation) if cached_translation else ""
        if resolved and _normalize_title(resolved) != _normalize_title(title):
            translations[title] = resolved
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
        MANUAL_TITLE_TRANSLATIONS.get(title.strip(), "")
        or _translate_with_deep_translator(title)
        or _translate_election_statement_title(title)
        or translated_title
    )


def _translate_titles_with_deep_translator(unique_titles: list[str]) -> dict[str, str]:
    return {
        title: _translate_with_deep_translator(title) or _translate_election_statement_title(title)
        for title in unique_titles
    }


def _translate_with_deep_translator(title: str) -> str:
    manual = MANUAL_TITLE_TRANSLATIONS.get(title.strip())
    if manual:
        return manual
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
        return (1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13)
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
