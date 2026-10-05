"""Imports every ORM model so `Base.metadata` is complete (Alembic autogenerate, drift test).

Add each new models module here.
"""

from stylesense.ai.gateway.models import LlmModel, LlmTaskConfig, LlmUsage
from stylesense.guards.outbox import OutboxMessage
from stylesense.infra.database import Base
from stylesense.modules.auth.models import RefreshToken
from stylesense.modules.catalog.models import (
    Offer,
    OutboundClick,
    PriceSnapshot,
    Product,
    ProductImage,
    Store,
)
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
    "Consent",
    "LlmModel",
    "LlmTaskConfig",
    "LlmUsage",
    "Offer",
    "OutboundClick",
    "OutboxMessage",
    "PriceSnapshot",
    "Product",
    "ProductImage",
    "RefreshToken",
    "Store",
    "User",
    "UserDevice",
]
