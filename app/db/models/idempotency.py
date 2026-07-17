import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.base import Base


class IdempotencyKey(Base):
    """Idempotency tracking for all money-moving operations.

    When a client sends a request with an Idempotency-Key header:
    1. First request: Process normally, store the response keyed by the idempotency key
    2. Duplicate request: Return the stored response without processing

    This provides exactly-once semantics for the API layer.

    Columns:
        id: Auto-incrementing PK
        key: The idempotency key (unique, indexed)
        response_status: HTTP status code of the original response
        response_body: JSON string of the original response body
        created_at: When the key was first used (for TTL-based cleanup)

    Indexes:
        (key): UNIQUE — fast lookup for deduplication
    """

    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    response_status = Column(Integer, nullable=False)
    response_body = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
