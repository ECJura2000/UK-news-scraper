# 資料來源

本專案整理英國政府機關、監管機關與 UK Parliament 公開發布的新聞及研究資料。程式實際使用的最新來源仍以 [`UK_news_scraper/config.py`](UK_news_scraper/config.py) 與 Parliament scraper 為準。

## 機關新聞來源

| 簡稱 | 機關 | 官方首頁／新聞頁 | RSS／Atom |
| --- | --- | --- | --- |
| BIST | Department for Business, Innovation, Science and Trade | [GOV.UK](https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade) | [Atom](https://www.gov.uk/government/organisations/department-for-business-innovation-science-and-trade.atom) |
| DCMS | Department for Digital, Culture, Media and Sport | [GOV.UK current department page](https://www.gov.uk/government/organisations/department-for-culture-media-and-sport) | [Atom](https://www.gov.uk/government/organisations/department-for-culture-media-and-sport.atom) |
| AISI | AI Security Institute | [GOV.UK](https://www.gov.uk/government/organisations/ai-safety-institute) | [Atom](https://www.gov.uk/government/organisations/ai-safety-institute.atom) |
| ICO | Information Commissioner's Office | [News and blogs](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/) | 網站自動發現或 HTML |
| CMA | Competition and Markets Authority | [GOV.UK](https://www.gov.uk/government/organisations/competition-and-markets-authority) | [Atom](https://www.gov.uk/government/organisations/competition-and-markets-authority.atom) |
| UK IPO | UK Intellectual Property Office | [GOV.UK](https://www.gov.uk/government/organisations/intellectual-property-office) | [Atom](https://www.gov.uk/government/organisations/intellectual-property-office.atom) |
| GDS | Government Digital Service | [GOV.UK](https://www.gov.uk/government/organisations/government-digital-service) | [Atom](https://www.gov.uk/government/organisations/government-digital-service.atom) |
| Ofcom | Office of Communications | [News and updates](https://www.ofcom.org.uk/news-and-updates) | [RSS](https://www.ofcom.org.uk/news-centre/rss) |
| NCSC | National Cyber Security Centre | [Homepage](https://www.ncsc.gov.uk/)；[Guidance collection](https://www.ncsc.gov.uk/collection/what-to-do-when-cyber-attacks-disrupt-your-organisation) | [RSS](https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml)；官方 Guidance 頁面 |
| Electoral Commission | Electoral Commission | [Media centre](https://www.electoralcommission.org.uk/news-and-views/media-centre) | HTML；失敗時使用 Google News RSS 備援 |
| Cabinet Office | Cabinet Office | [GOV.UK](https://www.gov.uk/government/organisations/cabinet-office) | [Atom](https://www.gov.uk/government/organisations/cabinet-office.atom) |
| NPSA | National Protective Security Authority | [Blog](https://www.npsa.gov.uk/blog) | 官網受阻時使用 Google News RSS 備援 |
| UKRI | UK Research and Innovation | [News](https://www.ukri.org/news/)、[evaluation reports](https://www.ukri.org/who-we-are/how-we-are-doing/evaluation-reports/browse/)、[investment and outputs](https://www.ukri.org/what-we-do/what-we-have-funded/investment-and-outputs-publication/) | [Feed](https://www.ukri.org/feed/) |

2026 年 7 月的政府組織調整將 DSIT 職能重新分配：BIST 承接科學、研究與
創新；DCMS 承接電信、線上安全、數位身分與 GDS；Cabinet Office 承接
AI 策略、公部門 AI 採用與 AI Security Institute。程式使用仍持續更新的
現行 DCMS GOV.UK slug，不使用標示為 2017 至 2023 年且已撤回的舊
`department-for-digital-culture-media-sport` feed。

GOV.UK Atom 來源會保留 `/government/news/`、`/guidance/`、
`/government/publications/`、`/government/consultations/`、研究及統計頁面，
並在 Excel 的「資料類型」欄區分 `news`、`guidance`、`report` 與 `publication`。
機關官方索引頁也會作為 RSS 以外的補充來源；只收有明確日期且在查詢期間內的項目。

## UK Parliament Research Briefings

| 資料 | 入口 | 用途 |
| --- | --- | --- |
| Research Briefings API | [API JSON](https://lda.data.parliament.uk/researchbriefings.json) | 可選的主要 API／健康檢查來源 |
| House of Commons Library | [Official RSS](https://commonslibrary.parliament.uk/research-briefings/feed/) | Commons research briefings |
| House of Lords Library | [Official RSS](https://lordslibrary.parliament.uk/research-briefings/feed/) | Lords research briefings |
| POST | [Official feed](https://post.parliament.uk/feed/) | Parliamentary Office of Science and Technology |
| Commons Technology | [Topic archive](https://commonslibrary.parliament.uk/topic/science/technology/) | 補充 RSS 未收錄文章 |
| Commons Sciences | [Topic archive](https://commonslibrary.parliament.uk/topic/science/sciences/) | 補充 RSS 未收錄文章 |
| Lords Science & Technology | [Topic archive](https://lordslibrary.parliament.uk/topic/science-environment/science-environment-science-technology/) | 補充 RSS 未收錄文章 |
| Research briefing PDFs | `researchbriefings.files.parliament.uk` | 依 briefing identifier 建立官方 PDF 連結 |

## 第三方備援與服務

| 服務 | 用途 | 注意事項 |
| --- | --- | --- |
| [Google News RSS](https://news.google.com/) | NPSA 與 Electoral Commission 官網無法讀取時的備援搜尋 | 非官方來源；結果會過濾雜訊，仍應回到原始新聞頁查核 |
| `googletrans`／`deep-translator` | 英文標題與摘要翻譯 | 可能將文字傳送至外部翻譯服務；不得用於機密或未公開內容 |

## 維護要求

新增或變更來源時，請同步更新：

1. [`UK_news_scraper/config.py`](UK_news_scraper/config.py) 的 `AGENCIES`。
2. [`UK_news_scraper/scrapers/parliament/research_briefings.py`](UK_news_scraper/scrapers/parliament/research_briefings.py) 的 Parliament 來源。
3. 本文件的來源表格。
4. 對應測試 fixture 與來源健康門檻。
