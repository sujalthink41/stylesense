import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stylesense.modules.users.schemas import UserProfile


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_token: str
    access_token_expires_in: int
    refresh_token: str
    refresh_token_expires_in: int
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105  # a scheme name, not a secret


class SignInResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tokens: TokenPair
    user: UserProfile
    is_new_user: bool


class GoogleSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1, max_length=4096)
    installation_id: uuid.UUID | None = None  # one session per app install


class DevSignInRequest(BaseModel):
    """Local development only (see Settings.dev_sign_in_enabled)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    installation_id: uuid.UUID | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _tidy(cls, email: object) -> object:
        return email.strip().lower() if isinstance(email, str) else email


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=200)
