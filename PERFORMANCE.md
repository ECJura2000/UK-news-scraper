# Performance And Capacity Benchmark

Reference run on 2026-06-13:

```bash
python3 scripts/benchmark_capacity.py --sizes 1000 10000 100000 --workers 1 4 6 13
```

## Dedupe

| Records | Best | Mean | P95 | Peak memory |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.472 ms | 1.118 ms | 1.925 ms | 0.099 MB |
| 10,000 | 5.100 ms | 6.821 ms | 8.476 ms | 1.281 MB |
| 100,000 | 68.630 ms | 82.235 ms | 95.174 ms | 8.994 MB |

## Synthetic I/O Concurrency

| Workers | Best | Mean | P95 |
| ---: | ---: | ---: | ---: |
| 1 | 158.822 ms | 177.101 ms | 193.705 ms |
| 4 | 40.512 ms | 40.609 ms | 40.683 ms |
| 6 | 27.634 ms | 27.842 ms | 28.191 ms |
| 13 | 13.304 ms | 13.372 ms | 13.431 ms |

Synthetic I/O isolates thread-pool scheduling. Real source limits and health results remain
the deciding factors for the production worker count.


## Phase 0 run instrumentation

Both runtimes add `performance` schema version 1 to `.run.json`. Existing summaries
remain readable. Diagnostics do not enter fingerprint v3 or delivery identity;
collection, relevance, ordering, translation policy, and workbook contents are
unchanged. Full-text enrichment is not implemented: `detail_fetch_enabled` is
false, and no detail-request savings are claimed.

### Time boundaries

All durations are seconds from a monotonic clock. `total_wall_seconds` starts at
run entry (including retry-data loading and output-lock waiting where applicable)
and ends immediately before summary serialization. The terminal reports
`summary_write_seconds` and `artifacts_complete_seconds` after successful writes.
A retry's `run_kind` is `retry`; its timers and HTTP counters never include the
previous run. Final workbook counts can include preserved records.

| `stages` field | Measurement |
| --- | --- |
| `collection_wall_seconds` | Caller wait for agency and Parliament collection; parallel source times are not added |
| `dedupe_work_seconds` | Sum of existing dedupe operation durations, including parser, merge, and export calls |
| `relevance_seconds` | Existing weighted relevance evaluation |
| `translation_seconds` | Translation, including cache reads/writes and English fallback |
| `excel_write_seconds` | Workbook construction, save and existing verification; excludes translation |
| `json_write_seconds` | Rust `.run.data.json` serialization and atomic write; Python has no separate data JSON and reports `null` |

Dedupe work can overlap collection, relevance, or Excel timings, and concurrent
worker durations can overlap one another. These stages must **not** be summed to
reconstruct total wall time. Summary serialization is excluded from the summary's
own timings to avoid rewriting the report merely to measure itself.

### Counts and network costs

`counts.agency` and `counts.parliament` use the same definitions:

- `list_items_count`: `null`. Raw pre-date-filter totals are not consistently
  available from existing adapters; zero would incorrectly imply an empty list.
- `candidate_count`: sum of existing source-health candidates for this run's
  fetched sources. Parser-specific candidates may include malformed records and
  duplicates; this is not a universal raw discovery count.
- `source_output_count`: sum of fetched source-health item counts before global
  combination (can count the same record through multiple routes).
- `date_filtered_count`: collection records remaining in the requested interval
  at the orchestration boundary. Existing source dedupe has already occurred.
- `deduped_count`: unique newly fetched records at that boundary. Because date
  filtering and dedupe already occur inside sources, these two counts commonly
  match; they are not evidence of a new standalone dedupe stage.
- `final_output_count`: all records in the final output, including preserved
  records on a retry; equals the corresponding authoritative summary count.
- `relevant_output_count`: records included by current relevance rules; equals
  the corresponding filtered summary count.

`http` contains `list`, `search_api`, `fallback`, and `translation` buckets, each
with `attempted_count`, `retry_count`, and `rate_limited_count`. Attempts are
counted when a transport call starts, including failures; waiting for a host slot
or a job that never starts is not an attempt. `retry_count` counts transport-loop
retries, not whole-source reruns. Every received 429 is counted. GOV.UK search and
Parliament API requests are `search_api`; Google News and Python's browser-TLS
fallback are `fallback`; other source requests are `list`. Translation requests
use Rust provider instrumentation or Python HTTPX hooks, so cache hits do not
inflate HTTP counts. These are explicit client calls, not TCP packets or automatic
redirect hops. Python's production requests adapter currently has zero internal
urllib3 retries. Changing that policy requires extending instrumentation first.

`runtime`, `runtime_version`, `workers`, `translation_cache_hits`, and
`translation_cache_misses` provide comparison context. Cache counts are unique
texts looked up per translation batch, not article counts. Old summaries default
to empty/zero diagnostic values and must not be treated as measured baselines.

### Establishing a baseline

Collect 3–5 normal weekly runs before selecting the next optimization. Compare
matching date windows, selected sources, profile/hash, runtime, code revision,
workers, machine and translation-cache conditions. Record code revision and cache
conditions alongside the summaries. Keep full runs separate from retries and
complete runs separate from degraded runs; compare source-health results and
logical record identities alongside elapsed time. Replay saved responses for
quality comparisons when upstream content can change. Do not claim a 20% speedup
from a single run, a smaller output, or synthetic concurrency benchmarks.
