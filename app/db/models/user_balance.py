import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.enums import Currency
from app.db.base import Base, TimestampMixin, VersionMixin


class UserBalance(Base, TimestampMixin, VersionMixin):
    """Cached balance for a user.

    This is a DENORMALIZATION of the ledger for fast reads.
    The SOURCE OF TRUTH is the ledger_entries table.

    Balance is recalculated from ledger entries periodically
    and on every write. Optimistic locking (version column)
    prevents concurrent write conflicts.

    Columns:
        id: UUID primary key
        user_id: FK unique — one balance row per user
        available_balance: Funds available for withdrawal
        pending_balance: Funds pending (awaiting settlement)
        currency: ISO 4217 currency code
        last_calculated_at: When the balance was last synced with the ledger
    """

    __tablename__ = "user_balances"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    available_balance = Column(Numeric(12, 2), default=0.0, nullable=False)
    pending_balance = Column(Numeric(12, 2), default=0.0, nullable=False)
    currency = Column(String(3), default=Currency.INR.value, nullable=False)
    last_calculated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="balance")
