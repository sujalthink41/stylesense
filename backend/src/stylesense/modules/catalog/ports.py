from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

EMBEDDING_DIMENSIONS = 1536  # fixed by the vector column; changing it needs a migration


@dataclass(frozen=True, slots=True)
class RawOffer:
    """One store's listing of a product, as a source reports it."""

    store: str  # store code: amazon | flipkart | myntra
    external_id: str  # the store's own id (ASIN, FSN, …)
    canonical_key: str  # same physical product across stores shares this key
    title: str
    brand: str
    category: str
    gender: str
    url: str
    price_paise: int | None  # None: real price unknown (never estimate one)
    mrp_paise: int | None = None
    subcategory: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)
    colors: tuple[str, ...] = ()
    sizes: tuple[str, ...] = ()
    sizes_in_stock: tuple[str, ...] = ()
    in_stock: bool = True
    rating: float | None = None
    rating_count: int = 0
    image_urls: tuple[str, ...] = ()


class ProductSource(Protocol):
    name: str

    async def offers(self) -> Sequence[RawOffer]: ...


class Embedder(Protocol):
    model: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
