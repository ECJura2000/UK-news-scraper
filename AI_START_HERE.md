# 交給 AI 工具執行

這個專案可以交給 Codex、Claude Code、GitHub Copilot CLI 或其他可操作
終端機與檔案的 AI 工具執行。建議使用正式 Release 內的
`UKNewsScraper-版本-Source.zip`，不要把 Windows、macOS 或 Linux 執行檔
誤當成原始碼。

## 下載原始碼

- [最新正式版本](https://github.com/ECJura2000/UK-news-scraper/releases/latest)：
  展開 Assets，下載檔名結尾為 `-Source.zip` 的檔案。
- [目前開發版本 ZIP](https://github.com/ECJura2000/UK-news-scraper/archive/refs/heads/main.zip)：
  適合需要最新修正並願意執行測試的人。
- Git 使用者可以執行：

```bash
git clone https://github.com/ECJura2000/UK-news-scraper.git
cd UK-news-scraper
```

正式 Source ZIP 只包含 Git 已追蹤的專案檔案，不包含 `.git`、虛擬環境、
抓取結果、翻譯快取、寄送紀錄或本機密碼。

## 可直接交給 AI 的指令

將 Source ZIP 解壓縮並用 AI 工具開啟該資料夾後，可以輸入：

> 請先閱讀 AGENTS.md 與 README.md。使用本機可用的 Python 建立 `.venv`，
> 安裝 `requirement-lock.txt`，先執行測試與 runtime check；通過後執行
> `python -m UK_news_scraper`。不要寄送電子郵件，也不要修改
> delivery registry。完成後告訴我 Excel 與 `.run.json` 的位置、邏輯筆數
> 及來源健康狀態。

這段指令預設只抓取及匯出 Excel，不會要求 AI 寄信。

## 人工安裝

macOS 或 Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirement-lock.txt
.venv/bin/python -m UK_news_scraper --check-runtime
.venv/bin/python -m UK_news_scraper
```

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirement-lock.txt
.\.venv\Scripts\python.exe -m UK_news_scraper --check-runtime
.\.venv\Scripts\python.exe -m UK_news_scraper
```

若要啟動桌面介面，將最後一行改為：

```bash
python3 -m UK_news_scraper --ui
```

## 驗收輸出

預設輸出位於專案的 `新聞放置區/`，每次成功執行會產生：

- `{開始日}-{結束日}_UK新聞查詢.xlsx`
- 同名的 `.run.json`

Excel 至少應包含 `全部新聞`、`已初步篩選工作表`、`國會研究資料` 與
`篩選設定`。筆數、執行狀態、來源健康與防重寄識別碼應以 `.run.json`
為準，不要用 Excel 的實體列數推算。

## 電子郵件安全

抓取程式本身不會自動寄信。只有另外設定的排程或 AI 明確操作 Gmail
時才會寄送。若要建立寄送自動化，必須遵守：

1. 附件使用 `.run.json` 的 `output_file`。
2. 寄送前執行 `delivery_registry claim`，只有 `claimed=true` 才能寄。
3. Gmail 明確成功並取得 message ID 後，才執行 `complete`。
4. 不確定是否送出的連線錯誤不得直接重送或釋放 claim。
5. 密碼、OAuth token、收件者資料及本機輸出不得提交到 Git。

完整維護與寄送復原流程請見
[docs/MAINTENANCE.md](docs/MAINTENANCE.md)。
