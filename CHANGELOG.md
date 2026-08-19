# Changelog

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
