import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stylesense.modules.catalog.schemas import ProductSummary

BoardName = Annotated[str, Field(min_length=1, max_length=60)]
Note = Annotated[str, Field(max_length=200)]
MAX_ITEMS = 200


class BoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Client-generated (UUIDv7) so an offline app can create boards and retry safely.
    id: uuid.UUID | None = None
    name: BoardName

    @field_validator("name")
    @classmethod
    def _tidy(cls, name: str) -> str:
        tidy = " ".join(name.split())
        if not tidy:
            raise ValueError("name can't be blank")
        return tidy


class BoardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: BoardName | None = None
    cover_product_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, name: str | None) -> str | None:
        return BoardCreate._tidy(name) if name is not None else None


class ItemAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Note | None = None


class ItemOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(max_length=MAX_ITEMS)


class BoardItemView(BaseModel):
    product: ProductSummary
    position: int
    note: str | None
    added_at: datetime


class BoardSummary(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["wishlist", "outfit"]
    version: int  # also the ETag; send it back as If-Match to edit
    item_count: int
    cover_image_url: str | None
    updated_at: datetime


class BoardView(BoardSummary):
    items: list[BoardItemView]


class ItemReceipt(BaseModel):
    board_id: uuid.UUID
    product_id: uuid.UUID
    added: bool  # False = it was already on the board (safe to retry)
    version: int
