from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.user_balance import UserBalance
from app.db.repositories.base import BaseRepository


class BalanceRepository(BaseRepository[UserBalance]):
    """Repository for cached UserBalance entity."""

    def __init__(self, db: Session):
        super().__init__(db, UserBalance)

    def get_by_user(self, user_id: Any) -> UserBalance | None:
        """Get balance row for a specific user."""
        stmt = select(UserBalance).where(UserBalance.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_user_for_update(self, user_id: Any) -> UserBalance | None:
        """Get balance row with SELECT FOR UPDATE (within transaction)."""
        stmt = select(UserBalance).where(UserBalance.user_id == user_id)
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(self, user_id: Any) -> UserBalance:
        """Get existing balance or create a new one for the user."""
        balance = self.get_by_user(user_id)
        if balance is None:
            import uuid
            from datetime import datetime, timezone

            balance = UserBalance(
                id=str(uuid.uuid4()),
                user_id=user_id,
                available_balance=0.0,
                pending_balance=0.0,
            )
            self.db.add(balance)
            self.db.flush()
        return balance

    def update_balance(
        self,
        user_id: Any,
        available_delta: float = 0.0,
        pending_delta: float = 0.0,
    ) -> UserBalance:
        """Atomically update a user's cached balance.

        Uses an UPDATE statement for atomicity rather than
        read-modify-write, avoiding race conditions.
        """
        import uuid
        from datetime import datetime, timezone

        balance = self.get_by_user(user_id)
        if balance is None:
            balance = UserBalance(
                id=str(uuid.uuid4()),
                user_id=user_id,
                available_balance=max(0.0, available_delta),
                pending_balance=max(0.0, pending_delta),
            )
            self.db.add(balance)
        else:
            balance.available_balance = max(0.0, balance.available_balance + available_delta)
            balance.pending_balance = max(0.0, balance.pending_balance + pending_delta)

        self.db.flush()
        return balance
