# UK News Scraper 專題報告

## 問題與需求

英國政府、監管機關與國會研究資料分散於 RSS、HTML 與 API。本系統統一抓取、分類、去重、翻譯與 Excel 輸出，並避免相同報告被重複寄送。

## 架構與資料結構

agency registry 建立 scraper，thread pool 執行來源，domain models 保存新聞與國會資料，`set`／`dict` 完成去重與 delivery claim，JSON registry 以原子寫入保存寄送狀態。詳見 `ARCHITECTURE.md`。

## 複雜度、效能與驗證

去重平均 O(n)，排序 O(n log n)，delivery claim 查找平均 O(1)。容量結果見 `PERFORMANCE.md`。驗證包含 fixture、整合、property、故障注入、跨平台 build、安全掃描、benchmark 與來源 smoke test。

## 限制與未來工作

來源可能受 Cloudflare、API 改版或翻譯服務限制。未來應累積長期來源健康資料、完成真人 UAT 並移除無修正版漏洞的暫時安全豁免。
