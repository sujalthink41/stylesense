import dataclasses
import uuid
from collections import Counter
from collections.abc import Sequence

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.infra.database import UnitOfWork, create_session_factory
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.integrations.sources.mock import MockSource
from stylesense.modules.catalog.exceptions import OfferNotFoundError, ProductNotFoundError
from stylesense.modules.catalog.models import Offer, OutboundClick, PriceSnapshot, Product
from stylesense.modules.catalog.ports import RawOffer
from stylesense.modules.catalog.schemas import ProductFilters
from stylesense.modules.catalog.service import CatalogService
from tests.fakes.clock import FixedClock

TEE = RawOffer(
    store="amazon",
    external_id="A-1",
    canonical_key="tee-1",
    title="Kalaa Men Navy Oversized T-Shirt",
    brand="Kalaa",
    category="tshirt",
    gender="men",
    url="https://www.amazon.in/s?k=navy+tee",
    price_paise=49_900,
    mrp_paise=99_900,
    attributes={"fabric": "cotton", "fit": "oversized"},
    colors=("navy",),
    sizes=("M", "L"),
    sizes_in_stock=("M",),
    rating=4.2,
    rating_count=120,
    image_urls=("https://placehold.co/600x800",),
)


class ListSource:
    name = "list"

    def __init__(self, offers: Sequence[RawOffer]) -> None:
        self._offers = list(offers)

    async def offers(self) -> Sequence[RawOffer]:
        return self._offers


class RenamedEmbedder(HashingEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.model = "hashing-v2-1536"


@pytest.fixture
async def sessions(engine: AsyncEngine, migrated: None) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE products, users CASCADE"))
    return create_session_factory(engine)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


def _service(
    sessions: async_sessionmaker[AsyncSession],
    clock: FixedClock,
    embedder: HashingEmbedder | None = None,
) -> CatalogService:
    return CatalogService(
        lambda: UnitOfWork(sessions), clock=clock, embedder=embedder or HashingEmbedder()
    )


async def _count(sessions: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessions() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.fixture
async def seeded(sessions: async_sessionmaker[AsyncSession], clock: FixedClock) -> CatalogService:
    catalog = _service(sessions, clock)
    await catalog.ingest(MockSource())
    while await catalog.embed_pending(batch_size=100):
        pass
    return catalog


# ---------- ingest ----------


async def test_ingest_builds_canonical_products_with_offers(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    report = await _service(sessions, clock).ingest(MockSource())

    assert (report.products_created, report.offers_created, report.rejected_offers) == (300, 666, 0)
    assert report.price_changes == 666  # first sighting of every price
    assert await _count(sessions, Product) == 300
    assert await _count(sessions, Offer) == 666


async def test_ingest_is_idempotent(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    await catalog.ingest(MockSource())

    again = await catalog.ingest(MockSource())

    assert (again.products_created, again.products_updated) == (0, 0)
    assert (again.offers_created, again.offers_updated, again.price_changes) == (0, 0, 0)
    assert await _count(sessions, PriceSnapshot) == 666


async def test_price_change_is_snapshotted_and_updates_best_price(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    flipkart = dataclasses.replace(
        TEE,
        store="flipkart",
        external_id="F-1",
        url="https://www.flipkart.com/search?q=tee",
        price_paise=54_900,
    )
    await catalog.ingest(ListSource([TEE, flipkart]))

    report = await catalog.ingest(
        ListSource([TEE, dataclasses.replace(flipkart, price_paise=39_900)])
    )

    assert (report.price_changes, report.offers_updated) == (1, 1)
    async with sessions() as s:
        product = await s.scalar(select(Product))
        assert product is not None
        assert product.min_price_paise == 39_900
        prices = (
            await s.scalars(select(PriceSnapshot.price_paise).order_by(PriceSnapshot.price_paise))
        ).all()
    assert prices == [39_900, 49_900, 54_900]


async def test_out_of_stock_offers_do_not_set_the_best_price(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    cheap_but_gone = dataclasses.replace(
        TEE,
        store="myntra",
        external_id="M-1",
        url="https://www.myntra.com/tee",
        price_paise=19_900,
        in_stock=False,
    )

    await _service(sessions, clock).ingest(ListSource([TEE, cheap_but_gone]))

    async with sessions() as s:
        assert await s.scalar(select(Product.min_price_paise)) == 49_900


@pytest.mark.parametrize(
    "bad",
    [
        dataclasses.replace(TEE, url="https://evil.example/phish"),
        dataclasses.replace(TEE, url="http://www.amazon.in/s?k=tee"),
        dataclasses.replace(TEE, store="unknown-store"),
        dataclasses.replace(TEE, price_paise=0),
        dataclasses.replace(TEE, mrp_paise=100),
    ],
    ids=["foreign-host", "plain-http", "unknown-store", "zero-price", "mrp-below-price"],
)
async def test_unsafe_or_invalid_offers_are_rejected(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock, bad: RawOffer
) -> None:
    report = await _service(sessions, clock).ingest(ListSource([bad]))

    assert report.rejected_offers == 1
    assert await _count(sessions, Offer) == 0
    assert await _count(sessions, Product) == 0


@pytest.mark.parametrize(
    "new_images",
    [
        ("https://placehold.co/new.png",),
        ("https://placehold.co/a.png", "https://placehold.co/b.png"),
        (),
    ],
    ids=["replaced", "more", "none"],
)
async def test_image_changes_are_applied_without_conflicts(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock, new_images: tuple[str, ...]
) -> None:
    catalog = _service(sessions, clock)
    await catalog.ingest(ListSource([TEE]))

    await catalog.ingest(ListSource([dataclasses.replace(TEE, image_urls=new_images)]))

    async with sessions() as s:
        product_id = await s.scalar(select(Product.id))
    assert product_id is not None
    assert (await catalog.get_product(product_id)).images == list(new_images)


# ---------- embeddings ----------


async def test_embedding_runs_once_per_content(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    await catalog.ingest(MockSource())

    assert await catalog.embed_pending(batch_size=1000) == 300
    assert await catalog.embed_pending(batch_size=1000) == 0


async def test_changed_product_is_re_embedded(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    await catalog.ingest(ListSource([TEE]))
    await catalog.embed_pending()

    await catalog.ingest(ListSource([dataclasses.replace(TEE, attributes={"fabric": "linen"})]))

    assert await catalog.embed_pending() == 1


async def test_switching_embedding_model_re_embeds_everything(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock, seeded: CatalogService
) -> None:
    switched = _service(sessions, clock, embedder=RenamedEmbedder())

    assert await switched.embed_pending(batch_size=1000) == 300


async def test_similar_items_are_mostly_the_same_kind(
    seeded: CatalogService, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as s:
        tees = (
            await s.scalars(select(Product).where(Product.category == "tshirt").limit(10))
        ).all()

    for tee in tees:
        similar = await seeded.similar(tee.id, limit=5)
        assert tee.id not in {p.id for p in similar}
        assert len(similar) == 5
        assert Counter(p.category for p in similar)["tshirt"] >= 3, [p.title for p in similar]
        assert all(p.gender in {tee.gender, "unisex"} or tee.gender == "unisex" for p in similar)


async def test_similar_is_empty_until_the_product_is_embedded(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    await catalog.ingest(ListSource([TEE]))
    async with sessions() as s:
        product_id = await s.scalar(select(Product.id))

    assert product_id is not None
    assert await catalog.similar(product_id) == []


# ---------- reads ----------


async def test_product_detail_lists_offers_cheapest_first_with_the_best_flagged(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    catalog = _service(sessions, clock)
    flipkart = dataclasses.replace(
        TEE,
        store="flipkart",
        external_id="F-1",
        url="https://www.flipkart.com/search?q=tee",
        price_paise=44_900,
    )
    await catalog.ingest(ListSource([TEE, flipkart]))
    async with sessions() as s:
        product_id = await s.scalar(select(Product.id))
    assert product_id is not None

    detail = await catalog.get_product(product_id)

    assert [(o.store, o.price_paise, o.is_best) for o in detail.offers] == [
        ("flipkart", 44_900, True),
        ("amazon", 49_900, False),
    ]
    assert detail.offers[0].discount_percent == 55
    assert detail.offers[0].buy_path == f"/v1/out/{detail.offers[0].id}"


async def test_unknown_or_inactive_product_is_not_found(
    seeded: CatalogService, sessions: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(ProductNotFoundError):
        await seeded.get_product(uuid.uuid4())

    async with sessions() as s, s.begin():
        product_id = await s.scalar(select(Product.id).limit(1))
        await s.execute(update(Product).where(Product.id == product_id).values(active=False))
    assert product_id is not None
    with pytest.raises(ProductNotFoundError):
        await seeded.get_product(product_id)


async def test_filters_respect_category_gender_and_budget(seeded: CatalogService) -> None:
    page = await seeded.list_products(
        ProductFilters(category="tshirt", gender="men", max_price_paise=50_000, limit=50)
    )

    assert page.items
    for item in page.items:
        assert item.category == "tshirt"
        assert item.gender in {"men", "unisex"}
        assert item.min_price_paise is not None
        assert item.min_price_paise <= 50_000


async def test_pagination_walks_every_product_exactly_once(seeded: CatalogService) -> None:
    seen: list[uuid.UUID] = []
    cursor: str | None = None
    while True:
        page = await seeded.list_products(ProductFilters(limit=37, cursor=cursor))
        seen.extend(p.id for p in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert len(seen) == len(set(seen)) == 300


# ---------- outbound ----------


async def test_outbound_redirect_logs_the_click(
    seeded: CatalogService, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as s:
        offer = await s.scalar(select(Offer).limit(1))
    assert offer is not None

    url = await seeded.outbound(offer.id, user_id=None, source="feed")

    assert url == offer.url
    async with sessions() as s:
        click = await s.scalar(select(OutboundClick))
    assert click is not None
    assert (click.offer_id, click.source, click.user_id) == (offer.id, "feed", None)


async def test_outbound_for_unknown_offer_is_not_found(seeded: CatalogService) -> None:
    with pytest.raises(OfferNotFoundError):
        await seeded.outbound(uuid.uuid4(), user_id=None, source="feed")


async def test_tampered_offer_url_is_never_redirected_to(
    seeded: CatalogService, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as s, s.begin():
        offer_id = await s.scalar(select(Offer.id).limit(1))
        await s.execute(
            update(Offer).where(Offer.id == offer_id).values(url="https://evil.example/x")
        )
    assert offer_id is not None

    with pytest.raises(OfferNotFoundError):
        await seeded.outbound(offer_id, user_id=None, source="feed")
    assert await _count(sessions, OutboundClick) == 0


class DownEmbedder(HashingEmbedder):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise AIUnavailableError("provider down")


async def test_embedding_outage_defers_work_without_losing_it(
    sessions: async_sessionmaker[AsyncSession], clock: FixedClock
) -> None:
    await _service(sessions, clock).ingest(ListSource([TEE]))

    assert await _service(sessions, clock, embedder=DownEmbedder()).embed_pending() == 0
    assert await _service(sessions, clock).embed_pending() == 1  # still pending, picked up later
