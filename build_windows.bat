@echo off
setlocal

py -3 -m venv .build-venv
.build-venv\Scripts\python -m pip install --upgrade pip
.build-venv\Scripts\python -m pip install -r requirement-build.txt
.build-venv\Scripts\python -m PyInstaller --clean --noconfirm --onefile --collect-data tzdata --name UKNewsScraper run_scraper.py

echo Windows executable created: dist\UKNewsScraper.exe
