# 品質與效能診斷

這些工具不改變採集、去重、篩選與翻譯規則，不建立或釋放寄送 claim。
輸出的診斷報告保存在 `新聞放置區/`，不提交到 Git。

## 每日來源解析檢查

```bash
.venv/bin/python -m scripts.smoke_sources --output 新聞放置區/source-smoke.json
```

使用內建 `uk-tech-law` 的 13 個機關，加上國會的 RSS 與主題頁，重用正式
採集器、網域限流、期限與來源歸屬規則；不是查詢整份機關名錄。
預設檢查最近 60 天，`--days` 可選 1–90 天。檢查標題、日期區間、文章
連結、機關名稱／網域、國會網域與解析候選數。Google News 備援使用正式
解析器既有的發布者核對；缺少發布者資訊仍有既有規則的限制。

回傳碼 0 表示沒有發現取得失敗、解析異常或不合契約的文章；1 表示有
異常。正常零筆不視為失敗。備援與歷史涵蓋警告仍完整保存在
`source_health`，回傳 0 不代表歷史期間完整或所有資料都來自官方管道。
JSON 保存來源健康、端點 HTTP 狀態、回應雜湊與逐項異常；原始回應內容
不在這份 JSON。每個來源失敗獨立記錄，成功來源資料仍可檢查。

每日 GitHub workflow 安裝鎖定依賴並執行這個檢查，異常時工作失敗；
無論成功與否都嘗試保存診斷 JSON，保留 14 天，不改動正式 release gates。

## 固定篩選驗證集

`tests/fixtures/relevance_quality_v1.json` 保留 2026-09-14 四週分析中的
41 個不重複標題：22 個相關、9 個不相關、10 個邊界案例。
歷史分類不是這次重新人工審閱的結果；每筆 `basis` 說明來源。
`baseline_included` 是 v2.3.6 自動判定結果，不能當作人工分類。

```bash
.venv/bin/python -m scripts.evaluate_relevance \
  --output 新聞放置區/quality/relevance-baseline.json
# 調整規則後，使用同一份固定案例與已保存的基準。
.venv/bin/python -m scripts.evaluate_relevance \
  --baseline 新聞放置區/quality/relevance-baseline.json \
  --output 新聞放置區/quality/relevance-candidate.json
```

報告包含案例雜湊、主題設定雜湊、誤選、漏選、分數與命中詞。
有新漏選或新誤選時，比較指令回傳 1。改變案例集後不可沿用舊基準。
邊界案例獨立列出，不計入二元指標，不限制其入選決定。
Python 與 Rust 測試都使用同一份案例，保護原本正確的案例不退步，並限制
總誤選不超過 1、漏選不超過 3。改善這四個已知案例前，應核對原文與範圍，
不可為了測試數字改寫人工分類或降低品質門檻。

指標只代表這批歷史、標題為主的樣本；不是所有新聞的準確率或召回率。
此工具單獨評估相關性規則；首頁排除等採集規則有另外的回歸測試。
之後可加入經人工核對的完整標題、摘要與來源 URL，更新版本並重新建立基準。

## 效能紀錄與可比較基準

桌面「每週報表」顯示摘要寫入前的總耗時、各階段耗時、翻譯快取與請求／
重試／429 次數。重試明確標為本次重試。舊報表未量測的欄位顯示「未記錄」，
不當作零秒。各階段可能重疊，不能相加還原總耗時。

每次量測前，記錄當次程式版本（有本機變更時也保存檔案或差異雜湊）、
機器識別與翻譯快取條件。不要把目前環境補寫到過去的摘要。
`cache-key` 應記錄執行前快取的雜湊，空快取可使用固定值 `empty`。
機器識別可用本機代號，無須透露使用者或主機名稱。

```bash
.venv/bin/python -m scripts.performance_baseline record \
  --summary /absolute/report.run.json \
  --revision EXECUTED_REVISION --machine LOCAL_MACHINE \
  --cache-state warm --cache-key PRE_RUN_CACHE_HASH \
  --output 新聞放置區/performance/run-1.baseline.json
# 每次不同的實際執行保存一份；重複匯入同次執行不增加樣本數。
.venv/bin/python -m scripts.performance_baseline report \
  新聞放置區/performance/*.baseline.json \
  --output 新聞放置區/performance/baseline-report.json
```

工具按相同日期、來源、設定雜湊、程式版本、執行環境、機器、快取、
來源健康、邏輯筆數與資料 fingerprint 分組，報告中位數、p95、最小／最大值。
跨週日期或上游內容變動會分組，不能把資料減少當成加速。
完整與降級、完整執行與重試分組；只有至少三次可比且完整的正常執行才標為
`baseline_ready: true`。單次或未實測的舊報表不能建立基準。
這次加入量測呈現與比較工具，不宣稱已取得三次正常生產基準或任何加速幅度。
詳見 [PERFORMANCE.md](../PERFORMANCE.md)。

## 來源警告的處理建議

桌面來源健康表保留原始警告，另顯示以下建議。複合警告可顯示多種原因。
分類是對既有文字的保守判讀，不改變摘要狀態或後端重試選取。

| 類型 | 建議 |
| --- | --- |
| 取得失敗 | 稍後重試；網站限流或封鎖持續發生時檢查官方端點 |
| 解析需檢查 | 核對原始回應與解析器；單純重試可能無法改善 |
| 期間涵蓋不足 | 改用可分頁的來源或縮短查詢期間 |
| 使用備援 | 核對官方原文與發布日期；官方恢復後再重試 |
| 發布頻率需核對 | 核對官方近期發布情況與健康門檻 |
| 期間內未取得資料 | 零筆不等於失敗；有預期文章時再核對 |
| 未知警告 | 保留原文，提示使用者查核，不自行猜測原因 |
