# 免安裝 Python 的可攜版

GitHub Release 會提供 Windows、macOS 與 Linux x86_64 的 ZIP。使用者不需要安裝 Python、pip、VS Code 或其他開發工具。

## Windows

1. 下載 Windows ZIP。
2. 解壓縮。
3. 雙擊 `run_windows.bat`。
4. 輸入天數、起始日期或日期區間；直接按 Enter 會使用預設 14 天。

## macOS

下載並解壓縮 macOS ZIP，在該資料夾開啟終端機後執行：

```bash
chmod +x UKNewsScraper
./UKNewsScraper
```

若 Gatekeeper 阻擋，請在 Finder 對執行檔按右鍵選擇「打開」，或到「系統設定 > 隱私權與安全性」允許執行。

## Linux x86_64

下載並解壓縮 Linux ZIP，執行：

```bash
chmod +x UKNewsScraper
./UKNewsScraper
```

## 日期範例

```bash
./UKNewsScraper 30
./UKNewsScraper 20160501
./UKNewsScraper 20160501～20160515
```

未指定輸出位置時，Excel 會寫入桌面的 `UK新聞抓取/新聞放置區`。

## 驗證下載檔案

每個 ZIP 都附有同名 `.sha256`。Linux／macOS 可用 `sha256sum -c`；Windows 可用 PowerShell 的 `Get-FileHash` 計算後比對。
