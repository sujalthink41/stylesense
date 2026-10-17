"""Real products from Amazon.in, Flipkart and Myntra, found through DuckDuckGo search.

Only those three stores: every result whose link isn't a product page on one of them is
dropped. Prices are never estimated. Flipkart product pages carry structured data (JSON-LD)
with the real price, stock and rating, so Flipkart items are priced; Amazon and Myntra block
automated page reads, so their items are priced only if the search result itself shows a
price, and otherwise stored as "price unknown" (shown as "See price on …").

Interim until the stores' affiliate APIs (CP21). Searches are throttled and cached by the
caller (WebCatalog); this module only finds and parses.
"""

import asyncio
import html
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import structlog

from stylesense.modules.catalog.ports import RawOffer
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.stylist.understanding import parse_request

logger = structlog.get_logger(__name__)

Search = Callable[[str, int], Awaitable[list[dict[str, Any]]]]
Fetch = Callable[[str], Awaitable[str | None]]


@dataclass(frozen=True, slots=True)
class StoreSite:
    code: str
    domain: str
    keyword: str  # added to the query so the engine favours this store


SITES = (
    StoreSite("flipkart", "flipkart.com", "flipkart"),
    StoreSite("amazon", "amazon.in", "amazon.in"),
    StoreSite("myntra", "myntra.com", "myntra"),
)

_PRICE = re.compile(r"(?:₹|rs\.?\s?|inr\s?)([\d,]{2,7})(?:\.\d{1,2})?", re.I)
_GENDER_WORDS = re.compile(r"\b(men'?s?|women'?s?|boys?|girls?|unisex|kids)\b", re.I)
_NOT_BRAND = {
    "kurta",
    "kurti",
    "kurtas",
    "set",
    "rayon",
    "cotton",
    "printed",
    "embroidered",
    "pure",
    "regular",
    "slim",
    "solid",
    "casual",
    "shirt",
    "t-shirt",
    "jeans",
    "dress",
    "top",
    "georgette",
    "linen",
    "silk",
    "polyester",
    "for",
    "with",
    "and",
    "black",
    "white",
    "blue",
    "red",
    "green",
}
_MAX_PRICE_PAISE = 10_000_000  # ₹1,00,000: anything above is a parse error


@dataclass(frozen=True, slots=True)
class WebQuery:
    text: str  # e.g. "women black kurta"
    category: str | None = None  # what we searched for: a fallback when the title is vague
    gender: str | None = None


def product_id(site: StoreSite, url: str) -> tuple[str, str] | None:
    """(the store's product id, a clean product URL) for real product pages; None otherwise."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not (host == site.domain or host.endswith(f".{site.domain}")):
        return None
    path = parts.path
    if site.code == "amazon":
        m = re.search(r"/dp/([A-Z0-9]{10})", path)
        return (m.group(1), f"https://www.amazon.in/dp/{m.group(1)}") if m else None
    if site.code == "flipkart":
        m = re.search(r"/p/(itm[0-9a-z]+)", path)
        pid = re.search(r"(?:^|&)pid=([A-Z0-9]+)", parts.query)
        if not m:
            return None
        clean = f"https://www.flipkart.com{path}" + (f"?pid={pid.group(1)}" if pid else "")
        return (pid.group(1) if pid else m.group(1), clean)
    m = re.search(r"/(\d{5,})/buy", path)  # myntra
    return (m.group(1), f"https://www.myntra.com{path}") if m else None


def clean_title(site: StoreSite, title: str) -> str:
    t = re.sub(r"\s+", " ", html.unescape(title)).strip()
    t = re.sub(r"^buy\s+", "", t, flags=re.I)
    if site.code == "myntra":  # "X - Kurtas for Women 1234 | Myntra"
        t = t.split(" - ")[0]
    t = re.split(
        r"\s+[-|:]\s+(?=[^-|:]*(?:myntra|flipkart|amazon|online|buy|shop|price))",
        t,
        maxsplit=1,
        flags=re.I,
    )[0]
    t = re.sub(r"\s*(?:\.\.\.|…)$", "", t)
    return t.strip(" -|:")[:160]


def brand_of(title: str) -> str:
    """The words before the gender word ("HERE&NOW Men Black Jeans" → "HERE&NOW")."""
    m = _GENDER_WORDS.search(title)
    head = title[: m.start()].strip() if m and m.start() > 0 else ""
    words = head.split() if head else title.split()[:1]
    kept: list[str] = []
    for w in words[:3]:
        if w.lower().strip(",'s") in _NOT_BRAND:
            break  # "rytras Rayon …", "LYMI LABEL Kurta …": the brand ended already
        kept.append(w)
    return " ".join(kept)[:60] or (words[0] if words else "Unbranded")


def better_image(site: StoreSite, url: str) -> str:
    if site.code == "myntra":
        return re.sub(r"/h_\d+,w_\d+,c_fill,g_auto/", "/", url)
    if site.code == "flipkart":
        return re.sub(r"/image/\d+/\d+/", "/image/832/1100/", url)
    return url


def flipkart_product(html: str) -> dict[str, Any] | None:
    """The schema.org Product block Flipkart embeds in every product page."""
    for block in re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S
    ):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


@dataclass(frozen=True, slots=True)
class PageFacts:
    """What a store's own product page says: the only source of prices we trust."""

    title: str | None = None
    brand: str | None = None
    price_paise: int | None = None
    mrp_paise: int | None = None
    in_stock: bool = True
    rating: float | None = None
    rating_count: int = 0
    image: str | None = None


def flipkart_facts(html: str) -> PageFacts | None:
    item = flipkart_product(html)
    if item is None:
        return None
    b = item.get("brand")
    offers = item.get("offers") or {}
    offers = offers[0] if isinstance(offers, list) and offers else offers
    images = item.get("image")
    agg = item.get("aggregateRating") or {}
    return PageFacts(
        title=str(item.get("name") or "") or None,
        brand=str(b.get("name") if isinstance(b, dict) else b or "") or None,
        price_paise=_paise(offers.get("price")) if isinstance(offers, dict) else None,
        in_stock="InStock" in str(offers.get("availability", "InStock"))
        if isinstance(offers, dict)
        else True,
        rating=_rating(agg.get("ratingValue")) if isinstance(agg, dict) else None,
        rating_count=int(agg.get("reviewCount") or agg.get("ratingCount") or 0)
        if isinstance(agg, dict)
        else 0,
        image=str(images[0])
        if isinstance(images, list) and images
        else images
        if isinstance(images, str)
        else None,
    )


def myntra_facts(html: str) -> PageFacts | None:
    """Myntra server-renders its product data into `window.__myx`."""
    m = re.search(r"window\.__myx\s*=\s*(\{.*?\})</script>", html, re.S)
    if not m:
        return None
    try:
        pdp = json.loads(m.group(1)).get("pdpData") or {}
    except ValueError:
        return None
    price = pdp.get("price") or {}
    ratings = pdp.get("ratings") or {}
    albums = (pdp.get("media") or {}).get("albums") or [{}]
    images = albums[0].get("images") or [{}]
    image = str(images[0].get("imageURL") or "").replace("http://", "https://", 1) or None
    return PageFacts(
        title=pdp.get("name"),
        brand=(pdp.get("brand") or {}).get("name"),
        price_paise=_paise(price.get("discounted") or price.get("mrp")),
        mrp_paise=_paise(price.get("mrp")),
        in_stock=not (pdp.get("flags") or {}).get("outOfStock", False),
        rating=_rating(ratings.get("averageRating")),
        rating_count=int(ratings.get("totalCount") or 0),
        image=image,
    )


def amazon_facts(html: str) -> PageFacts | None:
    price = re.search(r'"priceAmount"\s*:\s*([\d.]+)', html) or re.search(
        r'name="items\[0\.base\]\[customerVisiblePrice\]\[amount\]" value="([\d.]+)"', html
    )
    title = re.search(r'id="productTitle"[^>]*>\s*([^<]{3,300})', html)
    if not (price or title):
        return None
    availability = re.search(r'id="availability"[^>]*>\s*<span[^>]*>\s*([^<]{2,60})', html)
    rating = re.search(r'id="acrPopover"[^>]*title="([\d.]+) out of 5', html)
    count = re.search(r'id="acrCustomerReviewText"[^>]*>\s*([\d,]+)', html)
    return PageFacts(
        title=" ".join(title.group(1).split()) if title else None,
        price_paise=_paise(price.group(1)) if price else None,
        in_stock="unavailable" not in (availability.group(1).lower() if availability else ""),
        rating=_rating(rating.group(1)) if rating else None,
        rating_count=int(count.group(1).replace(",", "")) if count else 0,
    )


PAGE_PARSERS: dict[str, Callable[[str], PageFacts | None]] = {
    "flipkart": flipkart_facts,
    "myntra": myntra_facts,
    "amazon": amazon_facts,
}


class WebSearchFinder:
    """Turns one shopping query into RawOffers from the three stores."""

    def __init__(
        self, *, search: Search, fetch: Fetch, per_store: int = 8, concurrency: int = 8
    ) -> None:
        self._search = search
        self._fetch = fetch
        self._per_store = per_store
        self._pages = asyncio.Semaphore(concurrency)

    async def find(self, query: WebQuery) -> list[RawOffer]:
        found: list[RawOffer] = []
        for site in SITES:
            try:
                results = await self._search(f"{query.text} {site.keyword}", self._per_store * 4)
            except Exception as exc:  # noqa: BLE001 - engine throttling/changes: skip this store
                logger.warning("web_search_failed", store=site.code, error=type(exc).__name__)
                continue
            picked: dict[str, tuple[str, dict[str, Any]]] = {}
            for r in results:
                ident = product_id(site, str(r.get("url", "")))
                if (
                    ident
                    and ident[0] not in picked
                    and "/aplus-media" not in str(r.get("image", ""))
                ):
                    picked[ident[0]] = (ident[1], r)
                if len(picked) >= self._per_store:
                    break
            offers = await asyncio.gather(
                *(self._offer(site, query, pid, url, r) for pid, (url, r) in picked.items())
            )
            found.extend(o for o in offers if o is not None)
        return found

    async def _offer(
        self, site: StoreSite, query: WebQuery, pid: str, url: str, r: dict[str, Any]
    ) -> RawOffer | None:
        title = clean_title(site, str(r.get("title", "")))
        image = better_image(site, str(r.get("image", "")))
        facts = await self._page(site, url) or PageFacts(
            price_paise=_price_in(str(r.get("title", "")))
        )
        title = html.unescape(facts.title or title)[:160]
        brand = html.unescape(facts.brand or brand_of(title))[:60]
        if facts.image and facts.image.startswith("https://"):
            image = facts.image
        slots = parse_request(title)
        category = slots.category or query.category
        if not category or not title or not image.startswith("https://"):
            return None  # can't place it in the catalog (or show it) reliably
        gender = slots.gender or query.gender or "unisex"
        mrp = (
            facts.mrp_paise
            if facts.mrp_paise and facts.price_paise and facts.mrp_paise >= facts.price_paise
            else None
        )
        return RawOffer(
            store=site.code,
            external_id=pid,
            canonical_key=f"web-{site.code}-{pid}",
            title=title,
            brand=brand,
            category=category,
            gender=gender if gender in {"men", "women", "unisex"} else "unisex",
            url=url,
            price_paise=facts.price_paise,
            mrp_paise=mrp,
            attributes={k: v for k, v in (("fit", slots.fit), ("fabric", slots.fabric)) if v},
            colors=tuple(slots.colors),
            in_stock=facts.in_stock,
            rating=facts.rating,
            rating_count=facts.rating_count,
            image_urls=(image,),
        )

    async def _page(self, site: StoreSite, url: str) -> PageFacts | None:
        async with self._pages:
            try:
                html = await self._fetch(url)
            except Exception as exc:  # noqa: BLE001 - a page we can't read just stays unpriced
                logger.info("store_page_unavailable", store=site.code, error=type(exc).__name__)
                return None
        return PAGE_PARSERS[site.code](html) if html else None


class WebCatalog:
    """LiveCatalog for the stylist: finds products for a request and stores them.

    Each request shape is searched at most once per `ttl_s` (the engine throttles and the
    stores don't change that fast); concurrent identical requests share one search.
    """

    def __init__(
        self,
        catalog: CatalogService,
        finder: WebSearchFinder,
        *,
        ttl_s: float = 6 * 3600,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._catalog = catalog
        self._finder = finder
        self._ttl_s = ttl_s
        self._now = now
        self._searched: dict[tuple[str, str | None, str | None], float] = {}
        self._inflight: dict[tuple[str, str | None, str | None], asyncio.Task[int]] = {}

    async def refresh(self, text: str, *, category: str | None, gender: str | None) -> int:
        key = (" ".join(text.lower().split()), category, gender)
        if key in self._inflight:
            return await asyncio.shield(self._inflight[key])
        last = self._searched.get(key)
        if last is not None and self._now() - last < self._ttl_s:
            return 0
        task = asyncio.ensure_future(self._search(WebQuery(text, category, gender)))
        self._inflight[key] = task
        try:
            added = await asyncio.shield(task)
        finally:
            self._inflight.pop(key, None)
            self._searched[key] = self._now()
        return added

    async def _search(self, query: WebQuery) -> int:
        offers = await self._finder.find(query)
        if not offers:
            return 0
        report = await self._catalog.ingest(StaticSource("web", offers))
        await self._catalog.embed_pending()
        logger.info(
            "live_catalog_refreshed",
            query=query.text,
            found=len(offers),
            added=report.products_created,
        )
        return report.products_created


class StaticSource:
    """Wraps already-found offers so CatalogService.ingest can store them."""

    def __init__(self, name: str, offers: Sequence[RawOffer]) -> None:
        self.name = name
        self._offers = offers

    async def offers(self) -> Sequence[RawOffer]:
        return self._offers


def _price_in(text: str) -> int | None:
    m = _PRICE.search(text)
    return _paise(m.group(1).replace(",", "")) if m else None


def _rating(value: object) -> float | None:
    try:
        rating = round(float(str(value)), 1)
    except (TypeError, ValueError):
        return None
    return rating if 0 < rating <= 5 else None  # noqa: PLR2004


def _paise(value: object) -> int | None:
    try:
        paise = round(float(str(value).replace(",", "")) * 100)
    except ValueError:
        return None
    return paise if 0 < paise <= _MAX_PRICE_PAISE else None


# ---------- the real engine and page fetcher (thin; replaced by fakes in tests) ----------


async def ddg_images(query: str, limit: int) -> list[dict[str, Any]]:
    from ddgs import DDGS  # noqa: PLC0415 - heavy import, only when web search is on

    def run() -> list[dict[str, Any]]:
        return list(
            DDGS(timeout=10).images(query, region="in-en", safesearch="moderate", max_results=limit)
        )

    return await asyncio.to_thread(run)


async def fetch_page(url: str) -> str | None:
    from primp import Client  # noqa: PLC0415

    def run() -> str | None:
        # A normal browser profile: the stores serve their regular product page to it.
        response = Client(impersonate="chrome", follow_redirects=True, timeout=12).get(url)
        return response.text if response.status_code == 200 else None  # noqa: PLR2004

    return await asyncio.to_thread(run)
