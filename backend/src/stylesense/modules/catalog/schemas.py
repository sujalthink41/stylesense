import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Gender = Literal["men", "women", "unisex"]
ClickSource = Literal["stylist", "feed", "board", "poll", "share", "product", "other"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class OfferOut(_Frozen):
    id: uuid.UUID
    store: str
    store_name: str
    price_paise: int | None  # None: price not known yet ("See price on <store>")
    mrp_paise: int | None
    discount_percent: int
    rating: float | None
    in_stock: bool
    sizes_in_stock: list[str]
    is_best: bool
    buy_path: str  # always via /v1/out so clicks are tracked; raw store URLs are never exposed


class ProductSummary(_Frozen):
    id: uuid.UUID
    title: str
    brand: str
    category: str
    subcategory: str | None
    gender: str
    primary_image_url: str | None
    min_price_paise: int | None
    rating: float | None
    rating_count: int
    offer_count: int
    best_store: str | None
    tags: list[str]


class ProductDetail(ProductSummary):
    attributes: dict[str, str]
    colors: list[str]
    sizes_available: list[str]
    images: list[str]
    offers: list[OfferOut]


class ProductPage(_Frozen):
    items: list[ProductSummary]
    next_cursor: str | None


class ProductFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, max_length=40)
    gender: Gender | None = None  # "men" also returns unisex items
    min_price_paise: int | None = Field(default=None, ge=0)
    max_price_paise: int | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=64)


class SearchQuery(BaseModel):
    """Hard filters (SQL) + optional free text for vector similarity."""

    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    gender: Gender | None = None  # "men"/"women" also match unisex; None = any
    min_price_paise: int | None = Field(default=None, ge=0)
    max_price_paise: int | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, max_length=500)
    exclude_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    size: str | None = Field(default=None, max_length=10)  # only items stocked in this size
    taste: list[float] | None = None  # user's taste vector: scored, and the order without text
    limit: int = Field(default=50, ge=1, le=200)
    # True: only products with a real price (decks, budgets). False: only those whose price we
    # don't know yet ("See price on …"). None: both.
    price_known: bool | None = True


@dataclass(frozen=True, slots=True)
class SearchHit:
    product: ProductSummary
    similarity: float | None  # cosine similarity to the request text, when it was embedded
    taste_similarity: float | None = None  # cosine similarity to the user's taste vector


@dataclass(slots=True)
class IngestReport:
    products_created: int = 0
    products_updated: int = 0
    offers_created: int = 0
    offers_updated: int = 0
    price_changes: int = 0
    rejected_offers: int = 0
