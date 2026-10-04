"""Pure catalog rules: no I/O, so they're cheap to test exhaustively."""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

_MAX_DISCOUNT = 99


@dataclass(frozen=True, slots=True)
class OfferView:
    store: str
    price_paise: int
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
    """Cheapest in-stock offer; price ties go to the better-rated listing."""
    in_stock = [o for o in offers if o.in_stock]
    if not in_stock:
        return None
    return min(in_stock, key=lambda o: (o.price_paise, -(o.rating or 0), o.store))


def discount_percent(price_paise: int, mrp_paise: int | None) -> int:
    if not mrp_paise or mrp_paise <= price_paise:
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
