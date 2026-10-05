import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.modules.stylist.models import SessionEvent, StylistSession


class StylistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def add(self, row: StylistSession | SessionEvent) -> None:
        self._s.add(row)

    async def flush(self) -> None:
        await self._s.flush()

    async def get(self, session_id: uuid.UUID, user_id: uuid.UUID) -> StylistSession | None:
        row: StylistSession | None = await self._s.scalar(
            select(StylistSession).where(
                StylistSession.id == session_id, StylistSession.user_id == user_id
            )
        )
        return row

    async def claim_turn(
        self, session_id: uuid.UUID, user_id: uuid.UUID, expected_turn: int, now: datetime
    ) -> StylistSession | None:
        """Compare-and-swap: only the request acting on the current turn wins, exactly once."""
        row: StylistSession | None = await self._s.scalar(
            update(StylistSession)
            .where(
                StylistSession.id == session_id,
                StylistSession.user_id == user_id,
                StylistSession.turn_id == expected_turn,
                StylistSession.status == "active",
            )
            .values(turn_id=StylistSession.turn_id + 1, status="busy", last_activity_at=now)
            .returning(StylistSession)
        )
        return row

    async def complete_turn(
        self,
        session_id: uuid.UUID,
        turn_id: int,
        *,
        state: dict[str, Any],
        envelope: dict[str, Any],
        status: str,
        now: datetime,
    ) -> None:
        await self._s.execute(
            update(StylistSession)
            .where(StylistSession.id == session_id, StylistSession.turn_id == turn_id)
            .values(state=state, envelope=envelope, status=status, last_activity_at=now)
        )

    async def prune_events(self, before: datetime) -> int:
        result = await self._s.execute(delete(SessionEvent).where(SessionEvent.created_at < before))
        return int(result.rowcount)  # type: ignore[attr-defined]
