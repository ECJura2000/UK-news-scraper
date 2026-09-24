# Deployment And Maintenance

## Weekly Runtime And Fallback

Run the verified `UKNewsScraper` Rust executable with the built-in `uk-tech-law`
profile and Gregorian dates. Validate the workbook's four sheets and use the
same-name `.run.json` as the authority for status, counts, source health,
`output_file`, and `delivery_id`. A valid `degraded` report remains deliverable.

If Rust has not produced a valid workbook and run summary, and no delivery claim
has been obtained for that period, run the Python implementation for the same
dates as a fallback. Never launch the fallback after obtaining a claim or to
replace a valid `degraded` report. Both implementations use the same delivery ID
for the same logical data. Before sending, claim the summary's delivery ID and
proceed only when `claimed=true`; uncertain Gmail transport requires checking
Sent while retaining the claim.

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
