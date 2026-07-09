---
inclusion: manual
---

# Skill: Backend Engineering

## Purpose
Build server-side systems that are correct under concurrency, honest under failure, and observable in production.

## Request Handling
- Layering: handler (parse/validate/format, no logic) → service (business rules) → persistence/clients. Handlers stay thin enough to be boring.
- Validate every input at the boundary with a schema (pydantic/zod/etc.): type, length, range, enum. Reject with specific 4xx messages; never "fix up" bad input silently.
- Every endpoint: authn + authz **per object** (IDOR check), never mutate on GET, paginate every list from v1 (keyset over OFFSET), cap page sizes and body sizes server-side.
- Errors: structured error codes + human message out; stack traces and SQL only into logs. One exception-to-response translator at the top, not try/except in every handler.

## Reliability Defaults
- Timeout on **every** external call (DB, HTTP, queue, subprocess). Inner timeouts shorter than outer.
- Retries only on idempotent operations, with exponential backoff + jitter and a cap. Offer idempotency keys on mutating endpoints.
- Transactions: short, never held across external calls or user think-time; the transactional boundary matches the business invariant.
- Background jobs: idempotent, safe to run twice, failures visible (DLQ/alert), not just logged.
- Writes that span services: outbox pattern / sagas with compensation — never hope.
- Graceful shutdown: stop accepting, drain in-flight, exit. Health checks shallow enough not to cascade failures.

## Data
- UTC in storage; timezone at the display edge. Decimal/integer money. Migrations automated, ordered, expand/contract (add column → deploy code → backfill → remove old) so no deploy needs lockstep.
- N+1 queries are the #1 latency bug: batch, JOIN, eager-load. EXPLAIN before optimizing further.
- Connection pools sized deliberately; pool exhaustion masquerades as "slow DB".

## Configuration & Secrets
- Config from env, validated at startup — missing config fails at boot with a clear message, not at first use.
- Secrets from env/secret manager only; never in code, logs, URLs, or error messages.

## Observability
- Structured logs with correlation/request IDs through every hop; log once at the handling boundary with the data needed to act.
- RED metrics (rate, errors, duration) per endpoint; p95/p99, not means.
- Log security events (logins, failures, permission denials) without logging secrets/PII.

## Checklist
- [ ] Every external call has a timeout? Every retry idempotent?
- [ ] Every list endpoint paginated and capped?
- [ ] Authz checked against the specific object, server-side?
- [ ] What happens if this handler runs twice concurrently for the same entity?
- [ ] Partial failure mid-operation: what state remains? Is it recoverable?
