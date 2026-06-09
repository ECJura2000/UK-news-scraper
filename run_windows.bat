@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "UKNewsScraper.exe" (
  echo 找不到 UKNewsScraper.exe
  echo 請確認 run_windows.bat 和 UKNewsScraper.exe 放在同一個資料夾。
  pause
  exit /b 1
)

echo 請輸入搜尋期間，直接按 Enter 則預設 14 天。
echo 範例：
echo   30
echo   20160501
echo   20160501～20160515
echo.
set /p PERIOD=搜尋期間：

if "%PERIOD%"=="" (
  "UKNewsScraper.exe"
) else (
  "UKNewsScraper.exe" %PERIOD%
)

echo.
echo 執行完成。Excel 會輸出到桌面\UK新聞抓取\新聞放置區
pause
