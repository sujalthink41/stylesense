import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from stylesense.modules.catalog.models import Offer, OutboundClick, PriceSnapshot, Product, Store
from stylesense.modules.catalog.schemas import ProductFilters, SearchQuery


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def stores_by_code(self) -> dict[str, Store]:
        stores = (await self._s.scalars(select(Store).where(Store.active))).all()
        return {s.code: s for s in stores}

    async def products_by_key(self, keys: Sequence[str]) -> dict[str, Product]:
        rows = await self._s.scalars(
            select(Product)
            .where(Product.canonical_key.in_(keys))
            .options(selectinload(Product.offers), selectinload(Product.images))
        )
        return {p.canonical_key: p for p in rows}

    def add(self, row: Product | Offer | PriceSnapshot | OutboundClick) -> None:
        self._s.add(row)

    async def flush(self) -> None:
        await self._s.flush()

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        product: Product | None = await self._s.scalar(
            select(Product)
            .where(Product.id == product_id, Product.active)
            .options(
                selectinload(Product.images),
                selectinload(Product.offers).selectinload(Offer.store),
            )
        )
        return product

    async def list_products(self, f: ProductFilters, after: uuid.UUID | None) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.active)
            .options(selectinload(Product.offers).selectinload(Offer.store))
            .order_by(Product.id)
            .limit(f.limit + 1)  # one extra row tells us whether there's a next page
        )
        if f.category:
            stmt = stmt.where(Product.category == f.category)
        if f.gender:
            stmt = stmt.where(Product.gender.in_({f.gender, "unisex"}))
        if f.min_price_paise is not None:
            stmt = stmt.where(Product.min_price_paise >= f.min_price_paise)
        if f.max_price_paise is not None:
            stmt = stmt.where(Product.min_price_paise <= f.max_price_paise)
        if after is not None:
            stmt = stmt.where(Product.id > after)  # keyset pagination: stable and index-friendly
        return list((await self._s.scalars(stmt)).all())

    async def search(
        self, q: SearchQuery, embedding: Sequence[float] | None
    ) -> list[tuple[Product, float | None]]:
        distance = Product.embedding.cosine_distance(embedding) if embedding is not None else None
        columns = (Product, distance.label("distance")) if distance is not None else (Product,)
        stmt = (
            select(*columns)
            .where(Product.active, Product.min_price_paise.is_not(None))
            .options(selectinload(Product.offers).selectinload(Offer.store))
            .limit(q.limit)
        )
        if q.category:
            stmt = stmt.where(Product.category == q.category)
        if q.gender in {"men", "women"}:
            stmt = stmt.where(Product.gender.in_({q.gender, "unisex"}))
        elif q.gender == "unisex":
            stmt = stmt.where(Product.gender == "unisex")
        if q.min_price_paise is not None:
            stmt = stmt.where(Product.min_price_paise >= q.min_price_paise)
        if q.max_price_paise is not None:
            stmt = stmt.where(Product.min_price_paise <= q.max_price_paise)
        if q.exclude_ids:
            stmt = stmt.where(Product.id.not_in(q.exclude_ids))
        if distance is not None:
            stmt = stmt.order_by(distance.asc().nulls_last(), Product.id)
        else:
            stmt = stmt.order_by(Product.rating.desc().nulls_last(), Product.id)
        rows = (await self._s.execute(stmt)).all()
        if distance is None:
            return [(row[0], None) for row in rows]
        return [(row[0], None if row[1] is None else 1.0 - float(row[1])) for row in rows]

    async def stale_embeddings(self, model: str, limit: int) -> list[Product]:
        # Mirrors rules.embedding_hash in SQL so the filter runs in the database.
        expected = func.encode(
            func.sha256(func.convert_to(model + ":" + Product.content_hash, "UTF8")), "hex"
        )
        stmt = (
            select(Product)
            .where(Product.embedding_hash.is_distinct_from(expected))
            .order_by(Product.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._s.scalars(stmt)).all())

    async def nearest(
        self, product: Product, embedding: Sequence[float], limit: int
    ) -> list[Product]:
        # Keep scanning the HNSW graph until enough rows pass the filters.
        await self._s.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        stmt = (
            select(Product)
            .where(
                Product.active,
                Product.id != product.id,
                Product.embedding.is_not(None),
            )
            .options(selectinload(Product.offers).selectinload(Offer.store))
            .order_by(Product.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        if product.gender != "unisex":
            stmt = stmt.where(Product.gender.in_({product.gender, "unisex"}))
        return list((await self._s.scalars(stmt)).all())

    async def get_offer_with_store(self, offer_id: uuid.UUID) -> Offer | None:
        offer: Offer | None = await self._s.scalar(
            select(Offer).where(Offer.id == offer_id).options(selectinload(Offer.store))
        )
        return offer
