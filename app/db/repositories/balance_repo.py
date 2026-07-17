from typing import Any

from sqlalchemy import case, select, text, update
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
        stmt = select(UserBalance).where(UserBalance.user_id == user_id).with_for_update()
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

        Uses an UPSERT (INSERT ON CONFLICT DO UPDATE) for atomicity.
        Clamps to zero to prevent negative balances (safety net).
        """
        import uuid
        from datetime import datetime, timezone

        dialect = self.db.bind.dialect.name if self.db.bind else "sqlite"

        if dialect == "postgresql":
            stmt = text("""
                INSERT INTO user_balances (id, user_id, available_balance, pending_balance, currency, created_at, updated_at, version)
                VALUES (:id, :user_id, GREATEST(0.0, :available_delta), GREATEST(0.0, :pending_delta), 'INR', NOW(), NOW(), 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    available_balance = GREATEST(0.0, user_balances.available_balance + :available_delta2),
                    pending_balance = GREATEST(0.0, user_balances.pending_balance + :pending_delta2),
                    updated_at = NOW(),
                    version = user_balances.version + 1
                RETURNING *
            """)
            result = self.db.execute(
                stmt,
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "available_delta": available_delta,
                    "pending_delta": pending_delta,
                    "available_delta2": available_delta,
                    "pending_delta2": pending_delta,
                },
            )
            row = result.fetchone()
            self.db.flush()
            return self.get_by_user(user_id)
        else:
            stmt = (
                update(UserBalance)
                .where(UserBalance.user_id == user_id)
                .values(
                    available_balance=case(
                        (UserBalance.available_balance + available_delta < 0, 0.0),
                        else_=UserBalance.available_balance + available_delta,
                    ),
                    pending_balance=case(
                        (UserBalance.pending_balance + pending_delta < 0, 0.0),
                        else_=UserBalance.pending_balance + pending_delta,
                    ),
                )
            )
            result = self.db.execute(stmt)

            if result.rowcount == 0:
                balance = UserBalance(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    available_balance=max(0.0, available_delta),
                    pending_balance=max(0.0, pending_delta),
                )
                self.db.add(balance)
                self.db.flush()
                return balance

            self.db.flush()
            return self.get_by_user(user_id)
