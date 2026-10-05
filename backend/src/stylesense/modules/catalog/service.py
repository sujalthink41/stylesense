import base64
import binascii
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict

import structlog
from sqlalchemy import update

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.infra.database import UnitOfWork
from stylesense.modules.catalog.exceptions import (
    InvalidCursorError,
    OfferNotFoundError,
    ProductNotFoundError,
)
from stylesense.modules.catalog.models import (
    Offer,
    OutboundClick,
    PriceSnapshot,
    Product,
    ProductImage,
    Store,
)
from stylesense.modules.catalog.ports import Embedder, ProductSource, RawOffer
from stylesense.modules.catalog.repository import CatalogRepository
from stylesense.modules.catalog.rules import (
    OfferView,
    best_offer,
    content_hash,
    derive_tags,
    discount_percent,
    embedding_hash,
    is_allowed_store_url,
    pick_alternatives,
    product_text,
)
from stylesense.modules.catalog.schemas import (
    ClickSource,
    IngestReport,
    OfferOut,
    ProductDetail,
    ProductFilters,
    ProductPage,
    ProductSummary,
    SearchHit,
    SearchQuery,
)
from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)

_INGEST_BATCH = 50  # products per transaction: bounded locks and memory


class CatalogService:
    def __init__(self, uow: Callable[[], UnitOfWork], *, clock: Clock, embedder: Embedder) -> None:
        self._uow = uow
        self._clock = clock
        self._embedder = embedder

    # ---------- ingest ----------

    async def ingest(self, source: ProductSource) -> IngestReport:
        """Upsert a source's listings into canonical products + offers. Safe to re-run:
        unchanged data writes nothing, and a price snapshot is recorded only on change.
        """
        groups: dict[str, list[RawOffer]] = defaultdict(list)
        for raw in await source.offers():
            groups[raw.canonical_key].append(raw)
        keys = list(groups)
        report = IngestReport()
        for start in range(0, len(keys), _INGEST_BATCH):
            batch = keys[start : start + _INGEST_BATCH]
            async with self._uow() as uow:
                repo = CatalogRepository(uow.session)
                stores = await repo.stores_by_code()
                existing = await repo.products_by_key(batch)
                for key in batch:
                    valid = [o for o in groups[key] if self._accept(o, stores, report)]
                    if valid:
                        self._upsert_product(repo, existing.get(key), valid, stores, report)
        logger.info("catalog_ingested", source=source.name, **asdict(report))
        return report

    def _accept(self, raw: RawOffer, stores: dict[str, Store], report: IngestReport) -> bool:
        store = stores.get(raw.store)
        problem = None
        if store is None:
            problem = "unknown_store"
        elif not is_allowed_store_url(raw.url, store.allowed_hosts):
            problem = "url_not_allowed"
        elif raw.price_paise is not None and raw.price_paise <= 0:
            problem = "invalid_price"
        elif (
            raw.price_paise is not None
            and raw.mrp_paise is not None
            and raw.mrp_paise < raw.price_paise
        ):
            problem = "mrp_below_price"
        if problem:
            report.rejected_offers += 1
            logger.warning(
                "offer_rejected", store=raw.store, external_id=raw.external_id, reason=problem
            )
            return False
        return True

    def _upsert_product(
        self,
        repo: CatalogRepository,
        product: Product | None,
        offers: list[RawOffer],
        stores: dict[str, Store],
        report: IngestReport,
    ) -> None:
        fields = _product_fields(offers)
        if product is None:
            product = Product(**fields)
            product.offers, product.images = [], []
            repo.add(product)
            report.products_created += 1
        elif _apply(product, fields):
            report.products_updated += 1

        _sync_images(product, offers[0].image_urls)

        by_store = {(o.store_id, o.external_id): o for o in product.offers}
        for raw in offers:
            store = stores[raw.store]
            offer = by_store.get((store.id, raw.external_id))
            values = _offer_fields(raw)
            if offer is None:
                offer = Offer(
                    store_id=store.id,
                    external_id=raw.external_id,
                    last_refreshed_at=self._clock.now(),
                    **values,
                )
                offer.store = store
                product.offers.append(offer)  # FKs resolve at commit: one batched INSERT per table
                if offer.price_paise is not None:
                    self._snapshot(repo, offer, report)
                report.offers_created += 1
                continue
            price_changed = offer.price_paise != raw.price_paise
            if _apply(offer, values):
                report.offers_updated += 1
            offer.last_refreshed_at = self._clock.now()
            if price_changed and offer.price_paise is not None:
                self._snapshot(repo, offer, report)

        best = best_offer([_view(o) for o in product.offers])
        min_price = best.price_paise if best else None
        if product.min_price_paise != min_price:
            product.min_price_paise = min_price

    def _snapshot(self, repo: CatalogRepository, offer: Offer, report: IngestReport) -> None:
        repo.add(
            PriceSnapshot(offer=offer, price_paise=offer.price_paise, captured_at=self._clock.now())
        )
        report.price_changes += 1

    # ---------- embeddings ----------

    async def retire(self, key_prefix: str) -> int:
        """Hide every product from one source (e.g. "mock-") without deleting history."""
        async with self._uow() as uow:
            result = await uow.session.execute(
                update(Product)
                .where(Product.canonical_key.startswith(key_prefix), Product.active)
                .values(active=False)
            )
        retired = int(result.rowcount or 0)  # type: ignore[attr-defined]
        logger.info("catalog_retired", prefix=key_prefix, count=retired)
        return retired

    async def embed_pending(self, *, batch_size: int = 64) -> int:
        """Embed products whose content or embedding model changed. Returns how many."""
        async with self._uow() as uow:
            stale = await CatalogRepository(uow.session).stale_embeddings(
                self._embedder.model, batch_size
            )
            if not stale:
                return 0
            try:
                vectors = await self._embedder.embed([_text_of(p) for p in stale])
            except AIUnavailableError as exc:
                # Nothing lost: rows stay stale and the worker retries on its next tick.
                logger.warning("catalog_embedding_deferred", reason=str(exc), pending=len(stale))
                return 0
            for product, vector in zip(stale, vectors, strict=True):
                product.embedding = vector
                product.embedding_hash = embedding_hash(
                    product.content_hash, model=self._embedder.model
                )
        logger.info("catalog_embedded", count=len(stale), model=self._embedder.model)
        return len(stale)

    # ---------- reads ----------

    async def get_product(self, product_id: uuid.UUID) -> ProductDetail:
        async with self._uow() as uow:
            product = await CatalogRepository(uow.session).get_product(product_id)
            if product is None:
                raise ProductNotFoundError
            return _detail(product)

    async def summaries(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, ProductSummary]:
        """Active products by id (one query); missing or inactive ids are simply absent."""
        async with self._uow() as uow:
            products = await CatalogRepository(uow.session).products_by_ids(
                list(dict.fromkeys(ids))
            )
            return {p.id: _summary(p) for p in products}

    async def exists(self, product_id: uuid.UUID) -> bool:
        return bool(await self.summaries([product_id]))

    async def list_products(self, filters: ProductFilters) -> ProductPage:
        after = _decode_cursor(filters.cursor) if filters.cursor else None
        async with self._uow() as uow:
            rows = await CatalogRepository(uow.session).list_products(filters, after)
        page, more = rows[: filters.limit], len(rows) > filters.limit
        return ProductPage(
            items=[_summary(p) for p in page],
            next_cursor=_encode_cursor(page[-1].id) if more and page else None,
        )

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        """Filtered retrieval, ordered by similarity to `query.text` when it can be embedded."""
        embedding = None
        if query.text:
            try:
                [embedding] = await self._embedder.embed([query.text])
            except AIUnavailableError as exc:
                logger.info("catalog_search_without_embedding", reason=str(exc))
        async with self._uow() as uow:
            rows = await CatalogRepository(uow.session).search(query, embedding)
            return [
                SearchHit(product=_summary(p), similarity=s, taste_similarity=t) for p, s, t in rows
            ]

    async def alternatives(
        self, product_id: uuid.UUID, *, max_price_paise: int | None = None, limit: int = 6
    ) -> list[ProductSummary]:
        """Same kind of item, most similar first, buyable now and within budget: the fallback
        when too few stores stock the exact product."""
        async with self._uow() as uow:
            repo = CatalogRepository(uow.session)
            product = await repo.get_product(product_id)
            if product is None:
                raise ProductNotFoundError
            query = SearchQuery(
                category=product.category,
                gender=product.gender,
                max_price_paise=max_price_paise,
                exclude_ids=[product.id],
                limit=min(4 * limit, 200),
            )
            embedding = list(product.embedding) if product.embedding is not None else None
            rows = await repo.search(query, embedding)
            summaries = [_summary(p) for p, _, _ in rows]
        return pick_alternatives(
            product_id, summaries, max_price_paise=max_price_paise, limit=limit
        )

    async def similar(self, product_id: uuid.UUID, *, limit: int = 10) -> list[ProductSummary]:
        async with self._uow() as uow:
            repo = CatalogRepository(uow.session)
            product = await repo.get_product(product_id)
            if product is None:
                raise ProductNotFoundError
            if product.embedding is None:
                return []
            neighbours = await repo.nearest(product, list(product.embedding), limit)
            return [_summary(p) for p in neighbours]

    # ---------- outbound ----------

    async def outbound(
        self, offer_id: uuid.UUID, *, user_id: uuid.UUID | None, source: ClickSource
    ) -> str:
        """Log the click and return the store URL to redirect to."""
        async with self._uow() as uow:
            repo = CatalogRepository(uow.session)
            offer = await repo.get_offer_with_store(offer_id)
            if offer is None:
                raise OfferNotFoundError
            # Re-checked at redirect time: an edited row must never become an open redirect.
            if not is_allowed_store_url(offer.url, offer.store.allowed_hosts):
                logger.error("outbound_url_blocked", offer_id=str(offer_id))
                raise OfferNotFoundError
            repo.add(OutboundClick(offer_id=offer.id, user_id=user_id, source=source))
            return offer.url


# ---------- mapping helpers ----------


def _product_fields(offers: list[RawOffer]) -> dict[str, object]:
    first = offers[0]
    ratings = [o.rating for o in offers if o.rating is not None]
    text_ = product_text(
        title=first.title,
        brand=first.brand,
        category=first.category,
        subcategory=first.subcategory,
        gender=first.gender,
        colors=first.colors,
        attributes=first.attributes,
    )
    return {
        "canonical_key": first.canonical_key,
        "title": first.title,
        "brand": first.brand,
        "category": first.category,
        "subcategory": first.subcategory,
        "gender": first.gender,
        "attributes": dict(first.attributes),
        "colors": list(first.colors),
        "tags": list(
            derive_tags(
                category=first.category,
                gender=first.gender,
                colors=first.colors,
                attributes=first.attributes,
            )
        ),
        "sizes_available": list(dict.fromkeys(s for o in offers for s in o.sizes)),
        "rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "rating_count": sum(o.rating_count for o in offers),
        "primary_image_url": first.image_urls[0] if first.image_urls else None,
        "content_hash": content_hash(text_),
    }


def _sync_images(product: Product, urls: Sequence[str]) -> None:
    """Update rows in place by position. Replacing the list would INSERT new rows before
    DELETEing old ones and trip the (product_id, position) unique constraint.
    """
    current = product.images
    for position, url in enumerate(urls):
        if position < len(current):
            if current[position].url != url:
                current[position].url = url
        else:
            current.append(ProductImage(url=url, position=position))
    del current[len(urls) :]


def _offer_fields(raw: RawOffer) -> dict[str, object]:
    return {
        "url": raw.url,
        "price_paise": raw.price_paise,
        "mrp_paise": raw.mrp_paise,
        "rating": raw.rating,
        "in_stock": raw.in_stock,
        "sizes_in_stock": list(raw.sizes_in_stock),
    }


def _apply(row: object, values: dict[str, object]) -> bool:
    """Set only differing fields, so unchanged rows produce no UPDATE (and no updated_at churn)."""
    changed = False
    for key, value in values.items():
        if getattr(row, key) != value:
            setattr(row, key, value)
            changed = True
    return changed


def _text_of(p: Product) -> str:
    return product_text(
        title=p.title,
        brand=p.brand,
        category=p.category,
        subcategory=p.subcategory,
        gender=p.gender,
        colors=p.colors,
        attributes=p.attributes,
    )


def _view(o: Offer) -> OfferView:
    return OfferView(
        store=str(o.store_id), price_paise=o.price_paise, in_stock=o.in_stock, rating=o.rating
    )


def _summary(p: Product) -> ProductSummary:
    best = _best(p.offers)
    return ProductSummary(
        id=p.id,
        title=p.title,
        brand=p.brand,
        category=p.category,
        subcategory=p.subcategory,
        gender=p.gender,
        primary_image_url=p.primary_image_url,
        min_price_paise=p.min_price_paise,
        rating=p.rating,
        rating_count=p.rating_count,
        offer_count=len(p.offers),
        # No priced offer yet: name the store that lists it ("See price on Myntra").
        best_store=best.store.code
        if best
        else next((o.store.code for o in p.offers if o.in_stock), None),
        tags=p.tags,
    )


def _best(offers: Sequence[Offer]) -> Offer | None:
    """The same rule ingest uses for min_price (rules.best_offer), keyed by store code."""
    by_view = {OfferView(o.store.code, o.price_paise, o.in_stock, o.rating): o for o in offers}
    best = best_offer(list(by_view))
    return by_view[best] if best is not None else None


def _detail(p: Product) -> ProductDetail:
    best = _best(p.offers)
    offers = sorted(p.offers, key=lambda o: (not o.in_stock, o.price_paise, o.store.code))
    return ProductDetail(
        **_summary(p).model_dump(),
        attributes=p.attributes,
        colors=p.colors,
        sizes_available=p.sizes_available,
        images=[i.url for i in p.images],
        offers=[
            OfferOut(
                id=o.id,
                store=o.store.code,
                store_name=o.store.name,
                price_paise=o.price_paise,
                mrp_paise=o.mrp_paise,
                discount_percent=discount_percent(o.price_paise, o.mrp_paise),
                rating=o.rating,
                in_stock=o.in_stock,
                sizes_in_stock=o.sizes_in_stock,
                is_best=best is not None and o.id == best.id,
                buy_path=f"/v1/out/{o.id}",
            )
            for o in offers
        ],
    )


def _encode_cursor(product_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(product_id.bytes).decode().rstrip("=")


def _decode_cursor(cursor: str) -> uuid.UUID:
    try:
        return uuid.UUID(bytes=base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, binascii.Error) as exc:
        raise InvalidCursorError from exc
