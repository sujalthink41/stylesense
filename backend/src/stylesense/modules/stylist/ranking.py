"""Hybrid ranking in plain code: hard filters were applied in SQL; here we order by soft signals.

score = 0.40 · attribute match + 0.35 · text similarity + 0.25 · rating confidence,
then a brand-diversity pass so one brand can't fill the deck.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from stylesense.modules.catalog.schemas import SearchHit
from stylesense.modules.stylist.slots import Slots

W_MATCH, W_SIMILARITY, W_RATING = 0.40, 0.35, 0.25
_BRAND_PENALTY = 0.85  # each extra pick from the same brand keeps 85% of its score
_RATING_FLOOR, _RATING_SPAN = 3.0, 2.0
_CONFIDENT_RATINGS = 200


@dataclass(frozen=True, slots=True)
class Ranked:
    hit: SearchHit
    score: float
    matched: tuple[str, ...]  # requested attributes this item has (used for reasons)


def rank(hits: Sequence[SearchHit], slots: Slots, *, limit: int) -> list[Ranked]:
    wanted = slots.preferences()
    scored = [_score(h, slots, wanted) for h in hits if _within_budget(h, slots)]
    scored.sort(key=lambda r: (-r.score, str(r.hit.product.id)))
    return _diversify(scored, limit)


def _within_budget(hit: SearchHit, slots: Slots) -> bool:
    """Defence in depth: SQL already filtered, but the budget promise is never broken here."""
    price = hit.product.min_price_paise
    if price is None:
        return False
    if slots.budget_max_paise is not None and price > slots.budget_max_paise:
        return False
    return slots.budget_min_paise is None or price >= slots.budget_min_paise


def _score(hit: SearchHit, slots: Slots, wanted: set[str]) -> Ranked:
    tags = set(hit.product.tags)
    matched = tuple(sorted(wanted & tags))
    match = len(matched) / len(wanted) if wanted else 0.0
    similarity = max(0.0, hit.similarity) if hit.similarity is not None else 0.0
    score = W_MATCH * match + W_SIMILARITY * similarity + W_RATING * _rating(hit)
    return Ranked(hit=hit, score=score, matched=matched)


def _rating(hit: SearchHit) -> float:
    product = hit.product
    if product.rating is None:
        return 0.0
    quality = min(1.0, max(0.0, (product.rating - _RATING_FLOOR) / _RATING_SPAN))
    confidence = min(1.0, product.rating_count / _CONFIDENT_RATINGS)
    return quality * confidence


def _diversify(ranked: list[Ranked], limit: int) -> list[Ranked]:
    picked: list[Ranked] = []
    brands: Counter[str] = Counter()
    pool = list(ranked)
    while pool and len(picked) < limit:
        best = max(pool, key=lambda r: r.score * _BRAND_PENALTY ** brands[r.hit.product.brand])
        pool.remove(best)
        picked.append(best)
        brands[best.hit.product.brand] += 1
    return picked
