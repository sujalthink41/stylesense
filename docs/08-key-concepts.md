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

## 56. OpenID Connect ID tokens
**What:** after "Sign in with Google", the app receives an **ID token**: a JWT signed by Google that says who the user is (`sub`, `email`) and which app it was issued for (`aud`).
**How we trust it:** check Google's signature with their published public keys, check `aud` is *our* client id (so a token for another app can't be replayed to us), check `iss` and expiry, and require a verified email.

## 57. JWT anatomy
**What:** `header.payload.signature`, each base64url-encoded. The payload is **readable by anyone**; the signature only proves it wasn't changed. Never put secrets in a JWT.
**Our claims:** `sub` (user id), `sid` (session), `role`, `iss`, `aud`, `iat`, `exp`, `jti` (unique id).

## 58. Algorithm confusion & `alg: none`
**Attack 1:** send a token with `"alg": "none"` and no signature. **Attack 2:** take a server that verifies RS256 with a *public* key and send an HS256 token "signed" with that public key as the HMAC secret.
**Defence:** pin the expected algorithm when verifying (`algorithms=["RS256"]` for Google, `["HS256"]` for ours). Both attacks are covered by tests.

## 59. Refresh token rotation & reuse detection
**What:** every refresh token works once. Using it returns a new one. If an *already used* token shows up again, someone copied it, so the whole session family is revoked.
**Grace window:** phones fire parallel requests; a spent token is honoured for 30 seconds so honest clients aren't mistaken for thieves.

## 60. Hashing high-entropy tokens
**What:** store `sha256(refresh_token)`, never the token. Passwords need slow, salted hashes (bcrypt/argon2) because people pick guessable ones; a 256-bit random token can't be guessed, so a fast hash is enough.
**Why:** a database leak doesn't hand out working sessions.

## 61. Ports & adapters in practice
**What:** the auth module defines a **port** (`IdentityVerifier`: "give me a token, I'll tell you who it is"). Google's implementation is an **adapter** in `integrations/`. Tests plug in a fake; adding Apple sign-in later is a new adapter, not a change to auth.

## 62. Structural typing (`Protocol`)
**What:** a `Protocol` describes a shape ("has `provider`, `subject`, `email`…"). Any object with that shape fits, without importing or inheriting from anything.
**Why we used it:** the users module needs identity data but must not import the auth module (auth already depends on users). A `Protocol` breaks that cycle.

## 63. Soft delete with a grace period
**What:** deleting an account first marks it `deleting` and blocks access; the real purge runs 30 days later (via the outbox). The deletion record outlives the user row as proof it was honoured.
**Why:** gives time to recover from mistakes or abuse, while meeting Play Store and DPDP deletion requirements.

## 64. Approximate nearest neighbour search (HNSW)
**What:** finding the closest vectors exactly means comparing against every row. **HNSW** (Hierarchical Navigable Small World) builds a layered graph you can "walk" towards the nearest points in roughly logarithmic time, trading a tiny bit of accuracy for huge speed.
**Our setup:** pgvector HNSW index with cosine distance; `hnsw.iterative_scan` keeps searching when filters (gender, active) discard results.

## 65. Feature hashing
**What:** turn text into a fixed-size vector by hashing each word into a bucket (with a random ±1 sign) instead of keeping a vocabulary. Items that share words share buckets, so they end up close.
**Trade-off:** no training, no API, deterministic; but it matches *words*, not meaning. Our CP5 baseline until a real embedding model arrives (ADR 0007).

## 66. Keyset (cursor) pagination
**What:** "give me 20 items after id X" (`WHERE id > X ORDER BY id LIMIT 21`) instead of `OFFSET 400`.
**Why:** OFFSET gets slower the deeper you go and skips or repeats rows when data changes; keyset stays fast and stable. The extra 21st row tells us whether there's a next page.

## 67. Conditional requests (ETag / 304)
**What:** the server labels a response with a fingerprint (ETag). Next time the app sends `If-None-Match: <etag>`; if nothing changed the server answers **304 Not Modified** with no body.
**Why:** saves mobile data and battery, and keeps the app fast on slow networks.

## 68. Open redirects
**What:** an endpoint like `/out?url=…` that redirects anywhere lets phishers send links that *look* like ours but land on their site.
**Our defence:** `/v1/out/{offer_id}` takes an id, never a URL; the target must be HTTPS on that store's allow-listed domains, checked at ingest **and** at redirect time. Tests cover lookalike hosts, `amazon.in.evil.com`, `amazon.in@evil.com`, `javascript:` and scheme-relative URLs.

## 69. N+1 queries
**What:** loading a list, then running one extra query *per item* (e.g. its offers): 1 + N queries. Invisible with 5 rows, crippling with 500.
**Our defence:** `selectinload` fetches all related rows in one extra query, relationships are `lazy="raise"` so accidental lazy loads fail loudly, and a test asserts listing 5 or 50 products costs the same number of queries.

## 70. Batched inserts and where ids come from
**What happened:** with database-generated ids, the ORM had to insert rows one at a time to learn each id (1,945 statements for one ingest). Generating time-ordered UUIDv7 ids in Python let it batch: 37 statements (ADR 0008).
**Lesson:** measure before optimising: the embedder looked suspicious, but profiling showed the database round trips were the real cost.

## 71. Fallback chains
**What:** each AI task lists models in order: primary first, then fallbacks (ideally on a *different* provider). If the primary is down, rate-limited, refusing or returning garbage, the next one answers.
**Why:** a single provider outage shouldn't take the stylist down.

## 72. Retryable vs non-retryable errors
**Retry:** rate limits (429), server errors (5xx), timeouts, connection drops: the same request may succeed in a moment.
**Don't retry:** bad request, auth failure, unknown model, refusal (4xx): repeating it just wastes money. Move on to the fallback instead.
**`Retry-After`:** when a provider says "wait 2 s", we wait 2 s; if it says "wait 2 minutes", we fail over immediately.

## 73. Structured output + repair
**What:** we ask the model for JSON matching a schema (using the provider's native structured-output mode), then **validate** it with Pydantic. If it's invalid, we send the errors back once ("that was invalid because…") and validate again.
**Why:** an LLM is not a reliable function; our code only ever sees validated objects.

## 74. Prompt injection: instructions vs data
**What:** user text can contain "ignore your rules and…". We keep instructions in the system message, wrap user data as JSON inside `<input>` tags, tell the model never to follow instructions found there, and constrain output to a schema. Links and prices never come from the model.

## 75. Hot-reloading config with a version counter
**What:** config lives in Postgres; each instance caches it. On every change an admin bumps a counter in Redis; each request does one cheap `GET` of that counter and reloads only when it moved.
**Why:** instant, consistent config changes across all instances without restarts or polling the database.

## 76. Money in micro-dollars
**What:** AI costs are tiny fractions of a cent, so we store integer **micro-USD** (1 USD = 1,000,000), and round *up* so budgets never undercount. Prices are "USD per million tokens", which conveniently equals micro-USD per token.

## 77. GenAI semantic conventions
**What:** OpenTelemetry defines standard attribute names for AI calls (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, …). Using them means any compatible tool (Tempo, Langfuse, vendor APMs) understands our traces without custom glue.

## 78. Discriminated unions
**What:** a field (`type`) tells the parser which shape to expect: `{"type": "chip_question", …}` vs `{"type": "budget_slider", …}`. Pydantic picks the right model from that one field, so validation errors are precise and the JSON Schema maps cleanly onto TypeScript unions.
**Where:** every GenUI component, action and stream event.

## 79. Compare-and-swap (CAS)
**What:** "change it from A to B only if it's still A", done atomically by the database (`UPDATE … WHERE turn_id = 3`). If two requests race, exactly one sees 1 row updated; the other sees 0 and knows it lost.
**Why:** turns advance exactly once, without locks held during slow AI work.

## 80. Server-Sent Events in practice
**What:** a normal HTTP response that stays open and sends `event:`/`data:` frames as they're ready. Comments (`: keep-alive`) are ignored by clients but stop proxies from closing quiet connections.
**Our twist:** each action's response is its own short stream, so no message broker is needed (ADR 0011).

## 81. Decoupling work from the connection
**What:** the turn runs in a background task and hands events to the HTTP response through a queue. If the user's train enters a tunnel, the turn still finishes and is saved; the app picks it up from the snapshot.

## 82. Contract snapshots
**What:** the GenUI JSON Schema is generated from code and committed. A test regenerates it and fails on any difference, so a backend change that would break the app's generated types can't slip through unnoticed.

## 83. Graceful version negotiation
**What:** the app says which catalog version it understands; the server never sends it anything newer, and swaps unknown components for an "update the app" banner in the same slot. Old app versions keep working instead of crashing.

## 84. Rules first, LLM for the gaps
**What:** a cheap, deterministic parser handles the common cases; the LLM is asked only about what the rules couldn't fill, and can't overwrite them. **Why:** it's free, instant, testable and works during outages; the model's job shrinks to the long tail. Numbers (budgets) always come from rules, because models can hallucinate them.

## 85. Golden evals
**What:** a file of real-looking inputs with expected outputs, plus a scorer that reports field accuracy and exact matches for any parser (rules or LLM). **Why:** "it seems better" isn't a measurement. Caveat: a set written next to the code it tests flatters that code; a **held-out** set (here: real queries from session events) is the honest number.

## 86. Hybrid retrieval
**What:** hard constraints (budget, category, gender) as SQL filters, then vector similarity for "feel". **Why:** a vector search alone happily returns a ₹3,000 shirt for "under 500". Filters guarantee correctness; vectors give relevance.

## 87. Ranking in code, not in the model
**What:** a transparent weighted score (attribute match, similarity, rating × confidence) instead of asking an LLM to pick. **Why:** deterministic, cheap, debuggable and tunable; "rating × confidence" stops a 5★ item with 3 reviews beating a 4.6★ item with 2,000.

## 88. Diversity re-ranking
**What:** each extra item from a brand already in the deck gets its score multiplied by a penalty (0.85). **Why:** without it, one brand with many similar products fills the whole deck.

## 89. A graph without a checkpointer
**What:** LangGraph is used for its node/edge structure and streaming, not its persistence: each turn runs the graph once from saved state and returns the new state. **Why:** session state already lives in one table with turn compare-and-swap; a second copy would drift.

## 90. Exponential moving average (EMA) for taste
**What:** each like moves the taste vector a fixed fraction towards the item: `taste = normalize((1 − α)·taste + α·item)`. Old likes fade geometrically instead of being stored forever. **Why:** one line of arithmetic, constant memory, and recent taste counts more than last year's.

## 91. Explicit vs implicit feedback
**What:** Style DNA picks are *explicit* (the user told us); swipes are *implicit* (we infer). Both feed the same taste, but new picks blend in at 50% rather than overwrite what swipes taught. **Why:** people describe themselves differently from how they behave; keep both signals.

## 92. Cold start
**What:** a new user has no swipes, so there's nothing to personalise from. Style DNA seeds the taste vector from the embedding of each picked style's description, so the very first deck is already personal. **Why:** the first session decides whether people come back.

## 93. Natural idempotency keys
**What:** some writes carry their own unique identity, e.g. a swipe is (user, product, session). A unique constraint plus `ON CONFLICT DO NOTHING` makes retries free, with no Idempotency-Key header or Redis entry. `NULLS NOT DISTINCT` makes "no session" count as one value. **Why:** the simplest correct mechanism is the one the data already has.

## 94. Row locks against lost updates
**What:** two swipes read the same taste, each adds its change, and the second write erases the first. `SELECT … FOR UPDATE` on the profile row makes them queue. **Why:** read-modify-write on shared state needs a lock (or CAS); an atomic SQL update isn't possible when the maths happens in code.

## 95. Prefetching
**What:** the app asks for the next cards (`GET …/deck`) while the user is still swiping the current ones, excluding what it already holds. **Why:** the next card appears instantly; the network round trip hides behind the swipe animation.

## 96. Soft filters with a fallback
**What:** the saved size is a SQL filter, but if it leaves nothing, the search runs again without it. **Why:** an empty screen is worse than a near miss.

## 97. Property-based testing
**What:** instead of a few hand-picked examples, state a rule ("a look never costs more than the budget") and let Hypothesis generate hundreds of random catalogs and budgets trying to break it; when one does, it shrinks it to the smallest failing case. **Why:** money and budget promises must hold for inputs nobody thought of.

## 98. Constrained search (a tiny knapsack)
**What:** choose at most one piece per slot to maximise the total score without exceeding the budget. With a shortlist of ~9 per slot and ≤ 3 slots, trying every combination (~1,000) is instant and exact. **Why:** greedy "best piece first" can blow the budget on one item and leave the others empty.

## 99. Fallback content
**What:** when the exact thing can't be offered (only one store stocks it, or it's sold out), show the next best thing (similar items in stock) instead of a dead end. **Why:** every screen should give the user a next step.

## 100. Schema evolution with version negotiation
**What:** new components ship as catalog v2; the server swaps them for an "update the app" banner for v1 apps, in the same slot, so old apps keep working. **Why:** mobile users update slowly; the backend must serve several app versions at once.

## 101. LLM as copywriter, not decider
**What:** code chooses products and prices; the model may only rename and rephrase, and its output can't introduce new ids. **Why:** a hallucinated price or product is a broken promise; wording is low-risk.

## 102. Optimistic locking (ETag / If-Match)
**What:** every board carries a version. Reads return it as `ETag`; edits send it back as `If-Match`. If someone changed the board in between, the edit is refused with 412 and the current version, instead of silently overwriting. **Why:** a phone and a tablet editing the same board shouldn't lose each other's changes, and locking rows across a user's think time is impossible.

## 103. Lost update
**What:** two writers read version 3, both write, and the second erases the first. Optimistic locking (check the version at write time) or pessimistic locking (`FOR UPDATE` during the write) prevents it; boards use both: the row lock serialises writes and the version catches edits based on stale reads.

## 104. Client-generated ids for idempotent creates
**What:** the app picks the new board's or poll's UUID itself. Retrying the same create finds the existing row instead of making a second one. **Why:** offline-first apps queue writes and replay them; the id is the idempotency key for free.

## 105. Unguessable public links
**What:** share and poll links use 8 random characters from 62 (≈ 2·10¹⁴ possibilities), so links can't be enumerated. **Why:** the link is the only access control for content shared on WhatsApp.

## 106. Pseudonymisation with HMAC
**What:** store `HMAC(key, ip)` instead of the IP. Equal inputs still match (to spot duplicates), but without the server key the table reveals nothing, and unlike a plain hash it can't be brute-forced over the small space of IPv4 addresses. **Why:** collect only what anti-abuse needs (data minimisation).

## 107. Layered anti-abuse
**What:** a unique key (one vote per device), a per-poll-per-network cap and per-IP rate limits each stop a different kind of abuse; none alone is enough. **Why:** cheap defences in depth beat one expensive one (CAPTCHAs) for low-stakes features.

## 108. Direct-to-storage uploads with signatures
**What:** the server signs "you may upload one file named X with these rules", and the app sends the bytes straight to the storage provider. **Why:** our servers never carry large uploads (bandwidth, memory, time), yet nobody can upload without our permission.

## 109. Trust, but verify (uploads)
**What:** after an upload, the server asks storage what actually arrived (format, size, dimensions) instead of believing the client. **Why:** clients can be modified; storage can't be lied to.

## 110. Data minimisation by expiry
**What:** user photos live 24 hours; a scheduled job deletes them. Storage first, then the database row, so a failure is retried rather than forgotten. **Why:** the safest personal data is data you no longer have.

## 111. Background jobs for slow, paid work
**What:** the request only records the job; a worker does the work and the app watches its status. **Why:** a 30-second vendor call shouldn't hold an HTTP request open, and a crash mid-call shouldn't lose the job.

## 112. At-least-once delivery + idempotent handlers
**What:** the outbox may deliver a message twice (e.g. after a crash), so the handler checks the job's state first and does nothing if it's already done. **Why:** "exactly once" is built from "at least once" plus idempotency.

## 113. Advisory locks
**What:** `pg_advisory_xact_lock(key)` is a lock on a number, not a row, held until the transaction ends. Locking per user makes "count today's jobs, then insert" safe against concurrent requests. **Why:** some checks span rows that don't exist yet, so there's no row to lock.

## 114. Retryable vs permanent failures (again)
**What:** a busy vendor or a 503 is worth retrying; "no person in the photo" or a 400 from storage isn't. Classifying errors decides between backoff and a clean, explained failure. **Why:** retrying the impossible wastes money and delays the user's answer.

## 115. CDN caching vs deletion
**What:** deleting a file at the origin doesn't instantly remove copies cached at CDN edges; invalidation takes time. **Why it matters:** privacy promises must account for caches. Here URLs are unguessable and only given to the owner, which bounds the risk.
