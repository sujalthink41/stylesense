# Architecture Decision Records

One file per significant decision: `NNNN-title.md` with **Context**, **Decision**, **Consequences**. Never edit an accepted ADR; supersede it with a new one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-uv-for-python-tooling.md) | uv for Python dependencies and tooling | Accepted |
| [0002](0002-layered-modular-monolith.md) | Layered modular monolith with routers in `api/` | Accepted |
| [0003](0003-defer-object-storage.md) | Defer choosing the object store until CP12 | Accepted |
| [0004](0004-defer-langfuse.md) | Defer Langfuse until the LLM gateway (CP6) | Accepted |
| [0005](0005-postgres-outbox-as-job-queue.md) | Postgres outbox as the job queue; no ARQ | Accepted |
| [0006](0006-authentication-design.md) | Google ID tokens in; own JWT + rotating refresh tokens out | Accepted |
