# Observability Guide: Learn the Tools

A beginner-friendly guide to the monitoring tools in StyleSense: what each one is, why we need it, and how to use its dashboard.

---

## 1. The big idea in one picture

Once the app is live, you can't see inside it. Users just say "it's slow" or "it broke". **Observability** means the app constantly reports what it's doing, so you can answer *what happened, where, and why* without guessing.

Think of the app as a **car**:

| Car | Our tool | Answers |
|---|---|---|
| Dashboard gauges (speed, fuel, temperature) | **Prometheus + Grafana** (metrics) | "How is the app doing *right now* and over time?" |
| A dashcam recording one trip, second by second | **Tempo** (traces) | "Why was *this one* request slow? Where did the time go?" |
| The mechanic's fault-code reader | **GlitchTip** (errors) | "What crashed, how often, and for which request?" |
| The trip diary | **Logs** | "What exactly happened, step by step?" |
| A friend calling every minute to ask "are you OK?" | **Uptime Kuma** | "Is the app reachable at all?" |

**The glue: the request ID.** Every request gets a unique ID (e.g. `28cd9ea7…`). It appears in the logs, the error report and the response header, so from one ID you can find everything about that request.

## 2. How the data flows

```
                 ┌──────────────► logs (stdout) ─────────► make logs s=api
                 │
 StyleSense API ─┼── /metrics ◄──── Prometheus scrapes every 15 s ──► Grafana dashboards
                 │
                 ├── traces ─► OTel Collector ─► Tempo ──────────────► Grafana → Explore
                 │
                 └── crashes ─► GlitchTip ─────────────────────────► GlitchTip UI

 Uptime Kuma ── calls /healthz and /readyz every minute ─► alerts if down
```

- **Prometheus pulls** numbers from the app (it visits `/metrics`).
- The **app pushes** traces (to the collector) and crashes (to GlitchTip).
- **Grafana stores nothing.** It's the screen that draws charts from Prometheus and Tempo.

## 3. Start everything

```bash
make obs-up
```

Then generate some traffic so there's something to look at:

```bash
for i in $(seq 1 50); do curl -s localhost:8000/readyz >/dev/null; curl -s localhost:8000/nope >/dev/null; done
```

| Tool | URL | Login |
|---|---|---|
| Grafana | http://localhost:3001 | `admin` / `GRAFANA_ADMIN_PASSWORD` from `.env` |
| Prometheus | http://localhost:9090 | none (local only) |
| GlitchTip | http://localhost:8001 | sign up on first visit |
| Uptime Kuma | http://localhost:3002 | create an admin on first visit |

---

## 4. Prometheus: the number collector

**What it is:** a database of **numbers over time** (time series). Every 15 seconds it visits `http://api:8000/metrics` and stores what it sees.

**What we record:**

| Metric | Meaning |
|---|---|
| `http_requests_total` | How many requests, split by route and status code |
| `http_request_duration_seconds` | How long requests took (as a histogram, so we can compute p95) |
| `http_requests_in_progress` | Requests being handled right now |
| `db_pool_size` / `db_pool_checked_out` | Database connections available / in use |
| `process_resident_memory_bytes`, `process_cpu_seconds_total` | Memory and CPU of the API |

### Try it
1. Open http://localhost:9090 → **Status → Targets**. `stylesense-api` should be **UP** (green). If it's down, Prometheus can't reach the app.
2. Go to **Query**, type each line below and press **Execute**, then switch to the **Graph** tab:

```promql
http_requests_total                                   # raw counters
sum by (route) (rate(http_requests_total[5m]))        # requests per second, per route
sum(rate(http_requests_total{status=~"5.."}[5m]))     # server errors per second
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))  # p95 latency
```

**PromQL in 30 seconds:**
- `rate(x[5m])` turns an ever-growing counter into "per second, averaged over 5 minutes".
- `sum by (route)` groups the results.
- `{status=~"5.."}` filters by label (here: any 5xx status).

You'll rarely use Prometheus's own UI. Grafana is nicer. But it's the best place to check that **targets are up**.

---

## 5. Grafana: the dashboard screen

**What it is:** the screen. It reads from Prometheus (metrics) and Tempo (traces) and draws charts. We **pre-built** a dashboard, so it's ready when Grafana starts.

### Our dashboard
1. Open http://localhost:3001 and log in.
2. **Dashboards → StyleSense → StyleSense API**.

| Panel | What it tells you | Worry when… |
|---|---|---|
| **Request rate** | Traffic right now (requests/second) | Drops to 0 unexpectedly (app or network down) |
| **Error rate (5xx)** | % of requests our server failed | Turns orange at 1%, red at 2% |
| **p95 latency** | 95% of requests were faster than this | Orange at 300 ms, red at 1 s |
| **In flight** | Requests being handled right now | Keeps climbing (something is stuck) |
| **Requests by route** | Which endpoints are busiest | — |
| **p95 latency by route** | Which endpoint is slow | One route much higher than the others |
| **Errors by route and status** | 4xx = client mistakes, 5xx = our bugs | Any steady 5xx |
| **DB connection pool** | Connections in use vs available | "in use" touching "pool size" (pool exhausted) |
| **Memory / CPU** | Resource use of the API | Memory only ever goes up (a leak) |

**Tips:**
- Top right: change the time range (last 15 min, 24 h, 7 days).
- Drag across a chart to zoom in.
- Hover a line to see exact values.

### Finding a trace (Explore)
1. Left menu → **Explore** → choose **Tempo** at the top.
2. **Search** tab → Service name `stylesense` → **Run query**.
3. Click a trace. You'll see a **waterfall**: each bar is one step (the HTTP request, each SQL query, each Redis call) and its width is how long it took. The widest bar is where the time went.

---

## 6. Tempo: the dashcam

**What it is:** stores **traces**. A trace is the full timeline of **one request**, broken into **spans** (steps):

```
GET /v1/stylist/sessions/{id}      ████████████████████████  420 ms
├─ SELECT products …               ████                       60 ms
├─ Redis GET cache:…               ▌                           2 ms
└─ LLM call stylist.explain                  ███████████████  340 ms   ← the slow part
```

**When you use it:** a metric says "p95 is high". Tempo shows *which step* in *which request* is slow.

**How data gets there:** the app sends spans to the **OpenTelemetry Collector**, which batches them and forwards them to Tempo. **OpenTelemetry (OTel)** is the industry standard for this; because we use it, we could switch Tempo for another tool without changing app code.

You never open Tempo directly. You view it **through Grafana → Explore**.

Health checks (`/healthz`, `/readyz`) are deliberately **not** traced, because they run every few seconds and would bury real traffic.

---

## 7. GlitchTip: the crash reporter

**What it is:** collects **unexpected errors** (crashes) and groups identical ones into **issues**: "RuntimeError in X happened 57 times, last seen 2 minutes ago". It speaks the same protocol as Sentry, a popular paid tool, so we use the free Sentry SDK.

**What gets reported:** only real bugs (500s). Expected errors like "not found" or "validation failed" are normal behaviour and are **not** reported. Every report has its **`request_id` tag**, and emails, phone numbers and tokens are replaced with `[REDACTED]` before sending.

### First-time setup
1. Open http://localhost:8001 → **Sign up** with any email and password (it's local).
2. Create an **organization** (e.g. "StyleSense") → create a **project** (platform: Python, name: `stylesense-api`).
3. Copy the project's **DSN** (the address the app sends errors to). It looks like `http://<key>@localhost:8001/<id>`.
4. Put it in `.env`, replacing `localhost:8001` with `glitchtip:8080` (inside Docker, the app reaches GlitchTip by service name):
   ```
   APP_SENTRY_DSN=http://<key>@glitchtip:8080/<id>
   ```
5. `make obs-up` again so the API picks it up.

### Using it
- **Issues** list: newest and most frequent crashes.
- Open one: the **stack trace** (which line failed), **tags** (`request_id`, `environment`, `release`) and how many times it happened.
- Workflow: take the `request_id` → search the logs for it → open its trace in Grafana.
- **Resolve** an issue once fixed. If it comes back, GlitchTip reopens it ("regression").

---

## 8. Uptime Kuma: the "are you alive?" checker

**What it is:** checks your app from **outside** every minute and alerts you (email, Telegram, etc.) when it's down. It catches problems that metrics can't, like the whole server being off.

### First-time setup
1. Open http://localhost:3002 → create an admin account.
2. **Add New Monitor**:
   - Type: **HTTP(s)**
   - Name: `API liveness`, URL: `http://api:8000/healthz`, interval: 60 s
3. Add a second monitor: `API readiness`, URL `http://api:8000/readyz`.
4. (Optional) **Settings → Notifications** → add Telegram or email so you get alerted.

Use `api:8000`, not `localhost`: Uptime Kuma runs inside Docker and reaches the API by its service name.

**Liveness vs readiness:** `/healthz` = "is the process running?" `/readyz` = "can it reach the database and Redis?" If readiness fails but liveness passes, the app is up but a dependency is down.

---

## 9. Logs: the diary

**What it is:** a line of JSON for every important event, printed to the container output.

```bash
make logs s=api
```

```json
{"event": "http_request", "method": "GET", "route": "/readyz", "status": 200,
 "duration_ms": 4.1, "request_id": "28cd9ea7…", "trace_id": "77bd18…", "level": "info"}
```

- `request_id` links to GlitchTip; `trace_id` links to the trace in Tempo.
- Personal data is masked automatically.
- In production we'll ship these to a log store (Loki) so they're searchable in Grafana too.

---

## 10. Debugging a real problem: the full workflow

> A user says: "The app showed an error when I opened my wishlist."

1. **Is everything down?** Uptime Kuma: are the monitors green?
2. **Is it widespread?** Grafana dashboard: did the error rate or latency spike? Which route?
3. **What crashed?** GlitchTip: the newest issue for that route shows the stack trace and a `request_id`.
4. **What happened around it?** Logs: search for that `request_id` to see every step of the request.
5. **Where was the time spent?** Grafana → Explore → Tempo: open the trace by `trace_id`.
6. **Fix it, write a test that reproduces it,** then resolve the issue in GlitchTip.

Each tool answers one question; the IDs connect them.

## 11. Learn more

| Topic | Where |
|---|---|
| PromQL basics | https://prometheus.io/docs/prometheus/latest/querying/basics/ |
| Grafana fundamentals | https://grafana.com/tutorials/grafana-fundamentals/ |
| OpenTelemetry concepts | https://opentelemetry.io/docs/concepts/ |
| Why p95 instead of average | `docs/08-key-concepts.md` §43 |
| How it's wired in our code | `docs/07-system-architecture.md` §2e |
