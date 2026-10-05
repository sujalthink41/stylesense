# Runbooks

Every alert links to a runbook here. Write it for someone woken at 3 a.m. who has never seen the system: short, concrete, copy-pasteable.

Copy [`_template.md`](_template.md) to `<alert-name>.md`.

| Runbook | Fires when |
|---|---|
| [api-not-ready](api-not-ready.md) | `/readyz` returns 503 |
| [outbox-backlog](outbox-backlog.md) | Outbox backlog grows or dead letters appear |
| [sign-in-unavailable](sign-in-unavailable.md) | Google sign-in returns 503 |
| [ai-degraded](ai-degraded.md) | AI calls unavailable or budget exhausted |
