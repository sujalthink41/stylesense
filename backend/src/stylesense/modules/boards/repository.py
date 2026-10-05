import uuid
from collections.abc import Sequence

from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.modules.boards.models import Board, BoardItem

WISHLIST_NAME = "Wishlist"


class BoardsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def add(self, board: Board) -> None:
        self._s.add(board)

    async def flush(self) -> None:
        await self._s.flush()

    async def get(
        self, board_id: uuid.UUID, *, for_update: bool = False, include_deleted: bool = False
    ) -> Board | None:
        stmt = select(Board).where(Board.id == board_id)
        if not include_deleted:
            stmt = stmt.where(Board.deleted_at.is_(None))
        if for_update:
            stmt = stmt.with_for_update()
        board: Board | None = await self._s.scalar(stmt)
        return board

    async def owned(
        self, user_id: uuid.UUID, board_id: uuid.UUID, *, for_update: bool = False
    ) -> Board | None:
        """Another user's board looks exactly like a missing one."""
        board = await self.get(board_id, for_update=for_update)
        return board if board is not None and board.user_id == user_id else None

    async def wishlist(self, user_id: uuid.UUID, *, for_update: bool = False) -> Board:
        """The user's wishlist, created on first use (race-safe via the partial unique index)."""
        await self._s.execute(
            insert(Board)
            .values(user_id=user_id, name=WISHLIST_NAME, kind="wishlist")
            .on_conflict_do_nothing(
                index_elements=["user_id"],
                index_where=text("kind = 'wishlist' AND deleted_at IS NULL"),
            )
        )
        stmt = select(Board).where(
            Board.user_id == user_id, Board.kind == "wishlist", Board.deleted_at.is_(None)
        )
        if for_update:
            stmt = stmt.with_for_update()
        board: Board = (await self._s.scalars(stmt)).one()
        return board

    async def list_for(self, user_id: uuid.UUID) -> list[tuple[Board, int]]:
        counts = (
            select(BoardItem.board_id, func.count().label("n"))
            .group_by(BoardItem.board_id)
            .subquery()
        )
        stmt = (
            select(Board, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.board_id == Board.id)
            .where(Board.user_id == user_id, Board.deleted_at.is_(None))
            .order_by(case((Board.kind == "wishlist", 0), else_=1), Board.created_at.desc())
        )
        return [(b, int(n)) for b, n in (await self._s.execute(stmt)).all()]

    async def count_outfits(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Board.user_id == user_id, Board.kind == "outfit", Board.deleted_at.is_(None)
        )
        return int(await self._s.scalar(stmt) or 0)

    async def items(self, board_id: uuid.UUID) -> list[BoardItem]:
        stmt = (
            select(BoardItem)
            .where(BoardItem.board_id == board_id)
            .order_by(BoardItem.position, BoardItem.added_at, BoardItem.id)
            # Positions may have just changed in SQL (reorder): refresh what's in the session.
            .execution_options(populate_existing=True)
        )
        return list((await self._s.scalars(stmt)).all())

    async def count_items(self, board_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(BoardItem.board_id == board_id)
        return int(await self._s.scalar(stmt) or 0)

    async def first_items(self, board_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
        """First product on each board (for covers), in one query."""
        if not board_ids:
            return {}
        stmt = (
            select(BoardItem.board_id, BoardItem.product_id)
            .where(BoardItem.board_id.in_(board_ids))
            .distinct(BoardItem.board_id)
            .order_by(BoardItem.board_id, BoardItem.position, BoardItem.added_at)
        )
        rows = (await self._s.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def add_item(self, board_id: uuid.UUID, product_id: uuid.UUID, note: str | None) -> bool:
        """Appends; False if the product is already on the board (unique key)."""
        position = select(func.coalesce(func.max(BoardItem.position), 0) + 1).where(
            BoardItem.board_id == board_id
        )
        stmt = (
            insert(BoardItem)
            .values(
                board_id=board_id,
                product_id=product_id,
                note=note,
                position=position.scalar_subquery(),
            )
            .on_conflict_do_nothing(constraint="uq_board_items_once")
            .returning(BoardItem.id)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def remove_item(self, board_id: uuid.UUID, product_id: uuid.UUID) -> bool:
        stmt = delete(BoardItem).where(
            BoardItem.board_id == board_id, BoardItem.product_id == product_id
        )
        return bool((await self._s.execute(stmt)).rowcount)  # type: ignore[attr-defined]

    async def reorder(self, board_id: uuid.UUID, product_ids: Sequence[uuid.UUID]) -> None:
        positions = {pid: i for i, pid in enumerate(product_ids, start=1)}
        await self._s.execute(
            update(BoardItem)
            .where(BoardItem.board_id == board_id, BoardItem.product_id.in_(positions))
            .values(position=case(positions, value=BoardItem.product_id))
        )
