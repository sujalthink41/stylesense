# 0012 — Stylist graph: LangGraph without a checkpointer, rules first, LLM fills gaps

**Status:** Accepted (2026-10-05)

## Context
The spec planned a LangGraph stylist with the Postgres checkpointer and `interrupt()` between turns, and an LLM `understand` node that extracts every slot from free text. Two things changed that picture:

- CP7 already persists each turn in `stylist_sessions` (state + rendered screen) with turn compare-and-swap (ADR 0011). A checkpointer would be a second copy of the same state, with its own schema, migrations and pruning.
- The app must work with no AI key configured, and with the AI degraded or over budget. An LLM-only `understand` turns every outage into "I don't understand you".

## Decision
- **LangGraph runs one turn at a time, compiled without a checkpointer.** The graph is `ingest → understand → (ask | search → rank → explain → compose | detail)`. Its input is the persisted session state; its output is the next screen plus the new state, which the session engine saves atomically with the turn bump. There's no `interrupt()`: the turn simply ends after rendering a question.
- **Rules first.** A deterministic parser (`understanding.py`) extracts category, gender, budget, occasion, colours, fit and fabric, including Hinglish budgets ("1000 tak"). **Numbers always come from the rules**: a model can invent a budget, a regex can't.
- **The LLM only fills gaps.** `stylist.understand` runs only when the rules left a required slot empty. Its output schema pins the vocabulary with `Literal`s, and its values never override what the rules or the user already set.
- **Questions are templates**, in a fixed order (category → gender → budget), at most one per missing slot.
- **Ranking is code**: hard filters (budget, category, gender) in SQL, pgvector similarity, then a weighted score (attribute match, similarity, rating × confidence) with a brand-diversity penalty.
- **Reasons are rules first** ("Within ₹500", "Rated 4.4★"); `stylist.explain` may rephrase them in one batched call, and its output is cleaned (dedupe, length cap) before display.
- **A golden set** (`evals/understand_golden.jsonl`) scores any parser; `cli eval-understand --engine rules|llm` runs it. CP8's bar is 90% field accuracy.

## Consequences
- With no key, or with the AI down, the stylist still works end to end; the only loss is free-text phrasings the rules don't cover. The session records `ai: "degraded"` for analysis.
- One source of truth for session state. Graph code stays pure and fast to test.
- LangGraph features that need a checkpointer (time travel, human-in-the-loop across processes) are off the table. If we ever need them, adopting the checkpointer is additive.
- The golden set was written alongside the parser, so the rules' 100% score is **not** a held-out result. Real queries from `session_events` must become a held-out set once there is traffic.
