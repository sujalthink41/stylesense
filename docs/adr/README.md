# Architecture Decision Records

One file per significant decision: `NNNN-title.md` with **Context**, **Decision**, **Consequences**. Never edit an accepted ADR; supersede it with a new one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-uv-for-python-tooling.md) | uv for Python dependencies and tooling | Accepted |
| [0002](0002-layered-modular-monolith.md) | Layered modular monolith with routers in `api/` | Accepted |
| [0003](0003-defer-object-storage.md) | Defer choosing the object store until CP12 | Superseded by 0016 |
| [0004](0004-defer-langfuse.md) | Defer Langfuse until the LLM gateway (CP6) | Superseded by 0010 |
| [0005](0005-postgres-outbox-as-job-queue.md) | Postgres outbox as the job queue; no ARQ | Accepted |
| [0006](0006-authentication-design.md) | Google ID tokens in; own JWT + rotating refresh tokens out | Accepted |
| [0007](0007-embedder-port-with-hashing-baseline.md) | Embedder port with an offline hashing baseline until CP6 | Accepted |
| [0008](0008-client-side-ids-and-batched-inserts.md) | Client-generated UUIDv7 keys and no eager server defaults | Accepted |
| [0009](0009-llm-gateway-design.md) | LLM gateway: own adapters, prompts in code, routing and prices in the DB | Accepted |
| [0010](0010-llm-observability-via-otel.md) | LLM observability via OTel GenAI spans + usage ledger | Accepted |
| [0011](0011-action-scoped-sse-and-turn-cas.md) | Action-scoped SSE streams and turn compare-and-swap | Accepted |
| [0012](0012-stylist-graph-rules-first.md) | Stylist graph: LangGraph without a checkpointer, rules first, LLM fills gaps | Accepted |
| [0013](0013-swipes-outside-the-turn-protocol.md) | Swipes outside the turn protocol, learned synchronously | Accepted |
| [0014](0014-detail-comparison-and-looks.md) | Detail, comparison fallback and complete-the-look: rules decide, catalog v2 | Accepted |
| [0015](0015-boards-shares-polls.md) | Boards, share links and polls: optimistic locking, natural idempotency, token voting | Accepted |
| [0016](0016-cloudinary-for-media.md) | Cloudinary for user photos (supersedes 0003) | Accepted |
| [0017](0017-tryon-as-background-jobs.md) | Virtual try-on: background jobs, a pluggable vendor, paid-call safety | Accepted |
