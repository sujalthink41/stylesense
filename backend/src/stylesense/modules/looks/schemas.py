import uuid

from pydantic import BaseModel, Field

from stylesense.modules.catalog.schemas import ProductSummary


class LookItem(BaseModel):
    slot: str  # bottom | shoes | layer | top
    product: ProductSummary
    reasons: list[str] = Field(max_length=3)


class Look(BaseModel):
    anchor_id: uuid.UUID
    title: str
    items: list[LookItem]
    total_paise: int  # anchor (best price) + every item
    budget_paise: int | None  # the whole look's budget, when the user set one
    remaining_paise: int | None  # budget left after the look
