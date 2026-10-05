"""Deterministic request understanding: free text → slots, no AI needed.

The LLM (when configured) only fills gaps this parser leaves; numbers always come from here,
because a model can hallucinate a budget but a regex can't.
"""

import re

from stylesense.modules.stylist.slots import MAX_BUDGET_PAISE, Slots

_MIN_RUPEES = 50  # smaller numbers are sizes, counts or typos, not prices
_AROUND_LOW, _AROUND_HIGH = 0.7, 1.2

# Order matters: longer, more specific phrases first ("t shirt" before "shirt").
_CATEGORY_TERMS: list[tuple[str, str]] = [
    (r"t[\s-]?shirts?|tees?|polo", "tshirt"),
    (r"crop tops?|tank tops?|tops?|tunics?|blouses?", "top"),
    (r"jeans", "jeans"),
    (r"trousers?|pants|chinos?|cargos?", "trousers"),
    (r"kurtas?|kurtis?", "kurta"),
    (r"dress(?:es)?|gowns?|frocks?", "dress"),
    (r"shorts", "shorts"),
    (r"sneakers?|shoes|trainers|kicks", "sneakers"),
    (r"jackets?|bombers?|puffers?|windcheaters?", "jacket"),
    (r"hoodies?|sweatshirts?", "hoodie"),
    (r"shirts?|button[\s-]?downs?", "shirt"),
]
_GENDER_TERMS: list[tuple[str, str]] = [
    (r"unisex", "unisex"),
    (r"women'?s?|woman|female|girls?|ladies|lady|her|wife", "women"),
    (r"men'?s?|man|male|boys?|guys?|gents|him|husband", "men"),
]
_OCCASION_TERMS: list[tuple[str, str]] = [
    (r"date night|date", "date night"),
    (r"wedding guest|wedding|shaadi|marriage|sangeet|reception", "wedding"),
    (r"diwali|festive|festival|eid|navratri|puja|pooja", "festive"),
    (r"party|partywear", "party"),
    (r"office|formal|work(?:wear)?", "office"),
    (r"college|campus|university", "college"),
    (r"gym|sports?|running|workout|training", "sports"),
    (r"travel|trip|vacation|holiday|beach|goa", "travel"),
    (r"summer", "summer"),
    (r"winter|cold", "winter"),
    (r"casual", "casual"),
]
_COLOR_TERMS: list[tuple[str, str]] = [
    (r"light blue|sky blue", "sky blue"),
    (r"off[\s-]?white", "off-white"),
    (r"gr[ae]y", "grey"),
    *(
        (rf"{c}", c)
        for c in (
            "black",
            "white",
            "navy",
            "olive",
            "beige",
            "maroon",
            "mustard",
            "pink",
            "red",
            "green",
            "lavender",
            "brown",
        )
    ),
]
_FIT_TERMS = [
    (r"wide[\s-]?leg", "wide-leg"),
    *(
        (rf"{f}", f)
        for f in ("oversized", "slim", "regular", "relaxed", "skinny", "straight", "bootcut")
    ),
]
_FABRIC_TERMS = [
    (rf"{f}", f)
    for f in (
        "cotton",
        "linen",
        "denim",
        "silk",
        "rayon",
        "polyester",
        "khadi",
        "georgette",
        "fleece",
    )
]

_AMOUNT = r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b"
_RANGE = re.compile(rf"(?:between\s+)?{_AMOUNT}\s*(?:-|\u2013|to|and)\s*{_AMOUNT}")
_AT_MOST = re.compile(
    rf"(?:under|below|less than|within|up\s?to|upto|max(?:imum)?|budget(?: of| is)?)\s*{_AMOUNT}"
    rf"|{_AMOUNT}\s*(?:tak|se kam|or less|max)\b"
)
_AROUND = re.compile(rf"(?:around|about|approx(?:imately)?|~)\s*{_AMOUNT}")
_BARE = re.compile(rf"(?<![\w.]){_AMOUNT}")
_SIZE_CONTEXT = re.compile(r"(?:size|uk|us|eu|waist)\s*\d+|\d+\s*(?:waist|inch|cm|uk)\b")


def parse_request(text: str) -> Slots:
    lowered = text.lower()
    low, high = _budget(lowered)
    return Slots(
        category=_first(lowered, _CATEGORY_TERMS),
        gender=_first(lowered, _GENDER_TERMS),
        occasion=_first(lowered, _OCCASION_TERMS),
        colors=_all(lowered, _COLOR_TERMS),
        fit=_first(lowered, _FIT_TERMS),
        fabric=_first(lowered, _FABRIC_TERMS),
        budget_min_paise=low,
        budget_max_paise=high,
    )


def _first(text: str, terms: list[tuple[str, str]]) -> str | None:
    """The value whose term appears earliest in the text (word-bounded)."""
    best: tuple[int, str] | None = None
    for pattern, value in terms:
        match = re.search(rf"\b(?:{pattern})\b", text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), value)
    return best[1] if best else None


def _all(text: str, terms: list[tuple[str, str]]) -> list[str]:
    found: dict[str, int] = {}
    for pattern, value in terms:
        match = re.search(rf"\b(?:{pattern})\b", text)
        if match and value not in found:
            found[value] = match.start()
    return sorted(found, key=found.__getitem__)


def _budget(text: str) -> tuple[int | None, int | None]:
    text = _SIZE_CONTEXT.sub(" ", text)
    if match := _RANGE.search(text):
        a, b = _rupees(match.group(1), match.group(2)), _rupees(match.group(3), match.group(4))
        if a and b:
            return _paise(min(a, b)), _paise(max(a, b))
    if match := _AT_MOST.search(text):
        amount = _rupees(match.group(1), match.group(2)) or _rupees(match.group(3), match.group(4))
        return (None, _paise(amount)) if amount else (None, None)
    if match := _AROUND.search(text):
        amount = _rupees(match.group(1), match.group(2))
        if amount:
            return _paise(amount * _AROUND_LOW), _paise(amount * _AROUND_HIGH)
    for match in _BARE.finditer(text):  # a lone plausible price, e.g. "kurta 1200"
        if amount := _rupees(match.group(1), match.group(2)):
            return None, _paise(amount)
    return None, None


def _rupees(number: str | None, thousands: str | None) -> float | None:
    if not number:
        return None
    try:
        value = float(number.replace(",", "")) * (1_000 if thousands else 1)
    except ValueError:
        return None
    if not _MIN_RUPEES <= value <= MAX_BUDGET_PAISE / 100:
        return None
    return value


def _paise(rupees: float | None) -> int | None:
    return round(rupees * 100) if rupees is not None else None
