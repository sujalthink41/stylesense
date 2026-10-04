"""Imports every ORM model so `Base.metadata` is complete (Alembic autogenerate, drift test).

Add each new models module here.
"""

from stylesense.guards.outbox import OutboxMessage
from stylesense.infra.database import Base
from stylesense.modules.auth.models import RefreshToken
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
    "OutboxMessage",
    "RefreshToken",
    "User",
    "UserDevice",
]
