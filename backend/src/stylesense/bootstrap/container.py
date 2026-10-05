from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

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
from stylesense.integrations.media.cloudinary import CloudinaryStore
from stylesense.integrations.tryon.fake import FakeTryOnProvider
from stylesense.integrations.tryon.openai_images import OpenAIImageTryOn
from stylesense.modules.auth.ports import IdentityVerifier
from stylesense.modules.auth.service import AuthService
from stylesense.modules.auth.tokens import AccessTokenCodec
from stylesense.modules.boards.service import BoardsService
from stylesense.modules.catalog.ports import Embedder
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.looks.service import LookService
from stylesense.modules.personalization.service import (
    PersonalizationMetrics,
    PersonalizationService,
)
from stylesense.modules.polls.service import PollsService
from stylesense.modules.sharing.service import SharingService
from stylesense.modules.stylist.flows.demo import DemoFlow
from stylesense.modules.stylist.flows.style_dna import StyleDnaFlow
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.tryon.ports import TryOnProvider
from stylesense.modules.tryon.service import MediaMetrics, TryOnService
from stylesense.modules.uploads.ports import MediaStore
from stylesense.modules.uploads.service import UploadsService
from stylesense.modules.users.service import UsersService
from stylesense.platform.clock import Clock, SystemClock
from stylesense.platform.config import Settings
from stylesense.platform.health import HealthCheck
from stylesense.platform.slugs import Pseudonymizer

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
    boards: BoardsService
    sharing: SharingService
    polls: PollsService
    uploads: UploadsService
    tryon: TryOnService
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
    media_store: MediaStore | None = None,
    tryon_provider: TryOnProvider | None = None,
) -> Container:
    """External services are injectable so tests can replace them with fakes
    (Google sign-in, image storage, the try-on vendor)."""
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
    store = media_store or _media_store(settings)
    if isinstance(store, CloudinaryStore):
        closers.append(store.aclose)
    uploads = UploadsService(
        uow,
        store=store,
        limiter=rate_limiter,
        clock=clock,
        ttl=timedelta(hours=settings.media_ttl_hours),
        daily_limit=settings.upload_daily_limit,
        photo_search_daily_limit=settings.photo_search_daily_limit,
    )
    tryon = TryOnService(
        uow,
        uploads=uploads,
        catalog=catalog,
        store=store,
        provider=tryon_provider or _tryon_provider(settings),
        outbox=outbox,
        clock=clock,
        ttl=timedelta(hours=settings.media_ttl_hours),
        daily_limit=settings.tryon_daily_limit,
        global_daily_limit=settings.tryon_global_daily_limit,
        metrics=MediaMetrics(telemetry.registry) if telemetry.registry else None,
    )
    boards = BoardsService(uow, catalog=catalog, clock=clock)
    sharing = SharingService(
        uow, catalog=catalog, boards=boards, clock=clock, public_url=settings.public_web_url
    )
    polls = PollsService(
        uow,
        catalog=catalog,
        limiter=rate_limiter,
        hasher=Pseudonymizer.derive(settings.jwt_secret.get_secret_value(), "poll-voters"),
        clock=clock,
        public_url=settings.public_web_url,
    )
    stylist = StylistService(
        uow,
        flows={
            "stylist": StylistFlow(catalog, gateway, personalization, looks, uploads),
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
        boards=boards,
        sharing=sharing,
        polls=polls,
        uploads=uploads,
        tryon=tryon,
        stylist=stylist,
        # In-flight stylist turns finish (and persist) before connections close.
        closers=(stylist.wait_for_turns, *closers),
    )


def _media_store(settings: Settings) -> MediaStore | None:
    if not settings.media_configured:
        return None  # photo search and try-on report "unavailable"; everything else works
    return CloudinaryStore(
        cloud_name=settings.cloudinary_cloud_name or "",
        api_key=settings.cloudinary_api_key or "",
        api_secret=settings.cloudinary_api_secret.get_secret_value()
        if settings.cloudinary_api_secret
        else "",
        upload_preset=settings.cloudinary_upload_preset,
    )


def _tryon_provider(settings: Settings) -> TryOnProvider | None:
    if settings.tryon_provider == "fake":
        return FakeTryOnProvider()
    if (
        settings.tryon_provider == "openai"
        and settings.openai_api_key
        and settings.tryon_openai_model
    ):
        return OpenAIImageTryOn(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.tryon_openai_model,
            quality=settings.tryon_openai_quality,
            cost_micro_usd=settings.tryon_cost_micro_usd,
        )
    return None


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
