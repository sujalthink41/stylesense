# 0007 — Embedder port with an offline hashing baseline until the LLM gateway

**Status:** Accepted (2026-10-05)

## Context
Similarity search (pgvector) needs product embeddings in CP5, but the provider-agnostic LLM gateway, which will call OpenAI's embedding models, only arrives in CP6.

## Decision
- The catalog declares an **`Embedder` port** (`modules/catalog/ports.py`): `model`, `dimensions`, `embed(texts)`.
- CP5 ships **`HashingEmbedder`** (`integrations/embeddings/hashing.py`): words and word pairs feature-hashed into a signed 1536-dimension vector, L2-normalised. Deterministic, offline and free.
- Each product stores `content_hash` (of its text) and `embedding_hash = sha256(model + content_hash)`. A product is re-embedded whenever its text **or the embedding model** changes, detected with a single SQL comparison.

## Consequences
- Similar items work today: neighbours share category, colour, fabric and fit vocabulary.
- **Limit:** hashing captures shared *words*, not meaning ("chill beach shirt" won't match "linen resort shirt"). The CP6 model-based embedder fixes this by plugging into the same port; switching models re-embeds the catalog automatically.
- The vector column is fixed at 1536 dimensions; an embedder with a different size needs a migration.
