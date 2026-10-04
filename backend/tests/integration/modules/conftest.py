from collections.abc import Callable
from dataclasses import dataclass

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.guards.outbox import OutboxWriter
from stylesense.infra.database import UnitOfWork, create_session_factory
from stylesense.modules.auth.service import AuthService
from stylesense.modules.auth.tokens import AccessTokenCodec
from stylesense.modules.users.service import UsersService
from tests.fakes.clock import FixedClock
from tests.fakes.identity import FakeIdentityVerifier

ADMIN_EMAIL = "founder@stylesense.app"


@dataclass
class Services:
    users: UsersService
    auth: AuthService
    tokens: AccessTokenCodec
    verifier: FakeIdentityVerifier
    clock: FixedClock
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(engine: AsyncEngine, migrated: None) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE users, account_deletions, outbox_messages RESTART IDENTITY CASCADE")
        )
    return create_session_factory(engine)


@pytest.fixture
def make_services(sessions: async_sessionmaker[AsyncSession]) -> Callable[..., Services]:
    def build(*, admin_emails: tuple[str, ...] = (ADMIN_EMAIL,), grace_s: int = 30) -> Services:
        clock = FixedClock()
        verifier = FakeIdentityVerifier()

        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        users = UsersService(
            uow,
            clock=clock,
            outbox=OutboxWriter(clock),
            admin_emails=frozenset(admin_emails),
            purge_delay_days=30,
        )
        tokens = AccessTokenCodec(
            secret=SecretStr("x" * 40),
            previous_secrets=[],
            issuer="stylesense",
            ttl_s=900,
            clock=clock,
        )
        auth = AuthService(
            uow,
            users=users,
            tokens=tokens,
            verifier=verifier,
            clock=clock,
            refresh_ttl_s=30 * 86_400,
            reuse_grace_s=grace_s,
        )
        return Services(users, auth, tokens, verifier, clock, sessions)

    return build


@pytest.fixture
def svc(make_services: Callable[..., Services]) -> Services:
    return make_services()
