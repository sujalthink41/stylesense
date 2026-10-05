# Photos or try-on failing

**Severity:** ticket (page if the purge has failed for > 6 h: stored photos would outlive their 24 h promise)  ·  **Owner:** backend  ·  **Dashboard:** Grafana → StyleSense API → "Try-on jobs by outcome", "Images purged after 24 h"

## What it means
- `media_unavailable` / `media_rejected` (503) on `/v1/uploads` or `/v1/tryon`: Cloudinary is down, misconfigured, or refusing our requests.
- Try-on jobs ending `gave_up`: the vendor was busy or timing out 3 times in a row.
- Purge errors in the worker log: expired photos are still stored.

## Check
```bash
make logs s=worker | grep -E "cloudinary_error|tryon_gave_up|tryon_result_refused|uploads_purged|tryon_results_purged"
docker compose ... exec api python -m stylesense.cli purge-media     # runs the purge now
curl -u "$KEY:$SECRET" https://api.cloudinary.com/v1_1/$CLOUD/ping   # credentials + cloud name
```
SQL: `select status, count(*) from tryon_jobs where created_at > now() - interval '1 day' group by 1;` and `select count(*) from uploads where deleted_at is null and expires_at < now();` (should be ~0).

## Fix
- **`cloud_name mismatch` / 401:** wrong `APP_CLOUDINARY_*` values; see [Cloudinary setup](../guides/cloudinary-setup.md). Restart api + worker after fixing `.env`.
- **"unknown file format not allowed":** something sent a format the preset refuses (e.g. SVG). The job fails once (not retried); fix the source of the image.
- **Cloudinary 5xx / timeouts:** wait; the purge and try-on retry by themselves. Rows are only marked deleted after Cloudinary confirms.
- **`gave_up` spikes:** the try-on vendor is struggling. Users can tap retry (no quota). If it persists, set `APP_TRYON_PROVIDER=none` to switch try-on off cleanly.
- **Spend:** `APP_TRYON_GLOBAL_DAILY_LIMIT` caps paid renders per day; lower it in an emergency.

## After
If expired photos stayed stored for more than 24 h, note it in the privacy log and confirm with the SQL above that the backlog reached zero.
