import json
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
import pytest

from stylesense.ai.gateway.types import (
    ChatCall,
    Message,
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderUnavailableError,
)
from stylesense.integrations.llm.anthropic_provider import AnthropicProvider
from stylesense.integrations.llm.errors import retry_after_s
from stylesense.integrations.llm.openai_provider import OpenAIProvider

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
CALL = ChatCall(
    messages=(Message("system", "Be brief."), Message("user", "<input>{}</input>")),
    json_schema=SCHEMA,
    schema_name="Answer",
    max_output_tokens=200,
    temperature=0.3,
    timeout_s=5,
    cache_key="task:v1",
)

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    @property
    def body(self) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(self.requests[-1].content)
        return parsed


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openai(handler: Handler) -> OpenAIProvider:
    return OpenAIProvider("sk-test", base_url="https://api.test/v1", http_client=_client(handler))


def _anthropic(handler: Handler) -> AnthropicProvider:
    return AnthropicProvider(
        "sk-ant-test", base_url="https://api.test", http_client=_client(handler)
    )


OPENAI_OK = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 0,
    "model": "m",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "logprobs": None,
            "message": {"role": "assistant", "content": '{"ok": true}', "refusal": None},
        }
    ],
    "usage": {
        "prompt_tokens": 1200,
        "completion_tokens": 30,
        "total_tokens": 1230,
        "prompt_tokens_details": {"cached_tokens": 1024},
    },
}
ANTHROPIC_OK = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "m",
    "content": [{"type": "text", "text": '{"ok": true}'}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 50,
        "output_tokens": 12,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 0,
    },
}


# ---------- OpenAI ----------


async def test_openai_sends_schema_limits_and_cache_key() -> None:
    rec = Recorder(httpx.Response(200, json=OPENAI_OK))

    output = await _openai(rec).chat("gpt-test", CALL)

    body = rec.body
    assert body["model"] == "gpt-test"
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert body["max_completion_tokens"] == 200
    assert body["temperature"] == 0.3
    assert body["prompt_cache_key"] == "task:v1"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert output.text == '{"ok": true}'
    assert (
        output.usage.input_tokens,
        output.usage.cached_input_tokens,
        output.usage.output_tokens,
    ) == (1200, 1024, 30)


async def test_openai_omits_temperature_when_unset() -> None:
    rec = Recorder(httpx.Response(200, json=OPENAI_OK))
    call = ChatCall(CALL.messages, None, "x", 100, None, 5)

    await _openai(rec).chat("m", call)

    assert "temperature" not in rec.body
    assert "response_format" not in rec.body


async def test_openai_refusal_is_rejected() -> None:
    refusal = json.loads(json.dumps(OPENAI_OK))
    refusal["choices"][0]["message"].update(content=None, refusal="I can't help with that")

    with pytest.raises(ProviderRejectedError):
        await _openai(Recorder(httpx.Response(200, json=refusal))).chat("m", CALL)


@pytest.mark.parametrize(
    ("status", "headers", "error", "retry_after"),
    [
        (429, {"retry-after": "2"}, ProviderRateLimitedError, 2.0),
        (429, {"retry-after-ms": "1500"}, ProviderRateLimitedError, 1.5),
        (500, {}, ProviderUnavailableError, None),
        (503, {}, ProviderUnavailableError, None),
        (400, {}, ProviderRejectedError, None),
        (401, {}, ProviderRejectedError, None),
        (404, {}, ProviderRejectedError, None),
    ],
)
async def test_openai_errors_are_normalised(
    status: int, headers: dict[str, str], error: type[Exception], retry_after: float | None
) -> None:
    rec = Recorder(
        httpx.Response(status, headers=headers, json={"error": {"message": "x", "type": "t"}})
    )

    with pytest.raises(error) as caught:
        await _openai(rec).chat("m", CALL)
    if retry_after is not None:
        assert caught.value.retry_after_s == retry_after  # type: ignore[attr-defined]
    assert len(rec.requests) == 1  # the SDK must not retry on its own


async def test_openai_network_failure_is_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError):
        await _openai(Recorder(httpx.ConnectError("refused"))).chat("m", CALL)


async def test_openai_embeddings_are_returned_in_input_order() -> None:
    body = {
        "object": "list",
        "model": "e",
        "data": [
            {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
            {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
        ],
        "usage": {"prompt_tokens": 7, "total_tokens": 7},
    }

    vectors, usage = await _openai(Recorder(httpx.Response(200, json=body))).embed(
        "e", ["a", "b"], timeout_s=5
    )

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert usage.input_tokens == 7


# ---------- Anthropic ----------


async def test_anthropic_separates_system_and_requests_json() -> None:
    rec = Recorder(httpx.Response(200, json=ANTHROPIC_OK))

    output = await _anthropic(rec).chat("claude-test", CALL)

    body = rec.body
    assert body["system"][0]["text"] == "Be brief."
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert body["max_tokens"] == 200
    assert "temperature" not in body  # removed from the 1.x Messages API
    assert output.text == '{"ok": true}'


async def test_anthropic_counts_cached_input_inside_total_input() -> None:
    output = await _anthropic(Recorder(httpx.Response(200, json=ANTHROPIC_OK))).chat("m", CALL)

    assert (
        output.usage.input_tokens,
        output.usage.cached_input_tokens,
        output.usage.output_tokens,
    ) == (950, 900, 12)


async def test_anthropic_refusal_is_rejected() -> None:
    refusal = {**ANTHROPIC_OK, "stop_reason": "refusal"}

    with pytest.raises(ProviderRejectedError):
        await _anthropic(Recorder(httpx.Response(200, json=refusal))).chat("m", CALL)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, ProviderRateLimitedError),
        (529, ProviderUnavailableError),
        (500, ProviderUnavailableError),
        (400, ProviderRejectedError),
        (401, ProviderRejectedError),
    ],
)
async def test_anthropic_errors_are_normalised(status: int, error: type[Exception]) -> None:
    body = {"type": "error", "error": {"type": "x", "message": "y"}}
    rec = Recorder(httpx.Response(status, json=body))

    with pytest.raises(error):
        await _anthropic(rec).chat("m", CALL)
    assert len(rec.requests) == 1


# ---------- Retry-After parsing ----------


def test_retry_after_accepts_http_dates() -> None:
    response = httpx.Response(
        429,
        headers={
            "retry-after": "Mon, 05 Oct 2026 10:00:30 GMT",
            "date": "Mon, 05 Oct 2026 10:00:00 GMT",
        },
    )

    assert retry_after_s(response) == 30.0


@pytest.mark.parametrize("headers", [{}, {"retry-after": "soon"}, {"retry-after-ms": "x"}])
def test_unparseable_retry_after_is_ignored(headers: dict[str, str]) -> None:
    assert retry_after_s(httpx.Response(429, headers=headers)) is None
