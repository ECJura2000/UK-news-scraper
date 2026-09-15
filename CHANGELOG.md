# Changelog

## Unreleased

- Added profile schema v2 hybrid Boolean/BM25 filtering with synonyms, per-topic thresholds, four-decimal scoring, and Python/Rust parity.
- Added the DSIT transitional source, DBT-to-BIST supplemental feed, GOV.UK Content API publisher checks, reorganisation ownership metadata, audit warnings, and fingerprint v4.
- Replaced Ofcom's blocked legacy RSS with the GOV.UK Atom feed plus filtered Google News supplementation.
- Switched Electoral Commission collection to its official sitemap and filtered database-page noise from fallback results.
- Retried all HTTP 403 responses with browser TLS so NPSA can recover from non-standard access-denied pages without false degraded warnings.

## 2.0.0-alpha.3 - 2026-08-20

- Updated the live source smoke gate for the initial BIST and DCMS successor transition; the later schema v2 audit restores DSIT as an independently required transitional source while its official feed remains active.

## 2.0.0-alpha.2 - 2026-08-19

- Replaced the split DSIT and renamed DBT sources with BIST and DCMS successor feeds.
- Reassigned AI, digital government, online safety, telecoms, and science topics to the responsible departments.
- Added automatic `DSIT` and `DBT` source migration for existing Python and Rust profiles.
- Updated `h2` to 4.4.1 and `hpack` to 4.2.0 to address CVE-2026-71554 in the locked Python dependencies.

## 2.0.0-alpha.1 - 2026-08-06

- Added the parallel Rust core and Tauri 2 + React desktop application.
- Preserved the four-sheet Excel, profile and delivery-registry contracts; fingerprint v4 is introduced in the hybrid-filter release.
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
