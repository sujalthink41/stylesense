import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TryOnStatus = Literal["queued", "running", "done", "failed"]
ReportReason = Literal["inappropriate", "offensive", "wrong_item", "spam", "other"]
ReportTarget = Literal["tryon", "product", "share", "poll"]


class TryOnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selfie_upload_id: uuid.UUID
    product_id: uuid.UUID


class TryOnView(BaseModel):
    id: uuid.UUID
    status: TryOnStatus
    product_id: uuid.UUID
    result_url: str | None = None  # signed; present when done (and not reported)
    error: str | None = None  # a friendly reason when failed
    retryable: bool = False
    created_at: datetime
    expires_at: datetime  # result and selfie are deleted after this


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: ReportTarget
    target_id: uuid.UUID
    reason: ReportReason
    note: str | None = Field(default=None, max_length=500)


class ReportReceipt(BaseModel):
    id: uuid.UUID
    created: bool  # False = you'd already reported this (safe to retry)
