"""The component catalog: every piece of UI the server may send. The app renders only these.

Adding a component or changing props in a breaking way bumps CATALOG_VERSION; older apps get
a safe fallback instead (see versioning.py).
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stylesense.genui.actions import Action

CATALOG_VERSION = 2  # v2 (CP10): product_detail, product_carousel

ComponentId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]
OptionId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]
Label = Annotated[str, Field(min_length=1, max_length=40)]
Paise = Annotated[int, Field(ge=0, le=100_000_000)]


class _Props(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------- props ----------


class ChipOption(_Props):
    id: OptionId
    label: Label
    icon: str | None = Field(default=None, max_length=8)  # an emoji


class ChipQuestionProps(_Props):
    question: ShortText
    options: list[ChipOption] = Field(min_length=2, max_length=12)
    multi: bool = False
    max_select: int = Field(default=1, ge=1, le=12)
    allow_custom: bool = False  # show a "type your own" affordance

    @model_validator(mode="after")
    def _consistent(self) -> "ChipQuestionProps":
        if len({o.id for o in self.options}) != len(self.options):
            raise ValueError("option ids must be unique")
        if not self.multi and self.max_select != 1:
            raise ValueError("single-choice questions select exactly one option")
        return self


class BudgetSliderProps(_Props):
    label: ShortText
    min_paise: Paise
    max_paise: Paise
    step_paise: int = Field(ge=100, le=1_000_000)
    default_min_paise: Paise
    default_max_paise: Paise

    @model_validator(mode="after")
    def _ordered(self) -> "BudgetSliderProps":
        if not self.min_paise <= self.default_min_paise <= self.default_max_paise <= self.max_paise:
            raise ValueError("slider bounds must satisfy min <= default_min <= default_max <= max")
        return self


class ImageChoice(_Props):
    id: OptionId
    label: Label
    image_url: str = Field(pattern=r"^https://", max_length=500)


class ImageChoiceGridProps(_Props):
    question: ShortText
    options: list[ImageChoice] = Field(min_length=2, max_length=12)
    max_select: int = Field(default=1, ge=1, le=12)


class ProductCardProps(_Props):
    product_id: uuid.UUID
    title: Annotated[str, Field(min_length=1, max_length=160)]
    brand: Label
    image_url: str | None = Field(default=None, max_length=500)
    price_paise: Paise | None
    best_store: str | None = Field(default=None, max_length=40)
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int = Field(default=0, ge=0)
    reasons: list[Label] = Field(default_factory=list, max_length=3)  # "why this pick" chips


class ProductSwipeDeckProps(_Props):
    title: ShortText | None = None
    cards: list[ProductCardProps] = Field(min_length=1, max_length=20)
    has_more: bool = False


class ProductDetailProps(_Props):
    product_id: uuid.UUID
    title: Annotated[str, Field(min_length=1, max_length=160)]
    brand: Label
    images: list[Annotated[str, Field(pattern=r"^https://", max_length=500)]] = Field(
        default_factory=list, max_length=8
    )
    price_paise: Paise | None  # best in-stock price; None = out of stock everywhere
    mrp_paise: Paise | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int = Field(default=0, ge=0)
    colors: list[Label] = Field(default_factory=list, max_length=10)
    sizes: list[Annotated[str, Field(min_length=1, max_length=10)]] = Field(
        default_factory=list, max_length=20
    )
    facts: list[Label] = Field(default_factory=list, max_length=8)  # "Cotton", "Slim fit"
    reasons: list[Label] = Field(default_factory=list, max_length=3)


class ProductCarouselProps(_Props):
    title: ShortText
    items: list[ProductCardProps] = Field(min_length=1, max_length=10)


class ComparedOffer(_Props):
    offer_id: uuid.UUID
    store: Label
    store_name: Label
    price_paise: Paise
    mrp_paise: Paise | None
    discount_percent: int = Field(ge=0, le=99)
    in_stock: bool
    is_best: bool
    buy_path: str = Field(pattern=r"^/v1/out/[0-9a-f-]{36}$")  # never a raw store URL


class StoreComparisonProps(_Props):
    product_id: uuid.UUID
    title: Annotated[str, Field(min_length=1, max_length=160)]
    offers: list[ComparedOffer] = Field(min_length=1, max_length=10)


class CompleteTheLookProps(_Props):
    title: ShortText
    anchor_product_id: uuid.UUID
    items: list[ProductCardProps] = Field(min_length=1, max_length=10)
    remaining_budget_paise: Paise | None = None


class Suggestion(_Props):
    id: OptionId
    label: Label
    action: Action  # sent back verbatim when tapped


class SuggestionBarProps(_Props):
    suggestions: list[Suggestion] = Field(min_length=1, max_length=6)


class InfoBannerProps(_Props):
    tone: Literal["info", "success", "warning"] = "info"
    text: Annotated[str, Field(min_length=1, max_length=200)]


class EmptyStateProps(_Props):
    title: ShortText
    body: Annotated[str, Field(max_length=200)] = ""
    recovery: list[Suggestion] = Field(default_factory=list, max_length=4)


class TextInputBarProps(_Props):
    placeholder: Annotated[str, Field(max_length=80)] = "Describe what you're looking for"
    allow_photo: bool = False


class LoadingSkeletonProps(_Props):
    shape: Literal["cards", "question", "comparison"]
    count: int = Field(default=3, ge=1, le=10)


# ---------- components ----------


class _Component(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ComponentId
    v: Literal[1] = 1


class ChipQuestion(_Component):
    type: Literal["chip_question"] = "chip_question"
    props: ChipQuestionProps


class BudgetSlider(_Component):
    type: Literal["budget_slider"] = "budget_slider"
    props: BudgetSliderProps


class ImageChoiceGrid(_Component):
    type: Literal["image_choice_grid"] = "image_choice_grid"
    props: ImageChoiceGridProps


class ProductCard(_Component):
    type: Literal["product_card"] = "product_card"
    props: ProductCardProps


class ProductSwipeDeck(_Component):
    type: Literal["product_swipe_deck"] = "product_swipe_deck"
    props: ProductSwipeDeckProps


class ProductDetail(_Component):
    type: Literal["product_detail"] = "product_detail"
    props: ProductDetailProps


class ProductCarousel(_Component):
    type: Literal["product_carousel"] = "product_carousel"
    props: ProductCarouselProps


class StoreComparison(_Component):
    type: Literal["store_comparison"] = "store_comparison"
    props: StoreComparisonProps


class CompleteTheLook(_Component):
    type: Literal["complete_the_look"] = "complete_the_look"
    props: CompleteTheLookProps


class SuggestionBar(_Component):
    type: Literal["suggestion_bar"] = "suggestion_bar"
    props: SuggestionBarProps


class InfoBanner(_Component):
    type: Literal["info_banner"] = "info_banner"
    props: InfoBannerProps


class EmptyState(_Component):
    type: Literal["empty_state"] = "empty_state"
    props: EmptyStateProps


class TextInputBar(_Component):
    type: Literal["text_input_bar"] = "text_input_bar"
    props: TextInputBarProps


class LoadingSkeleton(_Component):
    type: Literal["loading_skeleton"] = "loading_skeleton"
    props: LoadingSkeletonProps


Component = Annotated[
    ChipQuestion
    | BudgetSlider
    | ImageChoiceGrid
    | ProductCard
    | ProductSwipeDeck
    | StoreComparison
    | CompleteTheLook
    | ProductDetail
    | ProductCarousel
    | SuggestionBar
    | InfoBanner
    | EmptyState
    | TextInputBar
    | LoadingSkeleton,
    Field(discriminator="type"),
]

# Catalog version in which each component type first appeared.
INTRODUCED_IN: dict[str, int] = dict.fromkeys(
    (
        "chip_question",
        "budget_slider",
        "image_choice_grid",
        "product_card",
        "product_swipe_deck",
        "store_comparison",
        "complete_the_look",
        "suggestion_bar",
        "info_banner",
        "empty_state",
        "text_input_bar",
        "loading_skeleton",
    ),
    1,
)
INTRODUCED_IN |= {"product_detail": 2, "product_carousel": 2}
