"""Complete the look: rules pick the pieces (always), the LLM may word them (optional)."""

import asyncio
import uuid
from dataclasses import replace
from typing import Any, Protocol

import structlog

from stylesense.ai.gateway.exceptions import (
    AIInputTooLargeError,
    AIQuotaExceededError,
    AIUnavailableError,
)
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.modules.catalog.rules import DEFAULT_TYPICAL_PRICE_PAISE, TYPICAL_PRICE_PAISE
from stylesense.modules.catalog.schemas import ProductSummary, SearchQuery
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.looks.rules import OCCASIONS, Piece, assemble, reasons, slots_for
from stylesense.modules.looks.schemas import Look, LookItem
from stylesense.modules.looks.tasks import LOOK_COMPLETE, LookInput, LookOutput, LookPiece

logger = structlog.get_logger(__name__)

CANDIDATES_PER_CATEGORY = 15
_AI_FAILURES = (AIUnavailableError, AIQuotaExceededError, AIInputTooLargeError)
_MAX_REASON_CHARS = 40


class Assistant(Protocol):
    async def run(
        self, spec: TaskSpec[Any, Any], payload: Any, *, user_id: uuid.UUID | None = None
    ) -> Any: ...


class LookService:
    def __init__(self, catalog: CatalogService, ai: Assistant | None = None) -> None:
        self._catalog = catalog
        self._ai = ai

    async def complete(
        self,
        product_id: uuid.UUID,
        *,
        budget_paise: int | None = None,
        gender: str | None = None,
        occasion: str | None = None,
        user_id: uuid.UUID | None = None,
        polish: bool = False,
    ) -> Look:
        """`budget_paise` is for the whole look, anchor included. `polish` asks the LLM to word
        the look (callers opt in: it costs a call; public endpoints never do)."""
        detail = await self._catalog.get_product(product_id)
        anchor = _piece(detail)
        if occasion:  # the shopper's occasion counts as the anchor's, for matching pieces
            anchor = replace(anchor, tags=anchor.tags | {occasion})
        anchor_price = detail.min_price_paise or 0
        remaining = None if budget_paise is None else max(0, budget_paise - anchor_price)
        context = set(detail.tags) | ({occasion} if occasion else set())
        slots = slots_for(detail.category, context)
        who = detail.gender if detail.gender in {"men", "women"} else gender
        categories = sorted({c for slot in slots for c in slot.categories})
        caps = {c: _cap(c, remaining) for c in categories}
        text = " ".join(sorted(context & OCCASIONS)) or None
        found = await asyncio.gather(
            *(
                self._catalog.search(
                    SearchQuery(
                        category=c,
                        gender=who if who in {"men", "women", "unisex"} else None,
                        max_price_paise=caps[c],
                        text=text,
                        limit=CANDIDATES_PER_CATEGORY,
                    )
                )
                for c in categories
            )
        )
        summaries = {h.product.id: h.product for hits in found for h in hits}
        by_category = {
            c: [_piece(h.product) for h in hits] for c, hits in zip(categories, found, strict=True)
        }
        candidates = {
            slot.name: [p for c in slot.categories for p in by_category.get(c, [])]
            for slot in slots
        }
        picks = assemble(anchor, slots, candidates, remaining_paise=remaining, caps=caps)
        items = [
            LookItem(slot=p.slot, product=summaries[p.piece.id], reasons=reasons(anchor, p.piece))
            for p in picks
        ]
        title = _title(occasion or next(iter(sorted(anchor.occasions)), None))
        if polish and items:
            title, items = await self._polish(detail, items, title, user_id)
        total = anchor_price + sum(i.product.min_price_paise or 0 for i in items)
        return Look(
            anchor_id=detail.id,
            title=title,
            items=items,
            total_paise=total,
            budget_paise=budget_paise,
            remaining_paise=None if budget_paise is None else budget_paise - total,
        )

    async def _polish(
        self, anchor: ProductSummary, items: list[LookItem], title: str, user_id: uuid.UUID | None
    ) -> tuple[str, list[LookItem]]:
        if self._ai is None:
            return title, items
        payload = LookInput(
            anchor=_words(anchor),
            items=[_words(i.product) for i in items],
        )
        try:
            out: LookOutput = await self._ai.run(LOOK_COMPLETE, payload, user_id=user_id)
        except _AI_FAILURES as exc:
            logger.info("look_ai_degraded", reason=type(exc).__name__)
            return title, items
        worded = {
            w.product_id: [r[:_MAX_REASON_CHARS] for r in w.reasons if r.strip()] for w in out.items
        }
        polished = [
            i.model_copy(update={"reasons": worded.get(str(i.product.id)) or i.reasons})
            for i in items
        ]
        return out.title, polished


def _piece(p: ProductSummary) -> Piece:
    return Piece(
        id=p.id,
        category=p.category,
        price_paise=p.min_price_paise,
        tags=frozenset(p.tags),
        rating=p.rating,
        rating_count=p.rating_count,
    )


def _cap(category: str, remaining: int | None) -> int:
    """Per piece: what the category usually costs, and never more than the budget left."""
    typical = TYPICAL_PRICE_PAISE.get(category, DEFAULT_TYPICAL_PRICE_PAISE)
    return typical if remaining is None else min(typical, remaining)


def _title(occasion: str | None) -> str:
    return f"Complete the {occasion} look" if occasion else "Complete the look"


def _words(p: ProductSummary) -> LookPiece:
    return LookPiece(id=str(p.id), title=p.title[:80], tags=p.tags[:8])
