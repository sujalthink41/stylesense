# 05 — Database Design

**Engine:** PostgreSQL 18 + `pgvector`. Primary keys use `uuid DEFAULT uuidv7()` (time-ordered, index-friendly). All tables have `created_at timestamptz NOT NULL DEFAULT now()`; mutable tables also have `updated_at`. Money is stored as **integer paise** (`price_paise`) to avoid floating-point errors. Migrations are managed by Alembic.

**Conventions**
- `snake_case`, plural table names.
- Soft delete (`deleted_at`) only where needed for recovery (users, boards). Everything else is hard-deleted.
- Enums are Postgres `text` + `CHECK` constraints (easier to evolve than native enums).
- Embedding dimension `D` is set by the configured embedding model (e.g. 1536). Changing the model means re-embedding into a new column or table version.

## 1. Entity relationship overview

```
users ─┬─< auth_identities
       ├─< refresh_tokens
       ├─< user_devices
       ├─< consents
       ├── style_profiles (1:1)
       ├─< stylist_sessions ─< session_events
       ├─< swipes >── products
       ├─< boards ─< board_items >── products
       ├─< uploads
       ├─< tryon_jobs >── products
       ├─< polls ─< poll_options >── products
       │          └─< poll_votes
       ├─< shares
       ├─< price_alerts >── offers
       ├─< notifications
       ├─< outbound_clicks >── offers
       └─< llm_usage

stores ─< offers >── products ─< product_images
                     offers ─< price_snapshots
feed_collections ─< feed_items >── products
llm_providers ─< llm_task_configs ; prompt_templates
feature_flags ; audit_logs ; content_reports ; account_deletions
```

## 2. Identity & accounts

### users
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| email | citext UNIQUE | from Google |
| display_name | text | |
| avatar_url | text | |
| role | text | `user` \| `curator` \| `admin` (CHECK) |
| status | text | `active` \| `suspended` \| `deleting` |
| locale | text | default `en-IN` |
| last_seen_at | timestamptz | |
| deleted_at | timestamptz NULL | soft delete before purge |

### auth_identities
`id`, `user_id FK`, `provider` (`google`), `provider_subject` (Google `sub`), `UNIQUE(provider, provider_subject)`.

### refresh_tokens
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users (cascade) | |
| family_id | uuid | one sign-in session; reuse → revoke the whole family |
| token_hash | bytea UNIQUE | SHA-256 of the opaque token (raw token never stored) |
| installation_id | uuid NULL | app install that owns the session (one session per install) |
| expires_at | timestamptz | 30 days from issue |
| used_at | timestamptz NULL | set when rotated; reuse after the grace window = theft |
| revoked_at | timestamptz NULL | |
Indexes: `(family_id)`, `(user_id) WHERE revoked_at IS NULL`. Rows expired > 7 days are pruned by the worker.

### user_devices
`id`, `user_id`, `installation_id` (client-generated per install), `platform` (`android`/`ios`/`web`), `app_version`, `push_token` (unique when present; moved, not duplicated, when a phone switches accounts), `push_enabled`, `last_active_at`. `UNIQUE(user_id, installation_id)`, so registration is an idempotent upsert.

### consents
`id`, `user_id`, `kind` (`terms`, `privacy`, `photo_processing`, `marketing_push`), `version`, `granted bool`, `granted_at`. Append-only history.

### account_deletions
`id`, `user_id`, `requested_via` (`app`/`web`), `requested_at`, `purge_after` (= +30 days), `purged_at`.

## 3. Style & personalization *(built in CP9)*

### style_profiles (1:1 with users)
| Column | Type | Notes |
|---|---|---|
| user_id | uuid PK FK → users (CASCADE) | |
| fit_preference | text NULL | `men` \| `women` \| `unisex` \| `any` (CHECK); prefills the stylist's gender question |
| styles | text[] | Style DNA picks, e.g. `{streetwear,minimal}` (≤ 3, vocabulary in code) |
| sizes | jsonb | `{"top":"M","bottom":"32","shoe":"UK9"}` |
| taste_vector | vector(1536) NULL | unit EMA of liked product embeddings, seeded by style picks |
| tag_affinity | jsonb | `{"oversized": 4, "neon": -2}`; ±20 cap, ≤ 200 tags |
| swipe_count | int | |
| onboarding_done | bool | |
| updated_at | timestamptz | |

Deferred: `body_type`, `skin_tone` (sensitive; only when a feature needs them), `default_budget`.

### swipes
`id`, `user_id` FK (CASCADE), `product_id` FK (CASCADE), `session_id NULL` (dedupe scope, deliberately **not** a FK: ADR 0013), `direction` (`left`/`right`/`super`, CHECK), `created_at`.
Index: `(user_id, created_at DESC)`; `UNIQUE NULLS NOT DISTINCT (user_id, product_id, session_id)`: replays are no-ops.

## 4. Catalog *(built in CP5)*

### stores
`id`, `code` UNIQUE (`amazon`, `flipkart`, `myntra`), `name`, `allowed_hosts text[]` (the only domains `/v1/out` may redirect to), `active`. Seeded by migration 0004.

### products (canonical item)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | client-generated UUIDv7 (ADR 0008) |
| canonical_key | text UNIQUE | groups the same item across stores; makes ingest idempotent |
| title, brand, category, subcategory | text | |
| gender | text | `men` \| `women` \| `unisex` (CHECK) |
| attributes | jsonb | `{"fabric": "cotton", "fit": "oversized", "occasion": "casual, summer"}` |
| colors, tags, sizes_available | text[] | tags derived from category, gender, colours and attribute values |
| rating | numeric(2,1) | average across offers |
| rating_count | int | summed across offers |
| primary_image_url | text | |
| min_price_paise | int NULL | best in-stock offer, denormalised for filtering |
| active | bool | |
| content_hash | text | sha256 of the embeddable text |
| embedding | vector(1536) NULL | |
| embedding_hash | text NULL | `sha256(model:content_hash)`; stale when it differs (ADR 0007) |

Indexes: HNSW `(embedding vector_cosine_ops)` (m=16, ef_construction=64); `(category, gender, min_price_paise) WHERE active`; GIN `(tags)`.

### product_images
`id`, `product_id`, `url`, `position`; `UNIQUE(product_id, position)`. Updated in place by position on re-ingest.

### offers (a product sold at a store)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| product_id | uuid FK (cascade) | |
| store_id | uuid FK | |
| external_id | text | store's id; `UNIQUE(store_id, external_id)` |
| url | text | must be HTTPS on the store's `allowed_hosts`; never exposed to clients |
| price_paise | int | CHECK > 0 |
| mrp_paise | int NULL | CHECK ≥ price |
| rating | numeric(2,1) NULL | used to break price ties |
| in_stock | bool | |
| sizes_in_stock | text[] | |
| last_refreshed_at | timestamptz | |

### price_snapshots
`id`, `offer_id`, `price_paise`, `captured_at`. Written only when the price changes (first sighting included). Index `(offer_id, captured_at)`. The basis for price-drop alerts (CP13) and future price history.

### outbound_clicks
`id`, `offer_id`, `user_id NULL` (FK, `SET NULL` on purge), `source` (`stylist`/`feed`/`board`/`poll`/`share`/`product`/`other`), `created_at`. Index `(created_at)`.

## 5. Stylist sessions

### stylist_sessions
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | also the LangGraph `thread_id` |
| user_id | uuid FK | |
| entry | text | `occasion_tile` \| `search` \| `photo` \| `feed` |
| status | text | `active` \| `completed` \| `abandoned` |
| slots | jsonb | latest snapshot (for analytics; the checkpoint is authoritative) |
| turn_id | int | current turn (stale-action guard) |
| degraded | bool | ran in degraded mode at any point |
| last_activity_at | timestamptz | |

### session_events
`id`, `session_id`, `turn_id`, `kind` (`action`/`render`/`error`), `payload jsonb`, `created_at`. Used for analytics and debugging; retained 90 days.

### LangGraph checkpoint tables
Created and owned by `langgraph-checkpoint-postgres` (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) in a separate schema `lg`. Old threads are pruned after 30 days of inactivity.

## 6. Boards, shares, polls

### boards
`id`, `user_id`, `name`, `kind` (`wishlist`/`outfit`), `cover_product_id NULL`, `position`, `deleted_at`. One `wishlist` board per user (partial unique index on `(user_id) WHERE kind='wishlist'`).

### board_items
`id`, `board_id`, `product_id`, `preferred_offer_id NULL`, `position`, `note NULL`, `UNIQUE(board_id, product_id)`.

### shares
`id`, `user_id`, `slug` UNIQUE (short, random), `kind` (`look`/`product`/`board`), `payload jsonb` (product ids, title), `views int`, `created_at`.

### polls
`id`, `user_id`, `slug` UNIQUE, `question`, `closes_at`, `status` (`open`/`closed`).

### poll_options
`id`, `poll_id`, `product_id`, `position`.

### poll_votes
`id`, `poll_id`, `option_id`, `voter_fingerprint` (hash of device cookie), `ip_hash`, `created_at`, `UNIQUE(poll_id, voter_fingerprint)`.

## 7. Uploads & try-on

### uploads
`id`, `user_id`, `kind` (`photo_search`/`selfie`), `object_key` (MinIO), `mime`, `bytes`, `moderation_status` (`pending`/`ok`/`rejected`), `expires_at` (= +24 h), `deleted_at`.

### tryon_jobs
`id`, `user_id`, `selfie_upload_id`, `product_id`, `provider`, `provider_job_id`, `status` (`queued`/`running`/`done`/`failed`), `result_object_key NULL`, `error NULL`, `cost_usd numeric(10,4)`, `expires_at`, `created_at`, `finished_at`.
Index `(user_id, created_at DESC)` (also used for the daily quota count).

## 8. Feed & notifications

### feed_collections
`id`, `slug`, `title`, `subtitle`, `kind` (`auto`/`curated`), `rules jsonb` (for auto), `pinned bool`, `position`, `valid_from`, `valid_to`.

### feed_items
`id`, `collection_id`, `product_id`, `position`. `UNIQUE(collection_id, product_id)`.

### price_alerts
`id`, `user_id`, `offer_id`, `baseline_price_paise`, `threshold_pct` (default 10), `active bool`, `last_notified_at`. `UNIQUE(user_id, offer_id)`.

### notifications
`id`, `user_id`, `kind` (`price_drop`/`poll_result`/`tryon_ready`/`system`), `title`, `body`, `data jsonb` (deep link), `read_at NULL`, `pushed_at NULL`. Index `(user_id, created_at DESC)`.

## 9. AI configuration & metering *(built in CP6)*

### llm_models (prices)
`id`, `provider`, `model` (`UNIQUE(provider, model)`), `kind` (`chat`/`embedding`), `input_usd_per_mtok`, `cached_input_usd_per_mtok`, `output_usd_per_mtok` (numeric(12,6)), `active`, `updated_at`, `updated_by`. A model with no active row is never called (ADR 0009). API keys are **never** stored here; they come from environment variables.

### llm_task_configs (routing)
| Column | Type | Notes |
|---|---|---|
| task | text PK | e.g. `stylist.explain`, `diagnostics.echo` |
| targets | text[] | `provider:model`, primary first, then fallbacks |
| temperature | float NULL | ignored by providers that don't support it |
| max_input_tokens / max_output_tokens | int | |
| timeout_s | float | per attempt |
| cache_ttl_s | int | 0 = no response caching |
| enabled | bool | false → callers degrade immediately |
| updated_at, updated_by | | |

Prompts are not stored in the database; they live in code with a `prompt_version`.

### llm_usage (ledger)
One row **per attempt**: `id`, `call_id` (groups attempts of one gateway call), `task`, `provider`, `model`, `user_id` (FK, `SET NULL`), `prompt_version`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_micro_usd` (bigint), `latency_ms`, `outcome` (`ok`/`cache_hit`/`error`/`invalid_output`), `error`, `created_at`. Indexes `(created_at)`, `(task, created_at)`.

## 10. Platform & governance

- **feature_flags:** `key` PK, `enabled`, `rules jsonb` (percentage/user allow-list), `updated_at`.
- **rate_limit_policies:** `key` PK (e.g. `ai.per_user.hour`), `limit`, `window_s`, `updated_at` (cached in Redis; code defaults if missing).
- **audit_logs:** `id`, `actor_user_id`, `action`, `entity`, `entity_id`, `before jsonb`, `after jsonb`, `ip_hash`, `created_at`. Append-only.
- **content_reports:** `id`, `reporter_user_id`, `target_kind` (`tryon`/`product`/`share`/`poll`), `target_id`, `reason`, `status` (`open`/`actioned`/`dismissed`), `resolved_by`, `resolved_at`.

## 11. Data lifecycle

| Data | Retention |
|---|---|
| Selfies, photo uploads, try-on results | 24 h, then purged by cron |
| session_events | 90 days |
| LangGraph checkpoints | 30 days of inactivity |
| llm_usage | 13 months (rollups kept forever) |
| outbound_clicks | 24 months |
| Deleted accounts | purged 30 days after the request |

## 12. DB roles

- `stylesense_migrator`: DDL (Alembic only).
- `stylesense_app`: DML on app tables, no DDL.
- `stylesense_readonly`: analytics/admin reporting.
- Langfuse and GlitchTip use their **own databases** on the same Postgres instance.
