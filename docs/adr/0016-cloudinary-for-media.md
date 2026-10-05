# 0016 — Cloudinary for user photos (supersedes 0003)

**Status:** Accepted (2026-10-05)

## Context
CP12 needs private storage for user photos (photo search, try-on selfies) and try-on results. ADR 0003 deferred the choice and suggested self-hosted S3 (MinIO and similar). The owner chose not to run object storage on the homelab, and picked Cloudinary instead.

## Decision
- **Cloudinary behind a `MediaStore` port** (`modules/uploads/ports.py`), implemented over its REST API without the SDK (`integrations/media/cloudinary.py`). The port keeps the vendor swappable.
- **Direct, signed uploads.** `POST /v1/uploads` returns a form signed with our API secret (public id, timestamp, preset). The app uploads straight to Cloudinary, so the bytes never pass through our servers. Signatures expire after 1 hour (Cloudinary rule).
- **One signed upload preset** (`stylesense_user_uploads`) enforces, server-side at Cloudinary:
  - delivery type **authenticated** (no public URLs);
  - allowed formats `jpg,png,webp,heic`, no overwrite, unique names;
  - an **incoming transformation** `c_limit,w_1600,h_1600/q_auto:good` that resizes and re-encodes every file, which also **strips EXIF** (GPS location etc.).
- **We verify, not trust.** `POST /v1/uploads/{id}/confirm` inspects the stored asset through the Admin API and rejects (and deletes) wrong formats, files over 8 MB, or images under 200 px.
- **Signed delivery URLs.** Viewing goes through `s--signature--` URLs we mint; vision models get a 768 px signed variant (fewer tokens). Strict transformations are on, so unsigned resize requests can't spend the quota.
- **24 h lifetime.** Each upload and try-on result row has `expires_at`; the worker's `media.purge` (every 15 min, exclusive) deletes the files through the Admin API first and marks the rows second, so a storage outage leaves rows unmarked and the next run retries. Rows reference users with `SET NULL`, so an account purge never orphans stored files. `cli purge-media` runs it by hand.
- **Errors split in two:** `MediaUnavailableError` (5xx, 429, network: retry later) and `MediaRejectedError` (4xx: retrying can't help). Both render as 503 at the API.

## Consequences
- No storage service to operate. The free plan's credits cover early traffic; the storage cost stays small because nothing is kept beyond 24 h.
- **Signed URLs don't expire** on the free plan (expiring tokens are a paid feature). They're unguessable, only ever returned to the photo's owner, and stop working once the file is deleted.
- **CDN copies can outlive the purge** for a while (minutes, up to ~1 hour while Cloudinary invalidates edge caches). Verified live: originals are gone from storage immediately; one previously viewed URL kept serving from the edge cache briefly. Acceptable given the above; noted in the privacy docs.
- A Cloudinary outage disables photo search and try-on only; everything else keeps working.
