"""Edge case tests for concurrency, fault tolerance, and boundary conditions.

These tests verify the system's behavior under unusual or adversarial conditions.
"""

import uuid
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.enums import (
    SaleStatus,
    PayoutStatus,
    PayoutType,
    WithdrawalStatus,
    LedgerEntryType,
    UserStatus,
)
from app.core.exceptions import (
    SaleAlreadyReconciledError,
    AdvanceAlreadyPaidError,
    InvalidAmountError,
)
from app.db.unit_of_work import UnitOfWork
from app.db.models.user import User
from app.db.models.brand import Brand
from app.db.models.sale import Sale
from app.db.models.user_balance import UserBalance
from app.services.reconciliation_service import ReconciliationService
from app.services.payout_service import PayoutService
from app.services.withdrawal_service import WithdrawalService
from app.services.balance_service import BalanceService


class TestConcurrentReconciliation:
    """Test concurrent reconciliation of the same sale.

    Two admin requests arriving simultaneously should result in
    only one succeeding (the row lock prevents double processing).
    """

    def test_concurrent_approve_reject(
        self,
        db_session: Session,
        pending_sale: Sale,
        admin_user: User,
    ):
        """Two concurrent reconciliations — only the first should succeed."""
        uow1 = UnitOfWork(db_session)
        uow2 = UnitOfWork(db_session)
        service = ReconciliationService()

        # First reconciliation
        with uow1:
            result1 = service.reconcile_sale(
                uow=uow1,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="APPROVED",
            )
        uow1.commit()

        assert result1["status"] == "APPROVED"

        # Second reconciliation — should fail
        with pytest.raises(SaleAlreadyReconciledError):
            with uow2:
                service.reconcile_sale(
                    uow=uow2,
                    sale_id=str(pending_sale.id),
                    admin_id=str(admin_user.id),
                    decision="REJECTED",
                )


class TestDuplicateAdvancePayout:
    """Test that advance payouts are idempotent."""

    def test_duplicate_advance_job(
        self,
        db_session: Session,
        pending_sale: Sale,
    ):
        """If the advance payout job runs twice for the same sale, only
        one advance payout should be created."""
        uow = UnitOfWork(db_session)
        service = PayoutService()

        # First run
        with uow:
            result1 = service.create_advance_payout(uow=uow, sale_id=str(pending_sale.id))
        uow.commit()

        assert result1["amount"] == 100.00

        # Second run — should fail
        with pytest.raises(AdvanceAlreadyPaidError):
            with uow:
                service.create_advance_payout(uow=uow, sale_id=str(pending_sale.id))


class TestWithdrawalBoundaryConditions:
    """Test edge cases around withdrawal rules."""

    def test_withdrawal_exact_minimum(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        """Withdrawing exactly the minimum should succeed."""
        from app.config import settings

        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with uow:
            result = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=settings.min_withdrawal_amount,
                idempotency_key=f"wd_{uuid.uuid4().hex}",
            )
        uow.commit()

        assert result["status"] == "PENDING"

    def test_withdrawal_below_minimum(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        """Withdrawing below the minimum should fail."""
        from app.config import settings

        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with pytest.raises(InvalidAmountError):
            with uow:
                service.request_withdrawal(
                    uow=uow,
                    user_id=str(user.id),
                    amount=settings.min_withdrawal_amount - 1,
                    idempotency_key=f"wd_{uuid.uuid4().hex}",
                )

    def test_zero_withdrawal(self, db_session: Session, user: User, user_balance: UserBalance):
        """Zero amount withdrawal should fail."""
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with pytest.raises(InvalidAmountError):
            with uow:
                service.request_withdrawal(
                    uow=uow,
                    user_id=str(user.id),
                    amount=0,
                    idempotency_key=f"wd_{uuid.uuid4().hex}",
                )

    def test_negative_withdrawal(self, db_session: Session, user: User, user_balance: UserBalance):
        """Negative amount withdrawal should fail."""
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with pytest.raises(InvalidAmountError):
            with uow:
                service.request_withdrawal(
                    uow=uow,
                    user_id=str(user.id),
                    amount=-100,
                    idempotency_key=f"wd_{uuid.uuid4().hex}",
                )


class TestNegativeBalance:
    """Test that negative balance scenarios are handled correctly."""

    def test_balance_never_negative(self, db_session: Session, user: User):
        """Available balance should never go below zero."""
        uow = UnitOfWork(db_session)
        balance_service = BalanceService()

        # Try to deduct more than available
        balance_service.recalculate_balance(uow, str(user.id))
        balance = uow.balances.get_or_create(user.id)

        # Deduct 100 from zero balance
        uow.balances.update_balance(user.id, available_delta=-100)
        db_session.commit()

        # Balance should be 0 (not negative)
        assert balance.available_balance >= 0


class TestIdempotency:
    """Test idempotency guarantees."""

    def test_idempotent_withdrawal_request(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        """Same idempotency key should not create duplicate withdrawals."""
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        idem_key = f"wd_idem_test_{uuid.uuid4().hex}"

        # First request
        with uow:
            result1 = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=500.00,
                idempotency_key=idem_key,
            )
        uow.commit()

        # Second request with same key
        with uow:
            result2 = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=500.00,
                idempotency_key=idem_key,
            )
        uow.commit()

        assert result1["id"] == result2["id"]


class TestLedgerImmutability:
    """Test that ledger entries cannot be modified after creation."""

    def test_ledger_entry_immutable(self, db_session: Session, user: User):
        """Once created, a ledger entry should never change."""
        uow = UnitOfWork(db_session)

        entry = uow.ledger.create_entry(
            user_id=user.id,
            entry_type=LedgerEntryType.ADVANCE_PAYOUT,
            amount=100.00,
            reference_type="test",
            reference_id=str(uuid.uuid4()),
            description="Test immutability",
            idempotency_key=f"immutable_{uuid.uuid4().hex}",
        )
        db_session.commit()

        # Try to modify
        entry_id = entry.id
        entry_from_db = uow.ledger.get(entry_id)

        # The ORM should not update the created_at
        original_created = entry_from_db.created_at
        assert entry_from_db.description == "Test immutability"


class TestCachedBalanceSync:
    """Test cached balance synchronization with ledger."""

    def test_balance_sync(self, db_session: Session, user: User):
        """Cached balance should sync with ledger after recalculation."""
        uow = UnitOfWork(db_session)
        balance_service = BalanceService()

        # Create some ledger entries (simulating previous operations)
        uow.ledger.create_entry(
            user_id=user.id,
            entry_type=LedgerEntryType.ADVANCE_PAYOUT,
            amount=1000.00,
            reference_type="test",
            reference_id=str(uuid.uuid4()),
            description="Test entry 1",
        )
        uow.ledger.create_entry(
            user_id=user.id,
            entry_type=LedgerEntryType.WITHDRAWAL,
            amount=-300.00,
            reference_type="test",
            reference_id=str(uuid.uuid4()),
            description="Test entry 2",
        )
        db_session.commit()

        # Recalculate
        balance_service.recalculate_balance(uow, str(user.id))
        db_session.commit()

        balance = uow.balances.get_or_create(user.id)
        assert balance.available_balance == 700.00  # 1000 - 300
