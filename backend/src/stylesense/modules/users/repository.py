import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stylesense.modules.users.models import AccountDeletion, AuthIdentity, Consent, User, UserDevice
from stylesense.modules.users.schemas import DeviceRegistration


class UsersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: uuid.UUID, *, for_update: bool = False) -> User | None:
        stmt = select(User).where(User.id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        user: User | None = await self._s.scalar(stmt)
        return user

    async def get_by_identity(self, provider: str, subject: str) -> User | None:
        user: User | None = await self._s.scalar(
            select(User)
            .join(AuthIdentity, AuthIdentity.user_id == User.id)
            .where(AuthIdentity.provider == provider, AuthIdentity.subject == subject)
            .with_for_update(of=User)
        )
        return user

    async def email_taken(self, email: str) -> bool:
        return await self._s.scalar(select(User.id).where(User.email == email)) is not None

    async def create_with_identity(
        self,
        *,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        role: str,
        provider: str,
        subject: str,
        now: datetime,
    ) -> User:
        user = User(
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            role=role,
            last_seen_at=now,
        )
        self._s.add(user)
        await self._s.flush()
        self._s.add(AuthIdentity(user_id=user.id, provider=provider, subject=subject))
        await self._s.flush()
        await self._s.refresh(user)
        return user

    async def upsert_device(
        self, user_id: uuid.UUID, installation_id: uuid.UUID, reg: DeviceRegistration, now: datetime
    ) -> UserDevice:
        if reg.push_token:
            # A push token identifies a physical phone; free it from any other account first.
            await self._s.execute(
                update(UserDevice)
                .where(
                    UserDevice.push_token == reg.push_token,
                    (UserDevice.user_id != user_id)
                    | (UserDevice.installation_id != installation_id),
                )
                .values(push_token=None)
            )
        values = {
            "platform": reg.platform.value,
            "app_version": reg.app_version,
            "push_token": reg.push_token,
            "push_enabled": reg.push_enabled,
            "last_active_at": now,
        }
        stmt = (
            insert(UserDevice)
            .values(user_id=user_id, installation_id=installation_id, **values)
            .on_conflict_do_update(index_elements=["user_id", "installation_id"], set_=values)
            .returning(UserDevice)
        )
        device: UserDevice = (await self._s.execute(stmt)).scalar_one()
        return device

    async def delete_device(self, user_id: uuid.UUID, installation_id: uuid.UUID) -> None:
        await self._s.execute(
            delete(UserDevice).where(
                UserDevice.user_id == user_id, UserDevice.installation_id == installation_id
            )
        )

    async def add_consent(self, consent: Consent) -> Consent:
        self._s.add(consent)
        await self._s.flush()
        return consent

    async def latest_consents(self, user_id: uuid.UUID) -> list[Consent]:
        stmt = (
            select(Consent)
            .where(Consent.user_id == user_id)
            .distinct(Consent.kind)
            .order_by(Consent.kind, Consent.created_at.desc(), Consent.id.desc())
        )
        return list((await self._s.scalars(stmt)).all())

    async def get_deletion(
        self, user_id: uuid.UUID, *, for_update: bool = False
    ) -> AccountDeletion | None:
        stmt = select(AccountDeletion).where(AccountDeletion.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        deletion: AccountDeletion | None = await self._s.scalar(stmt)
        return deletion

    async def add_deletion(self, deletion: AccountDeletion) -> None:
        self._s.add(deletion)
        await self._s.flush()

    async def delete_user(self, user: User) -> None:
        # Cascades to identities, devices, consents and refresh tokens.
        await self._s.delete(user)
