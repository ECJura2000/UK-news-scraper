use anyhow::{Context, Result};
use rust_xlsxwriter::{Color, Format, FormatAlign, FormatBorder, Workbook, Worksheet, XlsxError};
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
};
use uk_news_core::{FilterProfile, NewsItem, ParliamentBriefing};

pub const REQUIRED_SHEETS: [&str; 4] = ["全部新聞", "已初步篩選工作表", "國會研究資料", "篩選設定"];
pub const NEWS_HEADERS: [&str; 7] = [
    "編號",
    "部會",
    "新聞日期",
    "單位分類",
    "資料類型",
    "新聞標題",
    "新聞連結",
];
pub const MATCH_HEADERS: [&str; 14] = [
    "編號",
    "部會",
    "新聞日期",
    "單位分類",
    "資料類型",
    "新聞標題",
    "新聞連結",
    "命中觀測領域",
    "命中關鍵字",
    "相關性",
    "分數",
    "核心關聯詞",
    "一般關聯詞",
    "輔助關聯詞",
];
pub const PARLIAMENT_HEADERS: [&str; 14] = [
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
];

#[derive(Clone, Copy)]
pub enum CalendarMode {
    Gregorian,
    Roc,
}
pub struct ExportOptions<'a> {
    pub calendar_mode: CalendarMode,
    pub profile: &'a FilterProfile,
}

fn header_format() -> Format {
    Format::new()
        .set_bold()
        .set_background_color(Color::RGB(0xD9EAF7))
        .set_align(FormatAlign::Center)
        .set_border(FormatBorder::Thin)
}
fn section_format() -> Format {
    Format::new()
        .set_bold()
        .set_background_color(Color::RGB(0xBDD7EE))
}
fn date_format(mode: CalendarMode) -> Format {
    Format::new().set_num_format(match mode {
        CalendarMode::Gregorian => "yyyy-mm-dd",
        CalendarMode::Roc => "[$-zh-TW-x-roc]e\"年\"mm\"月\"dd\"日\"",
    })
}
fn date_text(date: chrono::NaiveDate, mode: CalendarMode) -> String {
    match mode {
        CalendarMode::Gregorian => date.to_string(),
        CalendarMode::Roc => format!(
            "民國{}年{:02}月{:02}日",
            date.year() - 1911,
            date.month(),
            date.day()
        ),
    }
}
use chrono::Datelike;

pub fn export_news(
    all: &[NewsItem],
    filtered: &[NewsItem],
    parliament: &[ParliamentBriefing],
    filtered_parliament: &[ParliamentBriefing],
    translations: &HashMap<String, String>,
    output: &Path,
    options: ExportOptions<'_>,
) -> Result<PathBuf> {
    let mut workbook = Workbook::new();
    {
        let ws = workbook.add_worksheet();
        ws.set_name(REQUIRED_SHEETS[0])?;
        write_news(ws, 0, all, false, translations, options.calendar_mode)?;
        style_news(ws)?;
    }
    {
        let ws = workbook.add_worksheet();
        ws.set_name(REQUIRED_SHEETS[1])?;
        ws.write_string_with_format(0, 0, "新聞稿", &section_format())?;
        let next = write_news(ws, 1, filtered, true, translations, options.calendar_mode)? + 2;
        ws.write_string_with_format(next, 0, "研究", &section_format())?;
        write_parliament(
            ws,
            next + 1,
            filtered_parliament,
            true,
            translations,
            options.calendar_mode,
        )?;
    }
    {
        let ws = workbook.add_worksheet();
        ws.set_name(REQUIRED_SHEETS[2])?;
        write_parliament(
            ws,
            0,
            parliament,
            false,
            translations,
            options.calendar_mode,
        )?;
    }
    {
        let ws = workbook.add_worksheet();
        ws.set_name(REQUIRED_SHEETS[3])?;
        write_settings(ws, options.profile, options.calendar_mode)?;
    }
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?
    }
    let tmp = output.with_extension("tmp.xlsx");
    workbook.save(&tmp).context("write temporary workbook")?;
    if tmp.metadata()?.len() == 0 {
        anyhow::bail!("Excel 暫存檔為空")
    };
    fs::rename(&tmp, output).or_else(|_| {
        fs::copy(&tmp, output)?;
        fs::remove_file(&tmp)
    })?;
    Ok(output.to_path_buf())
}

fn write_headers(ws: &mut Worksheet, row: u32, headers: &[&str]) -> Result<(), XlsxError> {
    let f = header_format();
    for (c, v) in headers.iter().enumerate() {
        ws.write_string_with_format(row, c as u16, *v, &f)?;
    }
    Ok(())
}
fn write_news(
    ws: &mut Worksheet,
    start: u32,
    items: &[NewsItem],
    matches: bool,
    tr: &HashMap<String, String>,
    mode: CalendarMode,
) -> Result<u32, XlsxError> {
    let h = if matches {
        &MATCH_HEADERS[..]
    } else {
        &NEWS_HEADERS[..]
    };
    write_headers(ws, start, h)?;
    let mut row = start + 1;
    let mut sorted = items.to_vec();
    sorted.sort_by_key(|x| (x.agency.clone(), x.published_at, x.title.to_lowercase()));
    for (i, item) in sorted.iter().enumerate() {
        let values = [
            (i + 1).to_string(),
            item.agency.clone(),
            date_text(item.published_at.date_naive(), mode),
            item.unit_category.clone().unwrap_or_default(),
            item.content_type.to_string(),
            item.title.clone(),
            item.link.clone(),
        ];
        for (c, v) in values.iter().enumerate() {
            ws.write_string(row, c as u16, v)?;
        }
        if matches {
            let extra = [
                item.matched_topics.join("、"),
                item.matched_keywords.join("、"),
                item.relevance_level.clone(),
                item.relevance_score.to_string(),
                item.core_matched_keywords.join("、"),
                item.general_matched_keywords.join("、"),
                item.supporting_matched_keywords.join("、"),
            ];
            for (c, v) in extra.iter().enumerate() {
                ws.write_string(row, (c + 7) as u16, v)?;
            }
        }
        let zh = tr
            .get(&item.title)
            .cloned()
            .unwrap_or_else(|| item.title.clone());
        ws.write_string(row + 1, 5, &zh)?;
        for c in [0, 1, 2, 3, 4, 6] {
            ws.merge_range(
                row,
                c,
                row + 1,
                c,
                values[c as usize].as_str(),
                &Format::new(),
            )?;
        }
        if matches {
            let extra = [
                item.matched_topics.join("、"),
                item.matched_keywords.join("、"),
                item.relevance_level.clone(),
                item.relevance_score.to_string(),
                item.core_matched_keywords.join("、"),
                item.general_matched_keywords.join("、"),
                item.supporting_matched_keywords.join("、"),
            ];
            for (offset, value) in extra.iter().enumerate() {
                let c = (offset + 7) as u16;
                ws.merge_range(row, c, row + 1, c, value, &Format::new())?;
            }
            ws.write_number(row, 10, item.relevance_score as f64)?;
        }
        ws.write_number(row, 0, (i + 1) as f64)?;
        ws.write_datetime_with_format(row, 2, item.published_at.date_naive(), &date_format(mode))?;
        if !item.link.is_empty() {
            ws.write_url(row, 6, item.link.as_str())?;
        }
        row += 2;
    }
    Ok(row)
}
fn write_parliament(
    ws: &mut Worksheet,
    start: u32,
    items: &[ParliamentBriefing],
    matches: bool,
    tr: &HashMap<String, String>,
    mode: CalendarMode,
) -> Result<u32, XlsxError> {
    let mut headers = PARLIAMENT_HEADERS.to_vec();
    if matches {
        headers.extend_from_slice(&MATCH_HEADERS[7..]);
    }
    write_headers(ws, start, &headers)?;
    let mut row = start + 1;
    let mut sorted = items.to_vec();
    sorted.sort_by_key(|x| std::cmp::Reverse(x.published_at));
    for item in &sorted {
        let values = vec![
            date_text(item.published_at.date_naive(), mode),
            "United Kingdom".into(),
            "UK Parliament".into(),
            item.chamber.clone(),
            "Research Briefing".into(),
            item.publisher.clone(),
            item.topics.join("、"),
            item.document_type.clone(),
            item.title.clone(),
            item.summary.clone(),
            item.identifier.clone(),
            item.webpage_url.clone(),
            item.pdf_url.clone(),
            item.fetched_from.clone(),
        ];
        for (c, v) in values.iter().enumerate() {
            ws.write_string(row, c as u16, v)?;
        }
        ws.write_string(row + 1, 8, tr.get(&item.title).unwrap_or(&item.title))?;
        ws.write_string(row + 1, 9, tr.get(&item.summary).unwrap_or(&item.summary))?;
        if matches {
            let extra = [
                item.matched_topics.join("、"),
                item.matched_keywords.join("、"),
                item.relevance_level.clone(),
                item.relevance_score.to_string(),
                item.core_matched_keywords.join("、"),
                item.general_matched_keywords.join("、"),
                item.supporting_matched_keywords.join("、"),
            ];
            for (c, v) in extra.iter().enumerate() {
                ws.write_string(row, (c + 14) as u16, v)?;
            }
        }
        for c in [0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13] {
            ws.merge_range(row, c, row + 1, c, &values[c as usize], &Format::new())?;
        }
        if matches {
            let extra = [
                item.matched_topics.join("、"),
                item.matched_keywords.join("、"),
                item.relevance_level.clone(),
                item.relevance_score.to_string(),
                item.core_matched_keywords.join("、"),
                item.general_matched_keywords.join("、"),
                item.supporting_matched_keywords.join("、"),
            ];
            for (offset, value) in extra.iter().enumerate() {
                let c = (offset + 14) as u16;
                ws.merge_range(row, c, row + 1, c, value, &Format::new())?;
            }
            ws.write_number(row, 17, item.relevance_score as f64)?;
        }
        ws.write_datetime_with_format(row, 0, item.published_at.date_naive(), &date_format(mode))?;
        if !item.webpage_url.is_empty() {
            ws.write_url(row, 11, item.webpage_url.as_str())?;
        }
        if !item.pdf_url.is_empty() {
            ws.write_url(row, 12, item.pdf_url.as_str())?;
        }
        row += 2;
    }
    Ok(row)
}
fn write_settings(
    ws: &mut Worksheet,
    profile: &FilterProfile,
    mode: CalendarMode,
) -> Result<(), XlsxError> {
    write_headers(ws, 0, &["UK 新聞篩選設定", "值"])?;
    let rows = [
        ("設定檔 ID", profile.profile_id.clone()),
        ("設定檔名稱", profile.name.clone()),
        ("設定檔版本", profile.version.to_string()),
        ("最低納入分數", profile.minimum_score.to_string()),
        (
            "Excel 日期紀年",
            match mode {
                CalendarMode::Gregorian => "gregorian",
                CalendarMode::Roc => "roc",
            }
            .into(),
        ),
        ("選用來源", profile.selected_sources.join("、")),
    ];
    for (i, (k, v)) in rows.iter().enumerate() {
        ws.write_string((i + 1) as u32, 0, *k)?;
        ws.write_string((i + 1) as u32, 1, v)?;
    }
    Ok(())
}
fn style_news(ws: &mut Worksheet) -> Result<(), XlsxError> {
    for (c, w) in [14., 38., 18., 24., 16., 80., 72.].iter().enumerate() {
        ws.set_column_width(c as u16, *w)?;
    }
    ws.set_freeze_panes(1, 0)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use calamine::{open_workbook_auto, Reader};
    use tempfile::tempdir;

    #[test]
    fn workbook_preserves_required_sheet_contract() {
        let dir = tempdir().unwrap();
        let output = dir.path().join("report.xlsx");
        let profile = FilterProfile {
            profile_id: "test".into(),
            name: "Test".into(),
            description: String::new(),
            version: 1,
            selected_sources: vec!["NCSC".into()],
            topics: vec![],
            minimum_score: 3,
        };
        export_news(
            &[],
            &[],
            &[],
            &[],
            &HashMap::new(),
            &output,
            ExportOptions {
                calendar_mode: CalendarMode::Gregorian,
                profile: &profile,
            },
        )
        .unwrap();
        let workbook = open_workbook_auto(&output).unwrap();
        assert_eq!(
            workbook.sheet_names(),
            REQUIRED_SHEETS
                .iter()
                .map(|x| x.to_string())
                .collect::<Vec<_>>()
        );
    }
}
