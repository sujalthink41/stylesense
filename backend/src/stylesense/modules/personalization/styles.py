"""Style DNA vocabulary: what onboarding offers, and how each pick seeds taste.

Tags match catalog tag values, so a pick nudges ranking even before any swipe.
"""

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True, slots=True)
class Style:
    label: str
    tags: tuple[str, ...]
    color: str  # placeholder tile background (hex)

    @property
    def text(self) -> str:
        """What gets embedded to seed the taste vector."""
        return f"{self.label} style: {', '.join(self.tags)}"

    @property
    def image_url(self) -> str:
        return f"https://placehold.co/400x500/{self.color}/ffffff.png?text={quote_plus(self.label)}"


STYLES: dict[str, Style] = {
    "streetwear": Style(
        "Streetwear", ("oversized", "graphic print", "colour block", "chunky", "black"), "111111"
    ),
    "minimal": Style("Minimal", ("solid", "regular", "white", "beige", "grey"), "d8c3a5"),
    "classic": Style("Smart classic", ("office", "slim", "checked", "navy", "cotton"), "1f2a44"),
    "ethnic": Style(
        "Ethnic", ("festive", "wedding", "embroidered", "block print", "khadi"), "6d1a2b"
    ),
    "sporty": Style("Sporty", ("sports", "polyester", "mesh", "travel"), "2e8b57"),
    "boho": Style("Boho", ("floral print", "printed", "relaxed", "rayon", "linen"), "d4a017"),
    "party": Style("Party", ("party", "date night", "georgette", "polka dot"), "c0392b"),
    "summer": Style("Summer casual", ("summer", "casual", "linen", "sky blue"), "87ceeb"),
}
MAX_STYLES = 3

TOP_SIZES = ("XS", "S", "M", "L", "XL", "XXL")
BOTTOM_SIZES = ("28", "30", "32", "34", "36", "38")
SHOE_SIZES = tuple(f"UK{n}" for n in range(3, 12))

# Catalog category → which saved size applies to it.
SIZE_KIND = {
    "tshirt": "top",
    "shirt": "top",
    "kurta": "top",
    "dress": "top",
    "top": "top",
    "jacket": "top",
    "hoodie": "top",
    "shorts": "top",
    "jeans": "bottom",
    "trousers": "bottom",
    "sneakers": "shoe",
    "sweater": "top",
    "blazer": "top",
    "joggers": "bottom",
    "formal_shoes": "shoe",
    "loafers": "shoe",
    "boots": "shoe",
}
