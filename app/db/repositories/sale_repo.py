from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.orm import Session, joinedload

from app.core.enums import SaleStatus
from app.db.models.sale import Sale
from app.db.repositories.base import BaseRepository


class SaleRepository(BaseRepository[Sale]):
    """Repository for Sale entity.

    Provides queries for:
    - Finding pending sales eligible for advance payout
    - Checking for duplicate external IDs
    - Loading sales with user/brand relationships
    """

    def __init__(self, db: Session):
        super().__init__(db, Sale)

    def get_by_external_id(self, external_id: str) -> Sale | None:
        """Find a sale by its external tracking ID."""
        stmt = select(Sale).where(Sale.external_id == external_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_pending_sales_batch(
        self,
        batch_size: int = 100,
        offset: int = 0,
    ) -> Sequence[Sale]:
        """Get a batch of pending sales that haven't had advance payouts yet.

        Uses offset-based pagination for simplicity. For production at scale,
        this would use keyset pagination (seek method) for better performance.

        The query excludes sales that already have an ADVANCE payout.
        """
        from app.db.models.payout import Payout
        from app.core.enums import PayoutType

        # Subquery: sales that already have an advance payout
        subq = select(Payout.sale_id).where(Payout.type == PayoutType.ADVANCE).subquery()

        stmt = (
            select(Sale)
            .where(
                and_(
                    Sale.status == SaleStatus.PENDING,
                    Sale.id.notin_(select(subq.c.sale_id)),
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
        status: SaleStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Sale]:
        """Get sales for a specific user filtered by status."""
        stmt = (
            select(Sale)
            .where(and_(Sale.user_id == user_id, Sale.status == status))
            .order_by(Sale.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = self.db.execute(stmt)
        return result.scalars().all()

    def get_pending_sales_count(self) -> int:
        """Count pending sales that haven't had advance payouts."""
        from app.db.models.payout import Payout
        from app.core.enums import PayoutType

        subq = select(Payout.sale_id).where(Payout.type == PayoutType.ADVANCE).subquery()

        stmt = select(Sale).where(
            and_(
                Sale.status == SaleStatus.PENDING,
                Sale.id.notin_(select(subq.c.sale_id)),
            )
        )
        return len(self.db.execute(stmt).scalars().all())
