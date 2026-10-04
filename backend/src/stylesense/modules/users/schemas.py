import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SemVer = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=20)


class Role(StrEnum):
    USER = "user"
    CURATOR = "curator"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETING = "deleting"


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class ConsentKind(StrEnum):
    TERMS = "terms"
    PRIVACY = "privacy"
    PHOTO_PROCESSING = "photo_processing"
    MARKETING_PUSH = "marketing_push"


class DeletionChannel(StrEnum):
    APP = "app"
    WEB = "web"
    ADMIN = "admin"


class PurgeOutcome(StrEnum):
    PURGED = "purged"
    NOT_DUE = "not_due"  # retry later
    NOTHING_TO_DO = "nothing_to_do"  # no request, already purged, or account restored


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class UserProfile(_Frozen):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_url: str | None
    role: Role
    status: UserStatus
    locale: str
    created_at: datetime


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    locale: Literal["en-IN", "hi-IN"] | None = None


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    app_version: str = SemVer
    push_token: str | None = Field(default=None, min_length=1, max_length=4096)
    push_enabled: bool = True


class Device(_Frozen):
    installation_id: uuid.UUID
    platform: Platform
    app_version: str
    push_enabled: bool
    has_push_token: bool  # the token itself is never sent back to clients
    last_active_at: datetime


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConsentKind
    version: str = Field(min_length=1, max_length=20)
    granted: bool


class ConsentRecord(_Frozen):
    kind: ConsentKind
    version: str
    granted: bool
    created_at: datetime


class DeletionReceipt(_Frozen):
    purge_after: datetime
