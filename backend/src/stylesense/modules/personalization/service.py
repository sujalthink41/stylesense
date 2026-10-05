"""Swipes, taste learning and Style DNA.

A swipe is one short transaction: insert (idempotent by unique key) → lock the profile row →
update taste in code → commit. No LLM, no outbox: the next deck must already reflect it.
"""

import uuid
from collections.abc import Callable

import structlog
from prometheus_client import CollectorRegistry, Counter

from stylesense.ai.gateway.exceptions import AIUnavailableError
from stylesense.infra.database import UnitOfWork
from stylesense.modules.catalog.exceptions import ProductNotFoundError
from stylesense.modules.catalog.ports import Embedder
from stylesense.modules.personalization.models import StyleProfile
from stylesense.modules.personalization.repository import PersonalizationRepository
from stylesense.modules.personalization.schemas import (
    Sizes,
    StyleOption,
    StyleOptions,
    StyleProfileUpdate,
    StyleProfileView,
    SwipeInput,
    SwipeReceipt,
    Taste,
)
from stylesense.modules.personalization.styles import (
    BOTTOM_SIZES,
    MAX_STYLES,
    SHOE_SIZES,
    STYLES,
    TOP_SIZES,
)
from stylesense.modules.personalization.taste import (
    AFFINITY_STEP,
    blend,
    mean,
    update_affinity,
    update_vector,
)
from stylesense.platform.clock import Clock

logger = structlog.get_logger(__name__)

SEED_WEIGHT = 0.5  # new Style DNA picks move an existing taste halfway, never erase it
SEED_AFFINITY = 2  # per tag of a picked style
TOP_TAGS = 5


class PersonalizationMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.swipes = Counter(
            "swipes", "Swipes received", ["direction", "outcome"], registry=registry
        )


class PersonalizationService:
    def __init__(
        self,
        uow: Callable[[], UnitOfWork],
        *,
        embedder: Embedder,
        clock: Clock,
        metrics: PersonalizationMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._embedder = embedder
        self._clock = clock
        self._metrics = metrics

    # ---------- swipes ----------

    async def record_swipe(self, user_id: uuid.UUID, swipe: SwipeInput) -> SwipeReceipt:
        async with self._uow() as uow:
            repo = PersonalizationRepository(uow.session)
            signal = await repo.product_signal(swipe.product_id)
            if signal is None:
                raise ProductNotFoundError
            recorded = await repo.add_swipe(
                user_id, swipe.product_id, swipe.session_id, swipe.direction
            )
            if recorded:
                profile = await repo.profile_for_update(user_id)
                if signal.embedding is not None:
                    profile.taste_vector = update_vector(
                        _vector(profile), signal.embedding, swipe.direction
                    )
                profile.tag_affinity = update_affinity(
                    profile.tag_affinity, signal.tags, AFFINITY_STEP[swipe.direction]
                )
                profile.swipe_count += 1
                profile.updated_at = self._clock.now()
        if self._metrics:
            outcome = "recorded" if recorded else "replay"
            self._metrics.swipes.labels(swipe.direction, outcome).inc()
        return SwipeReceipt(recorded=recorded)

    async def session_swipes(self, user_id: uuid.UUID, session_id: uuid.UUID) -> list[uuid.UUID]:
        async with self._uow() as uow:
            return list(
                await PersonalizationRepository(uow.session).session_swipes(user_id, session_id)
            )

    # ---------- Style DNA ----------

    @staticmethod
    def options() -> StyleOptions:
        return StyleOptions(
            styles=[
                StyleOption(id=key, label=style.label, image_url=style.image_url)
                for key, style in STYLES.items()
            ],
            max_styles=MAX_STYLES,
            top_sizes=list(TOP_SIZES),
            bottom_sizes=list(BOTTOM_SIZES),
            shoe_sizes=list(SHOE_SIZES),
        )

    async def profile(self, user_id: uuid.UUID) -> StyleProfileView:
        async with self._uow() as uow:
            profile = await PersonalizationRepository(uow.session).profile(user_id)
            return _view(profile)

    async def update_profile(
        self, user_id: uuid.UUID, update: StyleProfileUpdate
    ) -> StyleProfileView:
        """Idempotent full replace. Newly picked styles seed taste; existing taste is kept."""
        seed = await self._seed_for(update.styles)
        async with self._uow() as uow:
            profile = await PersonalizationRepository(uow.session).profile_for_update(user_id)
            added = [s for s in update.styles if s not in profile.styles]
            if added:
                if seed is not None:
                    profile.taste_vector = blend(_vector(profile), seed, SEED_WEIGHT)
                affinity = profile.tag_affinity
                for style in added:
                    affinity = update_affinity(affinity, STYLES[style].tags, SEED_AFFINITY)
                profile.tag_affinity = affinity
            profile.fit_preference = update.fit_preference
            profile.styles = update.styles
            profile.sizes = update.sizes.model_dump(exclude_none=True)
            profile.onboarding_done = True
            profile.updated_at = self._clock.now()
            view = _view(profile)
        logger.info("style_profile_updated", styles=update.styles, added=added)
        return view

    async def taste(self, user_id: uuid.UUID) -> Taste | None:
        async with self._uow() as uow:
            profile = await PersonalizationRepository(uow.session).profile(user_id)
        if profile is None:
            return None
        return Taste(
            fit_preference=profile.fit_preference,
            sizes=dict(profile.sizes),
            vector=_vector(profile),
            affinity={k: int(v) for k, v in profile.tag_affinity.items()},
        )

    async def _seed_for(self, styles: list[str]) -> list[float] | None:
        """Embeds the picked styles before the transaction (never hold a row lock over I/O)."""
        if not styles:
            return None
        try:
            vectors = await self._embedder.embed([STYLES[s].text for s in styles])
        except AIUnavailableError as exc:
            logger.info("style_seed_without_embedding", reason=str(exc))
            return None
        return mean(vectors)


def _vector(profile: StyleProfile) -> list[float] | None:
    return list(profile.taste_vector) if profile.taste_vector is not None else None


def _view(profile: StyleProfile | None) -> StyleProfileView:
    if profile is None:
        return StyleProfileView(
            fit_preference=None,
            styles=[],
            sizes=Sizes(),
            onboarding_done=False,
            swipe_count=0,
            top_tags=[],
        )
    liked = sorted(
        ((tag, value) for tag, value in profile.tag_affinity.items() if value > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return StyleProfileView(
        fit_preference=profile.fit_preference,
        styles=list(profile.styles),
        sizes=Sizes.model_validate(profile.sizes),
        onboarding_done=profile.onboarding_done,
        swipe_count=profile.swipe_count,
        top_tags=[tag for tag, _ in liked[:TOP_TAGS]],
    )
