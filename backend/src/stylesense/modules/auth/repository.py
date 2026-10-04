import uuid
from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy import select as sql_select
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.modules.auth.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, token: RefreshToken) -> None:
        self._s.add(token)
        await self._s.flush()

    async def get_by_hash_for_update(self, token_hash: bytes) -> RefreshToken | None:
        # Row lock serialises concurrent refreshes of the same token.
        token: RefreshToken | None = await self._s.scalar(
            sql_select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return token

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> int:
        result = await self._s.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def revoke_for_user(
        self, user_id: uuid.UUID, now: datetime, *, installation_id: uuid.UUID | None = None
    ) -> int:
        stmt = update(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        if installation_id is not None:
            stmt = stmt.where(RefreshToken.installation_id == installation_id)
        result = await self._s.execute(stmt.values(revoked_at=now))
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def delete_expired(self, before: datetime) -> int:
        result = await self._s.execute(delete(RefreshToken).where(RefreshToken.expires_at < before))
        return int(result.rowcount)  # type: ignore[attr-defined]
