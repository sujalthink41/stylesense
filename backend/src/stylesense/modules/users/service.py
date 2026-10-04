import uuid
from collections.abc import Callable
from datetime import timedelta

import structlog
from sqlalchemy.exc import IntegrityError

from stylesense.guards.outbox import OutboxEnvelope, OutboxWriter
from stylesense.infra.database import UnitOfWork
from stylesense.modules.users.exceptions import (
    AccountDeletedError,
    AccountSuspendedError,
    EmailInUseError,
)
from stylesense.modules.users.models import AccountDeletion, Consent, User
from stylesense.modules.users.ports import ExternalIdentity
from stylesense.modules.users.repository import UsersRepository
from stylesense.modules.users.schemas import (
    ConsentInput,
    ConsentRecord,
    DeletionChannel,
    DeletionReceipt,
    Device,
    DeviceRegistration,
    Platform,
    ProfileUpdate,
    PurgeOutcome,
    Role,
    UserProfile,
    UserStatus,
)
from stylesense.platform.clock import Clock

PURGE_TOPIC = "users.purge"

logger = structlog.get_logger(__name__)


class PurgeNotDueError(Exception):
    """Raised by the outbox handler so the relay retries later instead of dropping the purge."""


class UsersService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        clock: Clock,
        outbox: OutboxWriter,
        admin_emails: frozenset[str],
        purge_delay_days: int,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._outbox = outbox
        self._admin_emails = admin_emails
        self._purge_delay = timedelta(days=purge_delay_days)

    # ---------- sign-in ----------

    async def sign_in(self, identity: ExternalIdentity) -> tuple[UserProfile, bool]:
        """Find the user for this identity or create one. Returns (profile, created)."""
        if existing := await self._sign_in_existing(identity):
            return existing, False
        try:
            async with self._uow() as uow:
                user = await UsersRepository(uow.session).create_with_identity(
                    email=identity.email,
                    display_name=identity.name,
                    avatar_url=identity.picture_url,
                    role=self._role_for(identity.email, current=None),
                    provider=identity.provider,
                    subject=identity.subject,
                    now=self._clock.now(),
                )
                profile = UserProfile.model_validate(user)
        except IntegrityError:
            # Lost a race with a concurrent first sign-in, or the email belongs to another account.
            if existing := await self._sign_in_existing(identity):
                return existing, False
            raise EmailInUseError from None
        logger.info("user_created", user_id=str(profile.id))
        return profile, True

    async def _sign_in_existing(self, identity: ExternalIdentity) -> UserProfile | None:
        async with self._uow() as uow:
            user = await UsersRepository(uow.session).get_by_identity(
                identity.provider, identity.subject
            )
            if user is None:
                return None
            self._ensure_active(user)
            user.role = self._role_for(user.email, current=Role(user.role))
            user.last_seen_at = self._clock.now()
            user.display_name = user.display_name or identity.name
            user.avatar_url = user.avatar_url or identity.picture_url
            return UserProfile.model_validate(user)

    def _role_for(self, email: str, *, current: Role | None) -> str:
        # The allow-list is the single source of truth for admins.
        if email.lower() in self._admin_emails:
            return Role.ADMIN.value
        if current is None or current is Role.ADMIN:
            return Role.USER.value
        return current.value

    # ---------- profile ----------

    async def get_active(self, user_id: uuid.UUID) -> UserProfile:
        async with self._uow() as uow:
            user = await UsersRepository(uow.session).get(user_id)
            if user is None:
                raise AccountDeletedError
            self._ensure_active(user)
            return UserProfile.model_validate(user)

    async def update_profile(self, user_id: uuid.UUID, update: ProfileUpdate) -> UserProfile:
        async with self._uow() as uow:
            user = await self._active_for_update(UsersRepository(uow.session), user_id)
            for field, value in update.model_dump(exclude_unset=True, exclude_none=True).items():
                setattr(user, field, value)
            await uow.session.flush()
            await uow.session.refresh(user)
            return UserProfile.model_validate(user)

    # ---------- devices ----------

    async def register_device(
        self, user_id: uuid.UUID, installation_id: uuid.UUID, registration: DeviceRegistration
    ) -> Device:
        async with self._uow() as uow:
            repo = UsersRepository(uow.session)
            await self._active_for_update(repo, user_id)
            device = await repo.upsert_device(
                user_id, installation_id, registration, self._clock.now()
            )
            return Device(
                installation_id=device.installation_id,
                platform=Platform(device.platform),
                app_version=device.app_version,
                push_enabled=device.push_enabled,
                has_push_token=device.push_token is not None,
                last_active_at=device.last_active_at,
            )

    async def remove_device(self, user_id: uuid.UUID, installation_id: uuid.UUID) -> None:
        async with self._uow() as uow:
            await UsersRepository(uow.session).delete_device(user_id, installation_id)

    # ---------- consents ----------

    async def record_consent(self, user_id: uuid.UUID, consent: ConsentInput) -> ConsentRecord:
        async with self._uow() as uow:
            repo = UsersRepository(uow.session)
            await self._active_for_update(repo, user_id)
            row = await repo.add_consent(
                Consent(
                    user_id=user_id,
                    kind=consent.kind.value,
                    version=consent.version,
                    granted=consent.granted,
                    created_at=self._clock.now(),
                )
            )
            return ConsentRecord.model_validate(row)

    async def current_consents(self, user_id: uuid.UUID) -> list[ConsentRecord]:
        async with self._uow() as uow:
            rows = await UsersRepository(uow.session).latest_consents(user_id)
            return [ConsentRecord.model_validate(r) for r in rows]

    # ---------- deletion ----------

    async def request_deletion(self, user_id: uuid.UUID, via: DeletionChannel) -> DeletionReceipt:
        """Idempotent: a repeated request returns the original receipt."""
        async with self._uow() as uow:
            repo = UsersRepository(uow.session)
            user = await repo.get(user_id, for_update=True)
            if user is None:
                raise AccountDeletedError
            if existing := await repo.get_deletion(user_id):
                return DeletionReceipt(purge_after=existing.purge_after)

            now = self._clock.now()
            purge_after = now + self._purge_delay
            user.status, user.deleted_at = UserStatus.DELETING.value, now
            await repo.add_deletion(
                AccountDeletion(
                    user_id=user_id,
                    requested_via=via.value,
                    requested_at=now,
                    purge_after=purge_after,
                )
            )
            # Same transaction: the purge is scheduled if and only if the request is recorded.
            await self._outbox.add(
                uow.session,
                PURGE_TOPIC,
                {"user_id": str(user_id)},
                dedupe_key=f"{PURGE_TOPIC}:{user_id}",
                delay=self._purge_delay,
            )
        logger.info("account_deletion_requested", user_id=str(user_id), via=via.value)
        return DeletionReceipt(purge_after=purge_after)

    async def purge(self, user_id: uuid.UUID) -> PurgeOutcome:
        async with self._uow() as uow:
            repo = UsersRepository(uow.session)
            deletion = await repo.get_deletion(user_id, for_update=True)
            if deletion is None or deletion.purged_at is not None:
                return PurgeOutcome.NOTHING_TO_DO
            now = self._clock.now()
            if now < deletion.purge_after:
                return PurgeOutcome.NOT_DUE
            user = await repo.get(user_id, for_update=True)
            if user is not None:
                if user.status != UserStatus.DELETING.value:
                    return PurgeOutcome.NOTHING_TO_DO  # restored by support: never purge
                await repo.delete_user(user)
            deletion.purged_at = now
        logger.info("account_purged", user_id=str(user_id))
        return PurgeOutcome.PURGED

    async def handle_purge(self, envelope: OutboxEnvelope) -> None:
        """Outbox handler for `users.purge`."""
        if await self.purge(uuid.UUID(envelope.payload["user_id"])) is PurgeOutcome.NOT_DUE:
            raise PurgeNotDueError

    # ---------- helpers ----------

    async def _active_for_update(self, repo: UsersRepository, user_id: uuid.UUID) -> User:
        user = await repo.get(user_id, for_update=True)
        if user is None:
            raise AccountDeletedError
        self._ensure_active(user)
        return user

    @staticmethod
    def _ensure_active(user: User) -> None:
        if user.status == UserStatus.DELETING.value:
            raise AccountDeletedError
        if user.status == UserStatus.SUSPENDED.value:
            raise AccountSuspendedError
