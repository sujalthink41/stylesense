"""The AI stylist, as a LangGraph state machine run once per turn.

    ingest ─► understand ─► decide ─┬─► ask                                (missing slot)
                                    ├─► search ─► rank ─► explain ─► compose  (all slots known)
                                    └─► detail                             (a card was opened)

Persistence is the session engine's job (turn CAS); the graph gets the stored state as input
and returns the next one, so no LangGraph checkpointer is needed (ADR 0012).
Works fully without AI: rules understand requests and explain picks; the LLM only adds to them.
Personal when a TasteSource is wired (CP9): Style DNA prefills gender and size, swipes are
recorded and reshape ranking, and `deck()` refills the swipe deck without a turn.
"""

import asyncio
import contextlib
import copy
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol, TypedDict, cast

import structlog
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from stylesense.ai.gateway.exceptions import (
    AIInputTooLargeError,
    AIQuotaExceededError,
    AIUnavailableError,
)
from stylesense.ai.gateway.tasks import TaskSpec
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
    CompleteTheLook,
    CompleteTheLookProps,
    Component,
    EmptyState,
    EmptyStateProps,
    InfoBanner,
    InfoBannerProps,
    LoadingSkeleton,
    LoadingSkeletonProps,
    ProductCardProps,
    ProductCarousel,
    ProductCarouselProps,
    ProductDetail,
    ProductDetailProps,
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
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.rules import (
    DEFAULT_TYPICAL_PRICE_PAISE,
    TYPICAL_PRICE_PAISE,
    OfferView,
    needs_alternatives,
)
from stylesense.modules.catalog.schemas import ProductDetail as Detail
from stylesense.modules.catalog.schemas import ProductSummary, SearchHit, SearchQuery
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.looks.schemas import Look
from stylesense.modules.looks.service import LookService
from stylesense.modules.personalization.schemas import SwipeInput, Taste
from stylesense.modules.personalization.styles import SIZE_KIND
from stylesense.modules.stylist.explain import clean, rule_reasons, rupees
from stylesense.modules.stylist.flows.base import DeckPage, Entry, Progress, Rendered, TurnContext
from stylesense.modules.stylist.ports import PhotoSource, TasteSource
from stylesense.modules.stylist.ranking import Ranked, rank
from stylesense.modules.stylist.slots import CATEGORIES, OCCASIONS, Slots
from stylesense.modules.stylist.tasks import (
    PHOTO_UNDERSTAND,
    STYLIST_EXPLAIN,
    STYLIST_UNDERSTAND,
    ExplainInput,
    ExplainOutput,
    ExplainProduct,
    PhotoInput,
    PhotoOutput,
    UnderstandInput,
    UnderstandOutput,
)
from stylesense.modules.stylist.understanding import parse_request
from stylesense.modules.uploads.exceptions import (
    DailyLimitError,
    UploadNotFoundError,
    UploadNotReadyError,
)
from stylesense.modules.uploads.ports import MediaUnavailableError

logger = structlog.get_logger(__name__)

DECK_SIZE = 10
PHOTO_UNAVAILABLE = "Photo search is unavailable right now. Tell me what you're after instead."
CANDIDATES = 60
MAX_HISTORY = 10
SLIDER_MAX_PAISE = 500_000
LOOK_SLIDER_MAX_PAISE = 1_000_000
ALTERNATIVES = 6
_GENDER_OPTIONS = [
    ("men", "Men"),
    ("women", "Women"),
    ("unisex", "Unisex"),
    ("any", "No preference"),
]
_AI_FAILURES = (AIUnavailableError, AIQuotaExceededError, AIInputTooLargeError)
_RESTART = Suggestion(id="restart", label="Start over", action=Restart())
_BACK = Suggestion(id="back", label="Back", action=Back())


class Assistant(Protocol):
    """The slice of the LLM gateway the stylist uses (structural, so tests can stub it)."""

    async def run(
        self, spec: TaskSpec[Any, Any], payload: Any, *, user_id: uuid.UUID | None = None
    ) -> Any: ...


class _State(TypedDict, total=False):
    persisted: dict[str, Any]  # survives between turns
    user_id: uuid.UUID
    session_id: uuid.UUID
    action: Action | None
    entry: Entry | None
    text: str | None
    notice: str | None
    hits: list[SearchHit]
    taste: Taste | None
    page: list[Ranked]
    has_more: bool
    reasons: dict[str, list[str]]
    components: list[Component]


def _fresh() -> dict[str, Any]:
    return {
        "slots": Slots().model_dump(),
        "step": "ask",
        "history": [],
        "dismissed": [],
        "liked": [],
        "page": 0,
        "query": "",
        "detail": None,
        "questions": 0,
        "ai": "unused",
    }


class StylistFlow:
    name = "stylist"

    def __init__(
        self,
        catalog: CatalogService,
        ai: Assistant | None,
        taste: TasteSource | None = None,
        looks: LookService | None = None,
        photos: PhotoSource | None = None,
    ) -> None:
        self._catalog = catalog
        self._ai = ai
        self._taste = taste
        self._looks = looks
        self._photos = photos
        graph = StateGraph(_State)
        for node in (
            "ingest",
            "understand",
            "ask",
            "search",
            "rank",
            "explain",
            "compose",
            "detail",
        ):
            graph.add_node(node, getattr(self, f"_{node}"))
        graph.add_edge(START, "ingest")
        graph.add_edge("ingest", "understand")
        graph.add_conditional_edges("understand", self._decide, ["ask", "search", "detail"])
        graph.add_edge("search", "rank")
        graph.add_edge("rank", "explain")
        graph.add_edge("explain", "compose")
        for terminal in ("ask", "compose", "detail"):
            graph.add_edge(terminal, END)
        self._graph = graph.compile(name="stylist")

    # ---------- Flow protocol ----------

    async def start(self, ctx: TurnContext, entry: Entry) -> Rendered:
        rendered: Rendered | None = None
        async for output in self._run(
            {
                "persisted": _fresh(),
                "entry": entry,
                "user_id": ctx.user_id,
                "session_id": ctx.session_id,
            }
        ):
            if isinstance(output, Rendered):
                rendered = output
        assert rendered is not None  # noqa: S101  # the graph always ends in a terminal node
        return rendered

    def act(
        self, ctx: TurnContext, state: Mapping[str, Any], screen: UiEnvelope, action: Action
    ) -> AsyncIterator[Progress | Rendered]:
        persisted = {**_fresh(), **copy.deepcopy(dict(state))}
        return self._run(
            {
                "persisted": persisted,
                "action": action,
                "user_id": ctx.user_id,
                "session_id": ctx.session_id,
            }
        )

    async def deck(
        self, ctx: TurnContext, state: Mapping[str, Any], *, exclude: list[uuid.UUID], limit: int
    ) -> DeckPage | None:
        """Next cards for the current request, skipping anything swiped or already on screen.
        Read-only (no turn) with rule reasons only: the app calls it often to prefetch."""
        p = {**_fresh(), **copy.deepcopy(dict(state))}
        slots = Slots.model_validate(p["slots"])
        if p["step"] not in {"results", "detail"} or slots.missing():
            return None
        hits, taste = await self._retrieve(ctx.user_id, ctx.session_id, p, extra_exclude=exclude)
        ranked = rank(hits, slots, limit=limit + 1, affinity=taste.affinity if taste else None)
        cards = [_card(r, rule_reasons(r, slots)) for r in ranked[:limit]]
        return DeckPage(cards=cards, has_more=len(ranked) > limit)

    async def _run(self, initial: _State) -> AsyncIterator[Progress | Rendered]:
        final: dict[str, Any] = {}
        async for mode, chunk in self._graph.astream(initial, stream_mode=["custom", "values"]):
            if mode == "custom":
                yield cast("Progress", chunk)
            else:
                final = cast("dict[str, Any]", chunk)
        yield Rendered(components=final["components"], state=final["persisted"])

    # ---------- nodes ----------

    async def _ingest(self, s: _State) -> _State:
        p = s["persisted"]
        slots = Slots.model_validate(p["slots"])
        text, notice = None, None
        action = s.get("action")
        if p["step"] == "detail" and not _stays_on_detail(action):
            p["step"], p["detail"] = "results", None  # any other action leaves the detail screen
        if entry := s.get("entry"):
            slots, text, notice = _apply_entry(entry, slots)
            if entry.kind == "photo":
                slots, notice = await self._from_photo(s, entry.value, slots)
            slots = _prefill(slots, await self._load_taste(s["user_id"]))
        if isinstance(action, Swipe):
            await self._record_swipe(s, action)
        p, slots, typed = _apply_action(action, p, slots)
        text = typed or text
        if slots.model_dump() != p["slots"]:
            p["page"] = 0  # new request: start the deck from the top
        p["slots"] = slots.model_dump()
        return {"persisted": p, "text": text, "notice": notice}

    async def _understand(self, s: _State) -> _State:
        text = s.get("text")
        if not text:
            return {}
        p = s["persisted"]
        known = Slots.model_validate(p["slots"])
        from_rules = parse_request(text)
        slots = known.merged(from_rules)
        if from_ai := await self._ai_understand(s, text, slots):
            slots = _fill_gaps(slots, from_ai)
        p["query"] = f"{p['query']} {text}".strip()[-500:]
        if slots == known:
            return {
                "persisted": p,
                "notice": "I didn't catch that. Try a category, colour or budget.",
            }
        p["slots"] = slots.model_dump()
        p["page"] = 0
        return {"persisted": p}

    def _decide(self, s: _State) -> str:
        p = s["persisted"]
        if p["step"] == "detail" and p.get("detail"):
            return "detail"
        return "ask" if Slots.model_validate(p["slots"]).missing() else "search"

    async def _ask(self, s: _State) -> _State:
        p = s["persisted"]
        slots = Slots.model_validate(p["slots"])
        missing = slots.missing()[0]
        if p.get("asking") != missing:
            p["questions"] += 1
        p["step"], p["asking"] = "ask", missing
        question: Component
        if missing == "category":
            question = _chips(
                "q_category",
                _lead(slots, "What are you shopping for?"),
                [(k, label, icon) for k, (label, icon) in CATEGORIES.items()],
            )
        elif missing == "gender":
            question = _chips(
                "q_gender",
                _lead(slots, "Who is it for?"),
                [(k, lbl, None) for k, lbl in _GENDER_OPTIONS],
            )
        else:
            question = _budget_slider(slots)
        components: list[Component] = [
            *_notice(s),
            question,
            TextInputBar(id="ask", props=TextInputBarProps()),
        ]
        if p["history"]:
            components.append(
                SuggestionBar(id="next", props=SuggestionBarProps(suggestions=[_BACK, _RESTART]))
            )
        return {"persisted": p, "components": components}

    async def _search(self, s: _State) -> _State:
        get_stream_writer()(
            Progress([LoadingSkeleton(id="loading", props=LoadingSkeletonProps(shape="cards"))])
        )
        hits, taste = await self._retrieve(s["user_id"], s["session_id"], s["persisted"])
        return {"hits": hits, "taste": taste}

    async def _rank(self, s: _State) -> _State:
        p = s["persisted"]
        page = p["page"]
        taste = s.get("taste")
        ranked = rank(
            s["hits"],
            Slots.model_validate(p["slots"]),
            limit=DECK_SIZE * (page + 1) + 1,
            affinity=taste.affinity if taste else None,
        )
        window = ranked[page * DECK_SIZE : (page + 1) * DECK_SIZE]
        return {"page": window, "has_more": len(ranked) > (page + 1) * DECK_SIZE}

    async def _explain(self, s: _State) -> _State:
        slots = Slots.model_validate(s["persisted"]["slots"])
        reasons = {str(r.hit.product.id): rule_reasons(r, slots) for r in s["page"]}
        if s["page"] and (from_ai := await self._ai_explain(s, slots)):
            for product_id, ai_reasons in from_ai.items():
                if product_id in reasons and (cleaned := clean(ai_reasons)):
                    reasons[product_id] = cleaned
        return {"reasons": reasons}

    async def _compose(self, s: _State) -> _State:
        p = s["persisted"]
        p["step"], p["asking"] = "results", None
        slots = Slots.model_validate(p["slots"])
        bar_items = [
            Suggestion(
                id="change_budget", label="Change budget", action=Shortcut(value="change_budget")
            ),
            _RESTART,
        ]
        if not s["page"]:
            empty = EmptyState(
                id="empty",
                props=EmptyStateProps(
                    title="Nothing matches yet",
                    body="Try a wider budget or a different style.",
                    recovery=bar_items,
                ),
            )
            return {"persisted": p, "components": [*_notice(s), empty]}
        if s["has_more"]:
            bar_items.insert(
                0, Suggestion(id="more", label="Show more", action=Shortcut(value="more"))
            )
        cards = [_card(r, s["reasons"].get(str(r.hit.product.id), [])) for r in s["page"]]
        deck = ProductSwipeDeck(
            id="deck",
            props=ProductSwipeDeckProps(
                title=_deck_title(slots), cards=cards, has_more=s["has_more"]
            ),
        )
        components: list[Component] = [
            *_notice(s),
            deck,
            SuggestionBar(id="next", props=SuggestionBarProps(suggestions=bar_items[:6])),
            TextInputBar(
                id="ask", props=TextInputBarProps(placeholder="Refine: e.g. only cotton, under 800")
            ),
        ]
        return {"persisted": p, "components": components}

    async def _detail(self, s: _State) -> _State:
        p = s["persisted"]
        try:
            detail = await self._catalog.get_product(uuid.UUID(p["detail"]))
        except ProductNotFoundError:
            p["step"], p["detail"] = "results", None
            notice = InfoBanner(
                id="notice",
                props=InfoBannerProps(tone="warning", text="That item is no longer available."),
            )
            return {
                "persisted": p,
                "components": [
                    notice,
                    SuggestionBar(
                        id="next", props=SuggestionBarProps(suggestions=[_BACK, _RESTART])
                    ),
                ],
            }
        slots = Slots.model_validate(p["slots"])
        alternatives, look = await asyncio.gather(
            self._alternatives(detail, slots), self._look(s, detail, slots)
        )
        components: list[Component] = [ProductDetail(id="detail", props=_detail_props(detail))]
        if detail.offers:
            components.append(_comparison(detail))
        if alternatives:
            title = "Similar, in stock now" if detail.min_price_paise is None else "Similar picks"
            components.append(
                ProductCarousel(
                    id="similar",
                    props=ProductCarouselProps(
                        title=title, items=[_summary_card(a, []) for a in alternatives]
                    ),
                )
            )
        if look is not None and look.items:
            components.append(
                CompleteTheLook(
                    id="look",
                    props=CompleteTheLookProps(
                        title=look.title[:120],
                        anchor_product_id=detail.id,
                        items=[_summary_card(i.product, i.reasons) for i in look.items],
                        remaining_budget_paise=look.remaining_paise,
                    ),
                )
            )
        if look is not None and (look.items or look.budget_paise is not None):
            components.append(_look_slider(look))
        back = Suggestion(id="back", label="Back to picks", action=Back())
        components.append(
            SuggestionBar(id="next", props=SuggestionBarProps(suggestions=[back, _RESTART]))
        )
        return {"persisted": p, "components": components}

    async def _alternatives(self, detail: Detail, slots: Slots) -> list[ProductSummary]:
        offers = [OfferView(o.store, o.price_paise, o.in_stock, o.rating) for o in detail.offers]
        if not needs_alternatives(offers):
            return []
        # The request's budget applies only to what was asked for.
        budget = slots.budget_max_paise if slots.category == detail.category else None
        return await self._catalog.alternatives(
            detail.id, max_price_paise=budget, limit=ALTERNATIVES
        )

    async def _look(self, s: _State, detail: Detail, slots: Slots) -> Look | None:
        if self._looks is None:
            return None
        p = s["persisted"]
        return await self._looks.complete(
            detail.id,
            budget_paise=p.get("look_budget"),
            gender=slots.gender,
            occasion=slots.occasion,
            user_id=s.get("user_id"),
            polish=self._ai is not None,
        )

    # ---------- retrieval & personalization ----------

    async def _retrieve(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        p: dict[str, Any],
        *,
        extra_exclude: list[uuid.UUID] | None = None,
    ) -> tuple[list[SearchHit], Taste | None]:
        slots = Slots.model_validate(p["slots"])
        taste = await self._load_taste(user_id)
        excluded = {uuid.UUID(i) for i in p["dismissed"]} | set(extra_exclude or [])
        if self._taste is not None:
            excluded |= set(await self._taste.session_swipes(user_id, session_id))
        size = taste.sizes.get(SIZE_KIND.get(slots.category or "", "")) if taste else None
        query = SearchQuery(
            category=slots.category,
            gender=None if slots.gender == "any" else slots.gender,
            min_price_paise=slots.budget_min_paise,
            max_price_paise=slots.budget_max_paise,
            text=_search_text(slots, p["query"]),
            exclude_ids=sorted(excluded)[:500],
            size=size,
            taste=taste.vector if taste else None,
            limit=CANDIDATES,
        )
        hits = await self._catalog.search(query)
        if not hits and size:  # nothing left in their size: showing other sizes beats nothing
            hits = await self._catalog.search(query.model_copy(update={"size": None}))
        return hits, taste

    async def _load_taste(self, user_id: uuid.UUID) -> Taste | None:
        return await self._taste.taste(user_id) if self._taste is not None else None

    async def _record_swipe(self, s: _State, swipe: Swipe) -> None:
        if self._taste is None:
            return
        # Removed from the catalog since the deck was drawn: nothing to learn.
        with contextlib.suppress(ProductNotFoundError):
            await self._taste.record_swipe(
                s["user_id"],
                SwipeInput(
                    product_id=swipe.product_id,
                    direction=swipe.direction,
                    session_id=s["session_id"],
                ),
            )

    # ---------- shop from a photo ----------

    async def _from_photo(
        self, s: _State, upload_id: str | None, slots: Slots
    ) -> tuple[Slots, str | None]:
        """Photo → attributes → the usual slots. Every failure becomes a notice: the session
        carries on with questions instead of dead-ending."""
        if self._photos is None or not upload_id:
            return slots, PHOTO_UNAVAILABLE
        try:
            url = await self._photos.photo_for_search(s["user_id"], uuid.UUID(upload_id))
        except _PHOTO_FAILURES as exc:
            return slots, _photo_notice(exc)
        seen = await self._ask_ai(s, PHOTO_UNDERSTAND, PhotoInput(image_urls=[url]))
        if not isinstance(seen, PhotoOutput):
            return slots, "I couldn't read the photo just now. Tell me what you're after instead."
        if not seen.usable:
            return slots, "I can't find clothes to match in that photo. Try another one?"
        return _fill_gaps(slots, seen.to_slots()), None

    # ---------- AI (optional; every failure degrades to rules) ----------

    async def _ai_understand(self, s: _State, text: str, known: Slots) -> Slots | None:
        result = await self._ask_ai(
            s,
            STYLIST_UNDERSTAND,
            UnderstandInput(text=text, known=known.model_dump(exclude_defaults=True)),
        )
        return result.to_slots() if isinstance(result, UnderstandOutput) else None

    async def _ai_explain(self, s: _State, slots: Slots) -> dict[str, list[str]] | None:
        products = [
            ExplainProduct(
                id=str(r.hit.product.id),
                title=r.hit.product.title[:80],
                price_rupees=(r.hit.product.min_price_paise or 0) // 100,
                tags=r.hit.product.tags[:8],
            )
            for r in s["page"]
        ]
        request = " ".join(f"{k}={v}" for k, v in slots.model_dump(exclude_defaults=True).items())
        result = await self._ask_ai(
            s, STYLIST_EXPLAIN, ExplainInput(request=request, products=products)
        )
        if not isinstance(result, ExplainOutput):
            return None
        return {item.product_id: item.reasons for item in result.items}

    async def _ask_ai[O: BaseModel](
        self, s: _State, spec: TaskSpec[Any, O], payload: BaseModel
    ) -> O | None:
        p = s["persisted"]
        if self._ai is None:
            p["ai"] = "degraded"
            return None
        try:
            result: O = await self._ai.run(spec, payload, user_id=s.get("user_id"))
        except _AI_FAILURES as exc:
            logger.info("stylist_ai_degraded", task=spec.name, reason=type(exc).__name__)
            p["ai"] = "degraded"
            return None
        p["ai"] = "ok"
        return result


# ---------- helpers ----------


def _fill_gaps(base: Slots, ai: Slots) -> Slots:
    """AI may only fill what rules and earlier turns left empty; it never overrides them."""
    gaps = {
        k: v
        for k, v in ai.model_dump().items()
        if v not in (None, []) and getattr(base, k) in (None, [])
    }
    return base.model_copy(update=gaps)


_PHOTO_FAILURES = (
    ValueError,
    UploadNotFoundError,
    UploadNotReadyError,
    DailyLimitError,
    MediaUnavailableError,
)


def _photo_notice(exc: Exception) -> str:
    if isinstance(exc, DailyLimitError):
        return "That's today's photo searches used up. Tell me what you're after instead."
    if isinstance(exc, MediaUnavailableError):
        return PHOTO_UNAVAILABLE
    return "I couldn't open that photo. Try uploading it again?"  # bad id, missing, not ready


def _stays_on_detail(action: Action | None) -> bool:
    """Opening another item, going back or setting the look budget keep the detail screen."""
    return isinstance(action, CardOpen | Back) or (
        isinstance(action, SliderSet) and action.component_id == "q_look_budget"
    )


def _detail_props(d: Detail) -> ProductDetailProps:
    best = next((o for o in d.offers if o.is_best), None)
    return ProductDetailProps(
        product_id=d.id,
        title=d.title[:160],
        brand=d.brand[:40],
        images=[i for i in d.images if i.startswith("https://")][:8],
        price_paise=d.min_price_paise,
        mrp_paise=best.mrp_paise if best else None,
        rating=d.rating,
        rating_count=d.rating_count,
        colors=[c[:40] for c in d.colors][:10],
        sizes=[z[:10] for z in d.sizes_available][:20],
        facts=_facts(d.attributes),
    )


_FACT_SUFFIX = {
    "fit": "fit",
    "sleeve": "sleeve",
    "rise": "rise",
    "wash": "wash",
    "length": "length",
}


def _facts(attributes: Mapping[str, str]) -> list[str]:
    """Attribute values as short chips: "Cotton", "Slim fit", "Half sleeve"."""
    facts = []
    for key, value in sorted(attributes.items()):
        if key == "occasion" or not value:
            continue
        suffix = _FACT_SUFFIX.get(key)
        facts.append((f"{value} {suffix}" if suffix else value).capitalize()[:40])
    return facts[:8]


def _comparison(d: Detail) -> StoreComparison:
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
        for o in d.offers
    ]
    return StoreComparison(
        id="compare",
        props=StoreComparisonProps(product_id=d.id, title=d.title[:160], offers=offers[:10]),
    )


def _look_slider(look: Look) -> BudgetSlider:
    step = 10_000
    if look.budget_paise is not None:
        default = look.budget_paise  # show exactly what's applied
    else:
        default = -(-look.total_paise // step) * step  # suggest: this look, rounded up
    default = min(LOOK_SLIDER_MAX_PAISE, default)
    return BudgetSlider(
        id="q_look_budget",
        props=BudgetSliderProps(
            label="Budget for the whole look",
            min_paise=0,
            max_paise=LOOK_SLIDER_MAX_PAISE,
            step_paise=step,
            default_min_paise=0,
            default_max_paise=default,
        ),
    )


def _summary_card(p: ProductSummary, reasons: list[str]) -> ProductCardProps:
    return ProductCardProps(
        product_id=p.id,
        title=p.title[:160],
        brand=p.brand[:40],
        image_url=p.primary_image_url,
        price_paise=p.min_price_paise,
        best_store=p.best_store,
        rating=p.rating,
        rating_count=p.rating_count,
        reasons=reasons[:3],
    )


def _prefill(slots: Slots, taste: Taste | None) -> Slots:
    """Style DNA answers the gender question up front; the request itself always wins."""
    if taste is None or taste.fit_preference is None or slots.gender is not None:
        return slots
    return slots.model_copy(update={"gender": taste.fit_preference})


def _push(p: dict[str, Any]) -> None:
    snapshot = {k: copy.deepcopy(v) for k, v in p.items() if k != "history"}
    p["history"] = [*p["history"], snapshot][-MAX_HISTORY:]


def _pop(p: dict[str, Any]) -> dict[str, Any]:
    if not p["history"]:
        return _fresh()
    previous = dict(p["history"][-1])
    previous["history"] = p["history"][:-1]
    previous["dismissed"], previous["liked"] = p["dismissed"], p["liked"]  # swipes stick
    return previous


def _known_occasion(value: str) -> str | None:
    lowered = value.strip().lower()
    return lowered if lowered in OCCASIONS else None


def _notice(s: _State) -> list[Component]:
    text = s.get("notice")
    return [InfoBanner(id="notice", props=InfoBannerProps(text=text))] if text else []


def _lead(slots: Slots, question: str) -> str:
    known = [slots.occasion, slots.colors[0] if slots.colors else None, slots.fit, slots.fabric]
    category = CATEGORIES[slots.category][0].lower() if slots.category else None
    summary = " ".join(w for w in [*known, category] if w)
    return f"Got it: {summary}. {question}"[:120] if summary else question


def _chips(
    component_id: str, question: str, options: list[tuple[str, str, str | None]]
) -> ChipQuestion:
    return ChipQuestion(
        id=component_id,
        props=ChipQuestionProps(
            question=question,
            options=[ChipOption(id=i, label=label, icon=icon) for i, label, icon in options],
            allow_custom=True,
        ),
    )


def _budget_slider(slots: Slots) -> BudgetSlider:
    typical = TYPICAL_PRICE_PAISE.get(slots.category or "", DEFAULT_TYPICAL_PRICE_PAISE)
    return BudgetSlider(
        id="q_budget",
        props=BudgetSliderProps(
            label=_lead(slots, "What's your budget?"),
            min_paise=0,
            max_paise=SLIDER_MAX_PAISE,
            step_paise=10_000,
            default_min_paise=0,
            default_max_paise=typical,
        ),
    )


def _search_text(slots: Slots, query: str) -> str | None:
    words = [query, *slots.preferences()]
    text = " ".join(w for w in words if w).strip()
    return text[:500] or None


def _deck_title(slots: Slots) -> str:
    label = CATEGORIES[slots.category][0] if slots.category else "Picks"
    who = {"men": " for men", "women": " for women", "unisex": ", unisex"}.get(
        slots.gender or "", ""
    )
    occasion = f"{slots.occasion.title()} " if slots.occasion else ""
    budget = f" under {rupees(slots.budget_max_paise)}" if slots.budget_max_paise else ""
    return f"{occasion}{label.lower() if occasion else label}{who}{budget}"[:120]


def _card(item: Ranked, reasons: list[str]) -> ProductCardProps:
    p = item.hit.product
    return ProductCardProps(
        product_id=p.id,
        title=p.title[:160],
        brand=p.brand[:40],
        image_url=p.primary_image_url,
        price_paise=p.min_price_paise,
        best_store=p.best_store,
        rating=p.rating,
        rating_count=p.rating_count,
        reasons=reasons[:3],
    )


def _apply_entry(entry: Entry, slots: Slots) -> tuple[Slots, str | None, str | None]:
    """How a session starts: (slots, text to understand, notice)."""
    if entry.kind == "occasion_tile" and entry.value:
        occasion = parse_request(entry.value).occasion or _known_occasion(entry.value)
        return slots.model_copy(update={"occasion": occasion}), None, None
    if entry.kind == "search" and entry.value:
        return slots, entry.value, None
    return slots, None, None


def _apply_action(
    action: Action | None, p: dict[str, Any], slots: Slots
) -> tuple[dict[str, Any], Slots, str | None]:
    """Applies one user action to persisted state: (persisted, slots, typed text)."""
    text = None
    match action:
        case Restart():
            p, slots = _fresh(), Slots()
        case Back():
            p = _pop(p)
            slots = Slots.model_validate(p["slots"])
        case ChipSelect(component_id="q_category", option_ids=[category, *_]):
            _push(p)
            slots = slots.model_copy(update={"category": category})
        case ChipSelect(component_id="q_gender", option_ids=[gender, *_]):
            _push(p)
            slots = slots.model_copy(update={"gender": gender})
        case SliderSet(component_id="q_budget") as budget:
            _push(p)
            low = budget.min_paise or None
            slots = slots.model_copy(
                update={"budget_min_paise": low, "budget_max_paise": budget.max_paise or None}
            )
        case Swipe() as swipe:
            p["dismissed"] = [*p["dismissed"], str(swipe.product_id)]
            if swipe.direction in {"right", "super"}:
                p["liked"] = [*p["liked"], str(swipe.product_id)]
        case CardOpen() as opened:
            _push(p)
            p["step"], p["detail"] = "detail", str(opened.product_id)
        case SliderSet(component_id="q_look_budget") as look_budget:
            p["look_budget"] = look_budget.max_paise or None  # 0 clears it
        case Shortcut(value="more"):
            p["page"] += 1
        case Shortcut(value="change_budget"):
            _push(p)
            slots = slots.model_copy(update={"budget_min_paise": None, "budget_max_paise": None})
        case TextInput() as typed:
            _push(p)
            text = typed.text
    return p, slots, text
