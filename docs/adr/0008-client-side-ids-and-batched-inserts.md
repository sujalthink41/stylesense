# 0008 — Client-generated UUIDv7 keys and no eager server defaults

**Status:** Accepted (2026-10-05)

## Context
Ingesting 300 mock products took **1,945 SQL statements**. With server-generated primary keys (`uuidv7()`) and server defaults fetched back after insert (SQLAlchemy's `eager_defaults`), every INSERT needed a `RETURNING` round trip, so rows couldn't be batched.

## Decision
- Primary keys are generated **in Python** with `platform.ids.new_id()` (RFC 9562 UUIDv7: time-ordered, index-friendly). The `uuidv7()` server default stays for raw SQL inserts.
- `Base` sets `eager_defaults=False`: server defaults (e.g. `created_at`) are not fetched after INSERT. Code that needs one right after inserting calls `session.refresh()` explicitly.
- Rows are linked through ORM relationships rather than flushing to obtain ids.

## Consequences
- The same ingest runs in **37 statements** (2.7 s → 0.6 s); every module benefits.
- Reading a server default right after insert without `refresh()` fails loudly under async (no silent lazy load), so mistakes surface in tests.
