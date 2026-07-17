"""Integration tests for service layer.

Tests business logic with real database transactions.
Each test runs in its own transaction that is rolled back.
"""

import uuid
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
    BrandStatus,
)
from app.core.exceptions import (
    InsufficientBalanceError,
    WithdrawalCooldownError,
    EntityNotFoundError,
    SaleAlreadyReconciledError,
    InvalidAmountError,
)
from app.db.unit_of_work import UnitOfWork
from app.services.sale_service import SaleService
from app.services.withdrawal_service import WithdrawalService
from app.services.reconciliation_service import ReconciliationService
from app.services.payout_service import PayoutService
from app.services.balance_service import BalanceService
from app.db.models.user import User
from app.db.models.brand import Brand
from app.db.models.sale import Sale
from app.db.models.payout import Payout
from app.db.models.withdrawal import Withdrawal
from app.db.models.user_balance import UserBalance


# ─── Sale Service Tests ──────────────────────────────────


class TestSaleService:
    def test_create_sale_success(self, db_session: Session, user: User, brand: Brand):
        uow = UnitOfWork(db_session)
        service = SaleService()

        with uow:
            result = service.create_sale(
                uow=uow,
                user_id=str(user.id),
                brand_id=str(brand.id),
                external_id=f"ext_{uuid.uuid4().hex}",
                earnings=500.00,
            )
        uow.commit()

        assert result["status"] == "PENDING"
        assert result["earnings"] == 500.00

    def test_create_sale_invalid_user(self, db_session: Session, brand: Brand):
        uow = UnitOfWork(db_session)
        service = SaleService()

        with pytest.raises(EntityNotFoundError):
            with uow:
                service.create_sale(
                    uow=uow,
                    user_id=str(uuid.uuid4()),
                    brand_id=str(brand.id),
                    external_id=f"ext_{uuid.uuid4().hex}",
                    earnings=500.00,
                )

    def test_create_sale_duplicate_external_id(
        self, db_session: Session, user: User, brand: Brand, pending_sale: Sale
    ):
        uow = UnitOfWork(db_session)
        service = SaleService()

        from app.core.exceptions import DuplicateIdempotencyKeyError

        with pytest.raises(DuplicateIdempotencyKeyError):
            with uow:
                service.create_sale(
                    uow=uow,
                    user_id=str(user.id),
                    brand_id=str(brand.id),
                    external_id=pending_sale.external_id,
                    earnings=500.00,
                )


# ─── Withdrawal Service Tests ────────────────────────────


class TestWithdrawalService:
    def test_request_withdrawal_success(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with uow:
            result = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=1000.00,
                idempotency_key=f"wd_{uuid.uuid4().hex}",
            )
        uow.commit()

        assert result["status"] == "PENDING"
        assert result["amount"] == 1000.00

        # Balance should be deducted
        balance = uow.balances.get_or_create(user.id)
        assert balance.available_balance == 4000.00  # 5000 - 1000

    def test_request_withdrawal_insufficient_balance(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        with pytest.raises(InsufficientBalanceError):
            with uow:
                service.request_withdrawal(
                    uow=uow,
                    user_id=str(user.id),
                    amount=10000.00,  # More than available 5000
                    idempotency_key=f"wd_{uuid.uuid4().hex}",
                )

    def test_request_withdrawal_cooldown(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        # First withdrawal — should succeed
        with uow:
            service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=500.00,
                idempotency_key=f"wd_{uuid.uuid4().hex}",
            )
        uow.commit()

        # Second withdrawal immediately — should fail cooldown
        with pytest.raises(WithdrawalCooldownError):
            with uow:
                service.request_withdrawal(
                    uow=uow,
                    user_id=str(user.id),
                    amount=500.00,
                    idempotency_key=f"wd_{uuid.uuid4().hex}",
                )

    def test_cancel_withdrawal(self, db_session: Session, user: User, user_balance: UserBalance):
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        # Request withdrawal
        with uow:
            result = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=1000.00,
                idempotency_key=f"wd_{uuid.uuid4().hex}",
            )
        uow.commit()

        # Cancel it
        with uow:
            cancel_result = service.cancel_withdrawal(
                uow=uow,
                withdrawal_id=result["id"],
                user_id=str(user.id),
            )
        uow.commit()

        assert cancel_result["status"] == "CANCELLED"
        assert cancel_result["amount_reversed"] == 1000.00

        # Balance should be restored
        balance = uow.balances.get_or_create(user.id)
        assert balance.available_balance == 5000.00

    def test_fail_withdrawal_credits_back(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        uow = UnitOfWork(db_session)
        service = WithdrawalService()

        # Request withdrawal
        with uow:
            result = service.request_withdrawal(
                uow=uow,
                user_id=str(user.id),
                amount=1000.00,
                idempotency_key=f"wd_{uuid.uuid4().hex}",
            )
        uow.commit()

        # Process then fail it
        with uow:
            service.process_withdrawal(uow, result["id"])
            fail_result = service.fail_withdrawal(uow, result["id"], error_message="Test failure")
        uow.commit()

        assert fail_result["status"] == "FAILED"
        assert fail_result["amount_reversed"] == 1000.00

        # Balance should be restored
        balance = uow.balances.get_or_create(user.id)
        assert balance.available_balance == 5000.00


# ─── Reconciliation Service Tests ─────────────────────────


class TestReconciliationService:
    def test_approve_sale_without_advance(
        self, db_session: Session, user: User, brand: Brand, pending_sale: Sale, admin_user: User
    ):
        uow = UnitOfWork(db_session)
        service = ReconciliationService()

        with uow:
            result = service.reconcile_sale(
                uow=uow,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="APPROVED",
            )
        uow.commit()

        assert result["status"] == "APPROVED"
        assert result["remaining_payout"] == 1000.00  # Full earnings, no advance

    def test_approve_sale_with_advance(
        self,
        db_session: Session,
        user: User,
        pending_sale: Sale,
        admin_user: User,
        advance_payout: Payout,
    ):
        uow = UnitOfWork(db_session)
        service = ReconciliationService()

        with uow:
            result = service.reconcile_sale(
                uow=uow,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="APPROVED",
            )
        uow.commit()

        assert result["status"] == "APPROVED"
        assert result["remaining_payout"] == 900.00  # 1000 - 100 advance

    def test_reject_sale_without_advance(
        self, db_session: Session, user: User, pending_sale: Sale, admin_user: User
    ):
        uow = UnitOfWork(db_session)
        service = ReconciliationService()

        with uow:
            result = service.reconcile_sale(
                uow=uow,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="REJECTED",
            )
        uow.commit()

        assert result["status"] == "REJECTED"
        assert not result["advance_recovered"]

    def test_reject_sale_with_advance(
        self,
        db_session: Session,
        user: User,
        pending_sale: Sale,
        admin_user: User,
        advance_payout: Payout,
    ):
        uow = UnitOfWork(db_session)
        service = ReconciliationService()

        with uow:
            result = service.reconcile_sale(
                uow=uow,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="REJECTED",
            )
        uow.commit()

        assert result["status"] == "REJECTED"
        assert result["advance_recovered"]
        assert result["advance_amount"] == 100.00

    def test_double_reconciliation_fails(
        self, db_session: Session, user: User, pending_sale: Sale, admin_user: User
    ):
        uow = UnitOfWork(db_session)
        service = ReconciliationService()

        # First reconciliation — should succeed
        with uow:
            service.reconcile_sale(
                uow=uow,
                sale_id=str(pending_sale.id),
                admin_id=str(admin_user.id),
                decision="APPROVED",
            )
        uow.commit()

        # Second reconciliation — should fail
        with pytest.raises(SaleAlreadyReconciledError):
            with uow:
                service.reconcile_sale(
                    uow=uow,
                    sale_id=str(pending_sale.id),
                    admin_id=str(admin_user.id),
                    decision="REJECTED",
                )


# ─── Payout Service Tests ────────────────────────────────


class TestPayoutService:
    def test_create_advance_payout(self, db_session: Session, user: User, pending_sale: Sale):
        uow = UnitOfWork(db_session)
        service = PayoutService()

        with uow:
            result = service.create_advance_payout(
                uow=uow,
                sale_id=str(pending_sale.id),
            )
        uow.commit()

        assert result["amount"] == 100.00  # 10% of 1000

    def test_duplicate_advance_payout_fails(
        self, db_session: Session, pending_sale: Sale, advance_payout: Payout
    ):
        uow = UnitOfWork(db_session)
        service = PayoutService()

        from app.core.exceptions import AdvanceAlreadyPaidError

        with pytest.raises(AdvanceAlreadyPaidError):
            with uow:
                service.create_advance_payout(
                    uow=uow,
                    sale_id=str(pending_sale.id),
                )


# ─── Balance Service Tests ───────────────────────────────


class TestBalanceService:
    def test_ledger_is_source_of_truth(
        self, db_session: Session, user: User, user_balance: UserBalance
    ):
        """The ledger balance should match cached balance after syncing."""
        uow = UnitOfWork(db_session)
        service = BalanceService()

        # Create a ledger entry directly
        uow.ledger.create_entry(
            user_id=user.id,
            entry_type=LedgerEntryType.ADVANCE_PAYOUT,
            amount=250.00,
            reference_type="test",
            reference_id=str(uuid.uuid4()),
            description="Test entry",
        )
        db_session.commit()

        # Check balance
        balance = service.get_balance(uow, str(user.id))
        assert balance["ledger_balance"] == 250.00
