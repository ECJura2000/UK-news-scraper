# 災難復原演練

1. 複製 registry 與輸出目錄到測試位置。
2. 模擬 registry 寫入中止、錯誤 JSON、輸出失敗與卡住 claim。
3. 執行 `python3 -m pytest tests/test_delivery_registry.py tests/test_fault_injection.py tests/test_integration_output_pipeline.py`。
4. 確認舊 registry 未破壞、重複寄送被阻止且 claim 僅在人工確認後釋放。
5. 記錄演練日期、復原時間、資料損失與改善事項。
