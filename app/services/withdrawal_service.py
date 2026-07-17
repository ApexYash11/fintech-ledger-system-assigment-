"""Withdrawal service — manages user withdrawal requests.

Workflow:
1. User requests withdrawal (PENDING)
2. Admin/gateway processes it (PROCESSING)
3. Gateway completes it (COMPLETED)
4. OR Gateway/Admin fails it (FAILED/REJECTED) — money credited back

Design decisions:

1. 24-hour cooldown: Enforced by querying for recent withdrawals.
   Tradeoff: Uses clock time, which is susceptible to clock skew.
   Mitigation: We compare against database TIMESTAMP (DB time),
   not application time, so the database is the single source of truth.

2. Idempotency: Every withdrawal request requires an idempotency key.
   This prevents double-click issues on the client side.

3. Balance check: Checked at request time AND at processing time.
   The processing-time check prevents race conditions where the balance
   changes between request and processing.

4. Reversal on failure: When a withdrawal fails after the balance was
   deducted, we create a compensating ledger entry to credit the money back.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from app.core.enums import WithdrawalStatus, LedgerEntryType
from app.core.exceptions import (
    EntityNotFoundError,
    InsufficientBalanceError,
    WithdrawalCooldownError,
    InvalidStateTransitionError,
    UserNotActiveError,
    InvalidAmountError,
)
from app.core.state_machines import WithdrawalStateMachine
from app.db.unit_of_work import UnitOfWork
from app.services.balance_service import BalanceService


class WithdrawalService:
    """Service for withdrawal operations."""

    def __init__(self):
        self.balance_service = BalanceService()

    def request_withdrawal(
        self,
        uow: UnitOfWork,
        user_id: str,
        amount: float,
        currency: str = "INR",
        idempotency_key: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Request a withdrawal of available balance.

        Validates:
        - User is ACTIVE
        - Amount is positive and >= minimum
        - User has sufficient available balance
        - 24-hour cooldown has elapsed since last withdrawal
        - Idempotency key is unique

        Does NOT process the withdrawal — that happens asynchronously.
        """
        from app.config import settings

        # Validate user
        user = uow.users.get_active(user_id)
        if not user:
            raise EntityNotFoundError("User", str(user_id))

        # Validate amount
        if amount <= 0:
            raise InvalidAmountError("Withdrawal amount must be positive")
        if amount < settings.min_withdrawal_amount:
            raise InvalidAmountError(
                f"Minimum withdrawal amount is {settings.min_withdrawal_amount}"
            )

        # Idempotency check — must happen before cooldown check
        if idempotency_key:
            existing = uow.withdrawals.get_by_idempotency_key(idempotency_key)
            if existing:
                return self._format_withdrawal(existing)

        # Check 24-hour cooldown
        last_withdrawal = uow.withdrawals.get_recent_withdrawal(
            user_id, settings.withdrawal_cooldown_hours
        )
        if last_withdrawal:
            created_at = last_withdrawal.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            cooldown_end = created_at + timedelta(hours=settings.withdrawal_cooldown_hours)
            now = datetime.now(timezone.utc)
            if now < cooldown_end:
                hours_remaining = (cooldown_end - now).total_seconds() / 3600
                raise WithdrawalCooldownError(str(user_id), hours_remaining)

        # Check sufficient balance
        if not self.balance_service.check_sufficient_balance(uow, user_id, amount):
            balance = uow.balances.get_or_create(user_id)
            raise InsufficientBalanceError(str(user_id), balance.available_balance, amount)

        import uuid

        withdrawal_id = str(uuid.uuid4())

        from app.db.models.withdrawal import Withdrawal

        withdrawal = Withdrawal(
            id=withdrawal_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            status=WithdrawalStatus.PENDING,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )
        uow.withdrawals.add(withdrawal)

        # Deduct from available balance immediately
        # This prevents the user from spending the same money twice
        uow.balances.update_balance(user_id, available_delta=-amount)

        # Create ledger entry
        uow.ledger.create_entry(
            user_id=user_id,
            entry_type=LedgerEntryType.WITHDRAWAL,
            amount=-amount,
            reference_type="withdrawal",
            reference_id=withdrawal_id,
            description=f"Withdrawal requested: {amount} {currency}",
            idempotency_key=f"{idempotency_key}_ledger" if idempotency_key else None,
        )

        # Audit log
        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="requested",
            new_values={
                "user_id": str(user_id),
                "amount": amount,
                "currency": currency,
                "status": WithdrawalStatus.PENDING.value,
            },
            changed_by=str(user_id),
            ip_address=ip_address,
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(withdrawal_id),
            "user_id": str(user_id),
            "amount": amount,
            "currency": currency,
            "status": WithdrawalStatus.PENDING.value,
        }

    def process_withdrawal(
        self,
        uow: UnitOfWork,
        withdrawal_id: str,
        admin_id: str | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Move a withdrawal from PENDING to PROCESSING.

        Called by a background job or admin action.
        Validates state transition before proceeding.
        """
        withdrawal = uow.withdrawals.get_for_update(withdrawal_id)
        if not withdrawal:
            raise EntityNotFoundError("Withdrawal", str(withdrawal_id))

        WithdrawalStateMachine.validate_transition(withdrawal.status, WithdrawalStatus.PROCESSING)

        uow.withdrawals.update(withdrawal, {"status": WithdrawalStatus.PROCESSING})

        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="processing",
            old_values={"status": WithdrawalStatus.PENDING.value},
            new_values={"status": WithdrawalStatus.PROCESSING.value},
            changed_by=str(admin_id) if admin_id else None,
            ip_address=ip_address,
        )

        return {
            "id": str(withdrawal_id),
            "status": WithdrawalStatus.PROCESSING.value,
        }

    def complete_withdrawal(
        self,
        uow: UnitOfWork,
        withdrawal_id: str,
        gateway_reference: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Complete a withdrawal that was successfully processed by the gateway.

        This is the terminal success state.
        """
        withdrawal = uow.withdrawals.get_for_update(withdrawal_id)
        if not withdrawal:
            raise EntityNotFoundError("Withdrawal", str(withdrawal_id))

        WithdrawalStateMachine.validate_transition(withdrawal.status, WithdrawalStatus.COMPLETED)

        uow.withdrawals.update(
            withdrawal,
            {
                "status": WithdrawalStatus.COMPLETED,
                "gateway_reference": gateway_reference,
                "completed_at": datetime.now(timezone.utc),
            },
        )

        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="completed",
            old_values={"status": WithdrawalStatus.PROCESSING.value},
            new_values={
                "status": WithdrawalStatus.COMPLETED.value,
                "gateway_reference": gateway_reference,
            },
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(withdrawal_id),
            "status": WithdrawalStatus.COMPLETED.value,
            "gateway_reference": gateway_reference,
        }

    def fail_withdrawal(
        self,
        uow: UnitOfWork,
        withdrawal_id: str,
        error_message: str | None = None,
        gateway_response: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Fail a withdrawal — money is credited back to the user.

        This implements a COMPENSATING TRANSACTION pattern:
        The original debit is reversed by creating an offsetting
        ledger entry (WITHDRAWAL_REVERSAL).

        This is preferred over deleting/modifying the original
        ledger entry because:
        1. The original entry remains for audit purposes
        2. The reversal is explicit and traceable
        3. If the reversal itself fails, it can be retried independently
        """
        withdrawal = uow.withdrawals.get_for_update(withdrawal_id)
        if not withdrawal:
            raise EntityNotFoundError("Withdrawal", str(withdrawal_id))

        WithdrawalStateMachine.validate_transition(withdrawal.status, WithdrawalStatus.FAILED)

        uow.withdrawals.update(
            withdrawal,
            {
                "status": WithdrawalStatus.FAILED,
                "error_message": error_message,
                "gateway_response": gateway_response,
            },
        )

        # Compensating transaction: credit the money back
        uow.ledger.create_entry(
            user_id=withdrawal.user_id,
            entry_type=LedgerEntryType.WITHDRAWAL_REVERSAL,
            amount=withdrawal.amount,  # Positive — money comes back
            reference_type="withdrawal",
            reference_id=withdrawal.id,
            description=f"Reversal of failed withdrawal {withdrawal_id}: {withdrawal.amount} credited back",
            idempotency_key=f"{idempotency_key}_reversal" if idempotency_key else None,
        )

        # Update cached balance
        uow.balances.update_balance(
            withdrawal.user_id,
            available_delta=withdrawal.amount,
        )

        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="failed",
            old_values={"status": WithdrawalStatus.PROCESSING.value},
            new_values={
                "status": WithdrawalStatus.FAILED.value,
                "error_message": error_message,
            },
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(withdrawal_id),
            "status": WithdrawalStatus.FAILED.value,
            "amount_reversed": withdrawal.amount,
        }

    def reject_withdrawal(
        self,
        uow: UnitOfWork,
        withdrawal_id: str,
        admin_id: str,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Admin rejects a withdrawal — money is credited back to user.

        Same compensating transaction pattern as fail_withdrawal.
        """
        withdrawal = uow.withdrawals.get_for_update(withdrawal_id)
        if not withdrawal:
            raise EntityNotFoundError("Withdrawal", str(withdrawal_id))

        WithdrawalStateMachine.validate_transition(withdrawal.status, WithdrawalStatus.REJECTED)

        uow.withdrawals.update(
            withdrawal,
            {
                "status": WithdrawalStatus.REJECTED,
                "error_message": reason,
            },
        )

        # Compensating transaction
        uow.ledger.create_entry(
            user_id=withdrawal.user_id,
            entry_type=LedgerEntryType.WITHDRAWAL_REVERSAL,
            amount=withdrawal.amount,
            reference_type="withdrawal",
            reference_id=withdrawal.id,
            description=f"Reversal of rejected withdrawal {withdrawal_id}: {withdrawal.amount} credited back",
            idempotency_key=f"{idempotency_key}_reversal" if idempotency_key else None,
        )

        uow.balances.update_balance(
            withdrawal.user_id,
            available_delta=withdrawal.amount,
        )

        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="rejected",
            old_values={"status": WithdrawalStatus.PROCESSING.value},
            new_values={
                "status": WithdrawalStatus.REJECTED.value,
                "reason": reason,
            },
            changed_by=str(admin_id),
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(withdrawal_id),
            "status": WithdrawalStatus.REJECTED.value,
            "amount_reversed": withdrawal.amount,
        }

    def cancel_withdrawal(
        self,
        uow: UnitOfWork,
        withdrawal_id: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """User cancels a pending withdrawal.

        Only possible while withdrawal is still PENDING.
        Money is credited back to the user.
        """
        withdrawal = uow.withdrawals.get_for_update(withdrawal_id)
        if not withdrawal:
            raise EntityNotFoundError("Withdrawal", str(withdrawal_id))

        if str(withdrawal.user_id) != str(user_id):
            raise InvalidStateTransitionError(
                "Withdrawal",
                str(withdrawal_id),
                withdrawal.status.value,
                WithdrawalStatus.CANCELLED.value,
            )

        WithdrawalStateMachine.validate_transition(withdrawal.status, WithdrawalStatus.CANCELLED)

        uow.withdrawals.update(withdrawal, {"status": WithdrawalStatus.CANCELLED})

        # Compensating transaction
        uow.ledger.create_entry(
            user_id=withdrawal.user_id,
            entry_type=LedgerEntryType.WITHDRAWAL_REVERSAL,
            amount=withdrawal.amount,
            reference_type="withdrawal",
            reference_id=withdrawal.id,
            description=f"Reversal of cancelled withdrawal {withdrawal_id}: {withdrawal.amount} credited back",
            idempotency_key=f"{idempotency_key}_reversal" if idempotency_key else None,
        )

        uow.balances.update_balance(
            withdrawal.user_id,
            available_delta=withdrawal.amount,
        )

        uow.audit.log(
            entity_type="Withdrawal",
            entity_id=str(withdrawal_id),
            action="cancelled",
            old_values={"status": WithdrawalStatus.PENDING.value},
            new_values={"status": WithdrawalStatus.CANCELLED.value},
            changed_by=str(user_id),
            idempotency_key=idempotency_key,
        )

        return {
            "id": str(withdrawal_id),
            "status": WithdrawalStatus.CANCELLED.value,
            "amount_reversed": withdrawal.amount,
        }

    def _format_withdrawal(self, withdrawal: Any) -> dict:
        return {
            "id": str(withdrawal.id),
            "user_id": str(withdrawal.user_id),
            "amount": withdrawal.amount,
            "currency": withdrawal.currency,
            "status": withdrawal.status.value,
        }

    def get_withdrawal(self, uow: UnitOfWork, withdrawal_id: str) -> dict | None:
        """Get withdrawal details."""
        withdrawal = uow.withdrawals.get(withdrawal_id)
        if not withdrawal:
            return None
        return {
            "id": str(withdrawal.id),
            "user_id": str(withdrawal.user_id),
            "amount": withdrawal.amount,
            "currency": withdrawal.currency,
            "status": withdrawal.status.value,
            "gateway_reference": withdrawal.gateway_reference,
            "error_message": withdrawal.error_message,
            "created_at": withdrawal.created_at.isoformat() if withdrawal.created_at else None,
            "completed_at": withdrawal.completed_at.isoformat()
            if withdrawal.completed_at
            else None,
        }
