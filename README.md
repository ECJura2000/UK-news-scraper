# UK News Scraper

依據「國際觀測用(英國)」Word 檔中的機關與觀測領域，抓取英國相關機關新聞稿。程式優先使用 RSS/Atom feed，並以觀測領域關鍵字先做初步篩選。同一份 Excel 也會納入 UK Parliament 的 Commons Library、Lords Library 與 POST research briefings。

完整的機關、RSS／API、國會資料與第三方備援入口請見 [資料來源](SOURCES.md)。程式碼授權與來源內容的權利界線請見 [NOTICE](NOTICE.md)。

專題成果請見 [正式報告](PROJECT_REPORT.md)、[操作示範](docs/DEMO.md)、[UAT](docs/UAT.md)、[災難復原](docs/DISASTER_RECOVERY.md) 與 [變更紀錄](CHANGELOG.md)。

資料流、模組責任、資料結構選擇與複雜度分析請見 [架構說明](ARCHITECTURE.md)。
Capacity, dedupe, and concurrency measurements are documented in [PERFORMANCE.md](PERFORMANCE.md).
Deployment, source maintenance, and delivery recovery are documented in [docs/MAINTENANCE.md](docs/MAINTENANCE.md).

## 下載

- [最新正式版本與各系統執行檔](https://github.com/ECJura2000/UK-news-scraper/releases/latest)
- [目前開發版原始碼 ZIP](https://github.com/ECJura2000/UK-news-scraper/archive/refs/heads/main.zip)
- [交給 Codex 或其他 AI 工具執行](AI_START_HERE.md)

正式 Release 會同時提供 Windows、macOS、Linux 可攜版及
`UKNewsScraper-版本-Source.zip`。若要讓 AI 工具協助安裝、修改或排程，
請下載 Source ZIP；AI 代理進入專案後可直接讀取 [AGENTS.md](AGENTS.md)
取得測試、輸出與寄信安全規則。

## 使用方式

### 桌面介面

```bash
python3 -m UK_news_scraper --ui
```

桌面介面可建立主題設定檔、選擇 UK 機關與國會來源、設定核心／一般／
輔助關鍵詞、使用西元或民國起訖日期，並在背景完成抓取與 Excel 匯出。
Windows 可攜版可直接雙擊 `run_windows_ui.bat`。

執行中可安全取消；來源發生錯誤或健康警告時，可使用「重試異常來源」
保留其他成功資料並只重新抓取異常來源。「最近執行」可重新開啟既有
Excel 與 `.run.json`。結果頁支援文字、類型、詞強度、來源、主題、分數
及日期篩選，也可點擊欄位標題切換排序。

設定檔會原子保存並保留 `.bak`；舊版格式會自動遷移。若設定檔損壞，
介面會隔離原檔、載入內建科技法制設定並顯示復原位置。

### 命令列

```bash
python3 -m UK_news_scraper
```

預設會依 `Asia/Taipei` 日曆日回推 14 天。從原始碼執行時輸出到專案的
`新聞放置區/`；封裝版輸出到桌面的 `UK新聞抓取/新聞放置區/`。預設檔名
為 `{起始日YYYYMMDD}-{結束日YYYYMMDD}_UK新聞查詢.xlsx`。

可用 `UK_NEWS_OUTPUT_DIR` 覆寫預設輸出資料夾，例如：

```bash
UK_NEWS_OUTPUT_DIR=/absolute/output/path python3 -m UK_news_scraper
```

每次執行也會在 Excel 旁產生同名的 `.run.json` 執行摘要，內容包含穩定 `run_id`、邏輯筆數、完整或降級狀態與來源警告。寄信流程應先用 `run_id` 檢查是否已寄送，避免同一期間重複寄信。

翻譯會使用持久快取，未命中內容預設以 4 個有限併發請求翻譯。可用
`UK_NEWS_TRANSLATION_CONCURRENCY` 調整併發數。
翻譯功能透過 `googletrans`／`deep-translator` 所連接的外部翻譯服務處理文字；不應傳送機密、個人或未公開內容。

第一次執行前請先安裝套件：

```bash
python3 -m pip install -r requirement.txt
```

正式建置與 CI 使用固定版本的 `requirement-lock.txt`，更新依賴後應重新驗證並同步該檔案。

## Rust + Tauri 原生預覽版

v2 使用 Rust 抓取與匯出核心，以及 Tauri 2 + React/TypeScript 桌面介面。Python
v1.2.4 在平行驗證完成前仍是正式版；原生版本不需要 Python runtime。

```bash
cd native/apps/desktop
npm ci
npm run build
cd ../../..
cargo build --release --locked -p uk-news-scraper
target/release/UKNewsScraper --check-runtime
target/release/UKNewsScraper --ui
```

Windows 的執行檔位於 `target\release\UKNewsScraper.exe`。macOS 與 Linux 位於
`target/release/UKNewsScraper`。各平台必須在目標作業系統建置，portable ZIP
上限為 35 MiB。v2 只有單一執行檔，不再提供試用期密碼版本。

原生寄送 registry 指令如下；過渡期間舊 Python 指令會在找到原生執行檔時轉送：

```bash
UKNewsScraper delivery-registry claim --summary /absolute/report.run.json
UKNewsScraper delivery-registry complete --delivery-id ID --message-id GMAIL_ID
```

```bash
python3 -m UK_news_scraper --days 14 --output output/本週英國新聞.xlsx
python3 -m UK_news_scraper --since 2026-05-01
python3 -m UK_news_scraper --workers 8
python3 -m UK_news_scraper --profile digital-health --excel-calendar roc
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
- 若未指定 `--output`，原始碼執行會輸出到專案的 `新聞放置區`；封裝版仍使用桌面的 `UK新聞抓取/新聞放置區`。檔名會自動帶入搜尋期間，例如 `20260419-20260519_UK新聞查詢.xlsx`。

輸出 Excel 會包含：

- `全部新聞`：抓到的所有機關新聞。
- `已初步篩選工作表`：分成 `新聞稿` 與 `研究` 兩區。依標題、摘要、詞組精確度與多重訊號計算相關性，達門檻才列入，並附上命中領域、關鍵字、相關性等級與分數。
- `國會研究資料`：Commons Library、Lords Library 與 POST research briefings，包含院別、主題、摘要、識別碼、網頁、PDF 及實際抓取來源。

官方機關的 `guidance`、`report` 與 `publication` 頁面也會放入前兩張新聞工作表，
並以「資料類型」欄與一般 `news` 新聞稿區分。官方頁面只收錄索引直接列出的項目，
且必須有明確發布日期並落在本次查詢期間。

命中關鍵字的資料會在原始工作表中只標黃實際命中的標題或摘要欄位，並依相關性使用深淺不同的黃色（高相關最深、低相關最淺）。廣義詞（例如 `technology`、`innovation`、`platform`）必須有其他訊號才會納入。目前觀測領域包含 `Science & Technology`、AI、資料治理、數位平台、網路安全、半導體與量子技術。

`新聞連結` 欄位會寫入 Excel 超連結，可直接點開原始新聞頁。GOV.UK 機關 feed 會排除 guidance、publication、transparency data 等文件更新，只保留 `/government/news/` 新聞頁。

每筆新聞會用兩列呈現，第一列是英文新聞標題，第二列是透過 `googletrans` 翻譯的繁體中文標題；`編號`、部會、日期、分類與連結會合併跨兩列。

## 目前納入機關

- BIST / DCMS / AI Security Institute / ICO / CMA / UK IPO / GDS
- Ofcom / NCSC / Electoral Commission
- Cabinet Office / NPSA
- UKRI

2026 年 7 月 DSIT 職能拆分後，科學、研究與創新新聞改由 BIST 承接；
電信、線上安全、數位身分與 GDS 相關新聞由 DCMS 承接；AI 策略、
公部門 AI 採用與 AI Security Institute 由 Cabinet Office 承接。舊自訂
設定檔中的 `DSIT` 與 `DBT` 來源會自動遷移到相應的新來源。

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

Rust 預覽版升為正式版前，需用相同期間分別執行 Python 與 Rust，並連續三次記錄完全一致的 logical counts 與 fingerprint v3：

```bash
python3 scripts/compare_parallel_runs.py \
  --python-summary /absolute/python-report.run.json \
  --rust-summary /absolute/rust-report.run.json \
  --history /absolute/parallel-history.json \
  --require-consecutive 3
```

若資料來源在兩次抓取之間更新而造成差異，必須用 `--explanation` 留下可稽核原因；有說明的差異仍會中斷連續三次一致門檻。

測試涵蓋日期區間穩定性、共用去重規則、來源狀態、執行摘要、HTTP
session 重用、翻譯快取、必要 Excel 工作表、結果篩選與排序、取消／來源
重試、設定檔遷移與損壞復原。

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
