"""Redis rate limiting: exact sliding-window log and token bucket, atomic via Lua.

Time comes from the injected clock (not Redis), so behaviour is deterministic in tests.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from stylesense.platform.clock import Clock
from stylesense.platform.errors import AppError

logger = structlog.get_logger(__name__)


class Algorithm(StrEnum):
    SLIDING_WINDOW = "sliding_window"  # exact: never more than `limit` in any window
    TOKEN_BUCKET = "token_bucket"  # noqa: S105  # smooth: bursts up to `limit`, refills steadily


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_s: int
    algorithm: Algorithm

    def __post_init__(self) -> None:
        if self.limit < 1 or self.window_s < 1:
            raise ValueError("limit and window_s must be positive")


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_s: int


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    title = "Too many requests"

    @classmethod
    def from_decision(cls, decision: RateLimitDecision) -> Self:
        return cls(
            headers={
                "Retry-After": str(decision.retry_after_s),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": str(decision.remaining),
            }
        )


# Defaults from the spec; an admin-editable store replaces these in CP14.
DEFAULT_POLICIES: dict[str, RateLimitPolicy] = {
    p.name: p
    for p in (
        RateLimitPolicy("api.per_ip", limit=60, window_s=60, algorithm=Algorithm.SLIDING_WINDOW),
        RateLimitPolicy("api.per_user", limit=120, window_s=60, algorithm=Algorithm.SLIDING_WINDOW),
        RateLimitPolicy("ai.per_user", limit=30, window_s=3600, algorithm=Algorithm.TOKEN_BUCKET),
    )
}

# KEYS[1]=log  ARGV: now_ms, window_ms, limit, member → {allowed, remaining, retry_ms}
_WINDOW_SCRIPT = """
local now, window, limit = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[4])
  redis.call('PEXPIRE', KEYS[1], window)
  return {1, limit - count - 1, 0}
end
local oldest = tonumber(redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')[2])
return {0, 0, oldest + window - now}
"""

# KEYS[1]=bucket  ARGV: now_ms, window_ms, capacity → {allowed, remaining, retry_ms}
_BUCKET_SCRIPT = """
local now, window, capacity = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
local rate = capacity / window
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local retry = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry = math.ceil((1 - tokens) / rate)
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('PEXPIRE', KEYS[1], window)
return {allowed, math.floor(tokens), retry}
"""

_SCRIPTS = {Algorithm.SLIDING_WINDOW: _WINDOW_SCRIPT, Algorithm.TOKEN_BUCKET: _BUCKET_SCRIPT}


class RateLimiter:
    def __init__(
        self, redis: Redis, clock: Clock, *, fail_open: bool = True, prefix: str = "rl:"
    ) -> None:
        self._redis = redis
        self._clock = clock
        self._fail_open = fail_open
        self._prefix = prefix

    async def hit(self, policy: RateLimitPolicy, subject: str) -> RateLimitDecision:
        key = f"{self._prefix}{policy.name}:{subject}"
        now_ms = int(self._clock.now().timestamp() * 1000)
        args: list[int | str] = [now_ms, policy.window_s * 1000, policy.limit]
        if policy.algorithm is Algorithm.SLIDING_WINDOW:
            args.append(f"{now_ms}:{uuid.uuid4().hex}")
        try:
            allowed, remaining, retry_ms = await self._redis.eval(
                _SCRIPTS[policy.algorithm], 1, key, *args
            )
        except RedisError as exc:
            # Fail open by default: a cache outage shouldn't take the whole API down.
            logger.warning("rate_limiter_unavailable", policy=policy.name, error=type(exc).__name__)
            return RateLimitDecision(
                allowed=self._fail_open, limit=policy.limit, remaining=0, retry_after_s=1
            )
        return RateLimitDecision(
            allowed=bool(allowed),
            limit=policy.limit,
            remaining=max(0, int(remaining)),
            retry_after_s=max(1, -(-int(retry_ms) // 1000)) if not allowed else 0,
        )
