"""AI tasks used by the stylist. Output schemas pin the vocabulary, so the model can't invent
categories or colours; numbers are bounded; everything is validated by the gateway.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.modules.stylist.slots import Slots

Category = Literal[
    "tshirt",
    "shirt",
    "jeans",
    "trousers",
    "kurta",
    "dress",
    "top",
    "shorts",
    "sneakers",
    "jacket",
    "hoodie",
]
Occasion = Literal[
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
]
Color = Literal[
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
]
Fit = Literal[
    "oversized", "slim", "regular", "relaxed", "skinny", "straight", "bootcut", "wide-leg"
]
Fabric = Literal[
    "cotton", "linen", "denim", "silk", "rayon", "polyester", "khadi", "georgette", "fleece"
]


class UnderstandInput(BaseModel):
    text: str
    known: dict[str, Any]


class UnderstandOutput(BaseModel):
    category: Category | None = None
    gender: Literal["men", "women", "unisex"] | None = None
    budget_min_rupees: int | None = Field(default=None, ge=50, le=100_000)
    budget_max_rupees: int | None = Field(default=None, ge=50, le=100_000)
    occasion: Occasion | None = None
    colors: list[Color] = Field(default_factory=list, max_length=3)
    fit: Fit | None = None
    fabric: Fabric | None = None

    def to_slots(self) -> Slots:
        low, high = self.budget_min_rupees, self.budget_max_rupees
        if low is not None and high is not None and low > high:
            low, high = high, low
        return Slots(
            category=self.category,
            gender=self.gender,
            occasion=self.occasion,
            colors=list(self.colors),
            fit=self.fit,
            fabric=self.fabric,
            budget_min_paise=low * 100 if low is not None else None,
            budget_max_paise=high * 100 if high is not None else None,
        )


class PhotoInput(BaseModel):
    image_urls: list[str] = Field(min_length=1, max_length=1)


class PhotoOutput(UnderstandOutput):
    usable: bool  # false: no clothing to match, or the photo is unsafe


PHOTO_UNDERSTAND = TaskSpec(
    name="photo.understand",
    prompt_version="2026-10-05",
    instructions=(
        "You look at a shopper's photo and describe the main clothing item so we can find "
        "similar products in an Indian online catalog. Set `usable` to false if there is no "
        "clearly visible clothing or footwear, or if the photo is sexual, violent or otherwise "
        "unsafe; then leave every other field null. Otherwise fill only what you can see: "
        "category, gender the item is cut for, up to 3 main colours, fit, fabric and the "
        "occasion it suits. Never guess a budget."
    ),
    input_type=PhotoInput,
    output_type=PhotoOutput,
    image_field="image_urls",
    bulkhead="vision",
)


STYLIST_UNDERSTAND = TaskSpec(
    name="stylist.understand",
    prompt_version="2026-10-05",
    instructions=(
        "You extract a fashion shopping request for Indian shoppers into structured fields. "
        "The text may mix English and Hindi (Hinglish). Fill only fields the user actually "
        "expressed; leave others null. `known` holds what we already know: do not repeat it. "
        "Budgets are in rupees ('1.5k' = 1500)."
    ),
    input_type=UnderstandInput,
    output_type=UnderstandOutput,
)


class ExplainProduct(BaseModel):
    id: str
    title: str = Field(max_length=80)
    price_rupees: int
    tags: list[str] = Field(max_length=8)


class ExplainInput(BaseModel):
    request: str
    products: list[ExplainProduct] = Field(max_length=10)


class ExplainItem(BaseModel):
    product_id: str
    reasons: list[str] = Field(max_length=3)


class ExplainOutput(BaseModel):
    items: list[ExplainItem] = Field(max_length=10)


STYLIST_EXPLAIN = TaskSpec(
    name="stylist.explain",
    prompt_version="2026-10-05",
    instructions=(
        "For each product, give up to 3 very short reasons (max 5 words each) why it suits the "
        "request, like chips on a shopping card. Use only the facts given (title, price, tags): "
        "never invent materials, discounts, ratings or prices."
    ),
    input_type=ExplainInput,
    output_type=ExplainOutput,
)
