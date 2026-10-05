"""Optional AI polish for a look the rules already built: a title and short reasons.
The model never picks products or prices; it only words what code decided."""

from pydantic import BaseModel, Field

from stylesense.ai.gateway.tasks import TaskSpec


class LookPiece(BaseModel):
    id: str
    title: str = Field(max_length=80)
    tags: list[str] = Field(max_length=8)


class LookInput(BaseModel):
    anchor: LookPiece
    items: list[LookPiece] = Field(max_length=4)


class LookItemWords(BaseModel):
    product_id: str
    reasons: list[str] = Field(max_length=3)


class LookOutput(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    items: list[LookItemWords] = Field(max_length=4)


LOOK_COMPLETE = TaskSpec(
    name="look.complete",
    prompt_version="2026-10-05",
    instructions=(
        "You name an outfit and say why each piece goes with the anchor item, for Indian "
        "shoppers. Give a short title (max 6 words) and up to 3 reasons per item (max 5 words "
        "each), like chips on a card. Use only the given titles and tags: never invent "
        "materials, prices, discounts or ratings."
    ),
    input_type=LookInput,
    output_type=LookOutput,
)
