import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

UploadKind = Literal["photo_search", "selfie"]
ALLOWED_FORMATS = frozenset({"jpg", "jpeg", "png", "webp", "heic"})
MAX_BYTES = 8 * 1024 * 1024
MIN_SIDE = 200  # px: smaller images can't show a garment or a person


class UploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: UploadKind


class UploadForm(BaseModel):
    """POST the file as multipart `file` plus these fields to `url`."""

    url: str
    fields: dict[str, str]


class UploadView(BaseModel):
    id: uuid.UUID
    kind: UploadKind
    status: Literal["pending", "ready", "rejected", "deleted"]
    expires_at: datetime  # the photo is deleted for good after this
    url: str | None = None  # signed view URL, once ready
    upload: UploadForm | None = None  # only when the upload slot is first issued
