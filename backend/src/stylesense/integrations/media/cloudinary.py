"""Cloudinary as private image storage, over its REST API (no SDK).

- Uploads go straight from the app to Cloudinary with a short-lived signature we issue.
- Assets are `authenticated`: they're reachable only through URLs we sign.
- The upload preset re-encodes every image on arrival (≤1600 px, q_auto), which also strips
  EXIF metadata such as GPS location.
"""

import base64
import hashlib
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx2 as httpx
import structlog

from stylesense.modules.uploads.ports import (
    MediaRejectedError,
    MediaUnavailableError,
    StoredAsset,
    UploadTicket,
)

logger = structlog.get_logger(__name__)

API = "https://api.cloudinary.com/v1_1"
CDN = "https://res.cloudinary.com"
DELIVERY_TYPE = "authenticated"
_DELETE_BATCH = 100  # Admin API limit per call
_RETRYABLE = {429, 500, 502, 503, 504}


def sign(params: dict[str, str], secret: str) -> str:
    """Cloudinary request signature: sha1 of the sorted params plus the API secret."""
    payload = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] != "")
    return hashlib.sha1((payload + secret).encode(), usedforsecurity=False).hexdigest()


def sign_delivery(path: str, secret: str) -> str:
    """Delivery URL signature component `s--xxxxxxxx--`."""
    digest = hashlib.sha1((path + secret).encode(), usedforsecurity=False).digest()
    return f"s--{base64.urlsafe_b64encode(digest).decode()[:8]}--"


class CloudinaryStore:
    name = "cloudinary"

    def __init__(
        self,
        *,
        cloud_name: str,
        api_key: str,
        api_secret: str,
        upload_preset: str,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
        timeout_s: float = 10.0,
    ) -> None:
        self._cloud = cloud_name
        self._key = api_key
        self._secret = api_secret
        self._preset = upload_preset
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._now = now

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------- MediaStore ----------

    def upload_ticket(self, public_id: str) -> UploadTicket:
        params = {
            "public_id": public_id,
            "timestamp": str(int(self._now())),  # Cloudinary rejects signatures older than 1 h
            "upload_preset": self._preset,
        }
        return UploadTicket(
            url=f"{API}/{self._cloud}/image/upload",
            fields={**params, "api_key": self._key, "signature": sign(params, self._secret)},
        )

    async def inspect(self, public_id: str) -> StoredAsset | None:
        response = await self._call(
            "GET", f"{API}/{self._cloud}/resources/image/{DELIVERY_TYPE}/{public_id}"
        )
        if response.status_code == 404:  # noqa: PLR2004
            return None
        return _asset(self._json(response))

    def url(self, public_id: str, *, max_side: int | None = None) -> str:
        transformation = f"c_limit,h_{max_side},w_{max_side}" if max_side else ""
        path = "/".join(p for p in (transformation, f"{public_id}.jpg") if p)
        signature = sign_delivery(path, self._secret)
        return f"{CDN}/{self._cloud}/image/{DELIVERY_TYPE}/{signature}/{path}"

    async def import_url(self, source_url: str, public_id: str) -> StoredAsset:
        params = {
            "public_id": public_id,
            "timestamp": str(int(self._now())),
            "upload_preset": self._preset,
        }
        response = await self._call(
            "POST",
            f"{API}/{self._cloud}/image/upload",
            data={
                **params,
                "file": source_url,
                "api_key": self._key,
                "signature": sign(params, self._secret),
            },
            auth=False,
        )
        return _asset(self._json(response))

    async def delete(self, public_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(public_ids))
        for start in range(0, len(ids), _DELETE_BATCH):
            batch = ids[start : start + _DELETE_BATCH]
            response = await self._call(
                "DELETE",
                f"{API}/{self._cloud}/resources/image/{DELIVERY_TYPE}",
                params=[("public_ids[]", pid) for pid in batch] + [("invalidate", "true")],
            )
            self._json(response)

    # ---------- plumbing ----------

    async def _call(
        self, method: str, url: str, *, auth: bool = True, **kwargs: Any
    ) -> httpx.Response:
        """One retry on timeouts and 429/5xx; every call here is safe to repeat."""
        for attempt in (1, 2):
            try:
                response = await self._client.request(
                    method, url, auth=(self._key, self._secret) if auth else None, **kwargs
                )
            except httpx.TransportError as exc:
                if attempt == 2:  # noqa: PLR2004
                    raise MediaUnavailableError(
                        f"cloudinary unreachable: {type(exc).__name__}"
                    ) from exc
                continue
            if response.status_code not in _RETRYABLE or attempt == 2:  # noqa: PLR2004
                return response
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:  # noqa: PLR2004
            message = response.headers.get("x-cld-error") or response.text[:200]
            logger.warning("cloudinary_error", status=response.status_code, error=message)
            if response.status_code in _RETRYABLE:
                raise MediaUnavailableError(f"cloudinary {response.status_code}")
            # 4xx: our request or the file is wrong; retrying the same thing can't help.
            raise MediaRejectedError(f"cloudinary {response.status_code}: {message}")
        body: dict[str, Any] = response.json()
        return body


def _asset(body: dict[str, Any]) -> StoredAsset:
    return StoredAsset(
        public_id=str(body["public_id"]),
        format=str(body.get("format", "")),
        bytes=int(body.get("bytes", 0)),
        width=int(body.get("width", 0)),
        height=int(body.get("height", 0)),
    )
