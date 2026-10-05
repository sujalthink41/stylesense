"""Circuit breaker with state in Redis, so every API/worker instance sees the same breaker.

closed ──(threshold failures within window)──► open ──(cooldown)──► half-open: one probe
  ▲                                                                     │
  └──────────── probe succeeds ◄────────────────────────────────────────┘  probe fails → open
"""

import uuid
from enum import StrEnum

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        redis: Redis,
        clock: Clock,
        *,
        name: str,
        failure_threshold: int,
        window_s: float,
        cooldown_s: float,
    ) -> None:
        self._redis = redis
        self._clock = clock
        self.name = name
        self._threshold = failure_threshold
        self._window_ms = round(window_s * 1000)
        self._cooldown_ms = round(cooldown_s * 1000)
        prefix = f"cb:{name}"
        self._failures_key = f"{prefix}:failures"
        self._open_until_key = f"{prefix}:open_until"
        self._probe_key = f"{prefix}:probe"

    async def allow(self) -> bool:
        try:
            open_until = await self._open_until()
            if open_until is None:
                return True
            if self._now_ms() < open_until:
                return False
            # Half-open: the first caller after cooldown wins the single probe slot.
            return bool(await self._redis.set(self._probe_key, "1", nx=True, px=self._cooldown_ms))
        except RedisError as exc:
            return self._fail_open(exc)

    async def record_success(self) -> None:
        try:
            await self._redis.delete(self._failures_key, self._open_until_key, self._probe_key)
        except RedisError as exc:
            self._fail_open(exc)

    async def record_failure(self) -> None:
        try:
            open_until = await self._open_until()
            if open_until is not None and self._now_ms() >= open_until:
                await self._trip()  # the half-open probe failed
                return
            now = self._now_ms()
            # Exact sliding window on the injected clock (not Redis TTLs): failures older than
            # the window drop out, so occasional errors never add up to an outage.
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zadd(self._failures_key, {f"{now}:{uuid.uuid4().hex}": now})
                pipe.zremrangebyscore(self._failures_key, "-inf", now - self._window_ms)
                pipe.zcard(self._failures_key)
                pipe.pexpire(self._failures_key, self._window_ms * 2)
                _, _, failures, _ = await pipe.execute()
            if failures >= self._threshold:
                await self._trip()
        except RedisError as exc:
            self._fail_open(exc)

    async def state(self) -> BreakerState:
        try:
            open_until = await self._open_until()
        except RedisError:
            return BreakerState.CLOSED
        if open_until is None:
            return BreakerState.CLOSED
        return BreakerState.OPEN if self._now_ms() < open_until else BreakerState.HALF_OPEN

    async def _trip(self) -> None:
        await self._redis.set(self._open_until_key, self._now_ms() + self._cooldown_ms)
        await self._redis.delete(self._failures_key, self._probe_key)
        logger.warning("circuit_opened", breaker=self.name, cooldown_ms=self._cooldown_ms)

    async def _open_until(self) -> int | None:
        raw = await self._redis.get(self._open_until_key)
        return int(raw) if raw is not None else None

    def _now_ms(self) -> int:
        return int(self._clock.now().timestamp() * 1000)

    def _fail_open(self, exc: Exception) -> bool:
        # A breaker we can't read must not block calls; it only ever protects.
        logger.warning("circuit_breaker_unavailable", breaker=self.name, error=type(exc).__name__)
        return True
