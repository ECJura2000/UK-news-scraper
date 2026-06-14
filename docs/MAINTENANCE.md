# Deployment And Maintenance

## Add Or Repair A Source

1. Update the agency configuration and parser.
2. Validate API payloads in `external_schemas.py`.
3. Add fixture, schema, and fault-injection tests.
4. Run pytest, compileall, and the small CI benchmark.

## Dependencies And Performance

- Update `requirement-lock.txt`, `requirement-dev.txt`, and build requirements together.
- Run `python3 scripts/benchmark_capacity.py --sizes 1000 10000 100000`.
- Review benchmark artifacts and observability warnings before release.
- CI compares results with `benchmarks/baseline.json`; update it only after reviewing an intentional performance change.
- The scheduled non-blocking `source smoke` workflow checks representative upstream endpoints.
- Security audit ignores only `PYSEC-2022-252` because `deep-translator` currently has no fixed release.
- Append verified run summaries with `python3 scripts/record_long_term_run.py --input <summary.run.json>` for at least two weeks before presenting stability claims.

## Recover A Delivery Claim

Confirm that no email was sent, then use:

```bash
python3 -m UK_news_scraper.delivery_registry recover --delivery-id <id> --confirm-release
```

Never release a claim without checking the mailbox first; doing so can permit a duplicate send.
