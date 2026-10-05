"""LLMGateway: the only way the app talks to AI providers.

run(task) ─► config (hot-reloaded) ─► input size cap ─► per-user quota ─► response cache
         ─► single-flight ─► daily budget ─► for each target (primary, then fallbacks):
               skip if no provider / no price / breaker open
               bulkhead ─► call with timeout + retries (backoff, Retry-After) ─► validate JSON
               ─► one repair attempt ─► success: record usage + cost, cache, return
         ─► nothing worked: AIUnavailableError (callers degrade to rule-based behaviour)
"""

import asyncio
import hashlib
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.trace import Tracer
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from stylesense.ai.gateway.budget import DailyBudget
from stylesense.ai.gateway.config import ConfigSnapshot, ConfigStore, TaskConfig
from stylesense.ai.gateway.exceptions import (
    AIInputTooLargeError,
    AIQuotaExceededError,
    AIUnavailableError,
)
from stylesense.ai.gateway.metrics import GatewayMetrics
from stylesense.ai.gateway.models import LlmUsage
from stylesense.ai.gateway.pricing import ModelPrice
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.ai.gateway.tokens import estimate_tokens
from stylesense.ai.gateway.types import (
    ChatCall,
    ChatOutput,
    ChatProvider,
    EmbeddingProvider,
    Message,
    ModelRef,
    ProviderError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    Usage,
)
from stylesense.guards.bulkhead import Bulkhead
from stylesense.guards.circuit_breaker import CircuitBreaker
from stylesense.guards.rate_limit import DEFAULT_POLICIES, RateLimiter
from stylesense.guards.singleflight import SingleFlight
from stylesense.infra.database import UnitOfWork
from stylesense.platform.clock import Clock
from stylesense.platform.ids import new_id
from stylesense.platform.observability.redaction import scrub

logger = structlog.get_logger(__name__)

_EMBED_TASK = "embed"
_MAX_ERROR_CHARS = 300
_REPAIR_PROMPT = (
    "That reply was invalid for the required schema: {errors}. "
    "Reply again with only valid JSON matching the schema."
)


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    daily_budget_micro_usd: int
    budget_alert_ratio: float
    max_attempts: int
    breaker_threshold: int
    breaker_window_s: float
    breaker_cooldown_s: float
    max_concurrency: int
    max_queued: int
    max_retry_after_s: float = 5.0  # longer waits fail over instead
    base_backoff_s: float = 0.5


class _TargetFailedError(Exception):
    def __init__(self, reason: str, *, trips_breaker: bool) -> None:
        super().__init__(reason)
        self.trips_breaker = trips_breaker


@dataclass(slots=True)
class _Attempt:
    task: str
    ref: ModelRef
    price: ModelPrice
    prompt_version: str
    call_id: uuid.UUID
    user_id: uuid.UUID | None


class LLMGateway:
    def __init__(
        self,
        *,
        config: ConfigStore,
        chat_providers: Mapping[str, ChatProvider],
        embedding_providers: Mapping[str, EmbeddingProvider],
        redis: Redis,
        clock: Clock,
        uow: Callable[[], UnitOfWork],
        rate_limiter: RateLimiter,
        settings: GatewaySettings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        tracer: Tracer | None = None,
        metrics: GatewayMetrics | None = None,
    ) -> None:
        self.config = config
        self.budget = DailyBudget(
            redis,
            clock,
            cap_micro_usd=settings.daily_budget_micro_usd,
            alert_ratio=settings.budget_alert_ratio,
        )
        self._chat = chat_providers
        self._embed = embedding_providers
        self._redis = redis
        self._clock = clock
        self._uow = uow
        self._limiter = rate_limiter
        self._s = settings
        self._sleep = sleep
        self._tracer = tracer or trace.NoOpTracer()
        self._metrics = metrics
        self._flight: SingleFlight[str] = SingleFlight()
        self._breakers: dict[ModelRef, CircuitBreaker] = {}
        self._bulkheads = {
            name: Bulkhead(
                f"llm.{name}",
                max_concurrent=settings.max_concurrency,
                max_waiting=settings.max_queued,
            )
            for name in ("chat", "embed")
        }

    # ---------- chat ----------

    async def run[I: BaseModel, O: BaseModel](
        self, spec: TaskSpec[I, O], payload: I, *, user_id: uuid.UUID | None = None
    ) -> O:
        snapshot = await self.config.snapshot()
        cfg = snapshot.tasks.get(spec.name)
        if cfg is None or not cfg.enabled or not cfg.targets:
            raise AIUnavailableError(f"task '{spec.name}' is not configured or disabled")
        messages = spec.messages(payload)
        if estimate_tokens(messages) > cfg.max_input_tokens:
            raise AIInputTooLargeError
        if user_id is not None:
            await self._check_quota(user_id)

        if cfg.cache_ttl_s <= 0:
            text = await self._route(spec, cfg, snapshot, messages, user_id)
        else:
            key = self._cache_key(spec, payload)
            text = await self._cached(
                spec=spec, cfg=cfg, snapshot=snapshot, messages=messages, user_id=user_id, key=key
            )
        return spec.output_type.model_validate_json(text)

    async def _cached(
        self,
        *,
        spec: TaskSpec[Any, Any],
        cfg: TaskConfig,
        snapshot: ConfigSnapshot,
        messages: tuple[Message, ...],
        user_id: uuid.UUID | None,
        key: str,
    ) -> str:
        if (hit := await self._cache_get(key)) is not None:
            await self._record_cache_hit(spec, cfg.targets[0], user_id)
            return hit

        async def compute() -> str:
            text = await self._route(spec, cfg, snapshot, messages, user_id)
            await self._cache_set(key, text, cfg.cache_ttl_s)
            return text

        # Concurrent identical requests share one provider call.
        return await self._flight.do(key, compute)

    async def _route(
        self,
        spec: TaskSpec[Any, Any],
        cfg: TaskConfig,
        snapshot: ConfigSnapshot,
        messages: tuple[Message, ...],
        user_id: uuid.UUID | None,
    ) -> str:
        await self.budget.check()
        call = ChatCall(
            messages=messages,
            json_schema=spec.output_type.model_json_schema(),
            schema_name=spec.output_type.__name__,
            max_output_tokens=cfg.max_output_tokens,
            temperature=cfg.temperature,
            timeout_s=cfg.timeout_s,
            cache_key=f"{spec.name}:{spec.prompt_version}",
        )
        call_id = new_id()
        for ref in cfg.targets:
            provider, price = self._chat.get(ref.provider), snapshot.prices.get(ref)
            if provider is None or price is None:
                logger.error(
                    "llm_target_unusable",
                    task=spec.name,
                    model=str(ref),
                    reason="no provider" if provider is None else "no price",
                )
                continue
            breaker = self._breaker(ref)
            if not await breaker.allow():
                logger.info(
                    "llm_target_skipped", task=spec.name, model=str(ref), reason="breaker_open"
                )
                continue
            attempt = _Attempt(spec.name, ref, price, spec.prompt_version, call_id, user_id)
            try:
                async with self._bulkheads[spec.bulkhead].slot():
                    text = await self._serve(spec, provider, call, attempt, breaker)
            except _TargetFailedError as failure:
                if failure.trips_breaker:
                    await breaker.record_failure()
                logger.warning(
                    "llm_target_failed", task=spec.name, model=str(ref), reason=str(failure)
                )
                continue
            return text
        raise AIUnavailableError(f"no model could serve '{spec.name}'")

    async def _serve(
        self,
        spec: TaskSpec[Any, Any],
        provider: ChatProvider,
        call: ChatCall,
        attempt: _Attempt,
        breaker: CircuitBreaker,
    ) -> str:
        output, _, latency = await self._with_retries(
            attempt, lambda: self._chat_once(provider, attempt.ref, call)
        )
        await breaker.record_success()
        if (errors := _validation_errors(spec, output.text)) is None:
            await self._record(attempt, output.usage, latency, "ok")
            return output.text

        await self._record(attempt, output.usage, latency, "invalid_output", error=errors)
        repair = ChatCall(
            messages=(
                *call.messages,
                Message("assistant", output.text),
                Message("user", _REPAIR_PROMPT.format(errors=errors)),
            ),
            json_schema=call.json_schema,
            schema_name=call.schema_name,
            max_output_tokens=call.max_output_tokens,
            temperature=call.temperature,
            timeout_s=call.timeout_s,
            cache_key=call.cache_key,
        )
        repaired, _, latency = await self._with_retries(
            attempt, lambda: self._chat_once(provider, attempt.ref, repair)
        )
        if (errors := _validation_errors(spec, repaired.text)) is None:
            await self._record(attempt, repaired.usage, latency, "ok")
            return repaired.text
        await self._record(attempt, repaired.usage, latency, "invalid_output", error=errors)
        raise _TargetFailedError("invalid output after repair", trips_breaker=False)

    async def _chat_once(
        self, provider: ChatProvider, ref: ModelRef, call: ChatCall
    ) -> tuple[ChatOutput, Usage]:
        with self._tracer.start_as_current_span(f"chat {ref.model}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.system", ref.provider)
            span.set_attribute("gen_ai.request.model", ref.model)
            async with asyncio.timeout(call.timeout_s):
                output = await provider.chat(ref.model, call)
            span.set_attribute("gen_ai.usage.input_tokens", output.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output.usage.output_tokens)
        return output, output.usage

    # ---------- embeddings ----------

    async def embed(
        self,
        ref: ModelRef,
        texts: Sequence[str],
        *,
        user_id: uuid.UUID | None = None,
        timeout_s: float = 30,
    ) -> list[list[float]]:
        snapshot = await self.config.snapshot()
        provider, price = self._embed.get(ref.provider), snapshot.prices.get(ref)
        if provider is None or price is None:
            raise AIUnavailableError(f"embedding model {ref} has no provider or no price")
        await self.budget.check()
        breaker = self._breaker(ref)
        if not await breaker.allow():
            raise AIUnavailableError(f"embedding model {ref} is failing")
        attempt = _Attempt(_EMBED_TASK, ref, price, "n/a", new_id(), user_id)

        async def once() -> tuple[list[list[float]], Usage]:
            with self._tracer.start_as_current_span(f"embeddings {ref.model}") as span:
                span.set_attribute("gen_ai.operation.name", "embeddings")
                span.set_attribute("gen_ai.system", ref.provider)
                span.set_attribute("gen_ai.request.model", ref.model)
                async with asyncio.timeout(timeout_s):
                    return await provider.embed(ref.model, texts, timeout_s=timeout_s)

        try:
            async with self._bulkheads["embed"].slot():
                vectors, usage, latency = await self._with_retries(attempt, once)
        except _TargetFailedError as failure:
            if failure.trips_breaker:
                await breaker.record_failure()
            raise AIUnavailableError(f"embedding failed: {failure}") from failure
        await breaker.record_success()
        await self._record(attempt, usage, latency, "ok")
        return vectors

    # ---------- shared retry loop ----------

    async def _with_retries[T](
        self, attempt: _Attempt, once: Callable[[], Awaitable[tuple[T, Usage]]]
    ) -> tuple[T, Usage, int]:
        for number in range(1, self._s.max_attempts + 1):
            started = time.perf_counter()
            try:
                result, usage = await once()
            except TimeoutError:
                error: ProviderError = ProviderUnavailableError("timeout")
            except ProviderError as exc:
                error = exc
            except Exception as exc:  # adapter bugs must not escape as 500s
                logger.exception("llm_adapter_error", model=str(attempt.ref))
                error = ProviderUnavailableError(type(exc).__name__)
            else:
                return result, usage, _elapsed_ms(started)

            await self._record(
                attempt, Usage(), _elapsed_ms(started), "error", error=_describe(error)
            )
            if not error.retryable:
                raise _TargetFailedError(_describe(error), trips_breaker=False)
            if number == self._s.max_attempts:
                raise _TargetFailedError("retries exhausted", trips_breaker=True)
            delay = self._delay(number, error)
            if delay > self._s.max_retry_after_s:
                raise _TargetFailedError(f"asked to wait {delay:.0f}s", trips_breaker=True)
            await self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def _delay(self, attempt: int, error: ProviderError) -> float:
        if isinstance(error, ProviderRateLimitedError) and error.retry_after_s is not None:
            return error.retry_after_s
        # Exponential backoff with jitter so instances don't retry in lockstep.
        backoff = self._s.base_backoff_s * float(2 ** (attempt - 1))
        return backoff * (1 + 0.25 * random.random())  # noqa: S311

    # ---------- bookkeeping ----------

    async def _record(
        self,
        attempt: _Attempt,
        usage: Usage,
        latency_ms: int,
        outcome: str,
        *,
        error: str | None = None,
    ) -> None:
        cost = attempt.price.cost_micro_usd(usage)
        await self.budget.add(cost)
        if self._metrics:
            self._metrics.observe(
                task=attempt.task,
                model=str(attempt.ref),
                outcome=outcome,
                usage=usage,
                cost_micro_usd=cost,
                latency_ms=latency_ms,
            )
        try:
            async with self._uow() as uow:
                uow.session.add(
                    LlmUsage(
                        call_id=attempt.call_id,
                        task=attempt.task,
                        provider=attempt.ref.provider,
                        model=attempt.ref.model,
                        user_id=attempt.user_id,
                        prompt_version=attempt.prompt_version,
                        input_tokens=usage.input_tokens,
                        cached_input_tokens=usage.cached_input_tokens,
                        output_tokens=usage.output_tokens,
                        cost_micro_usd=cost,
                        latency_ms=latency_ms,
                        outcome=outcome,
                        error=error,
                    )
                )
        except Exception:  # the ledger must never break a user request
            logger.exception("llm_usage_record_failed", task=attempt.task)

    async def _record_cache_hit(
        self, spec: TaskSpec[Any, Any], ref: ModelRef, user_id: uuid.UUID | None
    ) -> None:
        free = ModelPrice(*(0,) * 3)  # type: ignore[arg-type]
        await self._record(
            _Attempt(spec.name, ref, free, spec.prompt_version, new_id(), user_id),
            Usage(),
            0,
            "cache_hit",
        )

    async def _check_quota(self, user_id: uuid.UUID) -> None:
        decision = await self._limiter.hit(DEFAULT_POLICIES["ai.per_user"], f"user:{user_id}")
        if not decision.allowed:
            raise AIQuotaExceededError(headers={"Retry-After": str(decision.retry_after_s)})

    def _breaker(self, ref: ModelRef) -> CircuitBreaker:
        if ref not in self._breakers:
            self._breakers[ref] = CircuitBreaker(
                self._redis,
                self._clock,
                name=f"llm:{ref}",
                failure_threshold=self._s.breaker_threshold,
                window_s=self._s.breaker_window_s,
                cooldown_s=self._s.breaker_cooldown_s,
            )
        return self._breakers[ref]

    @staticmethod
    def _cache_key(spec: TaskSpec[Any, Any], payload: BaseModel) -> str:
        digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        return f"llm:cache:{spec.name}:{spec.prompt_version}:{digest}"

    async def _cache_get(self, key: str) -> str | None:
        try:
            raw = await self._redis.get(key)
        except RedisError:
            return None
        return raw if isinstance(raw, str) else None

    async def _cache_set(self, key: str, text: str, ttl_s: int) -> None:
        try:
            await self._redis.set(key, text, ex=ttl_s)
        except RedisError as exc:
            logger.warning("llm_cache_write_failed", error=type(exc).__name__)


def _validation_errors(spec: TaskSpec[Any, Any], text: str) -> str | None:
    try:
        spec.output_type.model_validate_json(text)
    except ValidationError as exc:
        return "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors()
        )[:_MAX_ERROR_CHARS]
    return None


def _describe(error: Exception) -> str:
    detail = str(error)
    text = f"{type(error).__name__}: {detail}" if detail else type(error).__name__
    return str(scrub(text))[:_MAX_ERROR_CHARS]


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
