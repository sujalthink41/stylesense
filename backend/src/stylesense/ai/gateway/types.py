"""Provider-agnostic request/response types and the ports every provider adapter implements."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Self

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
    images: tuple[str, ...] = ()  # image URLs the model should look at (vision tasks)


@dataclass(frozen=True, slots=True)
class ModelRef:
    provider: str
    model: str

    @classmethod
    def parse(cls, ref: str) -> Self:
        provider, sep, model = ref.partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"model ref must look like 'provider:model', got {ref!r}")
        return cls(provider, model)

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True, slots=True)
class ChatCall:
    messages: tuple[Message, ...]
    json_schema: dict[str, Any] | None  # ask for JSON matching this schema
    schema_name: str
    max_output_tokens: int
    temperature: float | None
    timeout_s: float
    cache_key: str | None = None  # provider-side prompt caching hint


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0  # subset of input_tokens served from the provider's cache
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ChatOutput:
    text: str
    usage: Usage


class ChatProvider(Protocol):
    name: str

    async def chat(self, model: str, call: ChatCall) -> ChatOutput: ...


class EmbeddingProvider(Protocol):
    name: str

    async def embed(
        self, model: str, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], Usage]: ...


# ---------- errors raised by adapters (normalised across providers) ----------


class ProviderError(Exception):
    retryable = False


class ProviderRateLimitedError(ProviderError):
    retryable = True

    def __init__(self, message: str = "", *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ProviderUnavailableError(ProviderError):
    """5xx, overload, timeouts, connection failures: worth retrying, then failing over."""

    retryable = True


class ProviderRejectedError(ProviderError):
    """4xx: bad request, auth, unknown model, content filter. Retrying won't help."""
