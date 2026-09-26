# Changelog

## 2.3.0 - 2026-09-25

- Added a reviewable directory snapshot for UK central and devolved bodies, courts and tribunals. GOV.UK organisations marked live and three official judicial RSS feeds can be selected in custom JSON profiles; unverified publication pages remain visible but cannot be selected.
- Kept the built-in weekly source selection unchanged, added jurisdiction search in the desktop app, and tagged judgment records distinctly in Excel and previews.
- Excluded BBC scraping and bulk TNA Find Case Law queries. Bounded GOV.UK historical searches, retained partial pages as degraded, and checked judicial RSS date coverage. Added catalog refresh and regression checks shared by Python and Rust.

## 2.2.2 - 2026-09-24

- Set English text in exported Excel workbooks and the desktop interface to Times New Roman, and Chinese text to the platform's 標楷體 family.
- Preserve separate fonts within mixed English and Chinese Excel cells, including titles and headings, without changing workbook data or hyperlinks.

## 2.2.1 - 2026-09-24

- Added an editable JSON topic-profile example to the release and a desktop import action that saves custom topics locally.
- Added a desktop source-worker selector from 1 to 16, used for normal collection and failed-source retry.

## 2.2.0 - 2026-09-23

- Promoted the Rust/Tauri desktop build with date presets, progress and source-health views, result filters, history, and workbook opening.
- Aligned Python and Rust relevance rules around the UK policy review examples while preserving report and delivery contracts.

## 2.1.1 - 2026-09-21

- Ran agency and Parliament collection concurrently, including independent Parliament RSS and topic-archive sources.
- Added bounded source and translation waits so a slow upstream preserves a degraded report instead of blocking the weekly delivery.
- Increased the default source worker pool and reduced the retry pause for the weekly performance target.
- Updated AnyIO and Soup Sieve to patched releases required by the dependency audit.

## 2.1.0 - 2026-09-14

- Improved relevance filtering with repeated-signal deduplication, boilerplate removal, longest-keyword matching, and additional digital sovereignty, Digital ID, and deepfake signals.
- Kept Python and Rust relevance policies synchronized and added regression coverage for the new scoring behavior.

## 2.0.0-alpha.3 - 2026-08-20

- Updated the live source smoke gate to verify the BIST and DCMS successor department pages instead of the former DSIT page.
- Added regression coverage to keep retired DSIT checks out of the source-health workflow.

## 2.0.0-alpha.2 - 2026-08-19

- Replaced the split DSIT and renamed DBT sources with BIST and DCMS successor feeds.
- Reassigned AI, digital government, online safety, telecoms, and science topics to the responsible departments.
- Added automatic `DSIT` and `DBT` source migration for existing Python and Rust profiles.
- Updated `h2` to 4.4.1 and `hpack` to 4.2.0 to address CVE-2026-71554 in the locked Python dependencies.

## 2.0.0-alpha.1 - 2026-08-06

- Added the parallel Rust core and Tauri 2 + React desktop application.
- Preserved fingerprint v3, four-sheet Excel, profile and delivery-registry contracts.
- Added native Guidance, Report, Publication, Parliament and translation-provider support.
- Removed the separate password-protected executable and all related build assets.
- Added three-platform native CI and a 35 MiB portable archive gate.

## 1.2.4 - 2026-08-06

- Added official guidance, report, and publication collection alongside RSS news.
- Added NCSC disruption-recovery guidance pages and official supplemental indexes for UK agencies.
- Added content-type labels to Excel output and source warnings for partial official-page failures.

## 1.2.3 - 2026-08-04

- Synchronized the release line with the latest merged checkout and republished the current source package as the next patch version.

## 1.2.2 - 2026-07-29

- Added a clearly named tracked-source ZIP to every formal release.
- Added human and AI-agent quick-start guidance for source installation and execution.
- Added release checks that require the source archive and include it in checksums and size budgets.

## 1.2.1 - 2026-07-29

- Added score/date result filters, sortable columns, visible counts, and deterministic core-first highlight priority.
- Added cooperative cancellation, safe close behavior, and failed-source-only retry with successful-data preservation.
- Added recent-run history for reopening workbooks and run summaries.
- Added profile backups, legacy migration, corrupt-file quarantine, import conflict confirmation, and default restoration.
- Split reusable desktop components and result-state logic into independently tested modules.

## 1.2.0 - 2026-07-28

- Added a high-DPI desktop research workspace with Gregorian and ROC date controls.
- Added reusable filter profiles, selectable UK sources, and three keyword-strength levels.
- Added configurable relevance scoring with exact keyword highlighting in the desktop results.
- Added Gregorian or ROC Excel date formatting and reproducible filter settings in each workbook.
- Changed default report names to `{start}-{end}_UK新聞查詢.xlsx`.
- Added a Windows UI launcher while preserving the existing CLI and delivery-registry workflow.

## 1.1.1 - 2026-07-13

- Added weighted relevance scoring and deterministic Excel highlighting.
- Added packaged-runtime registry checks on Windows, macOS, and Linux.
- Added consolidated checksums, size manifests, and strict release size budgets.

## 1.0.0 - 2026-06-14

- Added typed delivery state, idempotent claim recovery, schema validation, observability, and selective retry.
- Added integration, fault-injection, property, coverage, security, benchmark, source smoke, and cross-platform build checks.
- Added formal project delivery, UAT, long-term-run, and disaster-recovery procedures.

## 0.1.0

- Previous development release.
