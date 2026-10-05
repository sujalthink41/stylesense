# AI degraded or unavailable

**Severity:** ticket (page if the budget runs out before midday)  ·  **Owner:** backend  ·  **Dashboard:** Grafana → StyleSense API → AI panels

## What it means
Gateway calls end in `AIUnavailableError` (`ai_unavailable` / `ai_budget_exhausted`). The app keeps working with rule-based fallbacks: plainer questions and reasons, no photo understanding.

## Check
```bash
# providers + spend vs budget (admin token), or the CLI:
docker compose ... exec api python -m stylesense.cli llm-check
curl -s -H "Authorization: Bearer $ADMIN" localhost:8000/v1/admin/ai/usage?days=1 | jq
make logs s=api | grep -E "llm_target_failed|llm_target_unusable|circuit_opened|ai_budget"
```

## Fix
- **`ai_budget_exhausted`:** today's spend hit `APP_LLM_DAILY_BUDGET_USD`. Check the usage report for the expensive task; consider caching (`--cache-ttl`), a cheaper primary model, or a higher budget. Resets at 00:00 UTC.
- **`circuit_opened` / provider errors:** the provider is down or rate-limiting. Add or reorder fallbacks (`llm-route`); the breaker probes again after the cooldown automatically.
- **`llm_target_unusable` reason "no price":** the routed model has no price; set one (`llm-price`).
- **`llm_target_unusable` reason "no provider":** its API key isn't set in this environment.
- **Many `invalid_output`:** the model can't follow the schema; route the task to a stronger model and investigate the prompt (bump `prompt_version` with the fix).

## After
If a provider outage caused it, make sure every user-facing task has a fallback on a different provider.
