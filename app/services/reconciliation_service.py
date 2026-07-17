"""Reconciliation service — handles admin reconciliation of sales.

When a sale is reconciled:
- APPROVED: Remaining payout = Earnings - Advance Paid (if any)
- REJECTED: Advance becomes a negative adjustment against future payouts

This is a CRITICAL financial operation — every step uses the Unit of Work
pattern to ensure atomicity.

Design decision: Why use pessimistic locking (SELECT FOR UPDATE)?
- Prevents concurrent reconciliation of the same sale
- If two admin requests arrive simultaneously, one will wait and then
  see the updated status, preventing double processing
- Alternative: Optimistic locking (version check) — rejected because
  the second request would fail with a retryable error, creating a
  poor admin experience

Tradeoff: Row locks can cause contention at high throughput.
Mitigation: Reconciliation is an admin operation, not user-facing.
Admin operations have much lower concurrency requirements.
"""

from typing import Any

from app.core.enums import SaleStatus, PayoutType, LedgerEntryType
from app.core.exceptions import (
    EntityNotFoundError,
    SaleAlreadyReconciledError,
    InvalidStateTransitionError,
)
from app.core.state_machines import SaleStateMachine
from app.db.unit_of_work import UnitOfWork


class ReconciliationService:
    """Service for admin reconciliation of sales."""

    def reconcile_sale(
        self,
        uow: UnitOfWork,
        sale_id: str,
        admin_id: str,
        decision: str,
        notes: str | None = None,
        idempotency_key: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Reconcile a pending sale to APPROVED or REJECTED.

        Workflow:
        1. Lock the sale row (SELECT FOR UPDATE)
        2. Validate current state is PENDING
        3. Validate state transition (PENDING -> APPROVED|REJECTED)
        4. Update sale status
        5. If APPROVED: Calculate remaining payout, create final settlement
        6. If REJECTED: Create negative adjustment ledger entry
        7. Audit log everything

        All steps within a single transaction.
        """
        from datetime import datetime, timezone

        # 1. Lock and load the sale
        sale = uow.sales.get_for_update(sale_id)
        if not sale:
            raise EntityNotFoundError("Sale", str(sale_id))

        # 2. Validate current state
        if sale.status != SaleStatus.PENDING:
            raise SaleAlreadyReconciledError(sale_id, sale.status.value)

        # 3. Validate state transition
        target_status = SaleStatus(decision.upper())
        SaleStateMachine.validate_transition(sale.status, target_status)

        old_status = sale.status.value

        # 4. Update sale
        sale.status = target_status
        sale.reconciled_by = admin_id
        sale.reconciled_at = datetime.now(timezone.utc)
        sale.notes = notes
        sale.version += 1

        # 5. Handle financial implications
        result = {
            "sale_id": str(sale_id),
            "decision": target_status.value,
        }

        if target_status == SaleStatus.APPROVED:
            result.update(self._handle_approval(uow, sale, idempotency_key))
        else:  # REJECTED
            result.update(self._handle_rejection(uow, sale, idempotency_key))

        # 6. Audit log
        uow.audit.log(
            entity_type="Sale",
            entity_id=str(sale_id),
            action="reconciled",
            old_values={"status": old_status},
            new_values={
                "status": target_status.value,
                "reconciled_by": str(admin_id),
                "notes": notes,
            },
            changed_by=str(admin_id),
            ip_address=ip_address,
            idempotency_key=idempotency_key,
        )

        result["status"] = target_status.value
        return result

    def _handle_approval(
        self,
        uow: UnitOfWork,
        sale: Any,
        idempotency_key: str | None,
    ) -> dict:
        """Handle approved sale — calculate and create final settlement.

        Remaining payout = Earnings - Advance Paid
        If no advance was paid, full earnings are payed out.
        """
        from app.core.enums import PayoutType, PayoutStatus

        # Check if advance payout was made
        advance_payout = uow.payouts.get_by_sale_and_type(sale.id, PayoutType.ADVANCE)

        advance_amount = advance_payout.amount if advance_payout else 0.0
        remaining = sale.earnings - advance_amount

        if remaining > 0:
            # Create final settlement payout
            import uuid

            payout_id = str(uuid.uuid4())
            from app.db.models.payout import Payout

            final_payout = Payout(
                id=payout_id,
                sale_id=sale.id,
                user_id=sale.user_id,
                amount=remaining,
                type=PayoutType.FINAL_SETTLEMENT,
                status=PayoutStatus.PENDING,
                idempotency_key=f"{idempotency_key}_final"
                if idempotency_key
                else str(uuid.uuid4()),
            )
            uow.payouts.add(final_payout)

            # Create ledger entry
            uow.ledger.create_entry(
                user_id=sale.user_id,
                entry_type=LedgerEntryType.FINAL_PAYOUT,
                amount=remaining,
                reference_type="payout",
                reference_id=payout_id,
                description=f"Final settlement for sale {sale.id} (earnings: {sale.earnings}, advance: {advance_amount})",
                idempotency_key=f"{idempotency_key}_ledger" if idempotency_key else None,
            )

            return {
                "remaining_payout": remaining,
                "final_payout_id": str(payout_id),
                "advance_recovered": False,
            }
        elif remaining < 0:
            # Advance exceeded earnings — this shouldn't happen normally
            # but handle it gracefully by noting the excess as adjustment
            return {
                "remaining_payout": 0,
                "advance_recovered": True,
                "excess_advance": abs(remaining),
            }
        else:
            return {
                "remaining_payout": 0,
                "advance_recovered": True,
            }

    def _handle_rejection(
        self,
        uow: UnitOfWork,
        sale: Any,
        idempotency_key: str | None,
    ) -> dict:
        """Handle rejected sale — create negative adjustment.

        If advance was paid, the user now owes that money.
        The advance becomes a negative adjustment against future payouts.

        We record this as a ledger entry so the user's balance reflects
        the debt.
        """
        # Check if advance payout was made
        advance_payout = uow.payouts.get_by_sale_and_type(sale.id, PayoutType.ADVANCE)

        if advance_payout and advance_payout.amount > 0:
            # Create negative adjustment ledger entry
            # This reduces the user's available balance
            uow.ledger.create_entry(
                user_id=sale.user_id,
                entry_type=LedgerEntryType.NEGATIVE_ADJUSTMENT,
                amount=-advance_payout.amount,
                reference_type="sale",
                reference_id=sale.id,
                description=f"Negative adjustment for rejected sale {sale.id} (advance {advance_payout.amount} must be repaid)",
                idempotency_key=f"{idempotency_key}_neg" if idempotency_key else None,
            )

            # Update cached balance
            uow.balances.update_balance(
                sale.user_id,
                available_delta=-advance_payout.amount,
            )

            return {
                "advance_recovered": True,
                "advance_amount": advance_payout.amount,
                "adjustment": -advance_payout.amount,
            }

        return {"advance_recovered": False, "advance_amount": 0}

    def get_pending_sales(
        self,
        uow: UnitOfWork,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """List all pending sales needing reconciliation (admin view)."""
        from app.db.repositories.sale_repo import SaleRepository

        repo = SaleRepository(uow.db)
        sales = repo.get_by_status(SaleStatus.PENDING, skip, limit)

        return [
            {
                "id": str(s.id),
                "user_id": str(s.user_id),
                "brand_id": str(s.brand_id),
                "external_id": s.external_id,
                "earnings": s.earnings,
                "status": s.status.value,
                "currency": s.currency,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sales
        ]
