# UK News Scraper

依據「國際觀測用(英國)」Word 檔中的機關與觀測領域，抓取英國相關機關新聞稿。程式優先使用 RSS/Atom feed，並以觀測領域關鍵字先做初步篩選。同一份 Excel 也會納入 UK Parliament 的 Commons Library、Lords Library 與 POST research briefings。

完整的機關、RSS／API、國會資料與第三方備援入口請見 [資料來源](SOURCES.md)。程式碼授權與來源內容的權利界線請見 [NOTICE](NOTICE.md)。

專題成果請見 [正式報告](PROJECT_REPORT.md)、[操作示範](docs/DEMO.md)、[UAT](docs/UAT.md)、[災難復原](docs/DISASTER_RECOVERY.md) 與 [變更紀錄](CHANGELOG.md)。

資料流、模組責任、資料結構選擇與複雜度分析請見 [架構說明](ARCHITECTURE.md)。
Capacity, dedupe, and concurrency measurements are documented in [PERFORMANCE.md](PERFORMANCE.md).
Deployment, source maintenance, and delivery recovery are documented in [docs/MAINTENANCE.md](docs/MAINTENANCE.md).

## 使用方式

```bash
python3 -m UK_news_scraper
```

預設會依 `Asia/Taipei` 日曆日回推 14 天，輸出到桌面的 `UK新聞抓取/新聞放置區/英國相關機關爬蟲新聞（起始日-結束日）.xlsx`。同一天內重跑會使用相同日期區間與檔名。

每次執行也會在 Excel 旁產生同名的 `.run.json` 執行摘要，內容包含穩定 `run_id`、邏輯筆數、完整或降級狀態與來源警告。寄信流程應先用 `run_id` 檢查是否已寄送，避免同一期間重複寄信。

翻譯會使用持久快取，未命中內容預設以 4 個有限併發請求翻譯。可用
`UK_NEWS_TRANSLATION_CONCURRENCY` 調整併發數。
翻譯功能透過 `googletrans`／`deep-translator` 所連接的外部翻譯服務處理文字；不應傳送機密、個人或未公開內容。

第一次執行前請先安裝套件：

```bash
python3 -m pip install -r requirement.txt
```

正式建置與 CI 使用固定版本的 `requirement-lock.txt`，更新依賴後應重新驗證並同步該檔案。

## 打包成免安裝 Python 的執行檔

macOS：

```bash
./build_macos.sh
```

Windows：

```bat
build_windows.bat
```

macOS 會產生：

- `dist/UKNewsScraper`：原始無密碼版
- `dist/UKNewsScraper_protected`：第一次執行後 30 天內免密碼，超過 30 天後需輸入密碼

Windows 會產生：

- `dist\UKNewsScraper.exe`：原始無密碼版
- `dist\UKNewsScraper_protected.exe`：第一次執行後 30 天內免密碼，超過 30 天後需輸入密碼

免安裝 Python 的執行檔需在目標系統上各自打包，macOS 不能直接產生可正常使用的 Windows `.exe`。

Windows 原始無密碼版使用時，可把 `UKNewsScraper.exe` 和 `run_windows.bat` 放在同一個資料夾，從檔案總管雙擊 `run_windows.bat`。

Windows 防盜版版使用時，可把 `UKNewsScraper_protected.exe` 和 `run_windows_protected.bat` 放在同一個資料夾，從檔案總管雙擊 `run_windows_protected.bat`。第一次執行後 30 天內免密碼，超過 30 天後再執行會要求密碼。密碼必須透過 `UK_NEWS_RUN_PASSWORD` 環境變數設定，不會寫死在程式碼中。

```bash
python3 -m UK_news_scraper --days 14 --output output/本週英國新聞.xlsx
python3 -m UK_news_scraper --since 2026-05-01
python3 -m UK_news_scraper --workers 8
```

也可以直接在指令後面輸入搜尋期間：

```bash
python3 -m UK_news_scraper 30
python3 -m UK_news_scraper 20160501
python3 -m UK_news_scraper 20160501～20160515
python3 -m UK_news_scraper 20160501 ~ 20160515
```

- `30`：回推 30 天。
- `20160501`：從 2016-05-01 抓到現在。
- `20160501～20160515`：只保留 2016-05-01 到 2016-05-15 的新聞，結束日當天會包含在內。
- 全形 `～`、半形 `~`、前後半形或全形空格都可以解析。
- 若未指定 `--output`，輸出會放在桌面的 `UK新聞抓取/新聞放置區`，檔名會自動帶入搜尋期間，例如 `英國相關機關爬蟲新聞（20260419-20260519）.xlsx`。

輸出 Excel 會包含：

- `全部新聞`：抓到的所有機關新聞。
- `已初步篩選工作表`：分成 `新聞稿` 與 `研究` 兩區。標題或摘要命中觀測領域關鍵字的資料會列入，並附上命中領域與關鍵字。
- `國會研究資料`：Commons Library、Lords Library 與 POST research briefings，包含院別、主題、摘要、識別碼、網頁、PDF 及實際抓取來源。

命中關鍵字的資料也會在原始 `全部新聞` 或 `國會研究資料` 工作表中以黃底標記。目前觀測領域包含 `Science & Technology`、AI、資料治理、數位平台、網路安全、半導體與量子技術。

`新聞連結` 欄位會寫入 Excel 超連結，可直接點開原始新聞頁。GOV.UK 機關 feed 會排除 guidance、publication、transparency data 等文件更新，只保留 `/government/news/` 新聞頁。

每筆新聞會用兩列呈現，第一列是英文新聞標題，第二列是透過 `googletrans` 翻譯的繁體中文標題；`編號`、部會、日期、分類與連結會合併跨兩列。

## 目前納入機關

- DSIT / AI Safety Institute / ICO / CMA / UK IPO / GDS
- Ofcom / NCSC / Electoral Commission
- Cabinet Office / NPSA
- DBT / UKRI

## UK Parliament Research Briefings

國會研究資料預設使用 Commons Library、Lords Library 與 POST 的官方 RSS。
RSS 會逐頁抓取，直到資料日期早於本次搜尋起始日，避免只讀取每個 feed
最新 10 筆而漏掉同期間內的其他 research briefings。
此外會抓取 House of Lords Library 的 `Science & Technology` 主題頁，
以及 House of Commons Library 的 `Technology`、`Sciences` 主題頁，
補入 RSS 未收錄的 `In Focus` 與其他相關文章。
`Research Briefings API` 目前可透過環境變數 `UK_PARLIAMENT_TRY_API=1`
手動啟用健康檢查：

<https://lda.data.parliament.uk/researchbriefings.json>

若 API 暫時無法使用，程式會自動改抓官方 RSS。Excel 的 `抓取來源` 欄會保留實際來源。

NPSA 官網目前有 Cloudflare challenge，排程會直接使用 Google News RSS
作為備援，避免將已知的 `403 Forbidden` 誤判為整體抓取失敗。

## 測試

```bash
python3 -m pip install -r requirement-lock.txt -r requirement-dev.txt
python3 -m pytest -q
```

測試涵蓋日期區間穩定性、共用去重規則、來源狀態、執行摘要、HTTP session 重用、翻譯快取與必要 Excel 工作表。

`.run.json` 也會記錄每個來源的 critical 狀態、筆數、耗時、最新資料日期與健康警告。必要來源失敗或低於健康門檻時，整體狀態會標記為 `degraded`。

寄信 automation 應使用 delivery claim CLI，確保併發執行時只有一個寄信者：

```bash
python3 -m UK_news_scraper.delivery_registry claim --summary /absolute/report.run.json
python3 -m UK_news_scraper.delivery_registry complete --delivery-id <delivery_id> --message-id <gmail_message_id>
python3 -m UK_news_scraper.delivery_registry release --delivery-id <delivery_id>
python3 -m UK_news_scraper.delivery_registry status --state claimed
python3 -m UK_news_scraper.delivery_registry recover --delivery-id <delivery_id> --confirm-release
```

`recover` 僅適用於人工確認郵件未送出後釋放卡住的 claim；沒有
`--confirm-release` 時不會變更 registry。

來源健康門檻依機關發布頻率設定：高頻來源要求近 14 天有資料，低頻來源
使用 30、45 或 60 天 freshness 門檻，避免把正常的低頻發布誤判為異常。

## 授權

本專案程式碼使用 [MIT License](LICENSE)。抓取的新聞、國會研究資料、翻譯結果與第三方備援結果仍受各原始提供者的使用條款約束，詳見 [NOTICE](NOTICE.md)。
