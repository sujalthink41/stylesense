import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import structlog

from stylesense.infra.database import UnitOfWork
from stylesense.modules.auth.exceptions import InvalidRefreshTokenError, RefreshTokenReusedError
from stylesense.modules.auth.models import RefreshToken
from stylesense.modules.auth.ports import IdentityVerifier
from stylesense.modules.auth.repository import RefreshTokenRepository
from stylesense.modules.auth.schemas import SignInResult, TokenPair
from stylesense.modules.auth.tokens import AccessTokenCodec, hash_refresh_token, new_refresh_token
from stylesense.modules.users.exceptions import AccountDeletedError, AccountSuspendedError
from stylesense.modules.users.schemas import DeletionChannel, DeletionReceipt, UserProfile
from stylesense.modules.users.service import UsersService
from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DevIdentity:
    """A stand-in identity for local development: the email is the subject."""

    email: str
    provider: str = "dev"
    name: str | None = "Local Developer"
    picture_url: str | None = None

    @property
    def subject(self) -> str:
        return self.email


class AuthService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        users: UsersService,
        tokens: AccessTokenCodec,
        verifier: IdentityVerifier,
        clock: Clock,
        refresh_ttl_s: int,
        reuse_grace_s: int,
    ) -> None:
        self._uow = uow
        self._users = users
        self._tokens = tokens
        self._verifier = verifier
        self._clock = clock
        self._refresh_ttl = timedelta(seconds=refresh_ttl_s)
        self._grace = timedelta(seconds=reuse_grace_s)

    async def sign_in_with_google(
        self, id_token: str, *, installation_id: uuid.UUID | None = None
    ) -> SignInResult:
        identity = await self._verifier.verify(id_token)
        user, created = await self._users.sign_in(identity)
        pair = await self.issue_session(user, installation_id=installation_id)
        logger.info("signed_in", user_id=str(user.id), new_user=created)
        return SignInResult(tokens=pair, user=user, is_new_user=created)

    async def sign_in_dev(
        self, email: str, *, installation_id: uuid.UUID | None = None
    ) -> SignInResult:
        """Developer sign-in without Google. Callers must check it's enabled (never prod)."""
        user, created = await self._users.sign_in(DevIdentity(email=email.strip().lower()))
        pair = await self.issue_session(user, installation_id=installation_id)
        logger.info("signed_in_dev", user_id=str(user.id), new_user=created)
        return SignInResult(tokens=pair, user=user, is_new_user=created)

    async def issue_session(
        self, user: UserProfile, *, installation_id: uuid.UUID | None = None
    ) -> TokenPair:
        """Start a new session for an already-authenticated user."""
        async with self._uow() as uow:
            repo = RefreshTokenRepository(uow.session)
            if installation_id is not None:
                # One session per install: signing in again replaces the old session.
                await repo.revoke_for_user(
                    user.id, self._clock.now(), installation_id=installation_id
                )
            return await self._start_token(repo, user, uuid.uuid4(), installation_id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate: the presented token is spent and a new one issued in the same family.

        Reuse after the grace window means the token was stolen: revoke the whole family.
        """
        now = self._clock.now()
        failure: Exception | None = None
        pair: TokenPair | None = None
        async with self._uow() as uow:
            repo = RefreshTokenRepository(uow.session)
            row = await repo.get_by_hash_for_update(hash_refresh_token(refresh_token))
            if row is None or row.revoked_at is not None or row.expires_at <= now:
                failure = InvalidRefreshTokenError()
            elif row.used_at is not None and now - row.used_at > self._grace:
                await repo.revoke_family(row.family_id, now)
                logger.warning(
                    "refresh_token_reuse_detected",
                    user_id=str(row.user_id),
                    session_id=str(row.family_id),
                )
                failure = RefreshTokenReusedError()
            else:
                try:
                    user = await self._users.get_active(row.user_id)
                except (AccountDeletedError, AccountSuspendedError) as exc:
                    await repo.revoke_family(row.family_id, now)
                    failure = exc
                else:
                    # Within the grace window a parallel request gets a sibling, not a revocation.
                    row.used_at = row.used_at or now
                    pair = await self._start_token(repo, user, row.family_id, row.installation_id)
        # Raise only after commit, so a revocation is never rolled back.
        if failure is not None:
            raise failure
        assert pair is not None  # noqa: S101  # every non-failure branch issued a pair
        return pair

    async def logout(self, refresh_token: str) -> None:
        """Idempotent: unknown or already revoked tokens are not an error."""
        async with self._uow() as uow:
            repo = RefreshTokenRepository(uow.session)
            row = await repo.get_by_hash_for_update(hash_refresh_token(refresh_token))
            if row is not None:
                await repo.revoke_family(row.family_id, self._clock.now())

    async def revoke_all(self, user_id: uuid.UUID) -> int:
        async with self._uow() as uow:
            return await RefreshTokenRepository(uow.session).revoke_for_user(
                user_id, self._clock.now()
            )

    async def delete_account(self, user_id: uuid.UUID, via: DeletionChannel) -> DeletionReceipt:
        # Deletion first: if revoking fails afterwards, refresh still refuses deleted users.
        receipt = await self._users.request_deletion(user_id, via)
        revoked = await self.revoke_all(user_id)
        logger.info("sessions_revoked_for_deletion", user_id=str(user_id), sessions=revoked)
        return receipt

    async def prune_expired(self, *, older_than: timedelta = timedelta(days=7)) -> int:
        async with self._uow() as uow:
            return await RefreshTokenRepository(uow.session).delete_expired(
                self._clock.now() - older_than
            )

    async def _start_token(
        self,
        repo: RefreshTokenRepository,
        user: UserProfile,
        family_id: uuid.UUID,
        installation_id: uuid.UUID | None,
    ) -> TokenPair:
        raw = new_refresh_token()
        await repo.add(
            RefreshToken(
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_refresh_token(raw),
                installation_id=installation_id,
                expires_at=self._clock.now() + self._refresh_ttl,
            )
        )
        return TokenPair(
            access_token=self._tokens.issue(user_id=user.id, session_id=family_id, role=user.role),
            access_token_expires_in=self._tokens.ttl_s,
            refresh_token=raw,
            refresh_token_expires_in=int(self._refresh_ttl.total_seconds()),
        )
