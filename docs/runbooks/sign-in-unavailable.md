# Sign-in unavailable

**Severity:** page  ·  **Owner:** backend  ·  **Dashboard:** Grafana → StyleSense API → "Errors by route and status" (`/v1/auth/google` 503s)

## What it means
`POST /v1/auth/google` returns `503 sign_in_unavailable`. Existing users keep working (refresh doesn't need Google); new sign-ins fail.

## Check
```bash
curl -s -X POST localhost:8000/v1/auth/google -H 'content-type: application/json' -d '{"id_token":"x"}' | jq .detail
```
- `"Google sign-in is not configured"` → config problem.
- `"could not reach Google"` → network problem.

## Fix
- **Not configured:** `APP_GOOGLE_CLIENT_IDS` is empty or invalid JSON in the deployed env. Fix it and restart the API. See `docs/guides/google-sign-in-setup.md`.
- **Can't reach Google:** from the API container, `python -c "import urllib.request; print(urllib.request.urlopen('https://www.googleapis.com/oauth2/v3/certs', timeout=5).status)"`. Check DNS, the firewall and the homelab's outbound internet.

## After
If it was a network outage, consider alerting on outbound connectivity from the homelab.
