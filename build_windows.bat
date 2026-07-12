@echo off
setlocal

py -3 -m venv .build-venv
.build-venv\Scripts\python -m pip install --upgrade pip
.build-venv\Scripts\python -m pip install -r requirement-build.txt
.build-venv\Scripts\python -m PyInstaller --clean --noconfirm --onefile --collect-data tzdata --name UKNewsScraper run_scraper.py
.build-venv\Scripts\python -m PyInstaller --clean --noconfirm --onefile --collect-data tzdata --name UKNewsScraper_protected run_scraper_protected.py

echo Windows executable created: dist\UKNewsScraper.exe
echo Windows protected executable created: dist\UKNewsScraper_protected.exe
