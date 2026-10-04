# 08 — Key Concepts (Learn From This Project)

Short explanations of the important ideas used in StyleSense: **what** each one is, **why** we use it, and **where** it lives in the code. New concepts are added at each checkpoint.

---

## 1. Generative UI (GenUI)
**What:** instead of the AI replying with text, it replies with a **description of UI** (component type + props), and the app renders it.
**Why:** users tap instead of reading or typing. It's faster and feels like an app, not a chatbot.
**Key rule:** the AI may only choose from a **fixed, versioned catalog** of components, and its output is validated. The AI never "invents" UI.
**Where:** `backend/app/ai/genui/`, `mobile/src/genui/`.

## 2. Schema-first contracts (Pydantic → JSON Schema → TypeScript)
**What:** define a data shape once (Pydantic), generate JSON Schema, generate TS types from it.
**Why:** backend and mobile can never silently disagree on a component's shape. CI fails on drift.

## 3. State machines & LangGraph
**What:** a flow modeled as **nodes** (steps) and **edges** (transitions) over a shared **state** object. LangGraph runs it, saves state after each step (a **checkpoint**), and can **pause** (`interrupt()`) until the user acts, then resume.
**Why:** the stylist is a controlled flow (ask → answer → ask → results), not a free-roaming agent. Explicit graphs are testable and predictable.
**Where:** `backend/app/ai/graphs/stylist/`.

## 4. "Use the LLM only where it adds value"
**What:** deterministic code for everything predictable (questions, filters, ranking); the LLM only for language/vision understanding and explanations.
**Why:** 60–70% fewer tokens, faster responses and a system that still works when the AI is down (**degraded mode**).

## 5. Provider-agnostic LLM gateway (Adapter + Strategy patterns)
**What:** one interface (`gateway.run(task, …)`); concrete providers (OpenAI, Anthropic, …) are **adapters**. The task → model mapping is **config**.
**Why:** change provider or model without code changes; mix providers per task; fall back across providers.

## 6. Token optimization
- **Prompt caching:** providers cache a repeated prompt prefix, so keep the static part (system prompt, schemas) first and identical.
- **Compact context:** send a state summary, not chat history; send product "compact views", not full JSON.
- **Batching:** one call for N explanations.
- **Response caching:** identical normalized input → cached output.
- **Hard caps:** `max_input_tokens`/`max_output_tokens` per task.

## 7. Circuit breaker
**What:** a guard around a remote call with three states. **Closed** (normal), **Open** (too many failures, so fail fast without calling), **Half-open** (after a cool-down, let one test call through).
**Why:** a failing AI provider shouldn't make every request wait for timeouts; we switch to a fallback immediately.
**Detail:** breaker state is in **Redis** so all API instances share it.

## 8. Retries with exponential backoff + jitter
**What:** retry transient failures after growing, slightly randomized delays (e.g. 0.5 s, 1 s, 2 s ± random).
**Why:** avoids hammering a struggling service, and jitter prevents all clients retrying at the same instant ("thundering herd").
**Rule:** retry only retryable errors (429/5xx/timeouts); respect `Retry-After`.

## 9. Rate limiting algorithms
- **Fixed window:** count per minute. Simple, but allows bursts at window edges.
- **Sliding window:** smooths those edges. Used for API request limits.
- **Token bucket:** tokens refill at a steady rate; each action spends one; allows short bursts. Used for AI actions.
**Where:** Redis-backed middleware + gateway quotas.

## 10. Budget caps & graceful degradation
**What:** track AI spend in real time; at a threshold, alert; at the cap, switch to cheaper models or rule-based behavior.
**Why:** AI cost can never run away, and users still get a working app.

## 11. Embeddings & vector search (pgvector)
**What:** an embedding is a list of numbers representing meaning. Similar items have nearby vectors. **pgvector** stores them in Postgres and finds nearest neighbors quickly with **HNSW** indexes (cosine distance).
**Why:** "similar to this photo", "matches your taste", "linen resort shirt" ≈ "chill beach shirt".

## 12. Taste vector (online learning with an exponential moving average)
**What:** a user's taste is a vector nudged toward liked items and away from skipped ones: `taste = normalize(taste + α·liked − β·skipped)`.
**Why:** personalization that improves with every swipe, with no LLM and no model training.

## 13. Hybrid retrieval + ranking
**What:** first **filter** hard constraints in SQL (budget, size, category), then **score** candidates with a weighted formula (taste similarity, rating, budget fit, diversity).
**Why:** hard rules are never violated (budget is sacred), and soft signals personalize the order.

## 14. Server-Sent Events (SSE)
**What:** a one-way stream from server to client over plain HTTP.
**Why:** perfect for streaming UI components as they're ready; simpler than WebSockets, works through proxies and Cloudflare. Client → server actions use normal POSTs.

## 15. Idempotency keys & stale-action guards
**What:** the client sends a unique key per action; the server stores the result and returns it again if the same key repeats. `turn_id` rejects taps on outdated UI.
**Why:** mobile networks retry; users double-tap. Neither should cause duplicate effects.

## 16. JWT access tokens + rotating refresh tokens
**What:** a short-lived access token (15 min) for API calls; a long-lived opaque refresh token that is **replaced on every use**. If an old refresh token is reused, someone stole it, so the whole token family is revoked.
**Why:** a stolen access token expires quickly; a stolen refresh token is detected.

## 17. Canonical product + offers
**What:** separate *what the item is* (product) from *where it's sold and for how much* (offer).
**Why:** makes cross-store comparison natural and lets multiple sources feed one catalog.

## 18. Money as integers
**What:** store ₹499.00 as `49900` paise.
**Why:** floating-point numbers can't represent money exactly (0.1 + 0.2 ≠ 0.3).

## 19. Background jobs & queues (outbox + worker)
**What:** slow work (try-on, embeddings, alerts) is recorded as an outbox message and processed by the worker process; the API returns immediately.
**Why:** fast responses, retries for failed jobs, and protection of the API from slow third parties.

## 20. Bulkheads
**What:** separate concurrency limits per kind of work.
**Why:** a flood of try-on requests can't starve the stylist chat. Like the watertight compartments in a ship.

## 21. Presigned URLs
**What:** the backend signs a short-lived URL; the app uploads/downloads directly to/from object storage (MinIO).
**Why:** large files don't pass through the API; access is time-limited and private.

## 22. Prompt injection defense
**What:** user-supplied text can try to give the AI instructions ("ignore previous rules…"). We treat user content as **data**, constrain output to schemas, and **never take links or prices from the LLM**.

## 23. Observability: logs, metrics, traces (+ LLM traces)
**What:** **logs** say what happened, **metrics** show trends and alert, **traces** follow one request across services. Langfuse adds per-LLM-call traces with tokens and cost.
**Why:** you can't fix or optimize what you can't see.

## 24. Cloudflare Tunnel
**What:** a small agent on the homelab opens an outbound connection to Cloudflare; traffic for your domain flows through it.
**Why:** no open ports on the home router, the home IP stays hidden, and you get free HTTPS and DDoS protection.

## 25. Expand → migrate → contract (safe DB migrations)
**What:** add new columns/tables first, migrate data and code, remove old ones in a later release.
**Why:** zero-downtime deploys and safe rollbacks.

## 26. Affiliate attribution (business concept)
**What:** an affiliate link carries your ID. If the user buys within the store's attribution window, you earn commission. All outbound clicks route through `/out/{offer_id}`, so tagging can be added in one place later.

## 27. Modular monolith
**What:** one deployable app split internally into domain modules with strict boundaries (enforced by `import-linter`).
**Why:** the simplicity of a monolith now, with clean seams to extract services later only if scale demands it.

## 28. Test-driven development (TDD)
**What:** red (write a failing test) → green (simplest passing code) → refactor.
**Why:** tests define behavior before code exists; design stays testable; regressions are caught immediately.

## 29. Property-based testing (Hypothesis)
**What:** instead of hand-picked examples, state a rule ("ranked results never exceed budget") and let the tool generate hundreds of inputs to break it.
**Why:** finds edge cases humans don't think of.

## 30. Transactional outbox
**What:** write the side-effect intent (e.g. "send push") into an `outbox` table **in the same DB transaction** as the business change; a worker delivers it after commit.
**Why:** no lost or phantom side effects when a crash happens between "save" and "send".

## 31. At-least-once delivery & idempotent consumers
**What:** queues may deliver a job more than once. Handlers check state or use dedupe keys so running twice has the same effect as running once.

## 32. Single-flight (request coalescing)
**What:** if 10 identical requests arrive at once, only one does the expensive work; the other 9 wait for and share its result.
**Why:** avoids paying for the same LLM or embedding call repeatedly.

## 33. Optimistic locking
**What:** each row has a `version`; an update succeeds only if the version is unchanged since it was read.
**Why:** prevents lost updates without holding database locks.

## 34. SLOs & error budgets
**What:** an SLO is a reliability target (e.g. 99.5% available). The error budget is the allowed 0.5% failure. Alerts fire when the budget is burning too fast.
**Why:** alerts on what users feel, not on every blip.

## 35. Liveness vs readiness probes
**What:** *liveness* = "is the process alive?" (restart it if not). *Readiness* = "can it serve traffic right now?" (stop routing to it if not).
**Why separate:** if liveness checked the database, a short DB outage would make the orchestrator restart every API container at once and turn a blip into an outage.
**Where:** `api/health.py`.

## 36. Composition root
**What:** one place (`bootstrap/container.py`) that creates every concrete implementation and wires them together. Everything else depends on interfaces.
**Why:** swapping an implementation (or a fake in tests) touches one file.

## 37. Fail fast on configuration
**What:** settings are validated when the app starts; a missing or invalid value crashes startup with a clear error.
**Why:** a bad deploy fails at once, visibly, instead of hours later on the first request that needs the value.

## 38. Problem Details (RFC 9457)
**What:** a standard JSON error shape (`type`, `title`, `status`, `detail`, `instance`) served as `application/problem+json`, plus our stable `code`.
**Why:** clients handle every error the same way; codes stay stable even if wording changes.

## 39. Multi-stage Docker builds & non-root containers
**What:** build dependencies in one stage, copy only the result into a slim runtime stage that runs as an unprivileged user.
**Why:** smaller images, less attack surface, and a compromised process can't act as root. An allowlist `.dockerignore` keeps secrets and junk out of the build context.

## 40. Statement timeouts & lock timeouts
**What:** Postgres cancels any query running longer than `statement_timeout`; `lock_timeout` stops a migration from waiting forever behind a lock.
**Why:** one slow query can't hold a connection forever and starve the pool, and a stuck migration can't freeze production.

## 41. Correlation ids (request id + trace id)
**What:** a unique id attached to a request and carried into every log line, error report and response header. The trace id links the same request across services and spans.
**Why:** a user says "it failed"; you ask for the request id and find every log line, the trace and the error report in seconds.

## 42. RED metrics & label cardinality
**What:** **R**ate, **E**rrors, **D**uration per endpoint: the three numbers that tell you whether users are happy. Each unique label combination is a separate time series stored forever.
**Why it matters:** labelling by raw path (`/items/123`) or user id creates millions of series and kills Prometheus. Always label by **bounded** values: route templates, status codes, a fixed method list.

## 43. Histograms & percentiles (p95)
**What:** a histogram counts requests into latency buckets; Prometheus estimates percentiles from them. p95 = 95% of requests were faster than this.
**Why:** averages hide pain. A 50 ms average can hide 5% of users waiting 3 s.

## 44. Distributed tracing (OpenTelemetry)
**What:** a trace is a tree of timed **spans** (HTTP request → DB query → Redis call). OpenTelemetry is the vendor-neutral standard; spans go to a **collector**, which forwards them to a backend (Tempo).
**Why:** shows exactly where time went in one slow request. The collector lets us change backends without touching the app.

## 45. Sampling
**What:** recording only a fraction of traces (`APP_OTEL_SAMPLE_RATIO`). *Parent-based* sampling follows the caller's decision so traces are never half-recorded.
**Why:** full tracing at high traffic costs storage and CPU; at 1,000 DAU we can afford 100%.

## 46. PII redaction at the edge
**What:** scrubbing personal data (emails, phone numbers, tokens) in the last processing step before logs or error reports leave the process.
**Why:** logs get copied to many places and kept for a long time; once PII is in them, it's very hard to remove (and it's a DPDP Act risk).

## 47. Pure ASGI middleware
**What:** middleware written directly against the ASGI interface (`scope`, `receive`, `send`) instead of Starlette's `BaseHTTPMiddleware`.
**Why:** it doesn't buffer responses, so streaming (SSE) keeps working; it's also faster and has fewer context-variable pitfalls.

## 48. Property-based testing in practice
**What happened:** Hypothesis generated the email `'@A.Ao` and found it slipped past our redaction regex, and a test showed `stylesense@1.2.3` (a release name) being redacted as an email. Neither case was in the hand-written examples.
**Lesson:** for parsers, validators and scrubbers, generate inputs instead of guessing them.

## 49. Fail open vs fail closed
**What:** when a safety mechanism's dependency (Redis) is down, either let requests through (*open*) or reject them (*closed*).
**How we choose:** rate limiting fails **open** (better to serve without limits for a minute than be down). Idempotency fails **closed** (running a payment or a paid try-on twice is worse than a 503).

## 50. Sliding-window log vs token bucket
**Sliding-window log:** remember the timestamp of each allowed request; allow a new one only if fewer than `limit` happened in the last `window`. Exact, a little more memory.
**Token bucket:** a bucket holds up to `limit` tokens, refilled at a steady rate; each request spends one. Allows short bursts, then smooths to the average rate.
**Why Lua:** the check-and-update must be **atomic**; a Lua script runs in Redis as one indivisible step, so two API instances can't both take the last slot.

## 51. `SELECT … FOR UPDATE SKIP LOCKED`
**What:** lock the rows you select; rows already locked by someone else are skipped instead of waited on.
**Why:** turns a plain table into a safe multi-consumer queue. Four workers can drain the outbox in parallel and no message is handled twice.

## 52. Load shedding
**What:** when an instance is at capacity, reject new work immediately (503 + `Retry-After`) instead of queueing it.
**Why:** queued requests time out anyway and drag every other request down with them. Fast rejection keeps the instance healthy and lets clients retry later.

## 53. Heartbeats for liveness
**What:** a process proves it's alive by doing real work and touching a timestamp; a checker fails it when the timestamp gets old.
**Why:** a "health endpoint" served by a separate thread can stay green while the main loop is frozen. A heartbeat from the loop itself can't lie.

## 54. Lock ownership tokens
**What:** each lock holder stores a random token; release and extend only succeed if the token still matches.
**Why:** if a holder pauses past the TTL and someone else takes the lock, the slow holder must not delete the new owner's lock. The same idea protects idempotency results.

## 55. Never log stack-frame locals
**What happened:** exception logs included every frame's local variables by default, which can include tokens, request bodies and PII. A test now asserts a secret local never appears.
**Lesson:** redaction is a safety net, not a strategy; don't collect sensitive data in the first place.
