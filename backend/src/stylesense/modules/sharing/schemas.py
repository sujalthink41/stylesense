import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stylesense.modules.catalog.schemas import ProductSummary

ShareKind = Literal["look", "product", "board"]
MAX_LOOK_ITEMS = 6


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ShareKind
    title: str | None = Field(default=None, min_length=1, max_length=80)
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_LOOK_ITEMS)
    board_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("a product can appear only once")
        if self.kind == "product" and len(self.product_ids) != 1:
            raise ValueError("a product share names exactly one product")
        if self.kind == "look" and len(self.product_ids) < 2:  # noqa: PLR2004
            raise ValueError("a look has at least two products")
        if self.kind == "board" and (self.board_id is None or self.product_ids):
            raise ValueError("a board share names a board_id and no products")
        if self.kind != "board" and self.board_id is not None:
            raise ValueError("only board shares take a board_id")
        return self


class ShareView(BaseModel):
    slug: str
    kind: ShareKind
    url: str  # the web link that opens the app when installed (App Links)
    title: str | None
    views: int
    created_at: datetime


class PublicShare(BaseModel):
    """What anyone with the link sees: products and live prices, nothing about the owner."""

    slug: str
    kind: ShareKind
    title: str | None
    products: list[ProductSummary]
    created_at: datetime
