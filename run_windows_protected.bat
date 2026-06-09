@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "UKNewsScraper_protected.exe" (
  echo 找不到 UKNewsScraper_protected.exe
  echo 請確認 run_windows_protected.bat 和 UKNewsScraper_protected.exe 放在同一個資料夾。
  pause
  exit /b 1
)

echo 請輸入搜尋期間，直接按 Enter 則預設 14 天。
echo 範例：
echo   30
echo   20160501
echo   20160501～20160515
echo.
echo 第一次執行後 30 天內免密碼；超過 30 天後再執行會要求輸入密碼。
echo.
set /p PERIOD=搜尋期間：

if "%PERIOD%"=="" (
  "UKNewsScraper_protected.exe"
) else (
  "UKNewsScraper_protected.exe" %PERIOD%
)

echo.
echo 執行完成。Excel 會輸出到桌面\UK新聞抓取\新聞放置區
pause
