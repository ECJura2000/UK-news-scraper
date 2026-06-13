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

