"""Imports every ORM model so `Base.metadata` is complete (Alembic autogenerate, drift test).

Add each new models module here.
"""

from stylesense.ai.gateway.models import LlmModel, LlmTaskConfig, LlmUsage
from stylesense.guards.outbox import OutboxMessage
from stylesense.infra.database import Base
from stylesense.modules.auth.models import RefreshToken
from stylesense.modules.boards.models import Board, BoardItem
from stylesense.modules.catalog.models import (
    Offer,
    OutboundClick,
    PriceSnapshot,
    Product,
    ProductImage,
    Store,
)
from stylesense.modules.personalization.models import StyleProfile, Swipe
from stylesense.modules.polls.models import Poll, PollOption, PollVote
from stylesense.modules.sharing.models import Share
from stylesense.modules.stylist.models import SessionEvent, StylistSession
from stylesense.modules.users.models import (
    AccountDeletion,
    AuthIdentity,
    Consent,
    User,
    UserDevice,
)

__all__ = [
    "AccountDeletion",
    "AuthIdentity",
    "Base",
    "Board",
    "BoardItem",
    "Consent",
    "LlmModel",
    "LlmTaskConfig",
    "LlmUsage",
    "Offer",
    "OutboundClick",
    "OutboxMessage",
    "Poll",
    "PollOption",
    "PollVote",
    "PriceSnapshot",
    "Product",
    "ProductImage",
    "RefreshToken",
    "SessionEvent",
    "Share",
    "Store",
    "StyleProfile",
    "StylistSession",
    "Swipe",
    "User",
    "UserDevice",
]
