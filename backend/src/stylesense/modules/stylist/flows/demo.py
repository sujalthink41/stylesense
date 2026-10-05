"""Scripted, AI-free flow that exercises the whole GenUI protocol against the real catalog:
category → budget → swipe deck → store comparison, with back, restart and swipes.
"""

import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from stylesense.genui.actions import (
    Action,
    Back,
    CardOpen,
    ChipSelect,
    Restart,
    Shortcut,
    SliderSet,
    Swipe,
    TextInput,
)
from stylesense.genui.components import (
    BudgetSlider,
    BudgetSliderProps,
    ChipOption,
    ChipQuestion,
    ChipQuestionProps,
    ComparedOffer,
    Component,
    EmptyState,
    EmptyStateProps,
    InfoBanner,
    InfoBannerProps,
    LoadingSkeleton,
    LoadingSkeletonProps,
    ProductCardProps,
    ProductSwipeDeck,
    ProductSwipeDeckProps,
    StoreComparison,
    StoreComparisonProps,
    Suggestion,
    SuggestionBar,
    SuggestionBarProps,
    TextInputBar,
    TextInputBarProps,
)
from stylesense.genui.envelope import UiEnvelope
from stylesense.modules.catalog.schemas import ProductFilters, ProductSummary
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.stylist.flows.base import Entry, Progress, Rendered, TurnContext

CATEGORIES = {
    "tshirt": ("T-shirts", "👕"),
    "shirt": ("Shirts", "👔"),
    "jeans": ("Jeans", "👖"),
    "kurta": ("Kurtas", "🪔"),
    "dress": ("Dresses", "👗"),
    "sneakers": ("Sneakers", "👟"),
}
BUDGET_MAX_PAISE = 500_000
DEFAULT_BUDGET = (0, 100_000)
DECK_SIZE = 10
STEPS = ("category", "budget", "results", "detail")

_BACK = Suggestion(id="back", label="Back", action=Back())
_RESTART = Suggestion(id="restart", label="Start over", action=Restart())


class DemoFlow:
    name = "demo"

    def __init__(self, catalog: CatalogService) -> None:
        self._catalog = catalog

    async def start(self, ctx: TurnContext, entry: Entry) -> Rendered:
        state: dict[str, Any] = {"step": "category", "history": [], "occasion": entry.value}
        notice = None
        if entry.kind == "photo":
            notice = "Photo search is coming soon; let's find it together instead."
        return await self._render(state, notice=notice)

    async def act(
        self, ctx: TurnContext, state: Mapping[str, Any], screen: UiEnvelope, action: Action
    ) -> AsyncIterator[Progress | Rendered]:
        s = dict(state)
        match action:
            case Restart():
                s = {"step": "category", "history": [], "occasion": s.get("occasion")}
            case Back():
                history = list(s.get("history", []))
                s["step"] = history.pop() if history else "category"
                s["history"] = history
            case ChipSelect() if s["step"] == "category":
                s["category"] = action.option_ids[0]
                _advance(s, "budget")
            case SliderSet() if s["step"] == "budget":
                s["budget"] = [action.min_paise, action.max_paise]
                s["dismissed"] = []
                _advance(s, "results")
                yield Progress(
                    [LoadingSkeleton(id="loading", props=LoadingSkeletonProps(shape="cards"))]
                )
            case Swipe() if s["step"] == "results":
                s["dismissed"] = [*s.get("dismissed", []), str(action.product_id)]
            case CardOpen():
                s["product_id"] = str(action.product_id)
                _advance(s, "detail")
            case Shortcut(value="raise_budget"):
                _advance(s, "budget")
            case TextInput():
                yield await self._render(
                    s, notice="Typing your request arrives with the AI stylist soon."
                )
                return
        yield await self._render(s)

    # ---------- rendering (pure function of state, so back/restart/resume all work) ----------

    async def _render(self, s: dict[str, Any], *, notice: str | None = None) -> Rendered:
        components: list[Component] = []
        if notice:
            components.append(InfoBanner(id="notice", props=InfoBannerProps(text=notice)))
        match s["step"]:
            case "category":
                components += [_category_question(s.get("occasion")), _text_bar()]
            case "budget":
                components += [_budget_slider(s), _suggestions(_BACK)]
            case "results":
                components += await self._results(s)
            case "detail":
                components += await self._detail(uuid.UUID(s["product_id"]))
        return Rendered(components=components, state=s)

    async def _results(self, s: dict[str, Any]) -> list[Component]:
        low, high = s["budget"]
        page = await self._catalog.list_products(
            ProductFilters(
                category=s["category"], min_price_paise=low, max_price_paise=high, limit=DECK_SIZE
            )
        )
        dismissed = set(s.get("dismissed", []))
        cards = [_card(p, high) for p in page.items if str(p.id) not in dismissed]
        if not cards:
            return [
                EmptyState(
                    id="empty",
                    props=EmptyStateProps(
                        title="Nothing in that budget yet",
                        body="Try a wider budget or another category.",
                        recovery=[
                            Suggestion(
                                id="raise",
                                label="Change budget",
                                action=Shortcut(value="raise_budget"),
                            ),
                            _RESTART,
                        ],
                    ),
                )
            ]
        label, _ = CATEGORIES.get(s["category"], (s["category"], ""))
        return [
            ProductSwipeDeck(
                id="deck",
                props=ProductSwipeDeckProps(
                    title=f"{label} under {_rupees(high)}",
                    cards=cards,
                    has_more=page.next_cursor is not None,
                ),
            ),
            _suggestions(
                Suggestion(
                    id="raise", label="Change budget", action=Shortcut(value="raise_budget")
                ),
                _RESTART,
            ),
        ]

    async def _detail(self, product_id: uuid.UUID) -> list[Component]:
        detail = await self._catalog.get_product(product_id)
        offers = [
            ComparedOffer(
                offer_id=o.id,
                store=o.store,
                store_name=o.store_name,
                price_paise=o.price_paise,
                mrp_paise=o.mrp_paise,
                discount_percent=o.discount_percent,
                in_stock=o.in_stock,
                is_best=o.is_best,
                buy_path=o.buy_path,
            )
            for o in detail.offers
        ]
        return [
            StoreComparison(
                id="compare",
                props=StoreComparisonProps(product_id=detail.id, title=detail.title, offers=offers),
            ),
            _suggestions(Suggestion(id="back", label="Back to picks", action=Back()), _RESTART),
        ]


def _advance(s: dict[str, Any], step: str) -> None:
    s["history"] = [*s.get("history", []), s["step"]]
    s["step"] = step


def _category_question(occasion: str | None) -> ChipQuestion:
    question = (
        f"Shopping for {occasion}? What do you need?" if occasion else "What are you shopping for?"
    )
    return ChipQuestion(
        id="category",
        props=ChipQuestionProps(
            question=question[:120],
            options=[
                ChipOption(id=k, label=label, icon=icon) for k, (label, icon) in CATEGORIES.items()
            ],
            allow_custom=True,
        ),
    )


def _budget_slider(s: dict[str, Any]) -> BudgetSlider:
    low, high = s.get("budget") or DEFAULT_BUDGET
    return BudgetSlider(
        id="budget",
        props=BudgetSliderProps(
            label="What's your budget?",
            min_paise=0,
            max_paise=BUDGET_MAX_PAISE,
            step_paise=10_000,
            default_min_paise=low,
            default_max_paise=high,
        ),
    )


def _card(p: ProductSummary, budget_max: int) -> ProductCardProps:
    reasons = []
    if p.min_price_paise is not None and p.min_price_paise <= budget_max:
        reasons.append(f"Within {_rupees(budget_max)}")
    if p.rating is not None and p.rating >= 4.0:  # noqa: PLR2004  # "well rated" threshold
        reasons.append(f"Rated {p.rating:.1f}★")
    if p.offer_count > 1 and p.best_store:
        reasons.append(f"Best price on {p.best_store.title()}")
    return ProductCardProps(
        product_id=p.id,
        title=p.title,
        brand=p.brand,
        image_url=p.primary_image_url,
        price_paise=p.min_price_paise,
        best_store=p.best_store,
        rating=p.rating,
        rating_count=p.rating_count,
        reasons=reasons[:3],
    )


def _suggestions(*suggestions: Suggestion) -> SuggestionBar:
    return SuggestionBar(id="next", props=SuggestionBarProps(suggestions=list(suggestions)))


def _text_bar() -> TextInputBar:
    return TextInputBar(
        id="ask", props=TextInputBarProps(placeholder="Or describe it, e.g. linen shirt for Goa")
    )


def _rupees(paise: int) -> str:
    return f"₹{paise // 100:,}"
