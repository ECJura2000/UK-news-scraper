#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -r requirement-build.txt
.build-venv/bin/python -m PyInstaller --clean --noconfirm --onefile --collect-data tzdata --name UKNewsScraper run_scraper.py

chmod +x dist/UKNewsScraper

echo "Linux executable created: dist/UKNewsScraper"
