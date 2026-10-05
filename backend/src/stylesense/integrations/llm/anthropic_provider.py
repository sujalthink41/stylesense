from typing import Any

import anthropic
import httpx2 as httpx
from anthropic import AsyncAnthropic

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


class AnthropicProvider:
    """Chat only: Anthropic has no embeddings API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key, base_url=base_url, max_retries=0, http_client=http_client
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def chat(self, model: str, call: ChatCall) -> ChatOutput:
        system = "\n\n".join(m.content for m in call.messages if m.role == "system")
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": call.max_output_tokens,
            "messages": [_message(m) for m in call.messages if m.role != "system"],
            "timeout": call.timeout_s,
        }
        if system:
            # Cache the static system prompt; it's identical across calls of a task.
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        # No `temperature`: the 1.x Messages API removed sampling controls, so it's ignored here.
        if call.json_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": call.json_schema}
            }
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitedError(
                str(exc), retry_after_s=retry_after_s(exc.response)
            ) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            if is_retryable_status(exc.status_code):  # includes 529 overloaded
                raise ProviderUnavailableError(f"HTTP {exc.status_code}") from exc
            raise ProviderRejectedError(f"HTTP {exc.status_code}") from exc

        if response.stop_reason == "refusal":
            raise ProviderRejectedError("model refused the request")
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        return ChatOutput(
            text=text,
            # Anthropic reports cached tokens separately; we count all input, flagging cached reads.
            usage=Usage(
                input_tokens=usage.input_tokens + cache_read + cache_write,
                cached_input_tokens=cache_read,
                output_tokens=usage.output_tokens,
            ),
        )


def _message(m: Message) -> dict[str, Any]:
    if not m.images:
        return {"role": m.role, "content": m.content}
    blocks: list[dict[str, Any]] = [
        {"type": "image", "source": {"type": "url", "url": u}} for u in m.images
    ]
    return {"role": m.role, "content": [*blocks, {"type": "text", "text": m.content}]}
