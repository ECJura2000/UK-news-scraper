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

## Recover A Delivery Claim

Confirm that no email was sent, then use:

```bash
python3 -m UK_news_scraper.delivery_registry recover --delivery-id <id> --confirm-release
```

Never release a claim without checking the mailbox first; doing so can permit a duplicate send.

