from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.guards.idempotency import IdempotencyGuard
from stylesense.guards.locks import LockManager
from stylesense.guards.outbox import OutboxWriter
from stylesense.guards.rate_limit import RateLimiter
from stylesense.infra.database import UnitOfWork, create_engine, create_session_factory
from stylesense.infra.health import PostgresHealthCheck, RedisHealthCheck
from stylesense.infra.redis import create_redis
from stylesense.integrations.google_identity import GoogleIdTokenVerifier, google_signing_keys
from stylesense.modules.auth.ports import IdentityVerifier
from stylesense.modules.auth.service import AuthService
from stylesense.modules.auth.tokens import AccessTokenCodec
from stylesense.modules.users.service import UsersService
from stylesense.platform.clock import Clock, SystemClock
from stylesense.platform.config import Settings
from stylesense.platform.health import HealthCheck


@dataclass(slots=True)
class Container:
    """App-wide singletons. The only place concrete implementations are chosen."""

    settings: Settings
    clock: Clock
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    health_checks: tuple[HealthCheck, ...]
    rate_limiter: RateLimiter
    idempotency: IdempotencyGuard
    locks: LockManager
    outbox: OutboxWriter
    token_codec: AccessTokenCodec
    users: UsersService
    auth: AuthService
    closed: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self.closed:
            return
        try:
            await self.redis.aclose()
        finally:
            await self.engine.dispose()
            self.closed = True


def build_container(settings: Settings, *, verifier: IdentityVerifier | None = None) -> Container:
    """`verifier` is injectable so tests can replace Google with a fake."""
    # Clients are lazy: nothing connects until first use.
    engine = create_engine(settings)
    redis = create_redis(settings)
    clock = SystemClock()
    session_factory = create_session_factory(engine)
    outbox = OutboxWriter(clock)

    def uow() -> UnitOfWork:
        return UnitOfWork(session_factory)

    token_codec = AccessTokenCodec(
        secret=settings.jwt_secret,
        previous_secrets=settings.jwt_previous_secrets,
        issuer=settings.jwt_issuer,
        ttl_s=settings.access_token_ttl_s,
        clock=clock,
    )
    users = UsersService(
        uow,
        clock=clock,
        outbox=outbox,
        admin_emails=frozenset(settings.admin_emails),
        purge_delay_days=settings.account_purge_delay_days,
    )
    auth = AuthService(
        uow,
        users=users,
        tokens=token_codec,
        verifier=verifier
        or GoogleIdTokenVerifier(client_ids=settings.google_client_ids, keys=google_signing_keys()),
        clock=clock,
        refresh_ttl_s=settings.refresh_token_ttl_s,
        reuse_grace_s=settings.refresh_reuse_grace_s,
    )
    return Container(
        settings=settings,
        clock=clock,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        health_checks=(PostgresHealthCheck(engine), RedisHealthCheck(redis)),
        rate_limiter=RateLimiter(redis, clock, fail_open=settings.rate_limit_fail_open),
        idempotency=IdempotencyGuard(
            redis,
            lock_ttl_s=settings.idempotency_lock_ttl_s,
            result_ttl_s=settings.idempotency_ttl_s,
        ),
        locks=LockManager(redis),
        outbox=outbox,
        token_codec=token_codec,
        users=users,
        auth=auth,
    )
