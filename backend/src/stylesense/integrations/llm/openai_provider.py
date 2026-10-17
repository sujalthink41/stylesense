from collections.abc import Sequence
from typing import Any

import httpx2 as httpx
import openai
from openai import AsyncOpenAI

from stylesense.ai.gateway.types import (
    ChatCall,
    ChatOutput,
    Message,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderUnavailableError,
    Usage,
)
from stylesense.integrations.llm.errors import is_retryable_status, retry_after_s


class OpenAIProvider:
    name = "openai"
    supports_prompt_cache_key = True  # OpenAI-only; compatible APIs may reject it

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        # max_retries=0: the gateway owns retries, so we never retry twice on top of each other.
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, max_retries=0, http_client=http_client
        )

    async def aclose(self) -> None:
        await self._client.close()

    def _extra_options(self, model: str) -> dict[str, Any]:
        """Per-provider request options (none for OpenAI itself)."""
        return {}

    async def chat(self, model: str, call: ChatCall) -> ChatOutput:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [_message(m) for m in call.messages],
            "max_completion_tokens": call.max_output_tokens,
            "timeout": call.timeout_s,
            **self._extra_options(model),
        }
        if call.temperature is not None:
            kwargs["temperature"] = call.temperature
        if call.json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": call.schema_name,
                    "schema": call.json_schema,
                    "strict": False,
                },
            }
        if call.cache_key and self.supports_prompt_cache_key:
            kwargs["prompt_cache_key"] = call.cache_key  # groups requests sharing our static prefix
        response = await self._guard(self._client.chat.completions.create(**kwargs))
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise ProviderRejectedError("model refused the request")
        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        return ChatOutput(
            text=choice.message.content or "",
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                cached_input_tokens=(getattr(details, "cached_tokens", None) or 0)
                if details
                else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    async def embed(
        self, model: str, texts: Sequence[str], *, timeout_s: float
    ) -> tuple[list[list[float]], Usage]:
        response = await self._guard(
            self._client.embeddings.create(model=model, input=list(texts), timeout=timeout_s)
        )
        ordered = sorted(response.data, key=lambda d: d.index)
        tokens = response.usage.prompt_tokens if response.usage else 0
        return [list(d.embedding) for d in ordered], Usage(input_tokens=tokens)

    @staticmethod
    async def _guard[T](request: Any) -> Any:
        """Translate SDK errors into the gateway's provider-neutral ones."""
        try:
            return await request
        except openai.RateLimitError as exc:
            raise ProviderRateLimitedError(
                str(exc), retry_after_s=retry_after_s(exc.response)
            ) from exc
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        except openai.APIStatusError as exc:
            if is_retryable_status(exc.status_code):
                raise ProviderUnavailableError(f"HTTP {exc.status_code}") from exc
            raise ProviderRejectedError(f"HTTP {exc.status_code}") from exc


def _message(m: Message) -> dict[str, Any]:
    if not m.images:
        return {"role": m.role, "content": m.content}
    parts: list[dict[str, Any]] = [{"type": "text", "text": m.content}]
    # Low detail: a fixed small token cost, plenty for "what garment is this?".
    parts += [{"type": "image_url", "image_url": {"url": u, "detail": "low"}} for u in m.images]
    return {"role": m.role, "content": parts}
