# 手機手動雲端執行指南

## 架構與實際變更

手機瀏覽器 → GitHub Actions `workflow_dispatch` → GitHub Linux runner 抓取與產製 Excel → 驗證 Excel/JSON → GitHub Artifacts 備份 → rclone OAuth 上傳 Google Drive。

手機只送出指令，不負責運算；送出後可關閉網頁，電腦不必開機。本工作流程沒有 `schedule` 或 `push` 觸發。Repository 原有測試、Release 與來源 smoke 工作流程維持原設定。

新增：

- `.github/workflows/mobile-news.yml`：手機手動入口與兩份儲存。
- `scripts/cloud-delivery.mjs`：驗證日期、報表配對、產出 Actions 摘要與已驗證上傳集合。
- `scripts/upload-cloud-drive.sh`：從 Actions Secret 建立臨時 rclone 設定，上傳後核對檔案，最後刪除臨時設定。
- 不更動既有爬取、分類、排序或 Excel 格式。

英國：使用 Python 3.13 與 `requirement-lock.txt`，入口 `python -m UK_news_scraper`。日期留白時以臺北當日回推 days 天並另含今日（預設 7，即最多 8 個日曆日）；指定起訖時 days 不生效。保留原四張工作表與同名 `.run.json`。

Artifacts 保存 30 天，仍受 Repository/組織政策、配額及帳務限制；Drive 持續保留到你自行刪除或儲存容量用完。Runner 本機檔案不是持久儲存。成功產檔後先存 Artifacts，再上傳 Drive；Drive 授權失效或上傳錯誤會使工作流程失敗，但已上傳的 Artifacts 可下載。程式或建置失敗時，不一定能產生 Excel；已有的 collection.log 和輸出檔會嘗試保存為診斷 Artifacts。

## 首次設定（建議先在 Mac 完成一次）

### 1. 建立你自己的 Google OAuth client

到 Google Cloud Console 建立或選擇個人專用專案，啟用 Google Drive API。
在 Google Auth Platform 設定 Branding/Audience；個人 Gmail 選 External，Testing 時將自己加入 Test users。
在 Clients 建立 Desktop app，保留 client ID 與 client secret。不要將憑證貼到聊天或提交 Git。

正式長期使用時，將 OAuth app Publishing status 切到 In production。External 且 Testing 的 Drive 授權 refresh token 通常僅 7 天有效；這與爬蟲程式是否正確無關。Google 若顯示授權審查或組織限制，依該頁面處理，不保證所有帳號皆能自行略過。

### 2. 在 Mac 授權專用 rclone remote

```bash
brew install rclone
mkdir -p "$HOME/.config/news-cloud"
chmod 700 "$HOME/.config/news-cloud"
rclone config --config "$HOME/.config/news-cloud/rclone.conf"
```

這份檔案只供新聞上傳，不要複用含其他帳號的 rclone 設定。
依互動提示設定：

| 欄位 | 值 |
| --- | --- |
| New remote 名稱 | `gdrive`（必須相同） |
| Storage | `drive` |
| client_id / client_secret | 前一步自己的 Desktop app 憑證 |
| scope | `drive.file`：只存取此應用程式建立的檔案及資料夾 |
| Service account | 留白 |
| Auto browser authentication | Yes；登入你要儲存 Excel 的 Google 帳號 |
| Shared Drive | 個人「我的雲端硬碟」選 No |
| Config encryption | 此工作流程不支援 rclone 設定檔加密；機密由 GitHub Actions Secrets 保護 |

接著**使用同一個 rclone remote 建立**資料夾：

```bash
rclone mkdir gdrive:新聞雲端報表 --config "$HOME/.config/news-cloud/rclone.conf"
```

到 Google Drive 網頁打開這個新資料夾，複製網址 `/folders/` 後面的資料夾 ID。
因採 `drive.file`，不要換成先用網頁建立的另一個資料夾；它可能不在此 OAuth app 可存取範圍。
`root_folder_id` 是定位設定，不能自行縮減已授予的 OAuth 權限；此方案的權限縮減來自 `drive.file`。

rclone 的共用 client ID 正在退場，請使用自己的 client ID。
ChatGPT 已連接的 Google Drive 授權不會自動傳給 GitHub runner；這份 OAuth 是 GitHub Actions 專用。

### 3. 在兩個 Repository 分別設定

進入 `Settings → Secrets and variables → Actions`：

| 類型 | 名稱 | 內容 |
| --- | --- | --- |
| Repository secret | `RCLONE_CONFIG` | 專用 rclone.conf 的完整文字，包括 `[gdrive]`、type、client_id、client_secret、scope 與 token |
| Repository variable | `DRIVE_FOLDER_ID` | 前一步的資料夾 ID，不是完整網址 |

可使用本機編輯器開啟 rclone.conf，貼到 GitHub 的 Secret 欄位；不要貼到 issue、PR、README 或對話。兩個 Repository 可以使用同一份設定和同一個資料夾 ID。GitHub Secrets 只在受授權的 Actions 工作流程中提供。

這裡設定的是 **GitHub Repository Secrets**，不是 Codex Environment 的 Secrets。Codex 的環境網路開關也不會決定 GitHub runner 的網路權限。

Repository 若停用 Actions，到 `Settings → Actions → General` 啟用並允許工作流程使用的 actions。沒有必要增加 GITHUB_TOKEN 寫入權限；工作流程使用 `contents: read`。

## 手機操作

1. 合併本次 PR，讓 `mobile-news.yml` 存在 default branch (`main`)；否則 Actions 的手動按鈕可能不出現。
2. Safari/Chrome 登入 GitHub，開啟目標 Repository → Actions →「手機手動抓取新聞」。
3. 按 Run workflow，選 main；輸入起訖日期或兩欄同時留白，再按 Run workflow。
4. 可關閉頁面；稍後回來查看工作流程摘要、來源狀態與錯誤。
5. 打開 Google Drive App → 新聞雲端報表 → 專案名稱 → 本次 run 資料夾 → Excel。
6. 備份在 GitHub 該次執行頁最下方的 Artifacts；通常下載為 ZIP。

手機版若未顯示 Run workflow，可在 Safari/Chrome 選「要求桌面網站」。本方案以手機瀏覽器為正式操作入口，不依賴 GitHub App 是否提供同一按鈕。

起訖日期採西元 `YYYY-MM-DD`，包含迄日當日。任意字串不會直接插入 shell 指令，日期參數先驗證再透過 shell 陣列傳入 CLI。

## 檔案位置與結果判讀

```text
新聞雲端報表/
  UK-news-scraper/
    run-<GitHub run ID>-attempt-<重跑次數>/
      UK新聞查詢.xlsx
      UK新聞查詢.run.json
  taiwan-government-news-scraper/
    run-<GitHub run ID>-attempt-<重跑次數>/
      本週新聞整理….xlsx
      news_scraper_run_….json
      news_scraper_run_….complete
      latest_run.json
```

檔案維持 `.xlsx`，不轉成 Google Sheets。每次執行或重跑使用獨立遠端資料夾，避免覆蓋；上傳用 copy，不用會刪除目的端檔案的 sync。Drive 上傳後執行 rclone check 核對。

台灣的 latest_run.json/完成標記保留原始 runner 絕對路徑，提供稽核證據；下載後不能直接把指標當成本機可開啟路徑。

英國報表狀態為 complete/degraded，並保留各來源健康與翻譯失敗警告。

Actions 綠燈只表示工作流程與儲存步驟成功；抓取完整性以摘要中的 status、warnings/failed_sources、quality.alert_reasons 及 source_health 為準。降級報表仍保存，並在 Actions 發出警告；JSON 供逐來源追溯。

雲端 IP 可能遇到官方站點防機器人、429 或驗證頁；不承諾與家用網路結果完全一致。先以短期間跑一次並檢查 JSON。台灣 runner 每次新建環境，不自動還原過去週次的品質基準或 HTTP 快取，因此跨週異常偵測不具持久歷史；本版不把快取當成果。

## 驗收

- 首次選兩天內的日期區間，確認有 Excel、JSON 與來源狀態；無新聞也可能合法，但必須查看來源診斷。
- Drive App 能開啟 `.xlsx`，GitHub 同次 run 能下載 Artifacts。
- 再次手動執行，確認新增 run 資料夾且舊檔仍保留。
- 若 Drive 授權失效，先從 Artifacts 取得成果；本機執行 `rclone config reconnect gdrive: --config "$HOME/.config/news-cloud/rclone.conf"`，再更新兩個 Repository 的 RCLONE_CONFIG。
- 使用 Rerun all jobs 會重新抓取，屬新 attempt；它不是只重新上傳既有 Excel。

官方參考：
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
- https://rclone.org/drive/
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/workspace/drive/api/guides/about-shareddrives
