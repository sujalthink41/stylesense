"""Pure catalog rules: no I/O, so they're cheap to test exhaustively."""

import hashlib
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

_MAX_DISCOUNT = 99
MIN_STORES_TO_COMPARE = 2  # fewer in-stock stores than this: also show similar items

# What a category usually costs (paise): slider defaults and per-piece caps for looks.
TYPICAL_PRICE_PAISE: dict[str, int] = {
    "tshirt": 100_000,
    "shirt": 150_000,
    "jeans": 200_000,
    "trousers": 150_000,
    "kurta": 200_000,
    "dress": 250_000,
    "top": 100_000,
    "shorts": 100_000,
    "sneakers": 300_000,
    "jacket": 300_000,
    "hoodie": 150_000,
}
DEFAULT_TYPICAL_PRICE_PAISE = 150_000


@dataclass(frozen=True, slots=True)
class OfferView:
    store: str
    price_paise: int | None
    in_stock: bool
    rating: float | None


def is_allowed_store_url(url: str, allowed_hosts: Iterable[str]) -> bool:
    """Only HTTPS links to a store's own domains: our /out redirect must never become an
    open redirect that phishers can point anywhere.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def best_offer[O: OfferView](offers: Sequence[O]) -> O | None:
    """Cheapest in-stock offer with a known price; ties go to the better-rated listing."""
    priced = [o for o in offers if o.in_stock and o.price_paise is not None]
    if not priced:
        return None
    return min(priced, key=lambda o: (o.price_paise or 0, -(o.rating or 0), o.store))


def needs_alternatives(offers: Sequence[OfferView]) -> bool:
    """Exact comparison is enough only when several stores have it in stock."""
    return sum(o.in_stock for o in offers) < MIN_STORES_TO_COMPARE


class Priced(Protocol):
    @property
    def id(self) -> uuid.UUID: ...

    @property
    def min_price_paise(self) -> int | None: ...


def pick_alternatives[P: Priced](
    anchor_id: uuid.UUID, candidates: Sequence[P], *, max_price_paise: int | None, limit: int
) -> list[P]:
    """Similar items (in similarity order) that can be bought now, within budget, never the
    item itself, each at most once."""
    picked: list[P] = []
    seen = {anchor_id}
    for candidate in candidates:
        price = candidate.min_price_paise
        if candidate.id in seen or price is None:
            continue
        if max_price_paise is not None and price > max_price_paise:
            continue
        picked.append(candidate)
        seen.add(candidate.id)
        if len(picked) == limit:
            break
    return picked


def discount_percent(price_paise: int | None, mrp_paise: int | None) -> int:
    if price_paise is None or not mrp_paise or mrp_paise <= price_paise:
        return 0
    return min(_MAX_DISCOUNT, round((mrp_paise - price_paise) * 100 / mrp_paise))


def derive_tags(
    *, category: str, gender: str, colors: Iterable[str], attributes: Mapping[str, str]
) -> tuple[str, ...]:
    values = {category, gender, *colors}
    for value in attributes.values():
        values.update(part.strip() for part in value.split(","))
    return tuple(sorted(v.lower() for v in values if v.strip()))


def product_text(
    *,
    title: str,
    brand: str,
    category: str,
    subcategory: str | None,
    gender: str,
    colors: Iterable[str],
    attributes: Mapping[str, str],
) -> str:
    """The text we embed: everything a shopper would use to describe the item."""
    facts = "; ".join(f"{k}: {v}" for k, v in sorted(attributes.items()))
    kind = f"{subcategory} {category}" if subcategory else category
    return f"{title}. {brand}. {kind} for {gender}. colours: {', '.join(colors)}. {facts}."


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def embedding_hash(content_hash_: str, *, model: str) -> str:
    """What an up-to-date embedding was computed from. Including the model means switching
    embedders marks every product stale, even if no product changed.

    Must match the SQL in CatalogRepository.stale_embeddings.
    """
    return hashlib.sha256(f"{model}:{content_hash_}".encode()).hexdigest()
