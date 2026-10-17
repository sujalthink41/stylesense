from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LegalKind = Literal["privacy", "terms", "delete_account"]


class LegalView(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: LegalKind
    version: int
    title: str
    body_html: str
    published_at: datetime


class LegalPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: LegalKind
    title: str = Field(min_length=1, max_length=120)
    body_html: str = Field(min_length=1, max_length=200_000)
