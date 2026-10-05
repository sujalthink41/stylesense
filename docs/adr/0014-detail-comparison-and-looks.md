# 0014 — Detail, comparison fallback and complete-the-look: rules decide, catalog v2

**Status:** Accepted (2026-10-05)

## Context
CP10 adds three things to the stylist: a full product detail screen, a store comparison that still helps when only one store stocks the item, and "complete the look" within a budget. Three questions came up:

1. The v1 catalog had no full-detail component and no generic product rail. `complete_the_look` is semantically specific, so reusing it for "similar items" would mislead the renderer.
2. Who picks outfit pieces: an LLM ("what goes with this?"), or code?
3. What does "within budget" mean for a look, when the session's budget was for one item ("t-shirt under 500")?

## Decision
- **GenUI catalog v2** adds `product_detail` (images, price, MRP, rating, colours, sizes, fact chips) and `product_carousel` (a titled rail of product cards). `CATALOG_VERSION` = 2; a v1 app gets the update banner in those slots and still sees `store_comparison` and `complete_the_look` (ADR 0011 negotiation).
- **Comparison is exact first:** every store's offer for the same canonical product, with exactly one best offer: cheapest in stock, ties to the better rating, then the store code (`rules.best_offer`, shared by ingest and display). **Fallback:** when fewer than 2 stores have it in stock, a "Similar picks" rail shows the same category, ordered by embedding similarity, in stock, within the request's budget (only when the item is the category that was asked for).
- **Rules pick the look; the LLM only words it.** Slots per anchor category (e.g. t-shirt → bottom, shoes, plus a layer only for cold occasions); score = 0.45 colour harmony + 0.30 occasion fit + 0.25 rating confidence. A **casual/dressy clash is never eligible**. Assembly is an exact search over a shortlist per slot (best 6 by score + cheapest few), maximising Σ(1 + score), so fuller looks beat smaller ones. `look.complete` may rename the look and rephrase reasons; it can't add, remove or reprice pieces.
- **Budget semantics:** with no look budget, each piece is capped at its category's typical price (`TYPICAL_PRICE_PAISE`). With a look budget (slider `q_look_budget` on the detail screen, or `budget_paise` on the REST endpoint), it covers the **whole look, anchor included**: Σ pieces ≤ budget − anchor price, and each piece ≤ min(typical, remaining). The detail screen shows the remaining budget.
- **Public endpoints never spend LLM budget:** `GET /v1/products/{id}/complete-look` and `/alternatives` are rules-only and cacheable (ETag). The polished look appears only in signed-in stylist sessions, under the user's AI quota.

## Consequences
- Every budget and best-price rule is a pure function with property tests (Hypothesis): a look never exceeds the budget, never repeats or includes the anchor, never clashes, and fills every slot it can afford.
- Look quality is bounded by catalog tags. With mock data, a "formal trouser" tagged "casual" can still be paired with a tee. Real catalogs need clean occasion tags, and that's the place to fix it.
- A v1 app sees banners on the detail screen until it updates: acceptable, since no v1 app has shipped.
