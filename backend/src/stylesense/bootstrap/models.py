"""Imports every ORM model so `Base.metadata` is complete (Alembic autogenerate, drift test).

Add each new models module here.
"""

from stylesense.guards.outbox import OutboxMessage
from stylesense.infra.database import Base

__all__ = ["Base", "OutboxMessage"]
