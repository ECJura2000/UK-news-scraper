# 國家標準時間與程式校時

Python CLI、Python 桌面版與 Rust 原生桌面版預設使用 UDP 123，查詢：

- `tock.stdtime.gov.tw`
- `watch.stdtime.gov.tw`
- `time.stdtime.gov.tw`
- `clock.stdtime.gov.tw`
- `tick.stdtime.gov.tw`

這五個位址列於[國家時間與頻率標準實驗室的 NTP 資源頁](https://www.stdtime.gov.tw/Time/ntp/resource.htm)。
程式採 SNTP 的單次 client/server 交換，依 [RFC 5905](https://www.rfc-editor.org/rfc/rfc5905.html)
的四個時間戳估算校正差值與網路延遲，從有效回應中選擇往返延遲最小的一筆。
這是程式內的時間校正，不修改作業系統時鐘，不需要管理員權限。

## 作用範圍

CLI 先校時，再以 `Asia/Taipei` 日曆日解析預設日期與檔名。
桌面版向後端取得校正時間，套用到最近 7／14／30 天及初始日期；
使用者自行輸入的日期不會被背景更新覆寫。介面顯示國家標準時間來源，
或明確顯示本機時間與失敗原因。

報表產生時間、HTTP 擷取時間、來源新鮮度、記錄時間與 HTTP 日期格式的
`Retry-After` 使用同一套程式時計。英國文章原始發布日期及其時區解析不改寫。
內部仍保存 UTC 時間戳；介面與查詢日曆維持台北時間。抓取期限、重試等待、
取消與效能耗時仍使用單調時計，校時差值不會拉長或縮短這些期限。

`.run.json` 新增可選的 `time_sync`：`source`、`server`、`checked_at`、
`offset_seconds`、`round_trip_seconds`、`warning` 和各伺服器的 `attempts`。
Python 另保存取摘要時的 `utc`。這些觀測資訊不參與 fingerprint v3 或
`delivery_id`，舊摘要仍可讀取；未量測的偏移以 null 或缺少欄位表示。

## 查詢期限與失敗處理

每次同步最多等待 2 秒，並行向五台伺服器各發一個查詢；每台 UDP 接收等待
上限為 0.8 秒。DNS 阻塞也不會讓呼叫者超過整體等待期限。回應需通過
長度、NTP 版本、server 模式、同步狀態、stratum、originate timestamp
與延遲檢查；拒絕查詢、過期或錯配封包不採用。

成功後以標準時間加單調時計的經過時間維持程式時計，快取 30 分鐘。
桌面版每 30 分鐘更新；每次執行也檢查快取。失敗後使用本機時間、顯示
警告並記錄各台結果；一般執行在 60 秒內不重複發出失敗查詢。
超過 30 分鐘的校時樣本不能繼續宣稱是有效 NTP 時計。
網路不可用時仍可產出報表，校時警告獨立於文章來源的完整／降級狀態。

NTP 32-bit 秒數的 2036 年 rollover 以本機時間附近的 era 展開；這假設
本機日期與正確日期相差少於 68 年。單次網路取樣是校正估計，不能當成
特定精度的保證。

## 手動診斷

```bash
.venv/bin/python -m UK_news_scraper --check-time
cargo run --locked -p uk-news-scraper -- --check-time
```

這兩個指令顯示 JSON 校時結果，不抓新聞、不建立寄送 claim；未取得有效
NTP 回應時回傳碼為 1。正常查詢仍支援原有指令，會自動同步。
`--check-runtime` 維持離線檢查，不觸發 NTP。

隔離測試或明確停用時可設定 `UK_NEWS_TIME_SYNC=off`，摘要會記錄使用
本機時間與停用原因。單元測試不連接公開 NTP；實際連線證據另外保存於
本機 `新聞放置區/`，不提交 Git。
