"""Deterministic request understanding: free text → slots, no AI needed.

The LLM (when configured) only fills gaps this parser leaves; numbers always come from here,
because a model can hallucinate a budget but a regex can't.
"""

import difflib
import re

from stylesense.modules.stylist.brands import find_brand, strip_brands
from stylesense.modules.stylist.slots import MAX_BUDGET_PAISE, Slots

_MIN_RUPEES = 50  # smaller numbers are sizes, counts or typos, not prices
_AROUND_LOW, _AROUND_HIGH = 0.7, 1.2

# The earliest match in the text wins; at the same spot, the first term listed wins.
_CATEGORY_TERMS: list[tuple[str, str]] = [
    (r"t[\s-]?shirts?|tees?|polo", "tshirt"),
    (r"salwar(?: suits?)?|anarkalis?|kurta sets?|kurtas?|kurtis?", "kurta"),
    (r"crop tops?|tank tops?|tops?|tunics?|blouses?", "top"),
    (r"jeans|jeggings", "jeans"),
    (r"joggers?|track ?pants|track ?suits?|sweatpants", "joggers"),
    (r"trousers?|pants|chinos?|cargos?", "trousers"),
    (r"sarees?|saris?", "saree"),
    (r"lehengas?|lehenga cholis?|ghagras?", "lehenga"),
    (r"sherwanis?|bandhgalas?|achkans?", "sherwani"),
    (r"dress(?:es)?|gowns?|frocks?", "dress"),
    (r"swimwear|swimsuits?|bikinis?|swim ?trunks", "swimwear"),
    (r"night ?wear|night ?suits?|pyjamas?|pajamas?|night ?dress(?:es)?|loungewear", "nightwear"),
    (r"innerwear|underwear|boxers?|briefs|vests?|bras?|panties|lingerie|camisoles?", "innerwear"),
    (r"shorts", "shorts"),
    (r"skirts?", "skirt"),
    (r"jumpsuits?|rompers?|playsuits?", "jumpsuit"),
    (r"leggings?|churidars?", "leggings"),
    (r"formal shoes|oxfords?|derby shoes|brogues?", "formal_shoes"),
    (r"loafers?|moccasins?", "loafers"),
    (r"boots?", "boots"),
    (r"heels|stilettos?|wedges", "heels"),
    (r"sandals?|slippers?|flip[\s-]?flops?|chappals?|slides|kolhapuris?", "sandals"),
    (r"sneakers?|shoes|trainers|kicks", "sneakers"),
    (r"socks?", "socks"),
    (r"nehru jackets?|waistcoats?|blazers?", "blazer"),
    (r"jackets?|bombers?|puffers?|windcheaters?|coats?", "jacket"),
    (r"hoodies?|sweatshirts?", "hoodie"),
    (r"sweaters?|pullovers?|cardigans?|jumpers?", "sweater"),
    (r"suits?|tuxedos?", "suit"),
    (r"smart ?watch(?:es)?|watch(?:es)?", "watch"),
    (r"sunglasses|sunnies|aviators?", "sunglasses"),
    (r"backpacks?|rucksacks?|laptop bags?|school bags?", "backpack"),
    (r"bags?|handbags?|sling bags?|tote(?: bag)?s?|clutch(?:es)?|purses?", "bag"),
    (r"wallets?|card holders?", "wallet"),
    (r"belts?", "belt"),
    (r"caps|beanies?|hats?|cap(?![\s-]?sleeve)", "cap"),
    (r"scarf|scarves|stoles?|dupattas?|shawls?|mufflers?", "scarf"),
    (r"ties|neck ?ties?|bow ?ties?|tie(?![\s-]?(?:dye|up))", "tie"),
    (
        r"jewell?ery|jewelry|earrings?|necklaces?|bangles?|bracelets?|rings|pendants?"
        r"|anklets?|jhumkas?",
        "jewellery",
    ),
    (r"shirts?|button[\s-]?downs?", "shirt"),
]
# Item words a shopper might misspell ("shocks", "jens", "kurthi"): close matches count.
_ITEM_WORDS: dict[str, str] = {
    **{c: c for c in ("socks", "jeans", "kurta", "saree", "lehenga", "sherwani", "dress")},
    **{c: c for c in ("shorts", "skirt", "jumpsuit", "leggings", "joggers", "loafers", "boots")},
    **{c: c for c in ("heels", "sandals", "sneakers", "blazer", "jacket", "hoodie", "sweater")},
    **{c: c for c in ("watch", "sunglasses", "backpack", "wallet", "belt", "scarf", "jewellery")},
    "kurti": "kurta",
    "tshirt": "tshirt",
    "shirt": "shirt",
    "trousers": "trousers",
    "pants": "trousers",
    "shoes": "sneakers",
    "slippers": "sandals",
    "handbag": "bag",
    "earrings": "jewellery",
    "necklace": "jewellery",
    "innerwear": "innerwear",
    "pyjama": "nightwear",
    "swimwear": "swimwear",
}
_FUZZY_MIN = 4  # shorter words are too easy to mistake
_FUZZY_CUTOFF = {4: 0.86}  # by word length; longer words use the default
_FUZZY_DEFAULT = 0.8
_GENDER_TERMS: list[tuple[str, str]] = [
    (r"unisex", "unisex"),
    (
        r"women'?s?|woman|female|girls?|ladies|lady|her|wife|girlfriend|gf|sister|mom|mother"
        r"|mummy|daughter|bhabhi|didi",
        "women",
    ),
    (
        r"men'?s?|man|male|boys?|guys?|gents|him|husband|boyfriend|bf|brother|dad|father|papa"
        r"|son|bhai|bhaiya",
        "men",
    ),
]
# Garments that say who they're cut for, when the text doesn't (checked after _GENDER_TERMS).
_IMPLIED_GENDER: list[tuple[str, str]] = [
    (
        r"kurtis?|sarees?|sari|lehengas?|salwar|anarkali|blouses?|gowns?|frocks?|leggings"
        r"|skirts?|heels|bras?|panties|lingerie|jhumkas?|dupattas?",
        "women",
    ),
    (r"sherwanis?|bandhgala|kurta[\s-]?pyjamas?|kurta[\s-]?pajamas?", "men"),
]
_OCCASION_TERMS: list[tuple[str, str]] = [
    (r"date night|date", "date night"),
    (
        r"wedding guest|wedding|shaadi|marriage|sangeet|reception|mehe?n?di|haldi|engagement"
        r"|cocktail|baraat",
        "wedding",
    ),
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
        gender=_first(lowered, _GENDER_TERMS) or _first(lowered, _IMPLIED_GENDER),
        occasion=_first(lowered, _OCCASION_TERMS),
        colors=_all(lowered, _COLOR_TERMS),
        fit=_first(lowered, _FIT_TERMS),
        fabric=_first(lowered, _FABRIC_TERMS),
        budget_min_paise=low,
        budget_max_paise=high,
        brand=find_brand(text),
        keywords=unknown_words(text)[:4],
    )


# Words that carry no shopping meaning on their own.
MIN_WORD = 3  # shorter tokens are noise ("xl", "rs" and so on)
_STOPWORDS = frozenset(
    [
        "hmm",
        "hmmm",
        "sure",
        "yet",
        "okay",
        "maybe",
        "idk",
        "dunno",
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "from",
        "with",
        "without",
        "my",
        "me",
        "i",
        "im",
        "i'm",
        "we",
        "our",
        "you",
        "your",
        "want",
        "wants",
        "need",
        "needs",
        "show",
        "give",
        "find",
        "get",
        "buy",
        "looking",
        "look",
        "search",
        "some",
        "something",
        "anything",
        "any",
        "please",
        "pls",
        "good",
        "best",
        "nice",
        "new",
        "latest",
        "cheap",
        "budget",
        "price",
        "rupees",
        "rs",
        "inr",
        "under",
        "below",
        "above",
        "upto",
        "within",
        "around",
        "about",
        "less",
        "more",
        "than",
        "not",
        "too",
        "very",
        "really",
        "that",
        "this",
        "these",
        "those",
        "like",
        "also",
        "just",
        "pair",
        "pairs",
        "piece",
        "one",
        "two",
        "three",
        "wear",
        "wearing",
        "outfit",
        "outfits",
        "clothes",
        "clothing",
        "dress",
        "up",
        "item",
        "items",
        "friend",
        "friends",
        "cousin",
        "brother",
        "sister",
        "mom",
        "dad",
        "wife",
        "husband",
        "girlfriend",
        "boyfriend",
        "for",
        "him",
        "her",
        "his",
        "them",
        "they",
        "it",
        "its",
        "can",
        "could",
        "would",
        "should",
        "will",
        "is",
        "are",
        "was",
        "be",
        "been",
        "am",
        "have",
        "has",
        "go",
        "going",
    ]
)


def unknown_words(text: str) -> list[str]:
    """Words the rules couldn't place in any field (in order, deduplicated). Empty means the
    request is fully understood without AI; otherwise they become search keywords."""
    rest = strip_brands(text.lower())
    for pattern in (_RANGE, _AT_MOST, _AROUND, _BARE, _SIZE_CONTEXT):
        rest = pattern.sub(" ", rest)
    vocab = (_CATEGORY_TERMS, _GENDER_TERMS, _IMPLIED_GENDER, _OCCASION_TERMS, _COLOR_TERMS)
    for terms in (*vocab, _FIT_TERMS, _FABRIC_TERMS):
        for term, _ in terms:
            rest = re.sub(rf"\b(?:{term})\b", " ", rest)
    seen: list[str] = []
    for raw in re.findall(r"[a-z][a-z'-]{2,}", rest):
        word = raw.strip("'-")
        if word not in _STOPWORDS and word not in seen and len(word) >= MIN_WORD:
            seen.append(word)
    return seen


def guess_category(text: str) -> tuple[str, str] | None:
    """A misspelt item ("i need shocks" -> socks): (category, the word as typed), or None."""
    for word in unknown_words(text):
        if len(word) < _FUZZY_MIN:
            continue
        cutoff = _FUZZY_CUTOFF.get(len(word), _FUZZY_DEFAULT)
        if close := difflib.get_close_matches(word, _ITEM_WORDS, n=1, cutoff=cutoff):
            return _ITEM_WORDS[close[0]], word
    return None


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
