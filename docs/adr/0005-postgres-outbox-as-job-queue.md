# 0005 — Postgres outbox as the job queue; no ARQ

**Status:** Accepted (2026-10-04)

## Context
The spec planned ARQ (Redis-backed) for background jobs plus a separate transactional outbox for side effects. That means two delivery systems, and Redis-held jobs can be lost or duplicated relative to the database state that created them.

## Decision
Use the **transactional outbox table as the job queue**:
- Producers write an `outbox_messages` row **in the same transaction** as the business change (`OutboxWriter.add`), optionally with a `dedupe_key` and a delay.
- A **worker process** (`python -m stylesense.workers`) runs the relay: it claims one due message per transaction with `FOR UPDATE SKIP LOCKED`, calls the topic's handler with a timeout, then marks it `done`, reschedules it with exponential backoff + jitter, or dead-letters it after `max_attempts`.
- Periodic jobs run in the same process; cron-style jobs are `exclusive` and take a Redis lock so only one worker runs them at a time.

## Consequences
- One durable, transactional mechanism; no job is lost or sent for a change that rolled back.
- Any number of workers can run in parallel safely.
- Delivery is **at-least-once**: handlers must be idempotent (dedupe on `envelope.id`).
- Throughput is bounded by Postgres; comfortably enough at our scale (1,000 DAU). Revisit with a dedicated broker if the outbox exceeds ~100 messages/second sustained.
