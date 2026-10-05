"""Plays the mobile app against a fully wired stylist: personalization, looks, Style DNA."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stylesense.genui.actions import Action, ActionRequest
from stylesense.genui.components import CATALOG_VERSION, ProductSwipeDeck
from stylesense.genui.envelope import RenderEvent, UiEnvelope
from stylesense.infra.database import UnitOfWork
from stylesense.integrations.embeddings.hashing import HashingEmbedder
from stylesense.modules.catalog.service import CatalogService
from stylesense.modules.looks.service import Assistant, LookService
from stylesense.modules.personalization.service import PersonalizationService
from stylesense.modules.stylist.flows.style_dna import StyleDnaFlow
from stylesense.modules.stylist.flows.stylist import StylistFlow
from stylesense.modules.stylist.schemas import SessionCreate
from stylesense.modules.stylist.service import StylistService
from stylesense.modules.users.models import User
from tests.fakes.clock import FixedClock


class App:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
        *,
        ai: Assistant | None = None,
        version: int = CATALOG_VERSION,
    ) -> None:
        def uow() -> UnitOfWork:
            return UnitOfWork(sessions)

        self.personal = PersonalizationService(uow, embedder=HashingEmbedder(), clock=FixedClock())
        self.catalog = CatalogService(uow, clock=FixedClock(), embedder=HashingEmbedder())
        self.looks = LookService(self.catalog, ai)
        self.service = StylistService(
            uow,
            flows={
                "stylist": StylistFlow(self.catalog, ai, self.personal, self.looks),
                "style_dna": StyleDnaFlow(self.personal),
            },
            default_flow="stylist",
            entry_flows={"onboarding": "style_dna"},
            clock=FixedClock(),
        )
        self.user_id = user_id
        self.version = version
        self.screen: UiEnvelope | None = None

    async def start(self, entry: str, value: str | None = None) -> UiEnvelope:
        view = await self.service.start(
            self.user_id, SessionCreate(entry=entry, value=value), client_version=self.version
        )
        self.screen = view.ui
        return view.ui

    async def send(self, action: Action) -> UiEnvelope:
        assert self.screen is not None
        stream = await self.service.act(
            self.screen.session_id,
            self.user_id,
            ActionRequest(turn_id=self.screen.turn_id, action=action),
            client_version=self.version,
        )
        renders = [e for e in [event async for event in stream] if isinstance(e, RenderEvent)]
        self.screen = renders[-1].envelope
        return self.screen

    @property
    def session_id(self) -> uuid.UUID:
        assert self.screen is not None
        return self.screen.session_id

    def types(self) -> list[str]:
        assert self.screen is not None
        return [c.type for c in self.screen.components]

    def component(self, component_id: str) -> Any:
        assert self.screen is not None
        return next(c for c in self.screen.components if c.id == component_id)

    def has(self, component_id: str) -> bool:
        assert self.screen is not None
        return any(c.id == component_id for c in self.screen.components)

    def deck(self) -> ProductSwipeDeck:
        assert self.screen is not None
        return next(c for c in self.screen.components if isinstance(c, ProductSwipeDeck))

    async def refill(self, *, exclude: list[uuid.UUID] | None = None, limit: int = 10) -> Any:
        return await self.service.deck(
            self.session_id, self.user_id, exclude=exclude or [], limit=limit
        )


async def new_user(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = User(email=f"{uuid.uuid4().hex}@example.com")
        s.add(user)
    return user.id
