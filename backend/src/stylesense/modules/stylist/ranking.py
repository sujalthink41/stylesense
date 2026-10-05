"""Hybrid ranking in plain code: hard filters were applied in SQL; here we order by soft signals.

score = 0.40 · attribute match + 0.35 · text similarity + 0.25 · rating confidence
(attribute match is weighted: colour and fabric count more than occasion, see Slots)
with taste (CP9): 0.30 · match + 0.25 · similarity + 0.25 · taste + 0.20 · rating,
where taste = mean(taste-vector similarity, tag affinity). Then a brand-diversity pass so one
brand can't fill the deck.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from stylesense.modules.catalog.schemas import SearchHit
from stylesense.modules.personalization.taste import affinity_score
from stylesense.modules.stylist.slots import Slots

W_MATCH, W_SIMILARITY, W_RATING = 0.40, 0.35, 0.25
TW_MATCH, TW_SIMILARITY, TW_TASTE, TW_RATING = 0.30, 0.25, 0.25, 0.20
_BRAND_PENALTY = 0.85  # each extra pick from the same brand keeps 85% of its score
_RATING_FLOOR, _RATING_SPAN = 3.0, 2.0
_CONFIDENT_RATINGS = 200


@dataclass(frozen=True, slots=True)
class Ranked:
    hit: SearchHit
    score: float
    matched: tuple[str, ...]  # requested attributes this item has (used for reasons)
    liked: tuple[str, ...] = ()  # tags the user's swipes favour (used for reasons)


def rank(
    hits: Sequence[SearchHit],
    slots: Slots,
    *,
    limit: int,
    affinity: Mapping[str, int] | None = None,
) -> list[Ranked]:
    wanted = slots.preference_weights()
    affinity = affinity or {}
    personal = bool(affinity) or any(h.taste_similarity is not None for h in hits)
    scored = [
        _score(h, wanted, affinity if personal else None) for h in hits if _within_budget(h, slots)
    ]
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


def _score(
    hit: SearchHit, wanted: Mapping[str, float], affinity: Mapping[str, int] | None
) -> Ranked:
    tags = set(hit.product.tags)
    matched = tuple(sorted(wanted.keys() & tags))
    match = sum(wanted[t] for t in matched) / sum(wanted.values()) if wanted else 0.0
    similarity = max(0.0, hit.similarity) if hit.similarity is not None else 0.0
    if affinity is None:
        score = W_MATCH * match + W_SIMILARITY * similarity + W_RATING * _rating(hit)
        return Ranked(hit=hit, score=score, matched=matched)
    score = (
        TW_MATCH * match
        + TW_SIMILARITY * similarity
        + TW_TASTE * _taste(hit, tags, affinity)
        + TW_RATING * _rating(hit)
    )
    liked = tuple(
        sorted(
            (t for t in tags - wanted.keys() if affinity.get(t, 0) > 0),
            key=lambda t: (-affinity[t], t),
        )
    )
    return Ranked(hit=hit, score=score, matched=matched, liked=liked[:3])


def _taste(hit: SearchHit, tags: set[str], affinity: Mapping[str, int]) -> float:
    signals = [affinity_score(affinity, tags)] if affinity else []
    if hit.taste_similarity is not None:
        signals.append(max(0.0, hit.taste_similarity))
    return sum(signals) / len(signals) if signals else 0.0


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
