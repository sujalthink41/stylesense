# Outbox backlog or dead letters

**Severity:** ticket (page if backlog grows for > 15 min)  ·  **Owner:** backend  ·  **Dashboard:** Grafana → StyleSense API → "Outbox backlog"

## What it means
Side effects (push notifications, try-on jobs, emails) are waiting in `outbox_messages` and not being delivered, or some were given up on (`status = 'dead'`).

## Impact
Users don't get notifications or results; the core app still works.

## Check
1. Is the worker running and healthy?
   ```bash
   make ps            # worker should be "healthy"
   make logs s=worker
   ```
2. What is stuck, and why?
   ```sql
   -- make shell-db
   SELECT topic, status, count(*), max(attempts), min(available_at)
   FROM outbox_messages WHERE status <> 'done' GROUP BY 1, 2;

   SELECT id, topic, attempts, last_error FROM outbox_messages
   WHERE status = 'dead' ORDER BY created_at DESC LIMIT 20;
   ```

## Fix
- **Worker down or unhealthy:** restart it (`docker compose … up -d worker`). Its heartbeat healthcheck marks it unhealthy if the loop hangs.
- **One topic failing repeatedly:** read `last_error`; usually a downstream provider is down. Messages retry automatically with backoff; no action needed if the provider recovers.
- **Dead letters after a fix:** requeue them:
  ```sql
  UPDATE outbox_messages SET status = 'pending', attempts = 0, available_at = now(), last_error = NULL
  WHERE status = 'dead' AND topic = '<topic>';
  ```
  Safe because handlers are idempotent.
- **`no handler for topic`:** a producer writes a topic the worker doesn't know (deploy mismatch). Deploy the worker with the handler, then requeue.

## Escalate
If dead letters keep growing after the downstream recovers, or messages are lost, involve the module owner.

## After
Add a test for the failure mode; tune `outbox_max_attempts` or the handler timeout if retries are too aggressive.
