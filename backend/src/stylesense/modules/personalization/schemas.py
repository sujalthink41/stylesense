import uuid
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stylesense.modules.personalization.styles import (
    BOTTOM_SIZES,
    MAX_STYLES,
    SHOE_SIZES,
    STYLES,
    TOP_SIZES,
)
from stylesense.modules.personalization.taste import Direction

FitPreference = Literal["men", "women", "unisex", "any"]


MAX_BRANDS = 8


class SwipeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    direction: Direction
    session_id: uuid.UUID | None = None  # dedupe scope: one swipe per product per session


class SwipeReceipt(BaseModel):
    recorded: bool  # False = replay of a swipe we already have (safe to retry)


class Sizes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: Literal[TOP_SIZES] | None = None  # type: ignore[valid-type]
    bottom: Literal[BOTTOM_SIZES] | None = None  # type: ignore[valid-type]
    shoe: Literal[SHOE_SIZES] | None = None  # type: ignore[valid-type]


class StyleProfileUpdate(BaseModel):
    """Full replacement (PUT): what onboarding or the edit screen submits."""

    model_config = ConfigDict(extra="forbid")

    fit_preference: FitPreference | None = None
    styles: list[str] = Field(default_factory=list, max_length=MAX_STYLES)
    sizes: Sizes = Field(default_factory=Sizes)
    # None = keep what's saved (Style DNA doesn't ask for these, so retaking it can't wipe them).
    favorite_brands: list[Annotated[str, Field(min_length=1, max_length=40)]] | None = Field(
        default=None, max_length=MAX_BRANDS
    )
    usual_budget_paise: int | None = Field(default=None, ge=10_000, le=10_000_000)

    @field_validator("favorite_brands")
    @classmethod
    def _clean_brands(cls, brands: list[str] | None) -> list[str] | None:
        if brands is None:
            return None
        cleaned = [" ".join(b.split()) for b in brands]
        return list(dict.fromkeys(b for b in cleaned if b))

    @field_validator("styles")
    @classmethod
    def _known_styles(cls, styles: list[str]) -> list[str]:
        unknown = sorted(set(styles) - STYLES.keys())
        if unknown:
            raise ValueError(f"unknown styles: {', '.join(unknown)}")
        return list(dict.fromkeys(styles))  # dedupe, keep order


class StyleProfileView(BaseModel):
    fit_preference: FitPreference | None
    styles: list[str]
    sizes: Sizes
    onboarding_done: bool
    swipe_count: int
    top_tags: list[str]  # strongest learned likes, for "your style" chips
    favorite_brands: list[str] = []
    usual_budget_paise: int | None = None


class StyleOption(BaseModel):
    id: str
    label: str
    image_url: str


class StyleOptions(BaseModel):
    styles: list[StyleOption]
    max_styles: int
    top_sizes: list[str]
    bottom_sizes: list[str]
    shoe_sizes: list[str]


@dataclass(frozen=True, slots=True)
class Taste:
    """What ranking and prefill need, loaded once per turn."""

    fit_preference: str | None = None
    favorite_brands: tuple[str, ...] = ()
    sizes: dict[str, str] = field(default_factory=dict)
    vector: list[float] | None = None
    affinity: dict[str, int] = field(default_factory=dict)
