# AI Agent Instructions

These instructions apply to the entire repository.

## Start Here

1. Read `README.md`, `AI_START_HERE.md`, and `ARCHITECTURE.md`.
2. Use the repository-local `.venv` when available.
3. Install runtime dependencies from `requirement-lock.txt`.
4. Install test dependencies from `requirement-dev.txt` only when validating changes.

## Required Validation

Run these checks before claiming a code change is ready:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -q UK_news_scraper tests scripts
.venv/bin/python -m UK_news_scraper --check-runtime
```

On Windows, use `.\.venv\Scripts\python.exe` instead.

## Runtime Contract

- The default CLI command is `python -m UK_news_scraper`.
- The desktop UI command is `python -m UK_news_scraper --ui`.
- Default output belongs in `新聞放置區/`.
- A successful run produces an Excel workbook and a same-name `.run.json`.
- Preserve the worksheets `全部新聞`, `已初步篩選工作表`, `國會研究資料`,
  and `篩選設定`.
- Treat `.run.json` logical counts and source health as authoritative. Do not
  infer counts from physical Excel rows.
- Preserve English source text when translation fails and report the warning.

## Delivery Safety

Do not send email unless the user explicitly asks for delivery.

- Read the attachment path from `.run.json` field `output_file`.
- Claim with `python -m UK_news_scraper.delivery_registry claim --summary ...`.
- Send only when the response contains `claimed: true`.
- Complete the claim only after Gmail returns an explicit message ID.
- Do not release or retry an uncertain transport result until sent mail is checked.
- Never edit `sent_run_ids.json` directly.
- Never commit recipients, credentials, tokens, generated workbooks, run summaries,
  translation caches, or local application data.

## Change Discipline

- Preserve CLI compatibility unless the change is explicitly versioned.
- Add regression tests for behavior changes.
- Keep source-specific scraping failures isolated and represented in source health.
- Do not weaken release checksum, runtime smoke, or size gates.
- Build platform executables on their target operating system.
