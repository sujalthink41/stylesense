from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CollectorRegistry
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.ai.gateway.admin import LlmAdmin
from stylesense.ai.gateway.config import ConfigStore
from stylesense.ai.gateway.gateway import GatewaySettings, LLMGateway
from stylesense.ai.gateway.metrics import GatewayMetrics
from stylesense.ai.gateway.types import ChatProvider, EmbeddingProvider, ModelRef
from stylesense.guards.idempotency import IdempotencyGuard
from stylesense.guards.locks import LockManager
from stylesense.guards.outbox import OutboxWriter
from stylesense.guards.rate_limit import RateLimiter
from stylesense.infra.database import UnitOfWork, create_engine, create_session_factory
from stylesense.infra.health import PostgresHealthCheck, RedisHealthCheck
from stylesense.infra.redis import create_redis
from stylesense.integrations.embeddings.gateway import GatewayEmbedder
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.integrations.google_identity import GoogleIdTokenVerifier, google_signing_keys
from stylesense.integrations.llm.anthropic_provider import AnthropicProvider
from stylesense.integrations.llm.openai_provider import OpenAIProvider
from stylesense.modules.auth.ports import IdentityVerifier
from stylesense.modules.auth.service import AuthService
from stylesense.modules.auth.tokens import AccessTokenCodec
from stylesense.modules.catalog.ports import Embedder
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.looks.service import LookService
from stylesense.modules.personalization.service import (
    PersonalizationMetrics,
    PersonalizationService,
)
from stylesense.modules.stylist.flows.demo import DemoFlow
from stylesense.modules.stylist.flows.style_dna import StyleDnaFlow
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.users.service import UsersService
from stylesense.platform.clock import Clock, SystemClock
from stylesense.platform.config import Settings
from stylesense.platform.health import HealthCheck

_MICRO_USD_PER_USD = 1_000_000
# Adapters that exist in code (whether or not a key is configured yet).
KNOWN_LLM_PROVIDERS = frozenset({"openai", "anthropic"})

Closer = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Telemetry:
    """Process-level observability handed to the container by the entry point."""

    registry: CollectorRegistry | None = None
    tracer_provider: TracerProvider | None = None


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
    gateway: LLMGateway
    llm_admin: LlmAdmin
    llm_providers: tuple[str, ...]
    catalog: CatalogService
    personalization: PersonalizationService
    looks: LookService
    stylist: StylistService
    closers: tuple[Closer, ...] = ()
    closed: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self.closed:
            return
        try:
            for close in self.closers:
                await close()
            await self.redis.aclose()
        finally:
            await self.engine.dispose()
            self.closed = True


def build_container(
    settings: Settings,
    *,
    verifier: IdentityVerifier | None = None,
    telemetry: Telemetry | None = None,
) -> Container:
    """`verifier` is injectable so tests can replace Google with a fake."""
    telemetry = telemetry or Telemetry()
    # Clients are lazy: nothing connects until first use.
    engine = create_engine(settings)
    redis = create_redis(settings)
    clock = SystemClock()
    session_factory = create_session_factory(engine)
    outbox = OutboxWriter(clock)
    rate_limiter = RateLimiter(redis, clock, fail_open=settings.rate_limit_fail_open)

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

    chat, embed, closers = _llm_providers(settings)
    tracer = (
        telemetry.tracer_provider.get_tracer("stylesense.ai") if telemetry.tracer_provider else None
    )
    llm_config = ConfigStore(uow, redis)
    gateway = LLMGateway(
        config=llm_config,
        chat_providers=chat,
        embedding_providers=embed,
        redis=redis,
        clock=clock,
        uow=uow,
        rate_limiter=rate_limiter,
        settings=GatewaySettings(
            daily_budget_micro_usd=int(settings.llm_daily_budget_usd * _MICRO_USD_PER_USD),
            budget_alert_ratio=settings.llm_budget_alert_ratio,
            max_attempts=settings.llm_max_attempts,
            breaker_threshold=settings.llm_breaker_threshold,
            breaker_window_s=settings.llm_breaker_window_s,
            breaker_cooldown_s=settings.llm_breaker_cooldown_s,
            max_concurrency=settings.llm_max_concurrency,
            max_queued=settings.llm_max_queued,
        ),
        tracer=tracer,
        metrics=GatewayMetrics(telemetry.registry) if telemetry.registry else None,
    )
    embedder: Embedder = (
        HashingEmbedder()
        if settings.embedding_model == "hashing"
        else GatewayEmbedder(gateway, ModelRef.parse(settings.embedding_model))
    )

    catalog = CatalogService(uow, clock=clock, embedder=embedder)
    personalization = PersonalizationService(
        uow,
        embedder=embedder,
        clock=clock,
        metrics=PersonalizationMetrics(telemetry.registry) if telemetry.registry else None,
    )
    looks = LookService(catalog, gateway)
    stylist = StylistService(
        uow,
        flows={
            "stylist": StylistFlow(catalog, gateway, personalization, looks),
            "style_dna": StyleDnaFlow(personalization),
            # Kept so sessions started on it keep working.
            "demo": DemoFlow(catalog),
        },
        default_flow="stylist",
        entry_flows={"onboarding": "style_dna"},
        clock=clock,
    )

    return Container(
        settings=settings,
        clock=clock,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        health_checks=(PostgresHealthCheck(engine), RedisHealthCheck(redis)),
        rate_limiter=rate_limiter,
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
        gateway=gateway,
        llm_admin=LlmAdmin(
            uow, config=llm_config, clock=clock, known_providers=KNOWN_LLM_PROVIDERS
        ),
        llm_providers=tuple(sorted(chat)),
        catalog=catalog,
        personalization=personalization,
        looks=looks,
        stylist=stylist,
        # In-flight stylist turns finish (and persist) before connections close.
        closers=(stylist.wait_for_turns, *closers),
    )


def _llm_providers(
    settings: Settings,
) -> tuple[dict[str, ChatProvider], dict[str, EmbeddingProvider], list[Closer]]:
    chat: dict[str, ChatProvider] = {}
    embed: dict[str, EmbeddingProvider] = {}
    closers: list[Closer] = []
    if settings.openai_api_key:
        openai_provider = OpenAIProvider(settings.openai_api_key.get_secret_value())
        chat["openai"] = embed["openai"] = openai_provider
        closers.append(openai_provider.aclose)
    if settings.anthropic_api_key:
        anthropic_provider = AnthropicProvider(settings.anthropic_api_key.get_secret_value())
        chat["anthropic"] = anthropic_provider
        closers.append(anthropic_provider.aclose)
    return chat, embed, closers
