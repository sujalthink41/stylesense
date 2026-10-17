from typing import ClassVar

from stylesense.platform.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)


class TryOnNotFoundError(NotFoundError):
    code = "tryon_not_found"
    title = "Try-on not found"


class TryOnUnavailableError(ServiceUnavailableError):
    code = "tryon_unavailable"
    title = "Try-on is unavailable right now"


class TryOnQuotaError(AppError):
    status_code: ClassVar[int] = 429
    code: ClassVar[str] = "tryon_daily_limit"
    title: ClassVar[str] = "You've used today's try-ons"

    def __init__(self, *, limit: int, resets_at: str) -> None:
        super().__init__(f"You've used your {limit} try-ons for today. More from {resets_at}.")
        self.extra = {"limit": limit, "resets_at": resets_at}


class TryOnNotRetryableError(ConflictError):
    code = "tryon_not_retryable"
    title = "Only a failed try-on can be retried"
