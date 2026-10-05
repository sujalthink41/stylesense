import uuid
from typing import Protocol

from stylesense.modules.personalization.schemas import SwipeInput, SwipeReceipt, Taste


class TasteSource(Protocol):
    """What the stylist needs from personalization (implemented by PersonalizationService)."""

    async def taste(self, user_id: uuid.UUID) -> Taste | None: ...

    async def record_swipe(self, user_id: uuid.UUID, swipe: SwipeInput) -> SwipeReceipt: ...

    async def session_swipes(
        self, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[uuid.UUID]: ...
