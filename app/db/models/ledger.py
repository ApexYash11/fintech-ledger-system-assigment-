import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Enum as SAEnum, Text
from sqlalchemy.orm import relationship

from app.core.enums import LedgerEntryType, Currency
from app.db.base import Base


class LedgerEntry(Base):
    """An immutable record of every money movement in the system.

    This is the SOURCE OF TRUTH for all balances. The user_balances
    table is a cached denormalization of this table.

    Once written, a ledger entry is NEVER modified or deleted.
    Corrections are made via offsetting entries (compensating transactions).

    Columns:
        id: UUID primary key
        user_id: FK to the user whose balance is affected
        entry_type: Classification of the movement (ADVANCE_PAYOUT, WITHDRAWAL, etc.)
        amount: Signed float — positive = credit to user, negative = debit from user
        currency: ISO 4217 currency code
        reference_type: The entity type that caused this entry (sale, payout, withdrawal)
        reference_id: The ID of the entity that caused this entry
        description: Human-readable explanation of the movement
        idempotency_key: Unique — prevents duplicate ledger entries
        created_at: Immutable timestamp (no updated_at — entries are never updated!)

    Indexes:
        (user_id, created_at): For calculating user balance over time
        (reference_type, reference_id): For traceability from any entity to ledger
        (idempotency_key): UNIQUE — idempotency enforcement
    """

    __tablename__ = "ledger_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_type = Column(SAEnum(LedgerEntryType), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default=Currency.INR.value, nullable=False)
    reference_type = Column(String(50), nullable=False)
    reference_id = Column(String(36), nullable=False)
    description = Column(Text, nullable=True)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    user = relationship("User", back_populates="ledger_entries")


from sqlalchemy import Index

LedgerEntry.__table_args__ = (
    Index("ix_ledger_user_created", "user_id", "created_at"),
    Index("ix_ledger_reference", "reference_type", "reference_id"),
)
