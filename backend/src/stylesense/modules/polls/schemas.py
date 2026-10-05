import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stylesense.modules.catalog.schemas import ProductSummary

MIN_OPTIONS, MAX_OPTIONS = 2, 4
DEFAULT_QUESTION = "Which one should I buy?"
VoterToken = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")]


class PollCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID | None = None  # client-generated: retrying a create can't make two polls
    question: str = Field(default=DEFAULT_QUESTION, min_length=1, max_length=120)
    product_ids: list[uuid.UUID] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    closes_in_hours: int = Field(default=48, ge=1, le=168)

    @field_validator("product_ids")
    @classmethod
    def _distinct(cls, ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(ids)) != len(ids):
            raise ValueError("each option must be a different product")
        return ids


class VoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: uuid.UUID


class OptionView(BaseModel):
    option_id: uuid.UUID
    product: ProductSummary
    votes: int | None  # hidden from voters until they vote (no bandwagon), always for the owner


class PollView(BaseModel):
    id: uuid.UUID
    slug: str
    url: str
    question: str
    status: Literal["open", "closed"]
    closes_at: datetime
    total_votes: int
    options: list[OptionView]
    created_at: datetime


class PublicPoll(BaseModel):
    slug: str
    question: str
    status: Literal["open", "closed"]
    closes_at: datetime
    options: list[OptionView]
    total_votes: int | None
    your_vote: uuid.UUID | None
