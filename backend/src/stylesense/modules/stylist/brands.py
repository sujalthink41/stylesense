"""Fashion brands sold on Amazon.in, Flipkart and Myntra, matched by rules (no AI needed).

A brand in the request is a hard filter: "asics shoes" must show ASICS, not whatever sneakers
are nearby. Names are the canonical spelling stores use; patterns cover common variants.
"""

import re

# (canonical name, regex alternatives). Longer, more specific names first.
_BRANDS: list[tuple[str, str]] = [
    ("U.S. Polo Assn.", r"u\.?\s?s\.?\s?polo(?:\s+assn\.?)?|us\s?polo|uspa"),
    ("Tommy Hilfiger", r"tommy\s+hilfiger|tommy"),
    ("Calvin Klein", r"calvin\s+klein|ck\s+jeans"),
    ("Jack & Jones", r"jack\s*(?:&|and|n)\s*jones"),
    ("Pepe Jeans", r"pepe(?:\s+jeans)?"),
    ("Louis Philippe", r"louis\s+philippe"),
    ("Van Heusen", r"van\s+heusen"),
    ("Peter England", r"peter\s+england"),
    ("Allen Solly", r"allen\s+solly"),
    ("Park Avenue", r"park\s+avenue"),
    ("Flying Machine", r"flying\s+machine"),
    ("Mast & Harbour", r"mast\s*(?:&|and)\s*harbour"),
    ("Dennis Lingo", r"dennis\s+lingo"),
    ("Campus Sutra", r"campus\s+sutra"),
    ("The Souled Store", r"(?:the\s+)?souled\s+store"),
    ("The Bear House", r"(?:the\s+)?bear\s+house"),
    ("Rare Rabbit", r"rare\s+rabbit"),
    ("Bonkers Corner", r"bonkers\s+corner"),
    ("Being Human", r"being\s+human"),
    ("Red Tape", r"red\s?tape"),
    ("Red Chief", r"red\s?chief"),
    ("New Balance", r"new\s+balance|nb"),
    ("Under Armour", r"under\s+armou?r"),
    ("Hush Puppies", r"hush\s+puppies"),
    ("Steve Madden", r"steve\s+madden"),
    ("Global Desi", r"global\s+desi"),
    ("Vero Moda", r"vero\s+moda"),
    ("Forever 21", r"forever\s?21"),
    ("Tokyo Talkies", r"tokyo\s+talkies"),
    ("Kook N Keech", r"kook\s*n\s*keech"),
    ("HERE&NOW", r"here\s*(?:&|and)\s*now"),
    ("H&M", r"h\s*&\s*m|h\s+and\s+m"),
    ("Levi's", r"levi'?s|levis|levi"),
    *(
        (name, re.escape(name.lower()))
        for name in (
            "ASICS",
            "Nike",
            "Adidas",
            "Puma",
            "Reebok",
            "Skechers",
            "Fila",
            "Campus",
            "Sparx",
            "Bata",
            "Woodland",
            "HRX",
            "Roadster",
            "Wrangler",
            "Lee",
            "Spykar",
            "Mufti",
            "Killer",
            "Only",
            "Zara",
            "Uniqlo",
            "Raymond",
            "Arrow",
            "GAP",
            "Mango",
            "Biba",
            "Aurelia",
            "Libas",
            "Fabindia",
            "Manyavar",
            "Anouk",
            "Sangria",
            "Max",
            "Westside",
            "Snitch",
            "Bewakoof",
            "Highlander",
            "Crocs",
            "Converse",
            "Vans",
            "Decathlon",
            "Kipsta",
            "Kalenji",
            "Quechua",
            "Jockey",
            "Blackberrys",
            "Provogue",
            "Liberty",
            "Metro",
            "Mochi",
            "Clarks",
            "Aldo",
            "Lavie",
            "Caprese",
            "Fossil",
            "Titan",
            "Fastrack",
            "Casio",
            "Nobero",
            "Powerlook",
            "Urbanic",
            "Berrylush",
            "DressBerry",
            "Ketch",
            "Harpa",
            "Vishudh",
            "W",
            "Rangriti",
            "Shaye",
            "Indo Era",
            "Jaipur Kurti",
            "Janasya",
            "Kalini",
            "Klosia",
            "Ethnix",
            "Rodamo",
            "Wildcraft",
            "Asian",
            "Lancer",
            "Paragon",
            "Relaxo",
            "Khadim's",
            "Inc.5",
            "Mochiko",
        )
    ),
]
# Grouped, so the word boundaries apply to every alternative:
# "ck jeans" must never match inside "black jeans".
_COMPILED = [(name, re.compile(rf"(?<![\w&])(?:{pattern})(?![\w&])")) for name, pattern in _BRANDS]

# Single letters and everyday words that are also brand names only count with an explicit cue
# ("from only", "brand w"); "only black jeans" is a constraint, not a brand.
_AMBIGUOUS = {"Only", "W", "Max", "Metro", "Liberty", "Asian", "Lee", "GAP", "Ketch", "NB"}


def find_brand(text: str) -> str | None:
    """The brand named in the request, by its store spelling ("asics" → "ASICS")."""
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for name, pattern in _COMPILED:
        match = pattern.search(lowered)
        if not match:
            continue
        if name in _AMBIGUOUS and not _brand_context(lowered, match.start()):
            continue
        if best is None or match.start() < best[0]:
            best = (match.start(), name)
    return best[1] if best else None


def strip_brands(text: str) -> str:
    """The text with every brand name blanked out (lower-case input)."""
    for _, pattern in _COMPILED:
        text = pattern.sub(" ", text)
    return text


def _brand_context(text: str, at: int) -> bool:
    # Ambiguous names count only after an explicit cue: "jeans from Only", "brand W kurta".
    before = text[:at].split()
    return bool(before) and before[-1] in {"from", "by", "brand"}
