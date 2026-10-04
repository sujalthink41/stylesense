from redis.asyncio import Redis

from stylesense.platform.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        str(settings.redis_url),
        decode_responses=True,
        socket_timeout=settings.redis_timeout_s,
        socket_connect_timeout=settings.redis_timeout_s,
        health_check_interval=30,
    )
