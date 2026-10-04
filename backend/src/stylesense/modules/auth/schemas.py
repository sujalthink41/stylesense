import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=200)
