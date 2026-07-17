from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.enums import PayoutType, PayoutStatus
from app.db.models.payout import Payout
from app.db.repositories.base import BaseRepository


class PayoutRepository(BaseRepository[Payout]):
    """Repository for Payout entity."""

    def __init__(self, db: Session):
        super().__init__(db, Payout)

    def get_by_sale_and_type(self, sale_id: Any, payout_type: PayoutType) -> Payout | None:
        """Get payout for a specific sale and type.

        Used to check if an advance payout already exists for a sale.
        """
        stmt = select(Payout).where(and_(Payout.sale_id == sale_id, Payout.type == payout_type))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_idempotency_key(self, key: str) -> Payout | None:
        """Find a payout by its idempotency key."""
        stmt = select(Payout).where(Payout.idempotency_key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_pending_payouts_batch(self, batch_size: int = 100) -> list[Payout]:
        """Get batch of pending payouts for processing."""
        stmt = (
            select(Payout)
            .where(Payout.status == PayoutStatus.PENDING)
            .order_by(Payout.created_at)
            .limit(batch_size)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_by_user(self, user_id: Any, skip: int = 0, limit: int = 100) -> list[Payout]:
        """Get all payouts for a user."""
        stmt = (
            select(Payout)
            .where(Payout.user_id == user_id)
            .order_by(Payout.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())
