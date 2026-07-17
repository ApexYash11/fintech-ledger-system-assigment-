"""SQLAlchemy declarative base and common mixins.

All ORM models inherit from this base. Common columns
(id, created_at, updated_at) are defined here to avoid
repetition and ensure consistency.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models.

    Subclasses must define __tablename__ explicitly.
    """


class TimestampMixin:
    """Adds created_at and updated_at to any model."""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class VersionMixin:
    """Optimistic locking via integer version column.

    Incremented on every update. Application code checks the
    version matches the expected value before updating, preventing
    lost updates under concurrent access.
    """

    version = Column(Integer, default=1, nullable=False)
