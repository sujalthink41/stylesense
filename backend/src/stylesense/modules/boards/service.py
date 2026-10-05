"""Wishlist and outfit boards.

Every write locks the board row, checks the caller's version when it names one, applies the
change and bumps `version`, all in one transaction. Adds and removes are idempotent by
nature (unique item key), so they don't need a version; renames and reorders do, because
two devices editing blind would silently overwrite each other.
"""

import uuid
from collections.abc import Callable

import structlog

from stylesense.infra.database import UnitOfWork
from stylesense.modules.boards.exceptions import (
    BoardIdTakenError,
    BoardLimitError,
    BoardNotFoundError,
    InvalidOrderError,
    ItemLimitError,
    VersionConflictError,
    WishlistIsPermanentError,
)
from stylesense.modules.boards.models import Board, BoardItem
from stylesense.modules.boards.repository import BoardsRepository
from stylesense.modules.boards.schemas import (
    MAX_ITEMS,
    BoardCreate,
    BoardItemView,
    BoardSummary,
    BoardUpdate,
    BoardView,
    ItemReceipt,
)
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.schemas import ProductSummary
from stylesense.modules.catalog.service import CatalogService
from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)

MAX_OUTFIT_BOARDS = 50
WISHLIST = "wishlist"  # path alias: /v1/boards/wishlist/...


class BoardsService:
    def __init__(
        self, uow: Callable[[], UnitOfWork], *, catalog: CatalogService, clock: Clock
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._clock = clock

    # ---------- boards ----------

    async def list_boards(self, user_id: uuid.UUID) -> list[BoardSummary]:
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            await repo.wishlist(user_id)  # always there, even before the first save
            rows = await repo.list_for(user_id)
            firsts = await repo.first_items([b.id for b, _ in rows])
        covers = {b.id: b.cover_product_id or firsts.get(b.id) for b, _ in rows}
        products = await self._catalog.summaries([c for c in covers.values() if c])
        return [
            _summary(b, n, products.get(cover) if (cover := covers[b.id]) else None)
            for b, n in rows
        ]

    async def create(self, user_id: uuid.UUID, body: BoardCreate) -> tuple[BoardView, bool]:
        """Returns (board, created). Replaying a create with the same id returns the board."""
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            if body.id is not None and (existing := await repo.get(body.id, include_deleted=True)):
                if existing.user_id != user_id or existing.deleted_at is not None:
                    raise BoardIdTakenError
                return await self._view(repo, existing), False
            if await repo.count_outfits(user_id) >= MAX_OUTFIT_BOARDS:
                raise BoardLimitError
            board = Board(user_id=user_id, name=body.name, kind="outfit")
            if body.id is not None:
                board.id = body.id
            board.version = 1
            board.created_at = board.updated_at = self._clock.now()
            repo.add(board)
            await repo.flush()
            view = await self._view(repo, board)
        logger.info("board_created", board_id=str(board.id))
        return view, True

    async def get(self, user_id: uuid.UUID, board_id: uuid.UUID | str) -> BoardView:
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            return await self._view(repo, await self._owned(repo, user_id, board_id))

    async def update(
        self,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        body: BoardUpdate,
        *,
        expected_version: int,
    ) -> BoardView:
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await self._locked(repo, user_id, board_id, expected_version)
            if body.name is not None:
                if board.kind == "wishlist":
                    raise WishlistIsPermanentError
                board.name = body.name
            if "cover_product_id" in body.model_fields_set:
                if body.cover_product_id and not await self._catalog.exists(body.cover_product_id):
                    raise ProductNotFoundError
                board.cover_product_id = body.cover_product_id
            self._bump(board)
            return await self._view(repo, board)

    async def delete(self, user_id: uuid.UUID, board_id: uuid.UUID | str) -> None:
        """Soft delete; deleting twice is fine."""
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await self._find(repo, user_id, board_id, for_update=True)
            if board is None:
                return
            if board.kind == "wishlist":
                raise WishlistIsPermanentError
            board.deleted_at = self._clock.now()
            self._bump(board)

    # ---------- for sharing ----------

    async def owns(self, user_id: uuid.UUID, board_id: uuid.UUID) -> bool:
        async with self._uow() as uow:
            return await BoardsRepository(uow.session).owned(user_id, board_id) is not None

    async def shared_items(self, board_id: uuid.UUID) -> tuple[str, list[uuid.UUID]] | None:
        """A board's name and products for its public share link; None once it's deleted."""
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await repo.get(board_id)
            if board is None:
                return None
            return board.name, [i.product_id for i in await repo.items(board.id)]

    # ---------- items ----------

    async def add_item(
        self,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        product_id: uuid.UUID,
        *,
        note: str | None = None,
    ) -> ItemReceipt:
        if not await self._catalog.exists(product_id):
            raise ProductNotFoundError
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await self._locked(repo, user_id, board_id, None)
            if await repo.count_items(board.id) >= MAX_ITEMS:
                raise ItemLimitError
            added = await repo.add_item(board.id, product_id, note)
            if added:
                self._bump(board)
            return ItemReceipt(
                board_id=board.id, product_id=product_id, added=added, version=board.version
            )

    async def remove_item(
        self, user_id: uuid.UUID, board_id: uuid.UUID | str, product_id: uuid.UUID
    ) -> int:
        """Idempotent; returns the board's version."""
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await self._locked(repo, user_id, board_id, None)
            if await repo.remove_item(board.id, product_id):
                self._bump(board)
            return board.version

    async def reorder(
        self,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        product_ids: list[uuid.UUID],
        *,
        expected_version: int,
    ) -> BoardView:
        async with self._uow() as uow:
            repo = BoardsRepository(uow.session)
            board = await self._locked(repo, user_id, board_id, expected_version)
            current = [i.product_id for i in await repo.items(board.id)]
            if len(product_ids) != len(current) or set(product_ids) != set(current):
                raise InvalidOrderError
            await repo.reorder(board.id, product_ids)
            self._bump(board)
            return await self._view(repo, board)

    # ---------- helpers ----------

    async def _owned(
        self,
        repo: BoardsRepository,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        *,
        for_update: bool = False,
    ) -> Board:
        board = await self._find(repo, user_id, board_id, for_update=for_update)
        if board is None:
            raise BoardNotFoundError
        return board

    async def _find(
        self,
        repo: BoardsRepository,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        *,
        for_update: bool = False,
    ) -> Board | None:
        if board_id == WISHLIST:
            return await repo.wishlist(user_id, for_update=for_update)
        try:
            key = uuid.UUID(str(board_id))
        except ValueError:
            return None
        return await repo.owned(user_id, key, for_update=for_update)

    async def _locked(
        self,
        repo: BoardsRepository,
        user_id: uuid.UUID,
        board_id: uuid.UUID | str,
        expected_version: int | None,
    ) -> Board:
        board = await self._owned(repo, user_id, board_id, for_update=True)
        if expected_version is not None and expected_version != board.version:
            raise VersionConflictError(current_version=board.version)
        return board

    def _bump(self, board: Board) -> None:
        board.version += 1
        board.updated_at = self._clock.now()

    async def _view(self, repo: BoardsRepository, board: Board) -> BoardView:
        items: list[BoardItem] = await repo.items(board.id)
        products = await self._catalog.summaries([i.product_id for i in items])
        cover_id = board.cover_product_id or (items[0].product_id if items else None)
        if cover_id and cover_id not in products:
            products |= await self._catalog.summaries([cover_id])
        views = [
            BoardItemView(
                product=products[i.product_id],
                position=i.position,
                note=i.note,
                added_at=i.added_at,
            )
            for i in items
            if i.product_id in products  # inactive products drop out of view, not off the board
        ]
        return BoardView(
            **_summary(
                board, len(views), products.get(cover_id) if cover_id else None
            ).model_dump(),
            items=views,
        )


def _summary(board: Board, item_count: int, cover: ProductSummary | None) -> BoardSummary:
    return BoardSummary(
        id=board.id,
        name=board.name,
        kind=board.kind,
        version=board.version,
        item_count=item_count,
        cover_image_url=cover.primary_image_url if cover else None,
        updated_at=board.updated_at,
    )
