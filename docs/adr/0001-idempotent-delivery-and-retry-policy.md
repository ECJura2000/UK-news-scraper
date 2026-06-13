# ADR 0001: Idempotent Delivery And Selective Retry

## Status

Accepted

## Decision

Create a canonical data fingerprint and claim a delivery ID under an exclusive lock
before sending email. A completed claim is retained as `sent`; a failed send explicitly
releases the claim.

Only download/network failures are retried. Parsing, validation, and storage failures are
reported without automatic retry.

## Consequences

Concurrent automation launches cannot send the same result twice. Canonical JSON avoids
delimiter collisions and source-completion order changes. Manual recovery is required
when a process dies after sending but before marking the claim complete.

