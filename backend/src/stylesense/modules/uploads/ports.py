from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from stylesense.platform.errors import ServiceUnavailableError


class MediaUnavailableError(ServiceUnavailableError):
    """Storage is down or busy: worth retrying later."""

    code = "media_unavailable"
    title = "Photo storage is unavailable right now"


class MediaRejectedError(ServiceUnavailableError):
    """Storage refused this file or request for good (bad format, wrong credentials): retrying
    the same thing can't help. Deliberately not a MediaUnavailableError, which means "retry"."""

    code = "media_rejected"
    title = "Photo storage refused the request"


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """Everything the app needs to upload straight to storage (the bytes never touch us)."""

    url: str
    fields: dict[str, str] = field(default_factory=dict)  # send as multipart form fields


@dataclass(frozen=True, slots=True)
class StoredAsset:
    public_id: str
    format: str
    bytes: int
    width: int
    height: int


class MediaStore(Protocol):
    """Private image storage. Implemented by Cloudinary (integrations/media)."""

    name: str

    def upload_ticket(self, public_id: str) -> UploadTicket: ...

    async def inspect(self, public_id: str) -> StoredAsset | None:
        """The stored asset, or None if nothing was uploaded under that id."""
        ...

    def url(self, public_id: str, *, max_side: int | None = None) -> str:
        """A signed delivery URL (assets are private: unsigned URLs don't work)."""
        ...

    async def import_url(self, source_url: str, public_id: str) -> StoredAsset:
        """Copy an image from a URL into storage (e.g. a try-on result)."""
        ...

    async def delete(self, public_ids: Sequence[str]) -> None:
        """Idempotent: deleting a missing asset is fine."""
        ...
