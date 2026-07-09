---
inclusion: manual
---

# Skill: Databases

## Selection
Default PostgreSQL. SQLite for embedded/local/tests. Redis for cache/ephemera. Document stores only for genuinely schemaless data with no cross-entity transactions (rare — data is almost always relational). Search → Postgres FTS first, Elasticsearch when outgrown. Analytics → ClickHouse/BigQuery/DuckDB. Vectors → pgvector first.

## Schema Design
- Model invariants in the schema: NOT NULL by default, foreign keys ON, CHECK constraints for domain rules, UNIQUE for identity facts. The database is the last line of defense and the only one that holds under concurrent writers.
- Normalize until it hurts, denormalize where measured reads demand it — and document every denormalization's sync mechanism.
- Types: DECIMAL/INTEGER-cents for money (never float), TIMESTAMPTZ stored as UTC, real columns for anything queried/validated (JSONB only for genuinely schemaless payloads), enums via CHECK/lookup tables with forward-compatible readers.
- Primary keys: surrogate (bigint identity or UUIDv7 for distributed insert) — natural keys change; don't build on them.
- Soft-delete vs hard-delete decided per entity with compliance in mind; soft-delete needs partial indexes and WHERE deleted_at IS NULL discipline everywhere.

## Queries
- **EXPLAIN (ANALYZE, BUFFERS) before any optimization.** The plan is the truth.
- N+1 is the #1 real-world problem: batch, JOIN, eager-load.
- Select only needed columns. Keyset pagination (`WHERE id > $last ORDER BY id LIMIT n`) over OFFSET. Push filters/aggregation into the DB — it's better at it than app loops.
- Indexes match query shapes: WHERE/JOIN/ORDER BY columns; composite = equality columns first, then the range column; covering indexes for hot reads; partial indexes for skewed predicates. Every index taxes every write — don't hoard; drop unused ones (pg_stat_user_indexes).

## Transactions & Concurrency
- Transaction boundary = business invariant boundary. Short transactions; never held across external calls or user think-time.
- Know your isolation level and its anomalies; use `SELECT ... FOR UPDATE` or optimistic version columns for read-modify-write races; UPSERT (`INSERT ... ON CONFLICT`) over check-then-insert (a race).
- Deadlocks: consistent table/row acquisition order; keep retry logic for serialization failures.
- Pool sizing deliberate; exhaustion masquerades as "the DB is slow".

## Migrations
- Versioned, ordered, automated in deploy, reversible where possible. **Expand/contract always**: add nullable column → deploy code writing both → backfill in batches (not one giant UPDATE that locks the table) → enforce constraint → remove old. No deploy may require lockstep with the migration.
- Dangerous operations (type changes, NOT NULL on big tables, index builds) use the online path (CREATE INDEX CONCURRENTLY, etc.). Test migrations against production-sized data — a migration that takes 4 hours is an outage.
- Migrations never edited after merge; fix forward with a new one.

## Operations
- Backups are only real if restore is tested. Point-in-time recovery for anything that matters.
- Monitor: slow query log, connection counts, replication lag, table/index bloat, disk headroom.
- Read replicas before sharding; sharding last, partition key chosen with extreme care (nearly irreversible).

## Checklist
- [ ] Constraints encode the invariants, not just app code?
- [ ] Every list query indexed and paginated?
- [ ] Migration safe on production-sized data under live traffic?
- [ ] Concurrent writers on the same row — what happens?
- [ ] Restore actually tested?
