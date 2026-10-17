import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.genui.actions import (
    Action,
    ActionRequest,
    Back,
    CardOpen,
    ChipSelect,
    Shortcut,
    SliderSet,
    Swipe,
    TextInput,
)
from stylesense.genui.components import ChipQuestion, ProductSwipeDeck
from stylesense.genui.envelope import RenderEvent, UiEnvelope
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.repository import StylistRepository
from stylesense.modules.stylist.schemas import SessionCreate
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.stylist.tasks import ExplainItem, ExplainOutput, UnderstandOutput
from tests.fakes.clock import FixedClock


class StubAI:
    """Scripted assistant: answers per task name, or raises."""

    def __init__(
        self, answers: dict[str, Any] | None = None, error: Exception | None = None
    ) -> None:
        self.answers = answers or {}
        self.error = error
        self.calls: list[tuple[str, Any]] = []

    async def run(
        self, spec: TaskSpec[Any, Any], payload: Any, *, user_id: uuid.UUID | None = None
    ) -> Any:
        self.calls.append((spec.name, payload))
        if self.error:
            raise self.error
        answer = self.answers.get(spec.name)
        if callable(answer):
            return answer(payload)
        if answer is None:
            raise AIUnavailableError("not scripted")
        return answer


class Driver:
    """Plays the app: starts a session and sends actions on the current turn."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
        ai: StubAI | None,
        *,
        ai_reasons: bool = False,
    ) -> None:
        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        catalog = CatalogService(uow, clock=FixedClock(), embedder=HashingEmbedder())
        self.service = StylistService(
            uow,
            flows={"stylist": StylistFlow(catalog, ai, ai_reasons=ai_reasons)},
            default_flow="stylist",
            clock=FixedClock(),
        )
        self.user_id = user_id
        self.screen: UiEnvelope | None = None

    async def start(self, entry: str, value: str | None = None) -> UiEnvelope:
        view = await self.service.start(
            self.user_id, SessionCreate(entry=entry, value=value), client_version=1
        )
        self.screen = view.ui
        return view.ui

    async def send(self, action: Action) -> UiEnvelope:
        assert self.screen is not None
        stream = await self.service.act(
            self.screen.session_id,
            self.user_id,
            ActionRequest(turn_id=self.screen.turn_id, action=action),
            client_version=1,
        )
        renders = [e for e in [event async for event in stream] if isinstance(e, RenderEvent)]
        self.screen = renders[-1].envelope
        return self.screen

    def types(self) -> list[str]:
        assert self.screen is not None
        return [c.type for c in self.screen.components]

    def deck(self) -> ProductSwipeDeck:
        assert self.screen is not None
        return next(c for c in self.screen.components if isinstance(c, ProductSwipeDeck))

    async def state(self) -> dict[str, Any]:
        assert self.screen is not None
        async with self.service._uow() as uow:
            row = await StylistRepository(uow.session).get(self.screen.session_id, self.user_id)
        assert row is not None
        return row.state


# ---------- without AI (the default until keys are configured) ----------


async def test_summer_tshirt_under_500_needs_one_question(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)

    first = await app.start("search", "summer t-shirt under 500")
    assert first.components[0].type == "chip_question"
    assert first.components[0].id == "q_gender"  # category, budget, occasion already understood
    question = first.components[0]
    assert isinstance(question, ChipQuestion)
    assert "summer" in question.props.question.lower()

    await app.send(ChipSelect(component_id="q_gender", option_ids=["men"]))
    cards = app.deck().props.cards
    assert cards
    assert all(c.price_paise is not None and c.price_paise <= 50_000 for c in cards)
    assert all(c.reasons for c in cards)
    assert "Within ₹500" in cards[0].reasons
    state = await app.state()
    assert (state["questions"], state["ai"]) == (1, "unused")  # rules understood it: no tokens


async def test_occasion_tile_asks_at_most_three_questions(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)

    await app.start("occasion_tile", "party")
    await app.send(ChipSelect(component_id="q_category", option_ids=["dress"]))
    await app.send(ChipSelect(component_id="q_gender", option_ids=["women"]))
    await app.send(SliderSet(component_id="q_budget", min_paise=0, max_paise=300_000))

    title = app.deck().props.title
    assert title is not None
    assert title.startswith("Party dresses")
    assert (await app.state())["questions"] == 3


async def test_typing_a_refinement_re_searches(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("search", "men's jeans under 3000")

    await app.send(TextInput(text="actually under 1200"))

    assert all(c.price_paise <= 120_000 for c in app.deck().props.cards)  # type: ignore[operator]


async def test_gibberish_keeps_the_user_on_track(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("search", "jeans for men under 2000")

    await app.send(TextInput(text="hmmm"))

    assert app.types()[0] == "info_banner"
    assert "product_swipe_deck" in app.types()


async def test_back_returns_to_the_previous_question(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("occasion_tile", "office")
    await app.send(ChipSelect(component_id="q_category", option_ids=["shirt"]))

    back = await app.send(Back())

    assert back.components[0].id == "q_category"


async def test_swipes_remove_cards_and_are_remembered(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("search", "men's t-shirt under 2000")
    first = app.deck().props.cards[0]

    await app.send(Swipe(component_id="deck", product_id=first.product_id, direction="right"))

    assert first.product_id not in {c.product_id for c in app.deck().props.cards}
    assert str(first.product_id) in (await app.state())["liked"]


async def test_show_more_pages_through_new_items(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("search", "t-shirts for anyone under 5000")
    await app.send(ChipSelect(component_id="q_gender", option_ids=["any"]))
    page_one = {c.product_id for c in app.deck().props.cards}
    assert app.deck().props.has_more

    await app.send(Shortcut(value="more"))

    assert page_one.isdisjoint({c.product_id for c in app.deck().props.cards})


async def test_opening_a_card_shows_store_prices_and_back_returns(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)
    await app.start("search", "kurta for men under 3000")
    product = app.deck().props.cards[0].product_id

    await app.send(CardOpen(component_id="deck", product_id=product))
    # A v1 app can't draw product_detail (v2): it gets an update banner in that slot.
    assert app.types()[:2] == ["info_banner", "store_comparison"]

    await app.send(Back())
    assert "product_swipe_deck" in app.types()


async def test_impossible_requests_offer_recovery(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=None)

    await app.start("search", "men's jacket under 100")

    assert app.types()[0] == "empty_state"


# ---------- with AI ----------


async def test_ai_fills_gaps_rules_left(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ai = StubAI({"stylist.understand": UnderstandOutput(category="dress", gender="women")})
    app = Driver(catalog_sessions, user_id, ai=ai)

    first = await app.start("search", "something flowy for my cousin's sangeet under 2500")

    # rules: wedding + budget; AI: dress + women → no questions needed at all
    assert "product_swipe_deck" in [c.type for c in first.components]
    assert all(c.price_paise <= 250_000 for c in app.deck().props.cards)  # type: ignore[operator]


async def test_ai_never_overrides_what_rules_understood(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    hallucinated = UnderstandOutput(category="jacket", gender="men", budget_max_rupees=90_000)
    app = Driver(catalog_sessions, user_id, ai=StubAI({"stylist.understand": hallucinated}))

    await app.start("search", "jeans under 1000 for a farewell, something cool")

    state = await app.state()
    assert (state["slots"]["category"], state["slots"]["budget_max_paise"]) == ("jeans", 100_000)
    assert state["slots"]["gender"] == "men"  # a genuine gap: filled


async def test_ai_reasons_replace_rule_reasons_for_known_products_only(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    def explain(payload: Any) -> ExplainOutput:
        items = [
            ExplainItem(product_id=p.id, reasons=["Breathable for summer days"])
            for p in payload.products
        ]
        items.append(ExplainItem(product_id=str(uuid.uuid4()), reasons=["Injected"]))
        return ExplainOutput(items=items[-10:])

    app = Driver(
        catalog_sessions, user_id, ai=StubAI({"stylist.explain": explain}), ai_reasons=True
    )
    await app.start("search", "men's summer t-shirt under 1500")

    reasons = {r for c in app.deck().props.cards for r in c.reasons}
    assert "Breathable for summer days" in reasons
    assert "Injected" not in reasons
    assert (await app.state())["ai"] == "ok"


async def test_ai_outage_degrades_silently(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    app = Driver(catalog_sessions, user_id, ai=StubAI(error=AIUnavailableError("down")))

    await app.start("search", "kurta under 2000 that looks royal")

    # The AI was needed (who is it for?) and is down: the stylist simply asks instead.
    assert app.types()[0] == "chip_question"
    assert (await app.state())["ai"] == "degraded"


async def test_a_brand_search_spends_no_tokens_and_says_when_the_brand_is_not_stocked(
    catalog_sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    # The mock catalog has no ASICS: say so, then show the closest other brands.
    app = Driver(
        catalog_sessions, user_id, ai=StubAI(error=AIUnavailableError("must not be called"))
    )

    first = await app.start("search", "asics shoes for men under 6000")

    state = await app.state()
    assert (state["slots"]["brand"], state["slots"]["category"]) == ("ASICS", "sneakers")
    assert state["ai"] == "unused"  # fully understood by rules
    banner = next(c for c in first.components if c.id == "brand")
    assert "No ASICS" in banner.props.text  # type: ignore[union-attr]
    assert app.deck().props.cards
