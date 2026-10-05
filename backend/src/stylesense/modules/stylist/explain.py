"""'Why this pick' reasons: rule-based always; the LLM may rephrase them when available."""

from collections.abc import Sequence

from stylesense.modules.stylist.ranking import Ranked
from stylesense.modules.stylist.slots import Slots

MAX_REASONS = 3
MAX_REASON_CHARS = 40
_WELL_RATED = 4.0
# Learned from, but meaningless alone on a chip ("Your style: half" = sleeve length).
_VAGUE_TAGS = frozenset(
    {"half", "full", "mid", "high", "short", "knee", "calf", "light", "medium", "dark", "solid"}
)

_ATTRIBUTE_PHRASES = {
    "summer": "Made for summer",
    "winter": "Warm for winter",
    "party": "Party-ready",
    "wedding": "Wedding-worthy",
    "office": "Office-appropriate",
    "college": "College-ready",
    "festive": "Festive pick",
    "date night": "Date-night ready",
    "sports": "Built to move",
    "travel": "Great for travel",
    "casual": "Easy everyday wear",
}


def rule_reasons(item: Ranked, slots: Slots) -> list[str]:
    product = item.hit.product
    reasons = [_phrase(m) for m in item.matched]
    if style := next((t for t in item.liked if t not in _VAGUE_TAGS), None):
        reasons.append(f"Your style: {style}")
    if slots.budget_max_paise is not None and product.min_price_paise is not None:
        reasons.append(f"Within {rupees(slots.budget_max_paise)}")
    if product.rating is not None and product.rating >= _WELL_RATED:
        reasons.append(f"Rated {product.rating:.1f}★")
    if product.offer_count > 1 and product.best_store:
        reasons.append(f"Best price on {product.best_store.title()}")
    return clean(reasons)


def clean(reasons: Sequence[str]) -> list[str]:
    """Dedupe, trim and cap: reasons render as small chips on the card."""
    seen: list[str] = []
    for reason in reasons:
        text = " ".join(reason.split())[:MAX_REASON_CHARS].strip()
        if text and text.lower() not in {s.lower() for s in seen}:
            seen.append(text)
    return seen[:MAX_REASONS]


def rupees(paise: int) -> str:
    return f"₹{paise // 100:,}"


def _phrase(attribute: str) -> str:
    return _ATTRIBUTE_PHRASES.get(attribute, attribute.title())
