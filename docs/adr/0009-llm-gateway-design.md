# 0009 — LLM gateway: own adapters, prompts in code, routing and prices in the database

**Status:** Accepted (2026-10-05)

## Context
The spec planned an `LLMGateway` over LangChain's `init_chat_model`. The gateway must own retries, fallbacks, circuit breaking, caching, quotas, budgets and exact cost accounting.

## Decision
- **Thin adapters on the official SDKs** (`openai`, `anthropic`) behind a `ChatProvider`/`EmbeddingProvider` port, with SDK retries disabled. No LangChain chat models: they add a second hidden retry layer and blur token accounting. LangGraph (CP8) still works: graph nodes call the gateway.
- **Tasks are code** (`TaskSpec`: versioned instructions + input/output Pydantic schemas). Prompts change through code review and evals, never through a database edit.
- **Routing is configuration** (`llm_task_configs`): an ordered list of `provider:model` targets (primary, then fallbacks), limits, cache TTL and an on/off switch. Hot-reloaded on every instance through a Redis version counter.
- **No price, no call** (`llm_models`): a model without a configured price is never called, so the daily budget is always enforceable. Model names and prices are never hard-coded.
- Token pre-checks use a conservative tokenizer-free estimate; billing uses the provider's reported counts.

## Consequences
- Switching models, adding a fallback or disabling a task is an admin/CLI action, effective immediately.
- New providers are new adapters (`integrations/llm/`), not gateway changes.
- Prompt changes require a `prompt_version` bump, which is logged with every call for reproducibility.
