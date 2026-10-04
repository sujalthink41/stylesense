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
    price_paise: int
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


@dataclass(slots=True)
class IngestReport:
    products_created: int = 0
    products_updated: int = 0
    offers_created: int = 0
    offers_updated: int = 0
    price_changes: int = 0
    rejected_offers: int = 0
