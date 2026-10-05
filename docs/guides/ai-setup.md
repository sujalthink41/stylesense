# AI Setup: Keys, Prices, Routing

Every AI call in StyleSense goes through the **LLM gateway**. Nothing is hard-coded: you choose which provider and model serves each task, its fallbacks, and what each model costs. Until something is configured, AI features report "unavailable" and the app falls back to rule-based behaviour.

Three steps: **add a key → set prices → route tasks**.

---

## 1. Add an API key

In `.env` (never commit it, never paste it into chats or tickets):

```
APP_OPENAI_API_KEY=sk-...
# optional second provider, used as a fallback:
APP_ANTHROPIC_API_KEY=sk-ant-...
APP_LLM_DAILY_BUDGET_USD=2.00
```

Restart: `make up`. A provider is enabled only when its key is set.

## 2. Set model prices

The gateway **refuses to call a model without a price**; otherwise the daily budget cap couldn't work. Look up current prices on the provider's pricing page (OpenAI: https://openai.com/api/pricing, Anthropic: https://www.anthropic.com/pricing). Prices are **USD per million tokens**: input, cached input and output.

```bash
docker compose ... exec api python -m stylesense.cli llm-price openai:<chat-model> \
    --input <usd> --cached <usd> --output <usd>

# embeddings (only needed if you switch APP_EMBEDDING_MODEL away from "hashing")
docker compose ... exec api python -m stylesense.cli llm-price openai:<embedding-model> \
    --input <usd> --cached <usd> --output 0 --kind embedding
```

Or use the admin API: `PUT /v1/admin/ai/models/{provider}/{model}`.

## 3. Route tasks to models

Each task gets an ordered list: the first model is the **primary**, the rest are **fallbacks**.

```bash
# smoke-test task, used by llm-check
docker compose ... exec api python -m stylesense.cli llm-route diagnostics.echo \
    openai:<chat-model> anthropic:<backup-model> --max-output 100
```

Options: `--max-input` (token cap), `--max-output`, `--timeout` (seconds), `--cache-ttl` (seconds; 0 = no caching), `--temperature`, `--disable` (switch a task off instantly; callers degrade gracefully).

Changes apply to **every running instance within one request**; no restart needed. The admin equivalent is `PUT /v1/admin/ai/tasks/{task}`.

## 4. Check it works

```bash
docker compose ... exec api python -m stylesense.cli llm-check
# {"ok": true, "providers": ["openai"]}
```

`ok: false` comes with the reason: no key, no price, or the provider failing.

## 5. Switch embeddings to a real model (optional)

Similar-item search starts with an offline word-hashing embedder. For meaning-based search, set an embedding model that returns **1536-dimensional** vectors and price it (step 2):

```
APP_EMBEDDING_MODEL=openai:<1536-dim embedding model>
```

After a restart, the worker re-embeds the whole catalog automatically.

## Watching cost and health

| Where | What |
|---|---|
| `GET /v1/admin/ai/status` | Configured providers, spend today vs the daily budget |
| `GET /v1/admin/ai/usage?days=7` | Attempts, errors, cache hits, tokens, cost and p95 latency per day, task and model |
| Grafana → StyleSense API | "AI spend", "AI attempts by outcome", "AI p95 latency by model" |
| Grafana → Explore → Tempo | Each AI call is a `chat <model>` span with token counts |

## What protects you

| Guard | Behaviour |
|---|---|
| Daily budget | When today's spend reaches `APP_LLM_DAILY_BUDGET_USD`, AI calls stop and the app degrades; a warning is logged at 80% |
| Per-user quota | 30 AI actions per hour per user (token bucket) |
| Retries | Up to 3 attempts on rate limits/5xx/timeouts, with backoff; long `Retry-After` → switch to the fallback instead of waiting |
| Circuit breaker | A model failing repeatedly is skipped for a minute across all instances, then probed once |
| Repair | Invalid JSON gets one corrective retry before moving to the fallback |
| Input cap | Oversized inputs are refused before any tokens are spent |
| Cache | Identical requests (same task, prompt version and input) can be served from Redis for free |
