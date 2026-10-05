"""Virtual try-on with OpenAI image editing: the person photo plus the garment photo in, one
image of the person wearing it out.

The model name, quality and per-image cost come from settings (never hard-coded). The result
comes back as base64; we hand it on as a data URI, which our storage imports directly.
"""

from typing import Literal

import httpx2 as httpx
import openai
from openai import AsyncOpenAI, omit

from stylesense.modules.tryon.ports import TryOnRejectedError, TryOnResult, TryOnRetryableError

PROMPT = (
    "Virtual try-on. Image 1 is a person; image 2 is a garment. Show the same person, with the "
    "same face, body, skin tone, hair, pose and background, wearing exactly the garment from "
    "image 2: keep its colour, pattern, fabric and cut. Replace only the clothing it covers; "
    "keep everything else unchanged. Photorealistic, natural fit and lighting."
)
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class OpenAIImageTryOn:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        quality: Literal["low", "medium", "high"],
        input_fidelity: Literal["low", "high"] | None = None,
        cost_micro_usd: int,
        timeout_s: float = 150,
        http: httpx.AsyncClient | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(api_key=api_key, max_retries=0)
        self._http = http or httpx.AsyncClient(timeout=20, follow_redirects=True)
        self._model = model
        self._quality = quality
        self._fidelity = input_fidelity
        self._cost = cost_micro_usd
        self._timeout = timeout_s

    async def render(
        self, *, person_url: str, garment_url: str, idempotency_key: str
    ) -> TryOnResult:
        person = await self._download(person_url, "person")
        garment = await self._download(garment_url, "garment")
        try:
            result = await self._client.images.edit(
                model=self._model,
                image=[person, garment],
                prompt=PROMPT,
                size="1024x1536",
                quality=self._quality,
                input_fidelity=self._fidelity or omit,  # only some models accept it
                n=1,
                stream=False,
                user=idempotency_key,  # lets abuse monitoring group a job's calls
                timeout=self._timeout,
            )
        except (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        ) as e:
            raise TryOnRetryableError(type(e).__name__) from e
        except openai.BadRequestError as e:
            # Safety refusals and unusable photos: retrying won't change the answer.
            raise TryOnRejectedError(e.code or "bad_request") from e
        except openai.APIStatusError as e:
            if e.status_code >= 500:  # noqa: PLR2004
                raise TryOnRetryableError(str(e.status_code)) from e
            raise TryOnRejectedError(str(e.status_code)) from e
        data = result.data[0].b64_json if result.data else None
        if not data:
            raise TryOnRetryableError("empty_result")
        return TryOnResult(image_url=f"data:image/png;base64,{data}", cost_micro_usd=self._cost)

    async def _download(self, url: str, name: str) -> tuple[str, bytes, str]:
        try:
            response = await self._http.get(url)
        except httpx.HTTPError as e:
            raise TryOnRetryableError(f"{name}_download") from e
        if response.status_code >= 500:  # noqa: PLR2004
            raise TryOnRetryableError(f"{name}_download_{response.status_code}")
        if response.status_code != 200 or len(response.content) > MAX_IMAGE_BYTES:  # noqa: PLR2004
            raise TryOnRejectedError(f"{name}_unavailable")
        mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
        if not mime.startswith("image/"):
            raise TryOnRejectedError(f"{name}_not_an_image")
        return (f"{name}.{mime.split('/')[1]}", response.content, mime)

    async def aclose(self) -> None:
        await self._http.aclose()
