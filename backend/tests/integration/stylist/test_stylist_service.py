import asyncio
import dataclasses
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from stylesense.genui.actions import (
    Action,
    ActionRequest,
    Back,
    CardOpen,
    ChipSelect,
    Restart,
    Shortcut,
    SliderSet,
    Swipe,
    TextInput,
)
from stylesense.genui.envelope import (
    RenderEvent,
    UiEnvelope,
    UiEvent,
)
from stylesense.genui.validation import InvalidActionError
from stylesense.infra.database import UnitOfWork, create_session_factory
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.ports import RawOffer
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.stylist.exceptions import (
    SessionBusyError,
    SessionNotFoundError,
    StaleTurnError,
)
from stylesense.modules.stylist.flows.base import Entry, Progress, Rendered, TurnContext
from stylesense.modules.stylist.flows.demo import DemoFlow
from stylesense.modules.stylist.models import SessionEvent
from stylesense.modules.stylist.schemas import SessionCreate
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.users.models import User
from tests.fakes.clock import FixedClock

TEE = RawOffer(
    store="amazon",
    external_id="A-1",
    canonical_key="tee-1",
    title="Kalaa Men Navy Oversized T-Shirt",
    brand="Kalaa",
    category="tshirt",
    gender="men",
    url="https://www.amazon.in/s?k=navy+tee",
    price_paise=49_900,
    mrp_paise=99_900,
    rating=4.4,
    rating_count=120,
    image_urls=("https://placehold.co/600x800",),
)
PRICEY_TEE = dataclasses.replace(
    TEE,
    external_id="A-2",
    canonical_key="tee-2",
    title="Kalaa Men Black Tee",
    price_paise=249_900,
    mrp_paise=299_900,
)


class ListSource:
    name = "list"

    def __init__(self, offers: Sequence[RawOffer]) -> None:
        self._offers = list(offers)

    async def offers(self) -> Sequence[RawOffer]:
        return self._offers


class ExplodingFlow(DemoFlow):
    name = "demo"

    async def act(
        self, ctx: TurnContext, state: Mapping[str, Any], screen: UiEnvelope, action: Action
    ) -> AsyncIterator[Progress | Rendered]:
        for never in ():  # type: ignore[var-annotated]  # makes this an async generator that fails on first use
            yield never
        raise RuntimeError("model crashed")


@pytest.fixture
async def sessions(engine: AsyncEngine, migrated: None) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, products CASCADE"))
    factory = create_session_factory(engine)
    catalog = CatalogService(
        lambda: UnitOfWork(factory), clock=FixedClock(), embedder=HashingEmbedder()
    )
    await catalog.ingest(ListSource([TEE, PRICEY_TEE]))
    return factory


@pytest.fixture
async def user_id(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id


def _service(
    sessions: async_sessionmaker[AsyncSession], flow_cls: type[DemoFlow] = DemoFlow
) -> StylistService:
    def uow() -> UnitOfWork:
        return UnitOfWork(sessions)

    catalog = CatalogService(uow, clock=FixedClock(), embedder=HashingEmbedder())
    return StylistService(
        uow, flows={"demo": flow_cls(catalog)}, default_flow="demo", clock=FixedClock()
    )


async def _act(
    svc: StylistService, user: uuid.UUID, session: uuid.UUID, turn: int, action: Action
) -> list[UiEvent]:
    stream = await svc.act(
        session, user, ActionRequest(turn_id=turn, action=action), client_version=1
    )
    return [event async for event in stream]


def _screen(events: list[UiEvent]) -> UiEnvelope:
    renders = [e for e in events if isinstance(e, RenderEvent)]
    assert renders, events
    return renders[-1].envelope


async def _start(svc: StylistService, user: uuid.UUID) -> UiEnvelope:
    view = await svc.start(
        user, SessionCreate(entry="occasion_tile", value="college"), client_version=1
    )
    return view.ui


# ---------- the full demo flow ----------


async def test_demo_flow_walks_from_question_to_store_comparison(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    assert (first.turn_id, [c.type for c in first.components]) == (
        1,
        ["chip_question", "text_input_bar"],
    )
    assert "college" in first.components[0].props.question  # type: ignore[union-attr]

    budget = _screen(
        await _act(
            svc,
            user_id,
            first.session_id,
            1,
            ChipSelect(component_id="category", option_ids=["tshirt"]),
        )
    )
    assert (budget.turn_id, budget.components[0].type) == (2, "budget_slider")

    events = await _act(
        svc,
        user_id,
        first.session_id,
        2,
        SliderSet(component_id="budget", min_paise=0, max_paise=100_000),
    )
    assert [e.event for e in events] == ["ui.loading", "ui.render", "done"]  # skeletons first
    deck = _screen(events).components[0]
    assert deck.type == "product_swipe_deck"
    cards = deck.props.cards
    assert [c.title for c in cards] == [
        "Kalaa Men Navy Oversized T-Shirt"
    ]  # the ₹2,499 tee is over budget
    assert "Within ₹1,000" in cards[0].reasons

    compare = _screen(
        await _act(
            svc,
            user_id,
            first.session_id,
            3,
            CardOpen(component_id="deck", product_id=cards[0].product_id),
        )
    )
    comparison = compare.components[0]
    assert comparison.type == "store_comparison"
    assert comparison.props.offers[0].buy_path.startswith("/v1/out/")

    back = _screen(await _act(svc, user_id, first.session_id, 4, Back()))
    assert (back.turn_id, back.components[0].type) == (5, "product_swipe_deck")


async def test_swiping_removes_the_card_and_empties_gracefully(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    await _act(
        svc,
        user_id,
        first.session_id,
        1,
        ChipSelect(component_id="category", option_ids=["tshirt"]),
    )
    deck = _screen(
        await _act(
            svc,
            user_id,
            first.session_id,
            2,
            SliderSet(component_id="budget", min_paise=0, max_paise=100_000),
        )
    )
    card = deck.components[0].props.cards[0]  # type: ignore[union-attr]

    after = _screen(
        await _act(
            svc,
            user_id,
            first.session_id,
            3,
            Swipe(component_id="deck", product_id=card.product_id, direction="left"),
        )
    )

    assert after.components[0].type == "empty_state"


async def test_restart_and_text_input_keep_the_user_moving(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)

    typed = _screen(
        await _act(svc, user_id, first.session_id, 1, TextInput(text="linen shirt for goa"))
    )
    assert [c.type for c in typed.components] == ["info_banner", "chip_question", "text_input_bar"]

    await _act(
        svc, user_id, first.session_id, 2, ChipSelect(component_id="category", option_ids=["jeans"])
    )
    restarted = _screen(await _act(svc, user_id, first.session_id, 3, Restart()))
    assert restarted.components[0].type == "chip_question"


async def test_empty_results_offer_recovery(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    await _act(
        svc, user_id, first.session_id, 1, ChipSelect(component_id="category", option_ids=["dress"])
    )

    empty = _screen(
        await _act(
            svc,
            user_id,
            first.session_id,
            2,
            SliderSet(component_id="budget", min_paise=0, max_paise=100_000),
        )
    )
    budget = _screen(await _act(svc, user_id, first.session_id, 3, Shortcut(value="raise_budget")))

    assert empty.components[0].type == "empty_state"
    assert budget.components[0].type == "budget_slider"


# ---------- turn safety ----------


async def test_acting_on_an_old_turn_is_rejected(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    await _act(
        svc,
        user_id,
        first.session_id,
        1,
        ChipSelect(component_id="category", option_ids=["tshirt"]),
    )

    with pytest.raises(StaleTurnError) as err:
        await _act(
            svc,
            user_id,
            first.session_id,
            1,
            ChipSelect(component_id="category", option_ids=["jeans"]),
        )
    assert err.value.extra == {"current_turn": 2}


async def test_concurrent_double_tap_advances_the_turn_exactly_once(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    tap = ChipSelect(component_id="category", option_ids=["tshirt"])

    results = await asyncio.gather(
        *(_act(svc, user_id, first.session_id, 1, tap) for _ in range(5)), return_exceptions=True
    )

    assert sum(isinstance(r, list) for r in results) == 1
    losers = [r for r in results if not isinstance(r, list)]
    assert all(isinstance(r, StaleTurnError | SessionBusyError) for r in losers), losers
    assert (await svc.snapshot(first.session_id, user_id, client_version=1)).turn_id == 2


async def test_invalid_action_does_not_consume_the_turn(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)

    with pytest.raises(InvalidActionError):
        await _act(
            svc,
            user_id,
            first.session_id,
            1,
            ChipSelect(component_id="category", option_ids=["lingerie"]),
        )

    assert (await svc.snapshot(first.session_id, user_id, client_version=1)).turn_id == 1


async def test_other_users_cannot_see_or_drive_a_session(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    async with sessions() as s, s.begin():
        intruder = User(email="intruder@example.com")
        s.add(intruder)

    with pytest.raises(SessionNotFoundError):
        await svc.snapshot(first.session_id, intruder.id, client_version=1)
    with pytest.raises(SessionNotFoundError):
        await _act(svc, intruder.id, first.session_id, 1, Restart())


# ---------- resilience ----------


async def test_a_crashing_flow_yields_an_error_and_a_safe_screen(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions, flow_cls=ExplodingFlow)
    first = await _start(svc, user_id)

    events = await _act(svc, user_id, first.session_id, 1, Restart())

    assert [e.event for e in events] == ["error", "ui.render", "done"]
    assert events[0].problem["code"] == "turn_failed"  # type: ignore[union-attr]
    snapshot = await svc.snapshot(first.session_id, user_id, client_version=1)
    assert (snapshot.status, snapshot.turn_id) == ("active", 2)  # not stuck busy; user can go on
    assert "model crashed" not in snapshot.model_dump_json()


async def test_turn_completes_even_if_the_client_disconnects(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    await _act(
        svc,
        user_id,
        first.session_id,
        1,
        ChipSelect(component_id="category", option_ids=["tshirt"]),
    )
    stream = await svc.act(
        first.session_id,
        user_id,
        ActionRequest(
            turn_id=2, action=SliderSet(component_id="budget", min_paise=0, max_paise=100_000)
        ),
        client_version=1,
    )

    await anext(stream)  # read the loading skeleton, then hang up
    await stream.aclose()
    await svc.wait_for_turns()

    snapshot = await svc.snapshot(first.session_id, user_id, client_version=1)
    assert (snapshot.turn_id, snapshot.ui.components[0].type) == (3, "product_swipe_deck")


async def test_every_action_and_render_is_logged(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    svc = _service(sessions)
    first = await _start(svc, user_id)
    await _act(
        svc,
        user_id,
        first.session_id,
        1,
        ChipSelect(component_id="category", option_ids=["tshirt"]),
    )

    async with sessions() as s:
        kinds = (
            await s.execute(
                select(SessionEvent.turn_id, SessionEvent.kind)
                .where(SessionEvent.session_id == first.session_id)
                .order_by(SessionEvent.turn_id, SessionEvent.kind)
            )
        ).all()
        assert await s.scalar(select(func.count()).select_from(SessionEvent)) == 3
    assert [tuple(k) for k in kinds] == [(1, "render"), (2, "action"), (2, "render")]


async def test_photo_entry_explains_and_falls_back(
    sessions: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    view = await _service(sessions).start(user_id, SessionCreate(entry="photo"), client_version=1)

    assert view.ui.components[0].type == "info_banner"


def test_entry_is_validated() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        SessionCreate(entry="teleport")
    assert Entry("search", "tee").kind == "search"
