from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import openai
import pytest

from stylesense.integrations.tryon.openai_images import OpenAIImageTryOn
from stylesense.modules.tryon.ports import TryOnRejectedError, TryOnRetryableError

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeImages:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def edit(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _provider(
    outcome: object, files: dict[str, httpx.Response] | None = None
) -> tuple[OpenAIImageTryOn, FakeImages]:
    images = FakeImages(outcome)
    served = files or {
        "https://cdn/person.jpg": httpx.Response(
            200, content=PNG, headers={"content-type": "image/jpeg"}
        ),
        "https://cdn/garment.png": httpx.Response(
            200, content=PNG, headers={"content-type": "image/png"}
        ),
    }
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: served.get(str(r.url), httpx.Response(404)))
    )
    provider = OpenAIImageTryOn(
        api_key="k",
        model="configured-image-model",
        quality="medium",
        cost_micro_usd=42_000,
        http=http,
        client=SimpleNamespace(images=images),  # type: ignore[arg-type]
    )
    return provider, images


def _status(
    cls: type[openai.APIStatusError], code: int, error_code: str | None = None
) -> openai.APIStatusError:
    response = httpx.Response(
        code, request=httpx.Request("POST", "https://api.openai.com/v1/images/edits")
    )
    error = cls("refused", response=response, body={"code": error_code})
    error.code = error_code
    return error


async def render(provider: OpenAIImageTryOn) -> object:
    return await provider.render(
        person_url="https://cdn/person.jpg",
        garment_url="https://cdn/garment.png",
        idempotency_key="job-1",
    )


async def test_sends_both_photos_with_the_configured_model_and_returns_a_data_uri() -> None:
    provider, images = _provider(SimpleNamespace(data=[SimpleNamespace(b64_json="QUJD")]))

    result = await render(provider)

    call = images.calls[0]
    assert call["model"] == "configured-image-model"
    assert [f[0] for f in call["image"]] == ["person.jpeg", "garment.png"]
    assert call["input_fidelity"] is openai.omit  # only sent when the model supports it
    assert call["user"] == "job-1"
    assert result.image_url == "data:image/png;base64,QUJD"  # type: ignore[attr-defined]
    assert result.cost_micro_usd == 42_000  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "error",
    [
        _status(openai.RateLimitError, 429),
        _status(openai.InternalServerError, 500),
        _status(openai.APIStatusError, 503),
        openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com")),
    ],
)
async def test_busy_or_down_is_worth_retrying(error: Exception) -> None:
    provider, _ = _provider(error)

    with pytest.raises(TryOnRetryableError):
        await render(provider)


@pytest.mark.parametrize(
    "error",
    [
        _status(openai.BadRequestError, 400, "moderation_blocked"),
        _status(openai.APIStatusError, 403),
    ],
)
async def test_refusals_are_final(error: Exception) -> None:
    provider, _ = _provider(error)

    with pytest.raises(TryOnRejectedError):
        await render(provider)


async def test_an_empty_answer_is_retried() -> None:
    provider, _ = _provider(SimpleNamespace(data=[]))

    with pytest.raises(TryOnRetryableError):
        await render(provider)


@pytest.mark.parametrize(
    ("garment", "expected"),
    [
        (httpx.Response(404), TryOnRejectedError),
        (httpx.Response(503), TryOnRetryableError),
        (
            httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
            TryOnRejectedError,
        ),
    ],
)
async def test_photo_downloads_are_checked_before_paying(
    garment: httpx.Response, expected: type[Exception]
) -> None:
    files = {
        "https://cdn/person.jpg": httpx.Response(
            200, content=PNG, headers={"content-type": "image/jpeg"}
        ),
        "https://cdn/garment.png": garment,
    }
    provider, images = _provider(SimpleNamespace(data=[SimpleNamespace(b64_json="QUJD")]), files)

    with pytest.raises(expected):
        await render(provider)
    assert images.calls == []  # nothing sent to the paid API
    await provider.aclose()
