"""CP12: shop from a photo, through the stylist (vision AI optional; failures become notices)."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.ai.gateway.tasks import TaskSpec
from stylesense.genui.actions import ActionRequest, Shortcut, SliderSet
from stylesense.genui.components import InfoBanner, ProductSwipeDeck
from stylesense.genui.envelope import RenderEvent, UiEnvelope
from stylesense.guards.rate_limit import RateLimiter
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.schemas import SessionCreate
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.stylist.tasks import PhotoInput, PhotoOutput
from stylesense.modules.uploads.service import UploadsService
from tests.fakes.clock import FixedClock
from tests.fakes.media import FakeMediaStore


class VisionAI:
    def __init__(self, answer: PhotoOutput | Exception) -> None:
        self.answer = answer
        self.inputs: list[Any] = []

    async def run(
        self, spec: TaskSpec[Any, Any], payload: Any, *, user_id: uuid.UUID | None = None
    ) -> Any:
        if spec.name != "photo.understand":
            raise AIUnavailableError("only vision is scripted")
        self.inputs.append(payload)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class PhotoApp:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        user_id: uuid.UUID,
        ai: VisionAI | None,
        *,
        photo_limit: int = 10,
    ) -> None:
        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        self.store = FakeMediaStore()
        self.clock = FixedClock()
        self.uploads = UploadsService(
            uow,
            store=self.store,
            limiter=RateLimiter(redis, self.clock, prefix=f"t{uuid.uuid4().hex}:"),
            clock=self.clock,
            ttl=timedelta(hours=24),
            daily_limit=50,
            photo_search_daily_limit=photo_limit,
        )
        catalog = CatalogService(uow, clock=self.clock, embedder=HashingEmbedder())
        self.service = StylistService(
            uow,
            flows={"stylist": StylistFlow(catalog, ai, photos=self.uploads)},
            default_flow="stylist",
            clock=self.clock,
        )
        self.user_id = user_id

    async def photo(self, kind: str = "photo_search") -> uuid.UUID:
        upload = await self.uploads.create(self.user_id, kind)  # type: ignore[arg-type]
        self.store.simulate_upload(f"stylesense/u/{upload.id}")
        await self.uploads.confirm(self.user_id, upload.id)
        return upload.id

    async def start(self, value: str | None) -> UiEnvelope:
        view = await self.service.start(
            self.user_id, SessionCreate(entry="photo", value=value), client_version=2
        )
        return view.ui


def _banner(ui: UiEnvelope) -> str | None:
    banners = [c for c in ui.components if isinstance(c, InfoBanner)]
    return banners[0].props.text if banners else None


SEEN = PhotoOutput(usable=True, category="tshirt", gender="men", colors=["navy"], occasion="casual")


async def test_a_photo_goes_straight_to_matches_with_budget_as_a_refinement(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    ai = VisionAI(SEEN)
    app = PhotoApp(catalog_sessions, redis, user_id, ai)

    ui = await app.start(str(await app.photo()))

    assert _banner(ui) is None
    ids = [c.id for c in ui.components]
    assert ids[0] == "deck"  # category, gender, colour came from the photo: no questions
    assert "q_budget" not in ids
    bar = next(c for c in ui.components if c.id == "next")
    assert "change_budget" in [s.id for s in bar.props.suggestions]  # type: ignore[union-attr]
    [payload] = ai.inputs
    assert isinstance(payload, PhotoInput)
    assert payload.image_urls[0].endswith("side=768&sig=ok")  # downscaled, signed


async def test_without_vision_ai_the_stylist_asks_instead(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    app = PhotoApp(catalog_sessions, redis, user_id, VisionAI(AIUnavailableError("off")))

    ui = await app.start(str(await app.photo()))

    assert "couldn't read the photo" in (_banner(ui) or "")  # the banner says what to type
    assert [c.type for c in ui.components][-1] == "text_input_bar"


async def test_a_photo_without_clothes_is_explained(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    app = PhotoApp(catalog_sessions, redis, user_id, VisionAI(PhotoOutput(usable=False)))

    ui = await app.start(str(await app.photo()))

    assert "can't find clothes" in (_banner(ui) or "")


@pytest.mark.parametrize("value", [None, "not-a-uuid", str(uuid.uuid4())])
async def test_unknown_or_missing_photos_are_explained(
    catalog_sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    user_id: uuid.UUID,
    value: str | None,
) -> None:
    ai = VisionAI(SEEN)
    app = PhotoApp(catalog_sessions, redis, user_id, ai)

    ui = await app.start(value)

    assert _banner(ui)
    assert ai.inputs == []  # no paid vision call for a photo we can't open


async def test_a_selfie_cannot_be_used_for_photo_search(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    ai = VisionAI(SEEN)
    app = PhotoApp(catalog_sessions, redis, user_id, ai)

    ui = await app.start(str(await app.photo("selfie")))

    assert "couldn't open that photo" in (_banner(ui) or "")
    assert ai.inputs == []


async def test_the_daily_photo_search_limit(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    app = PhotoApp(catalog_sessions, redis, user_id, VisionAI(SEEN), photo_limit=1)
    photo = str(await app.photo())

    await app.start(photo)
    ui = await app.start(photo)

    assert "today's photo searches" in (_banner(ui) or "")


async def test_a_photo_with_a_budget_reaches_a_deck(
    catalog_sessions: async_sessionmaker[AsyncSession], redis: Redis, user_id: uuid.UUID
) -> None:
    app = PhotoApp(catalog_sessions, redis, user_id, VisionAI(SEEN))
    ui = await app.start(str(await app.photo()))

    async def act(turn: int, action: Any) -> list[RenderEvent]:
        stream = await app.service.act(
            ui.session_id, user_id, ActionRequest(turn_id=turn, action=action), client_version=2
        )
        return [e for e in [x async for x in stream] if isinstance(e, RenderEvent)]

    await act(1, Shortcut(value="change_budget"))  # budget is a refinement after a photo
    renders = await act(2, SliderSet(component_id="q_budget", min_paise=0, max_paise=150_000))

    deck = next(c for c in renders[-1].envelope.components if isinstance(c, ProductSwipeDeck))
    assert len(deck.props.cards) >= 5  # S11: an outfit photo returns ≥ 5 in-budget items
    assert all(c.price_paise is not None and c.price_paise <= 150_000 for c in deck.props.cards)
