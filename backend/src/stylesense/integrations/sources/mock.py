"""Deterministic mock catalog: realistic Indian-market fashion listings across three stores.

Brands are fictional and images are placeholders; links are real store *search* URLs so a
"Buy" tap lands somewhere sensible. Replaced by real adapters after v1 (CP21).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote_plus

from stylesense.modules.catalog.ports import RawOffer

STORE_HOSTS: dict[str, tuple[str, ...]] = {
    "amazon": ("amazon.in", "amzn.to"),
    "flipkart": ("flipkart.com",),
    "myntra": ("myntra.com",),
}

_APPAREL = ("XS", "S", "M", "L", "XL", "XXL")
_WAIST = ("28", "30", "32", "34", "36", "38")
_SHOES_MEN = tuple(f"UK{n}" for n in range(6, 12))
_SHOES_WOMEN = tuple(f"UK{n}" for n in range(3, 9))


@dataclass(frozen=True, slots=True)
class CategorySpec:
    label: str
    genders: tuple[str, ...]
    price_range_rupees: tuple[int, int]
    subcategories: tuple[str, ...]
    attributes: dict[str, tuple[str, ...]]
    weight: int  # how common the category is in the catalog


CATEGORIES: dict[str, CategorySpec] = {
    "tshirt": CategorySpec(
        "T-Shirt",
        ("men", "women", "unisex"),
        (199, 1299),
        ("crew neck", "v-neck", "polo", "oversized"),
        {
            "fabric": ("cotton", "cotton blend", "linen blend", "polyester"),
            "fit": ("regular", "slim", "oversized"),
            "sleeve": ("half", "full"),
            "pattern": ("solid", "striped", "graphic print", "colour block"),
            "occasion": ("casual", "casual, summer", "sports", "college"),
        },
        weight=7,
    ),
    "shirt": CategorySpec(
        "Shirt",
        ("men", "women"),
        (499, 2499),
        ("casual shirt", "formal shirt"),
        {
            "fabric": ("cotton", "linen", "rayon", "denim"),
            "fit": ("regular", "slim", "relaxed"),
            "sleeve": ("full", "half"),
            "pattern": ("solid", "checked", "striped", "floral print"),
            "occasion": ("office", "casual", "party", "casual, summer"),
        },
        weight=5,
    ),
    "jeans": CategorySpec(
        "Jeans",
        ("men", "women"),
        (699, 2999),
        ("denim",),
        {
            "fit": ("skinny", "slim", "straight", "relaxed", "bootcut"),
            "wash": ("light", "medium", "dark", "black"),
            "rise": ("mid", "high"),
            "occasion": ("casual", "college"),
        },
        weight=4,
    ),
    "trousers": CategorySpec(
        "Trousers",
        ("men", "women"),
        (599, 2499),
        ("chinos", "formal trousers", "cargo"),
        {
            "fabric": ("cotton", "linen", "polyester blend"),
            "fit": ("slim", "regular", "wide-leg"),
            "occasion": ("office", "casual", "travel"),
        },
        weight=3,
    ),
    "kurta": CategorySpec(
        "Kurta",
        ("men", "women"),
        (499, 2999),
        ("straight kurta", "a-line kurta", "kurta set"),
        {
            "fabric": ("cotton", "rayon", "silk blend", "khadi"),
            "length": ("short", "knee", "calf"),
            "pattern": ("solid", "printed", "embroidered", "block print"),
            "occasion": ("festive", "wedding", "casual", "office", "festive, wedding"),
        },
        weight=5,
    ),
    "dress": CategorySpec(
        "Dress",
        ("women",),
        (599, 3499),
        ("maxi", "midi", "mini", "shirt dress", "bodycon"),
        {
            "fabric": ("rayon", "cotton", "georgette", "crepe"),
            "pattern": ("solid", "floral print", "polka dot", "striped"),
            "occasion": ("party", "casual", "date night", "casual, summer", "wedding guest"),
        },
        weight=4,
    ),
    "top": CategorySpec(
        "Top",
        ("women",),
        (299, 1499),
        ("crop top", "peplum top", "tunic", "tank top"),
        {
            "fabric": ("cotton", "rayon", "georgette"),
            "pattern": ("solid", "printed", "ribbed"),
            "occasion": ("casual", "party", "casual, summer", "college"),
        },
        weight=3,
    ),
    "shorts": CategorySpec(
        "Shorts",
        ("men", "women"),
        (299, 1299),
        ("casual shorts", "denim shorts", "sports shorts"),
        {
            "fabric": ("cotton", "denim", "polyester"),
            "occasion": ("casual, summer", "sports", "travel"),
        },
        weight=2,
    ),
    "sneakers": CategorySpec(
        "Sneakers",
        ("men", "women", "unisex"),
        (999, 4999),
        ("low-top", "high-top", "chunky", "running"),
        {
            "material": ("canvas", "mesh", "synthetic leather"),
            "occasion": ("casual", "sports", "college"),
        },
        weight=4,
    ),
    "jacket": CategorySpec(
        "Jacket",
        ("men", "women"),
        (999, 4999),
        ("denim jacket", "bomber", "puffer", "windcheater"),
        {"fabric": ("denim", "polyester", "nylon"), "occasion": ("winter", "casual", "travel")},
        weight=2,
    ),
    "hoodie": CategorySpec(
        "Hoodie",
        ("men", "women", "unisex"),
        (599, 1999),
        ("pullover", "zip-up"),
        {
            "fabric": ("cotton fleece", "cotton blend"),
            "fit": ("regular", "oversized"),
            "occasion": ("winter", "casual", "college"),
        },
        weight=2,
    ),
}

_COLORS = {
    "black": "111111",
    "white": "f5f5f5",
    "navy": "1f2a44",
    "olive": "556b2f",
    "beige": "d8c3a5",
    "grey": "8a8a8a",
    "maroon": "6d1a2b",
    "sky blue": "87ceeb",
    "mustard": "d4a017",
    "pink": "f4a6c0",
    "red": "c0392b",
    "green": "2e8b57",
    "lavender": "b8a9d9",
    "brown": "7b4b2a",
    "off-white": "efe9de",
}
_BRANDS = (
    "Urbano Basics",
    "Kalaa",
    "Northwind",
    "Desi Threads",
    "Loom & Co",
    "Street Theory",
    "Sutra",
    "Monsoon Edit",
    "Bombay Denim Co.",
    "Stride Lab",
    "Coastline",
    "Indigo Leaf",
)
_STORES = tuple(STORE_HOSTS)
_GENDER_LABEL = {"men": "Men", "women": "Women", "unisex": "Unisex"}
_SIZE_SOLD_OUT_RATE = 0.2
_OUT_OF_STOCK_RATE = 0.05


class MockSource:
    name = "mock"

    def __init__(self, *, seed: int = 2026, products: int = 300) -> None:
        self._seed = seed
        self._products = products

    async def offers(self) -> Sequence[RawOffer]:
        rng = random.Random(self._seed)  # noqa: S311  # fixture data, not security
        categories = list(CATEGORIES)
        weights = [CATEGORIES[c].weight for c in categories]
        result: list[RawOffer] = []
        for n in range(1, self._products + 1):
            category = rng.choices(categories, weights)[0]
            result.extend(_product_offers(rng, n, category, CATEGORIES[category]))
        return result


def _product_offers(
    rng: random.Random, n: int, category: str, spec: CategorySpec
) -> list[RawOffer]:
    gender = rng.choice(spec.genders)
    color = rng.choice(list(_COLORS))
    brand = rng.choice(_BRANDS)
    subcategory = rng.choice(spec.subcategories)
    attributes = {k: rng.choice(v) for k, v in spec.attributes.items()}
    descriptor = (
        attributes.get("pattern") if attributes.get("pattern") not in (None, "solid") else ""
    )
    fit = attributes.get("fit", "")
    title = " ".join(
        p
        for p in (
            brand,
            _GENDER_LABEL[gender],
            color.title(),
            descriptor.title() if descriptor else "",
            fit.title(),
            subcategory.title() if subcategory != category else "",
            spec.label,
        )
        if p
    )
    sizes = _sizes(rng, category, gender)
    low, high = spec.price_range_rupees
    base_rupees = rng.randrange(low, high + 1, 50) - 1  # ₹499-style price points
    mrp_rupees = int(round(base_rupees * rng.uniform(1.2, 2.2), -2)) - 1
    product_rating = round(rng.uniform(3.4, 4.7), 1)

    offers = []
    for store in rng.sample(_STORES, k=rng.choice((1, 2, 2, 3, 3))):
        # Store prices vary ±10% and end in 9, like real listings (₹1,039, ₹999).
        price = max(low, min(high, int(round(base_rupees * rng.uniform(0.9, 1.1), -1)) - 1))
        offers.append(
            RawOffer(
                store=store,
                external_id=f"MOCK-{store.upper()}-{n:05d}",
                canonical_key=f"mock-{n:04d}",
                title=title,
                brand=brand,
                category=category,
                subcategory=subcategory,
                gender=gender,
                attributes=attributes,
                colors=(color,),
                sizes=sizes,
                sizes_in_stock=tuple(s for s in sizes if rng.random() > _SIZE_SOLD_OUT_RATE)
                or sizes[:1],
                in_stock=rng.random() > _OUT_OF_STOCK_RATE,
                url=_store_search_url(store, title),
                price_paise=price * 100,
                mrp_paise=max(price, mrp_rupees) * 100,
                rating=round(min(5.0, max(1.0, product_rating + rng.uniform(-0.3, 0.3))), 1),
                rating_count=rng.randint(12, 4_800),
                image_urls=(
                    f"https://placehold.co/600x800/{_COLORS[color]}/ffffff.png?text={quote_plus(spec.label)}",
                ),
            )
        )
    return offers


def _sizes(rng: random.Random, category: str, gender: str) -> tuple[str, ...]:
    if category == "sneakers":
        return _SHOES_WOMEN if gender == "women" else _SHOES_MEN
    if category in {"jeans", "trousers"}:
        return _WAIST
    start = rng.randint(0, 2)
    return _APPAREL[start : start + rng.randint(3, 4)]


def _store_search_url(store: str, title: str) -> str:
    query = quote_plus(title.lower())
    if store == "amazon":
        return f"https://www.amazon.in/s?k={query}"
    if store == "flipkart":
        return f"https://www.flipkart.com/search?q={query}"
    return f"https://www.myntra.com/{quote_plus(title.lower().replace(' ', '-'))}"
