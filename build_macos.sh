#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -r requirement-build.txt
.build-venv/bin/python -m PyInstaller --clean --onefile --name UKNewsScraper run_scraper.py
.build-venv/bin/python -m PyInstaller --clean --onefile --name UKNewsScraper_protected run_scraper_protected.py

echo "macOS executable created: dist/UKNewsScraper"
echo "macOS protected executable created: dist/UKNewsScraper_protected"
