# API not ready

**Severity:** page  ·  **Owner:** backend  ·  **Dashboard:** Grafana → StyleSense → StyleSense API

## What it means
`GET /readyz` returns 503: the API is running but can't reach a dependency (Postgres or Redis). Traffic should be routed away from it.

## Impact
If every API instance is not ready, the app is down for all users.

## Check
1. See which dependency is failing:
   ```bash
   curl -s localhost:8000/readyz | jq
   ```
   Each check shows `ok` and, on failure, only the error type (`TimeoutError`, `ConnectionRefusedError`, …).
2. Check the dependency containers:
   ```bash
   make ps
   make logs s=postgres   # or s=redis
   ```

## Fix
- **`postgres` failing, container down or restarting:** check disk space (`df -h`) and the Postgres logs; restart with `docker compose … up -d postgres`.
- **`postgres` failing with `TimeoutError` while the container is up:** the pool may be exhausted. In Grafana, check "DB connection pool" (in use = open = size + overflow). Look for slow queries: `make shell-db`, then `SELECT pid, now()-query_start AS age, query FROM pg_stat_activity WHERE state <> 'idle' ORDER BY age DESC;`
- **`redis` failing:** check memory (`redis-cli info memory`). We run `noeviction`, so a full Redis rejects writes; raise `maxmemory` or find the key growth.

## Escalate
If a dependency won't come back within 15 minutes, or data loss is suspected, stop and restore from backup (CP19 runbook).

## After
Postmortem if users were affected. Add an alert that would have warned earlier (disk, memory, pool saturation).
