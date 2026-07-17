from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session, joinedload

from app.core.enums import SaleStatus
from app.db.models.sale import Sale
from app.db.repositories.base import BaseRepository


class SaleRepository(BaseRepository[Sale]):
    """Repository for Sale entity."""

    def __init__(self, db: Session):
        super().__init__(db, Sale)

    def get_by_external_id(self, external_id: str) -> Sale | None:
        stmt = select(Sale).where(Sale.external_id == external_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_status(
        self,
        status: SaleStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Sale]:
        """Get sales by status regardless of user (admin view)."""
        stmt = (
            select(Sale)
            .where(Sale.status == status)
            .order_by(Sale.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def get_pending_sales_batch(
        self,
        batch_size: int = 100,
        offset: int = 0,
    ) -> Sequence[Sale]:
        """Get a batch of pending sales that haven't had advance payouts yet.

        Uses offset-based pagination. Excludes sales that already have an ADVANCE payout.
        Uses LEFT JOIN anti-join pattern for better performance than NOT IN.
        """
        from app.db.models.payout import Payout
        from app.core.enums import PayoutType

        stmt = (
            select(Sale)
            .outerjoin(
                Payout,
                and_(
                    Payout.sale_id == Sale.id,
                    Payout.type == PayoutType.ADVANCE,
                ),
            )
            .where(
                and_(
                    Sale.status == SaleStatus.PENDING,
                    Payout.id.is_(None),
                )
            )
            .options(joinedload(Sale.user), joinedload(Sale.brand))
            .order_by(Sale.created_at)
            .offset(offset)
            .limit(batch_size)
        )
        result = self.db.execute(stmt)
        return result.unique().scalars().all()

    def get_by_user_and_status(
        self,
        user_id: Any,
        status: SaleStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Sale]:
        """Get sales for a user, optionally filtered by status.

        When status is None, returns all statuses for the user.
        """
        stmt = select(Sale).where(Sale.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Sale.status == status)
        stmt = stmt.order_by(Sale.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def get_pending_sales_count(self) -> int:
        """Count pending sales without existing advance payouts."""
        from app.db.models.payout import Payout
        from app.core.enums import PayoutType

        stmt = (
            select(func.count(Sale.id))
            .outerjoin(
                Payout,
                and_(
                    Payout.sale_id == Sale.id,
                    Payout.type == PayoutType.ADVANCE,
                ),
            )
            .where(
                and_(
                    Sale.status == SaleStatus.PENDING,
                    Payout.id.is_(None),
                )
            )
        )
        return self.db.execute(stmt).scalar() or 0
