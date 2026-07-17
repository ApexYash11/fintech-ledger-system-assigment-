from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.core.enums import LedgerEntryType
from app.db.models.ledger import LedgerEntry
from app.db.repositories.base import BaseRepository


class LedgerRepository(BaseRepository[LedgerEntry]):
    """Repository for LedgerEntry entity.

    The ledger is the SOURCE OF TRUTH for all financial data.
    These queries are used for balance calculation and audit.
    """

    def __init__(self, db: Session):
        super().__init__(db, LedgerEntry)

    def get_by_idempotency_key(self, key: str) -> LedgerEntry | None:
        """Check if a ledger entry already exists for this idempotency key."""
        stmt = select(LedgerEntry).where(LedgerEntry.idempotency_key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_balance(self, user_id: Any) -> float:
        """Calculate actual user balance by summing all ledger entries.

        This is the SOURCE OF TRUTH balance calculation.
        The cached UserBalance table is derived from this.
        """
        stmt = select(func.sum(LedgerEntry.amount)).where(LedgerEntry.user_id == user_id)
        result = self.db.execute(stmt).scalar()
        return float(result) if result is not None else 0.0

    def get_user_entries(
        self,
        user_id: Any,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[LedgerEntry]:
        """Get all ledger entries for a user (paginated)."""
        stmt = (
            select(LedgerEntry)
            .where(LedgerEntry.user_id == user_id)
            .order_by(LedgerEntry.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()

    def get_entries_by_reference(
        self, reference_type: str, reference_id: Any
    ) -> Sequence[LedgerEntry]:
        """Get all ledger entries referencing a specific entity."""
        stmt = (
            select(LedgerEntry)
            .where(
                and_(
                    LedgerEntry.reference_type == reference_type,
                    LedgerEntry.reference_id == reference_id,
                )
            )
            .order_by(LedgerEntry.created_at)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()

    def create_entry(
        self,
        user_id: Any,
        entry_type: LedgerEntryType,
        amount: float,
        reference_type: str,
        reference_id: Any,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> LedgerEntry:
        """Create a new immutable ledger entry.

        This is the ONLY way money movements should be recorded.
        """
        import uuid

        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            entry_type=entry_type,
            amount=amount,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )
        self.db.add(entry)
        self.db.flush()
        return entry
