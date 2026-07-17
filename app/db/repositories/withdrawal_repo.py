from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from app.core.enums import WithdrawalStatus
from app.db.models.withdrawal import Withdrawal
from app.db.repositories.base import BaseRepository


class WithdrawalRepository(BaseRepository[Withdrawal]):
    """Repository for Withdrawal entity."""

    def __init__(self, db: Session):
        super().__init__(db, Withdrawal)

    def get_by_idempotency_key(self, key: str) -> Withdrawal | None:
        """Find a withdrawal by its idempotency key."""
        stmt = select(Withdrawal).where(Withdrawal.idempotency_key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_recent_withdrawal(self, user_id: Any, cooldown_hours: int = 24) -> Withdrawal | None:
        """Get the most recent withdrawal within the cooldown window.

        Used to enforce the 24-hour withdrawal cooldown.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
        stmt = (
            select(Withdrawal)
            .where(
                and_(
                    Withdrawal.user_id == user_id,
                    Withdrawal.created_at >= cutoff,
                    Withdrawal.status.in_(
                        [
                            WithdrawalStatus.PENDING,
                            WithdrawalStatus.PROCESSING,
                            WithdrawalStatus.COMPLETED,
                        ]
                    ),
                )
            )
            .order_by(Withdrawal.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_processing_withdrawals_batch(self, batch_size: int = 100) -> Sequence[Withdrawal]:
        """Get withdrawals stuck in PROCESSING for recovery job."""
        stmt = (
            select(Withdrawal)
            .where(Withdrawal.status == WithdrawalStatus.PROCESSING)
            .order_by(Withdrawal.updated_at)
            .limit(batch_size)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()

    def get_by_user(self, user_id: Any, skip: int = 0, limit: int = 100) -> Sequence[Withdrawal]:
        """Get all withdrawals for a user."""
        stmt = (
            select(Withdrawal)
            .where(Withdrawal.user_id == user_id)
            .order_by(Withdrawal.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()
