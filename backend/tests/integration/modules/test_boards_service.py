import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.boards.exceptions import (
    BoardIdTakenError,
    BoardNotFoundError,
    InvalidOrderError,
    VersionConflictError,
    WishlistIsPermanentError,
)
from stylesense.modules.boards.models import BoardItem
from stylesense.modules.boards.schemas import BoardCreate, BoardUpdate
from stylesense.modules.boards.service import BoardsService
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.models import Product
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.users.models import User
from tests.fakes.clock import FixedClock


def _service(sessions: async_sessionmaker[AsyncSession]) -> BoardsService:
    def uow() -> UnitOfWork:
        return UnitOfWork(sessions)

    catalog = CatalogService(uow, clock=FixedClock(), embedder=HashingEmbedder())
    return BoardsService(uow, catalog=catalog, clock=FixedClock())


async def _products(sessions: async_sessionmaker[AsyncSession], n: int) -> list[uuid.UUID]:
    async with sessions() as s:
        return list((await s.scalars(select(Product.id).order_by(Product.id).limit(n))).all())


async def _other_user(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id


# ---------- wishlist ----------


async def test_every_user_has_exactly_one_wishlist_even_under_concurrency(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)

    lists = await asyncio.gather(*(service.list_boards(user_id) for _ in range(8)))

    assert all([b.kind for b in boards] == ["wishlist"] for boards in lists)
    assert len({boards[0].id for boards in lists}) == 1


async def test_saving_to_the_wishlist_alias(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    [product] = await _products(catalog_sessions, 1)

    receipt = await service.add_item(user_id, "wishlist", product)

    wishlist = await service.get(user_id, "wishlist")
    assert receipt.added is True
    assert [i.product.id for i in wishlist.items] == [product]
    assert wishlist.cover_image_url is not None


async def test_the_wishlist_cannot_be_deleted_or_renamed(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    wishlist = await service.get(user_id, "wishlist")

    with pytest.raises(WishlistIsPermanentError):
        await service.delete(user_id, "wishlist")
    with pytest.raises(WishlistIsPermanentError):
        await service.update(
            user_id, "wishlist", BoardUpdate(name="Mine"), expected_version=wishlist.version
        )


# ---------- items ----------


async def test_concurrent_saves_of_the_same_product_keep_one_item(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    [product] = await _products(catalog_sessions, 1)

    receipts = await asyncio.gather(
        *(service.add_item(user_id, "wishlist", product) for _ in range(10))
    )

    assert sum(r.added for r in receipts) == 1
    wishlist = await service.get(user_id, "wishlist")
    async with catalog_sessions() as s:
        rows = await s.scalar(
            select(func.count()).select_from(BoardItem).where(BoardItem.board_id == wishlist.id)
        )
    assert rows == 1
    assert wishlist.version == 2  # created at 1, one real change


async def test_concurrent_saves_of_different_products_all_land_in_order(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    products = await _products(catalog_sessions, 8)

    await asyncio.gather(*(service.add_item(user_id, "wishlist", p) for p in products))

    wishlist = await service.get(user_id, "wishlist")
    assert {i.product.id for i in wishlist.items} == set(products)
    assert sorted(i.position for i in wishlist.items) == list(range(1, 9))  # no duplicates
    assert wishlist.version == 1 + len(products)


async def test_removing_is_idempotent_and_only_real_changes_bump_the_version(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    [product] = await _products(catalog_sessions, 1)
    await service.add_item(user_id, "wishlist", product)

    first = await service.remove_item(user_id, "wishlist", product)
    again = await service.remove_item(user_id, "wishlist", product)

    assert first == again == 3
    assert (await service.get(user_id, "wishlist")).items == []


async def test_saving_an_unknown_product_is_404(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    with pytest.raises(ProductNotFoundError):
        await _service(catalog_sessions).add_item(user_id, "wishlist", uuid.uuid4())


# ---------- outfit boards ----------


async def test_create_with_a_client_id_is_idempotent(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    body = BoardCreate(id=uuid.uuid4(), name="  Goa   trip ")

    first, created = await service.create(user_id, body)
    replay, created_again = await service.create(user_id, body)

    assert (created, created_again) == (True, False)
    assert first.id == replay.id == body.id
    assert first.name == "Goa trip"
    assert len(await service.list_boards(user_id)) == 2  # wishlist + this one


async def test_someone_elses_board_id_is_refused_and_their_board_looks_missing(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(id=uuid.uuid4(), name="Mine"))
    intruder = await _other_user(catalog_sessions)

    with pytest.raises(BoardIdTakenError):
        await service.create(intruder, BoardCreate(id=board.id, name="Theirs"))
    with pytest.raises(BoardNotFoundError):
        await service.get(intruder, board.id)
    with pytest.raises(BoardNotFoundError):
        await service.add_item(intruder, board.id, (await _products(catalog_sessions, 1))[0])


async def test_a_stale_version_is_refused_with_the_current_one(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(name="Office"))
    phone = await service.update(
        user_id, board.id, BoardUpdate(name="Office wear"), expected_version=board.version
    )

    with pytest.raises(VersionConflictError) as caught:
        await service.update(
            user_id, board.id, BoardUpdate(name="Work"), expected_version=board.version
        )

    assert caught.value.extra == {"current_version": phone.version}
    assert (await service.get(user_id, board.id)).name == "Office wear"


async def test_concurrent_edits_with_the_same_version_let_exactly_one_win(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(name="Party"))

    results = await asyncio.gather(
        *(
            service.update(
                user_id, board.id, BoardUpdate(name=f"Party {i}"), expected_version=board.version
            )
            for i in range(6)
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert all(isinstance(r, VersionConflictError) for r in results if isinstance(r, Exception))


async def test_reorder_needs_every_item_exactly_once(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(name="Look"))
    a, b, c = await _products(catalog_sessions, 3)
    for p in (a, b, c):
        await service.add_item(user_id, board.id, p)
    current = await service.get(user_id, board.id)

    reordered = await service.reorder(
        user_id, board.id, [c, a, b], expected_version=current.version
    )

    assert [i.product.id for i in reordered.items] == [c, a, b]
    for bad in ([c, a], [c, a, a], [c, a, b, uuid.uuid4()]):
        with pytest.raises(InvalidOrderError):
            await service.reorder(user_id, board.id, bad, expected_version=reordered.version)


async def test_deleted_boards_disappear_and_delete_is_idempotent(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(name="Old"))

    await service.delete(user_id, board.id)
    await service.delete(user_id, board.id)

    with pytest.raises(BoardNotFoundError):
        await service.get(user_id, board.id)
    assert board.id not in {b.id for b in await service.list_boards(user_id)}
    with pytest.raises(BoardIdTakenError):  # its id can't be reused
        await service.create(user_id, BoardCreate(id=board.id, name="Old"))


async def test_cover_must_be_a_real_product_and_can_be_cleared(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    service = _service(catalog_sessions)
    board, _ = await service.create(user_id, BoardCreate(name="Covers"))
    [product] = await _products(catalog_sessions, 1)

    with pytest.raises(ProductNotFoundError):
        await service.update(
            user_id, board.id, BoardUpdate(cover_product_id=uuid.uuid4()), expected_version=1
        )
    covered = await service.update(
        user_id, board.id, BoardUpdate(cover_product_id=product), expected_version=1
    )
    cleared = await service.update(
        user_id, board.id, BoardUpdate(cover_product_id=None), expected_version=covered.version
    )

    assert covered.cover_image_url is not None
    assert cleared.cover_image_url is None
