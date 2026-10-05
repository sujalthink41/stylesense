import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from stylesense.ai.gateway.exceptions import AIBudgetExhaustedError
from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)

_KEY_TTL_S = 3 * 86_400


class DailyBudget:
    """Global AI spend cap per UTC day, shared by every instance via Redis (integer micro-USD)."""

    def __init__(
        self, redis: Redis, clock: Clock, *, cap_micro_usd: int, alert_ratio: float
    ) -> None:
        self._redis = redis
        self._clock = clock
        self._cap = cap_micro_usd
        self._alert_at = int(cap_micro_usd * alert_ratio)

    async def check(self) -> None:
        spent = await self.spent_today()
        if spent >= self._cap:
            raise AIBudgetExhaustedError(f"daily AI budget used ({spent} of {self._cap} micro-USD)")

    async def add(self, cost_micro_usd: int) -> None:
        if cost_micro_usd <= 0:
            return
        key = self._key()
        try:
            total = await self._redis.incrby(key, cost_micro_usd)
            await self._redis.expire(key, _KEY_TTL_S)
            if total >= self._alert_at and await self._redis.set(
                f"{key}:alerted", "1", nx=True, ex=_KEY_TTL_S
            ):
                logger.warning("ai_budget_threshold_reached", spent=total, cap=self._cap)
        except RedisError as exc:
            logger.warning("ai_budget_record_failed", error=type(exc).__name__, cost=cost_micro_usd)

    async def spent_today(self) -> int:
        try:
            raw = await self._redis.get(self._key())
        except RedisError as exc:
            # Fail open: a cache outage shouldn't switch AI off; the Postgres ledger still counts.
            logger.warning("ai_budget_unavailable", error=type(exc).__name__)
            return 0
        return int(raw) if raw is not None else 0

    def _key(self) -> str:
        return f"llm:spend:{self._clock.now().date().isoformat()}"
