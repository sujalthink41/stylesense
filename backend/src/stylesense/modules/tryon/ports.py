from dataclasses import dataclass
from typing import Protocol


class TryOnRetryableError(Exception):
    """Provider busy, timed out or down: try again later."""


class TryOnRejectedError(Exception):
    """The provider refused these images (no person found, unsafe content): don't retry."""


class TryOnExhaustedError(Exception):
    """Our account can't render now (credit used up, key revoked, spend limit hit).
    Retrying only wastes requests: fail at once with a "come back later" message."""


@dataclass(frozen=True, slots=True)
class TryOnResult:
    image_url: str  # where to fetch the rendered image (copied into our storage at once)
    cost_micro_usd: int


class TryOnProvider(Protocol):
    name: str

    async def render(
        self, *, person_url: str, garment_url: str, idempotency_key: str
    ) -> TryOnResult:
        """`idempotency_key` (the job id) lets a provider that supports it charge once even if
        we call twice after a crash."""
        ...
