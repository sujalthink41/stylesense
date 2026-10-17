"""What the stylist knows about the request. Vocabularies match the catalog's attribute values."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES: dict[str, tuple[str, str]] = {  # id → (label, icon)
    "tshirt": ("T-shirts", "👕"),
    "shirt": ("Shirts", "👔"),
    "jeans": ("Jeans", "👖"),
    "trousers": ("Trousers", "👖"),
    "kurta": ("Kurtas", "🪔"),
    "dress": ("Dresses", "👗"),
    "top": ("Tops", "👚"),
    "shorts": ("Shorts", "🩳"),
    "sneakers": ("Sneakers", "👟"),
    "jacket": ("Jackets", "🧥"),
    "hoodie": ("Hoodies", "🧥"),
    "sweater": ("Sweaters", "🧶"),
    "blazer": ("Blazers", "🧥"),
    "suit": ("Suits", "🤵"),
    "skirt": ("Skirts", "👗"),
    "jumpsuit": ("Jumpsuits", "👗"),
    "leggings": ("Leggings", "👖"),
    "joggers": ("Joggers", "👖"),
    "saree": ("Sarees", "🥻"),
    "lehenga": ("Lehengas", "✨"),
    "sherwani": ("Sherwanis", "🤵"),
    "innerwear": ("Innerwear", "🩲"),
    "nightwear": ("Nightwear", "🌙"),
    "swimwear": ("Swimwear", "🩱"),
    "socks": ("Socks", "🧦"),
    "formal_shoes": ("Formal shoes", "👞"),
    "loafers": ("Loafers", "👞"),
    "boots": ("Boots", "🥾"),
    "heels": ("Heels", "👠"),
    "sandals": ("Sandals", "🩴"),
    "watch": ("Watches", "⌚"),
    "sunglasses": ("Sunglasses", "🕶️"),
    "bag": ("Bags", "👜"),
    "backpack": ("Backpacks", "🎒"),
    "wallet": ("Wallets", "👛"),
    "belt": ("Belts", "🪢"),
    "cap": ("Caps", "🧢"),
    "scarf": ("Scarves", "🧣"),
    "tie": ("Ties", "👔"),
    "jewellery": ("Jewellery", "💍"),
}
# Anything else a shopper names ("lungi", "mojari") is still a category: the AI names it in
# plain words and the live store search finds it. These ids just get nicer labels and rules.
MAX_CATEGORY_CHARS = 30


def category_label(category: str) -> str:
    """ "Socks", "Formal shoes", or the shopper's own word for anything we have no label for."""
    known = CATEGORIES.get(category)
    return known[0] if known else category.replace("_", " ").capitalize()


OCCASIONS = (
    "summer",
    "winter",
    "party",
    "wedding",
    "office",
    "college",
    "festive",
    "date night",
    "sports",
    "travel",
    "casual",
)
COLORS = (
    "black",
    "white",
    "navy",
    "olive",
    "beige",
    "grey",
    "maroon",
    "sky blue",
    "mustard",
    "pink",
    "red",
    "green",
    "lavender",
    "brown",
    "off-white",
)
FITS = ("oversized", "slim", "regular", "relaxed", "skinny", "straight", "bootcut", "wide-leg")
FABRICS = ("cotton", "linen", "denim", "silk", "rayon", "polyester", "khadi", "georgette", "fleece")

Gender = Literal["men", "women", "unisex", "any"]  # "any" = asked, no preference
MAX_BUDGET_PAISE = 10_000_000  # ₹1,00,000: anything above is a parsing mistake
COLOR_WEIGHT, FABRIC_WEIGHT, FIT_WEIGHT, OCCASION_WEIGHT = 1.5, 1.5, 1.0, 0.6


class Slots(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, max_length=MAX_CATEGORY_CHARS)
    gender: Gender | None = None
    budget_min_paise: int | None = Field(default=None, ge=0, le=MAX_BUDGET_PAISE)
    budget_max_paise: int | None = Field(default=None, gt=0, le=MAX_BUDGET_PAISE)
    occasion: str | None = None
    colors: list[str] = Field(default_factory=list)
    fit: str | None = None
    fabric: str | None = None
    # A named brand is a hard filter ("asics shoes" shows ASICS). Keywords are the words rules
    # didn't map to a field ("running", "chunky"): they sharpen the store search.
    brand: str | None = Field(default=None, max_length=40)
    keywords: list[str] = Field(default_factory=list, max_length=4)
    # Kept for stored sessions; budget is never a gate any more (see `missing`).
    budget_optional: bool = False

    def missing(self) -> list[str]:
        """What we must know before searching: only the item. Who it's for and the budget are
        refinements the shopper types when they care ("for women", "under 800"): asking first
        made "I need socks" answer with a questionnaire."""
        return ["category"] if self.category is None else []

    def merged(self, update: "Slots") -> Self:
        """Values present in `update` win; everything else is kept."""
        changes = {
            k: v for k, v in update.model_dump(exclude_defaults=True).items() if v not in (None, [])
        }
        return self.model_copy(update=changes)

    def preferences(self) -> set[str]:
        """Soft attributes to boost in ranking (never filters)."""
        return set(self.preference_weights())

    def preference_weights(self) -> dict[str, float]:
        """How much each wanted attribute counts: what you can see (colour, fabric) matters
        more than a broad occasion tag, so a photographed blue denim jacket ranks over a
        white windcheater that only shares "casual"."""
        weights: dict[str, float] = {}
        for tag, weight in (
            *((c, COLOR_WEIGHT) for c in self.colors),
            (self.fabric, FABRIC_WEIGHT),
            (self.fit, FIT_WEIGHT),
            (self.occasion, OCCASION_WEIGHT),
        ):
            if tag:
                weights[tag] = max(weights.get(tag, 0.0), weight)
        return weights
