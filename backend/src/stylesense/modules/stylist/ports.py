import uuid
from typing import Protocol

from stylesense.modules.personalization.schemas import SwipeInput, SwipeReceipt, Taste


class PhotoSource(Protocol):
    """Resolves a user's photo-search upload to a URL a vision model can fetch
    (implemented by UploadsService; it also spends the user's daily photo-search credit)."""

    async def photo_for_search(self, user_id: uuid.UUID, upload_id: uuid.UUID) -> str: ...


class LiveCatalog(Protocol):
    """Tops up the catalog from live store search when it has too little for a request
    (implemented by integrations.sources.web_search.WebCatalog). Returns products added."""

    async def refresh(self, text: str, *, category: str | None, gender: str | None) -> int: ...


class TasteSource(Protocol):
    """What the stylist needs from personalization (implemented by PersonalizationService)."""

    async def taste(self, user_id: uuid.UUID) -> Taste | None: ...

    async def record_swipe(self, user_id: uuid.UUID, swipe: SwipeInput) -> SwipeReceipt: ...

    async def session_swipes(
        self, user_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[uuid.UUID]: ...
