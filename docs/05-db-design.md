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
| user_id | uuid FK | |
| family_id | uuid | rotation family; reuse → revoke the whole family |
| token_hash | bytea UNIQUE | SHA-256 of the opaque token |
| expires_at | timestamptz | |
| revoked_at | timestamptz NULL | |
| replaced_by | uuid NULL | next token in the chain |
| device_id | uuid NULL FK user_devices | |
Index: `(user_id) WHERE revoked_at IS NULL`.

### user_devices
`id`, `user_id`, `platform` (`android`/`ios`), `push_token` UNIQUE, `app_version`, `last_active_at`, `push_enabled bool`.

### consents
`id`, `user_id`, `kind` (`terms`, `privacy`, `photo_processing`, `marketing_push`), `version`, `granted bool`, `granted_at`. Append-only history.

### account_deletions
`id`, `user_id`, `requested_via` (`app`/`web`), `requested_at`, `purge_after` (= +30 days), `purged_at`.

## 3. Style & personalization

### style_profiles (1:1 with users)
| Column | Type | Notes |
|---|---|---|
| user_id | uuid PK FK | |
| fit_preference | text | `men` \| `women` \| `unisex` \| `any` |
| body_type | text NULL | |
| skin_tone | text NULL | coarse buckets only |
| sizes | jsonb | `{"top":"M","bottom":"32","shoe":"9"}` |
| styles | text[] | e.g. `{streetwear,minimal}` |
| default_budget | int4range NULL | paise |
| taste_vector | vector(D) NULL | EMA of liked/skipped product embeddings |
| tag_affinity | jsonb | `{"oversized": 4, "neon": -2}` |
| onboarding_done | bool | |
| updated_at | timestamptz | |

### swipes
`id`, `user_id`, `product_id`, `session_id NULL`, `direction` (`left`/`right`/`super`), `created_at`.
Index: `(user_id, created_at DESC)`; `UNIQUE(user_id, product_id, session_id)`.

## 4. Catalog

### stores
`id`, `code` UNIQUE (`amazon`, `flipkart`, `myntra`), `name`, `logo_url`, `active bool`, `source_adapter` (`mock`/`amazon`/…), `affiliate_config jsonb` (non-secret params only).

### products (canonical item)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| title | text | |
| brand | text | |
| category | text | `tshirt`, `shirt`, `jeans`, `kurta`, `dress`, `shoes`, … |
| subcategory | text NULL | |
| gender | text | `men` \| `women` \| `unisex` |
| attributes | jsonb | `{"fabric":"cotton","fit":"oversized","sleeve":"half","pattern":"solid","occasion":["casual","summer"]}` |
| colors | text[] | normalized color names |
| tags | text[] | derived, used for affinity + LLM compact view |
| sizes_available | text[] | |
| rating | numeric(2,1) | best/aggregated across offers |
| rating_count | int | |
| primary_image_url | text | |
| embedding | vector(D) | text (+ later image) embedding |
| min_price_paise | int | denormalized best active offer price |
| active | bool | |
| updated_at | timestamptz | |

Indexes:
- `HNSW (embedding vector_cosine_ops)`
- `(category, gender, min_price_paise) WHERE active`
- `GIN (tags)`, `GIN (attributes jsonb_path_ops)`

### product_images
`id`, `product_id`, `url`, `position`, `alt`.

### offers (a product sold at a store)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| product_id | uuid FK | |
| store_id | uuid FK | |
| external_id | text | store's product id (ASIN, FSN, …) |
| url | text | plain product URL |
| price_paise | int | current price |
| mrp_paise | int NULL | for "% off" |
| in_stock | bool | |
| sizes_in_stock | text[] | |
| last_refreshed_at | timestamptz | |
`UNIQUE(store_id, external_id)`; index `(product_id)`.

### price_snapshots
`id`, `offer_id`, `price_paise`, `captured_at`. Index `(offer_id, captured_at DESC)`. Written only when the price changes. This is also the future base for price history.

### outbound_clicks
`id`, `user_id NULL`, `offer_id`, `session_id NULL`, `source` (`stylist`/`feed`/`board`/`poll`/`share`), `created_at`. Monthly partitioning once volume grows.

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

## 9. AI configuration & metering

### llm_providers
`id`, `code` UNIQUE (`openai`, `anthropic`, `google`, `ollama`), `enabled`, `base_url NULL`, `env_key_name` (name of the env var that holds the key, **never the key itself**).

### llm_task_configs
| Column | Type | Notes |
|---|---|---|
| task | text PK | e.g. `stylist.explain` |
| provider_code | text FK | |
| model | text | |
| fallbacks | jsonb | `[{"provider":"anthropic","model":"…"}]` |
| params | jsonb | temperature, top_p… |
| max_input_tokens / max_output_tokens | int | |
| timeout_s | int | |
| cache_ttl_s | int | |
| prompt_version | text | |
| enabled | bool | false → degraded mode for this task |
| updated_by / updated_at | | audited |

### prompt_templates
`id`, `task`, `version`, `system`, `template`, `notes`, `active bool`, `UNIQUE(task, version)`.

### llm_usage
`id`, `user_id NULL`, `session_id NULL`, `task`, `provider`, `model`, `prompt_version`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `cost_usd numeric(10,6)`, `latency_ms`, `cache_hit bool`, `outcome` (`ok`/`fallback`/`degraded`/`error`), `created_at`.
Index `(created_at)`, `(user_id, created_at)`. Monthly partitions. The daily rollup view feeds the admin cost dashboard.

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
