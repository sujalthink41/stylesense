from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import pytest
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.ai.gateway.config import ConfigStore
from stylesense.ai.gateway.gateway import GatewaySettings, LLMGateway
from stylesense.ai.gateway.models import LlmModel, LlmTaskConfig
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.guards.rate_limit import RateLimiter
from stylesense.infra.database import UnitOfWork, create_session_factory
from stylesense.platform.config import Settings
from tests.fakes.clock import FixedClock
from tests.fakes.llm import FakeChatProvider, FakeEmbeddingProvider, RecordingSleep


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    echo: str
    ok: bool


ECHO = TaskSpec(
    name="test.echo",
    prompt_version="v1",
    instructions="Repeat the input text in `echo` and set ok=true.",
    input_type=EchoIn,
    output_type=EchoOut,
)
GOOD = '{"echo": "hi", "ok": true}'


@dataclass
class Harness:
    gateway: LLMGateway
    provider: FakeChatProvider
    embeddings: FakeEmbeddingProvider
    sleep: RecordingSleep
    clock: FixedClock
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis

    async def configure(
        self,
        targets: list[str],
        *,
        enabled: bool = True,
        cache_ttl_s: int = 0,
        max_input_tokens: int = 2_000,
        timeout_s: float = 5,
        task: str = "test.echo",
    ) -> None:
        async with self.sessions() as s, s.begin():
            await s.execute(delete(LlmTaskConfig).where(LlmTaskConfig.task == task))
            s.add(
                LlmTaskConfig(
                    task=task,
                    targets=targets,
                    temperature=0.2,
                    max_input_tokens=max_input_tokens,
                    max_output_tokens=300,
                    timeout_s=timeout_s,
                    cache_ttl_s=cache_ttl_s,
                    enabled=enabled,
                )
            )
        await self.gateway.config.invalidate()

    async def price(self, ref: str, *, kind: str = "chat") -> None:
        provider, _, model = ref.partition(":")
        async with self.sessions() as s, s.begin():
            s.add(
                LlmModel(
                    provider=provider,
                    model=model,
                    kind=kind,
                    input_usd_per_mtok=Decimal("1.00"),
                    cached_input_usd_per_mtok=Decimal("0.10"),
                    output_usd_per_mtok=Decimal("4.00"),
                )
            )
        await self.gateway.config.invalidate()


@pytest.fixture
async def make_harness(
    engine: AsyncEngine, migrated: None, redis: Redis, settings: Settings
) -> Callable[..., Harness]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE llm_models, llm_task_configs, llm_usage"))
    await redis.flushdb()
    sessions = create_session_factory(engine)

    def build(**overrides: object) -> Harness:
        clock, sleep = FixedClock(), RecordingSleep()
        provider, embeddings = FakeChatProvider("fake"), FakeEmbeddingProvider("fake")
        gateway_settings = GatewaySettings(
            daily_budget_micro_usd=int(overrides.pop("daily_budget_micro_usd", 5_000_000)),  # type: ignore[call-overload]
            max_attempts=3,
            breaker_threshold=3,
            breaker_window_s=30,
            breaker_cooldown_s=60,
            max_concurrency=8,
            max_queued=8,
            budget_alert_ratio=0.8,
        )
        gateway = LLMGateway(
            config=ConfigStore(lambda: UnitOfWork(sessions), redis),
            chat_providers={"fake": provider},
            embedding_providers={"fake": embeddings},
            redis=redis,
            clock=clock,
            uow=lambda: UnitOfWork(sessions),
            rate_limiter=RateLimiter(redis, clock),
            settings=gateway_settings,
            sleep=sleep,
        )
        return Harness(gateway, provider, embeddings, sleep, clock, sessions, redis)

    return build


@pytest.fixture
async def h(make_harness: Callable[..., Harness]) -> Harness:
    harness = make_harness()
    await harness.price("fake:primary")
    await harness.price("fake:backup")
    await harness.configure(["fake:primary", "fake:backup"])
    return harness
