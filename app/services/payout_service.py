"""Payout service — manages advance and final settlement payouts.

Advance payout: 10% of earnings, paid when sale is PENDING.
Final settlement: Remaining balance after reconciliation.

Design decisions:
1. Advance payout is created by a background job, not in the API request path.
   This keeps the sale creation API fast and allows retry logic.

2. Payouts have their own idempotency keys to ensure exactly-once
   processing by the payment gateway.

3. We use the PAYMENT GATEWAY ABSTRACTION to actually send money.
   The gateway call is idempotent using the payout's idempotency key.
"""

from typing import Any

from app.core.enums import PayoutType, PayoutStatus, LedgerEntryType
from app.core.exceptions import (
    EntityNotFoundError,
    AdvanceAlreadyPaidError,
    PaymentGatewayError,
)
from app.core.state_machines import PayoutStateMachine
from app.db.unit_of_work import UnitOfWork
from app.config import settings


class PayoutService:
    """Service for managing payouts."""

    def create_advance_payout(self, uow: UnitOfWork, sale_id: str) -> dict:
        """Create an advance payout for a pending sale.

        Validates:
        - Sale exists and is PENDING
        - No advance payout already exists for this sale
        - Sale has a valid user

        Called by the advance payout background job.
        Each call is idempotent (checks for existing payout).
        """
        sale = uow.sales.get_for_update(sale_id)
        if not sale:
            raise EntityNotFoundError("Sale", str(sale_id))

        # Check if advance already exists
        existing = uow.payouts.get_by_sale_and_type(sale.id, PayoutType.ADVANCE)
        if existing:
            raise AdvanceAlreadyPaidError(str(sale_id))

        advance_amount = round(sale.earnings * settings.advance_payout_percentage, 2)

        import uuid

        payout_id = str(uuid.uuid4())

        from app.db.models.payout import Payout

        payout = Payout(
            id=payout_id,
            sale_id=sale.id,
            user_id=sale.user_id,
            amount=advance_amount,
            type=PayoutType.ADVANCE,
            status=PayoutStatus.PENDING,
            idempotency_key=f"advance_{sale_id}",
        )
        uow.payouts.add(payout)

        # Record in ledger
        uow.ledger.create_entry(
            user_id=sale.user_id,
            entry_type=LedgerEntryType.ADVANCE_PAYOUT,
            amount=advance_amount,
            reference_type="payout",
            reference_id=payout_id,
            description=f"Advance payout for sale {sale_id}: {advance_amount} ({settings.advance_payout_percentage * 100}% of {sale.earnings})",
            idempotency_key=f"advance_ledger_{sale_id}",
        )

        # Update cached balance
        uow.balances.update_balance(
            sale.user_id,
            available_delta=advance_amount,
        )

        # Audit log
        uow.audit.log(
            entity_type="Payout",
            entity_id=str(payout_id),
            action="created",
            new_values={
                "sale_id": str(sale_id),
                "user_id": str(sale.user_id),
                "amount": advance_amount,
                "type": PayoutType.ADVANCE.value,
                "status": PayoutStatus.PENDING.value,
            },
        )

        return {
            "payout_id": str(payout_id),
            "sale_id": str(sale_id),
            "user_id": str(sale.user_id),
            "amount": advance_amount,
            "type": PayoutType.ADVANCE.value,
        }

    def complete_payout(
        self,
        uow: UnitOfWork,
        payout_id: str,
        gateway_reference: str | None = None,
    ) -> dict:
        """Mark a payout as completed by the payment gateway.

        Called by:
        1. The payment gateway callback/webhook
        2. The recovery background job
        """
        payout = uow.payouts.get_for_update(payout_id)
        if not payout:
            raise EntityNotFoundError("Payout", str(payout_id))

        PayoutStateMachine.validate_transition(payout.status, PayoutStatus.COMPLETED)

        uow.payouts.update(
            payout,
            {
                "status": PayoutStatus.COMPLETED,
                "gateway_reference": gateway_reference,
            },
        )

        uow.audit.log(
            entity_type="Payout",
            entity_id=str(payout_id),
            action="completed",
            old_values={"status": PayoutStatus.PENDING.value},
            new_values={
                "status": PayoutStatus.COMPLETED.value,
                "gateway_reference": gateway_reference,
            },
        )

        return {
            "payout_id": str(payout_id),
            "status": PayoutStatus.COMPLETED.value,
        }

    def fail_payout(
        self,
        uow: UnitOfWork,
        payout_id: str,
        error_message: str | None = None,
    ) -> dict:
        """Mark a payout as failed.

        Note: For advance payouts, failure means the user doesn't get
        the money. The sale remains PENDING and another attempt can
        be made by the recovery job.
        """
        payout = uow.payouts.get_for_update(payout_id)
        if not payout:
            raise EntityNotFoundError("Payout", str(payout_id))

        PayoutStateMachine.validate_transition(payout.status, PayoutStatus.FAILED)

        uow.payouts.update(
            payout,
            {
                "status": PayoutStatus.FAILED,
                "gateway_response": error_message,
            },
        )

        uow.audit.log(
            entity_type="Payout",
            entity_id=str(payout_id),
            action="failed",
            old_values={"status": PayoutStatus.PENDING.value},
            new_values={
                "status": PayoutStatus.FAILED.value,
                "error_message": error_message,
            },
        )

        return {
            "payout_id": str(payout_id),
            "status": PayoutStatus.FAILED.value,
        }

    def process_pending_payouts_batch(
        self,
        uow: UnitOfWork,
        gateway: Any,
        batch_size: int = 100,
    ) -> dict:
        """Process a batch of pending payouts through the payment gateway.

        Called by the settlement background job.
        Implements at-least-once delivery: each payout is submitted to
        the gateway with its idempotency key for deduplication.
        """
        processed = 0
        succeeded = 0
        failed = 0

        payouts = uow.payouts.get_pending_payouts_batch(batch_size)
        for payout in payouts:
            processed += 1
            try:
                # Call payment gateway
                result = gateway.send_payout(
                    user_id=str(payout.user_id),
                    amount=payout.amount,
                    currency="INR",
                    idempotency_key=payout.idempotency_key,
                )

                if result["success"]:
                    self.complete_payout(
                        uow,
                        str(payout.id),
                        gateway_reference=result.get("reference"),
                    )
                    succeeded += 1
                else:
                    self.fail_payout(
                        uow,
                        str(payout.id),
                        error_message=result.get("error"),
                    )
                    failed += 1

            except PaymentGatewayError as e:
                # Gateway error — leave payout as PENDING for retry
                failed += 1

        uow.commit()

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
        }
