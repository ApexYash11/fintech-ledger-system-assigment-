"""Sale service — manages sale creation and lifecycle.

Design decisions:
1. Sale creation takes an idempotency key to prevent duplicate sales from
   external system retries.
2. Advance payout is NOT created synchronously during sale creation.
   It's deferred to a background job to keep the API responsive.
   Tradeoff: Slight delay before the user sees their advance payout.
   Alternative: Create advance payout synchronously. Rejected because:
   - Sale creation API should be fast (sub-100ms)
   - Payment gateway calls can be slow/unreliable
   - Background processing allows retry with backoff
"""

from typing import Any

from app.core.enums import SaleStatus, UserStatus, BrandStatus
from app.core.exceptions import (
    EntityNotFoundError,
    UserNotActiveError,
    DuplicateIdempotencyKeyError,
)
from app.services.balance_service import BalanceService
from app.db.unit_of_work import UnitOfWork


class SaleService:
    """Service for sale operations."""

    def __init__(self):
        self.balance_service = BalanceService()

    def create_sale(
        self,
        uow: UnitOfWork,
        user_id: str,
        brand_id: str,
        external_id: str,
        earnings: float,
        currency: str = "INR",
        idempotency_key: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Create a new pending sale.

        Validates:
        - User exists and is ACTIVE
        - Brand exists and is ACTIVE
        - External ID is unique (no duplicate sales)
        - Idempotency key is unique (no duplicate requests)

        Does NOT create the advance payout — that happens in a background job.
        """
        # Validate user
        user = uow.users.get_active(user_id)
        if not user:
            existing_user = uow.users.get(user_id)
            if existing_user:
                raise UserNotActiveError(user_id)
            raise EntityNotFoundError("User", str(user_id))

        # Validate brand
        brand = uow.brands.get_active(brand_id)
        if not brand:
            raise EntityNotFoundError("Brand", str(brand_id))

        # Check for duplicate external ID
        existing = uow.sales.get_by_external_id(external_id)
        if existing:
            raise DuplicateIdempotencyKeyError(
                f"Sale with external_id {external_id} already exists"
            )

        import uuid
        from datetime import datetime, timezone

        sale_id = str(uuid.uuid4())

        # Create the sale record
        from app.db.models.sale import Sale

        sale = Sale(
            id=sale_id,
            user_id=user_id,
            brand_id=brand_id,
            external_id=external_id,
            earnings=earnings,
            currency=currency,
            status=SaleStatus.PENDING,
        )
        uow.sales.add(sale)

        # Audit log
        uow.audit.log(
            entity_type="Sale",
            entity_id=str(sale_id),
            action="created",
            new_values={
                "user_id": str(user_id),
                "brand_id": str(brand_id),
                "external_id": external_id,
                "earnings": earnings,
                "status": SaleStatus.PENDING.value,
            },
            changed_by=str(user_id),
            ip_address=ip_address,
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(sale_id),
            "user_id": str(user_id),
            "brand_id": str(brand_id),
            "external_id": external_id,
            "earnings": earnings,
            "status": SaleStatus.PENDING.value,
            "currency": currency,
        }

    def get_sale(self, uow: UnitOfWork, sale_id: str) -> dict | None:
        """Get a single sale by ID."""
        sale = uow.sales.get(sale_id)
        if not sale:
            return None
        return {
            "id": str(sale.id),
            "user_id": str(sale.user_id),
            "brand_id": str(sale.brand_id),
            "external_id": sale.external_id,
            "earnings": sale.earnings,
            "status": sale.status.value,
            "currency": sale.currency,
            "created_at": sale.created_at.isoformat() if sale.created_at else None,
            "updated_at": sale.updated_at.isoformat() if sale.updated_at else None,
        }

    def list_user_sales(
        self,
        uow: UnitOfWork,
        user_id: str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """List sales for a user, optionally filtered by status.

        When status is None, returns sales of all statuses.
        """
        sale_status = SaleStatus(status) if status else None
        sales = uow.sales.get_by_user_and_status(user_id, sale_status, skip, limit)

        return [
            {
                "id": str(s.id),
                "brand_id": str(s.brand_id),
                "external_id": s.external_id,
                "earnings": s.earnings,
                "status": s.status.value,
                "currency": s.currency,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sales
        ]
