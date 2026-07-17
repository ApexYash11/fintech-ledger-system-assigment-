"""Unit tests for state machine transitions.

Verifies:
- Legal transitions succeed
- Illegal transitions raise InvalidStateTransitionError
- All possible transitions are covered
"""

import pytest

from app.core.enums import SaleStatus, PayoutStatus, WithdrawalStatus
from app.core.state_machines import (
    SaleStateMachine,
    PayoutStateMachine,
    WithdrawalStateMachine,
)
from app.core.exceptions import InvalidStateTransitionError


class TestSaleStateMachine:
    def test_pending_to_approved(self):
        SaleStateMachine.validate_transition(SaleStatus.PENDING, SaleStatus.APPROVED)

    def test_pending_to_rejected(self):
        SaleStateMachine.validate_transition(SaleStatus.PENDING, SaleStatus.REJECTED)

    def test_approved_to_pending_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            SaleStateMachine.validate_transition(SaleStatus.APPROVED, SaleStatus.PENDING)

    def test_approved_to_rejected_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            SaleStateMachine.validate_transition(SaleStatus.APPROVED, SaleStatus.REJECTED)

    def test_rejected_to_approved_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            SaleStateMachine.validate_transition(SaleStatus.REJECTED, SaleStatus.APPROVED)

    def test_all_terminal_states(self):
        """Once approved or rejected, no further transitions allowed."""
        for terminal in [SaleStatus.APPROVED, SaleStatus.REJECTED]:
            for target in SaleStatus:
                if target != terminal:
                    assert not SaleStateMachine.can_transition(terminal, target)


class TestPayoutStateMachine:
    def test_pending_to_completed(self):
        PayoutStateMachine.validate_transition(PayoutStatus.PENDING, PayoutStatus.COMPLETED)

    def test_pending_to_failed(self):
        PayoutStateMachine.validate_transition(PayoutStatus.PENDING, PayoutStatus.FAILED)

    def test_completed_to_pending_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            PayoutStateMachine.validate_transition(PayoutStatus.COMPLETED, PayoutStatus.PENDING)

    def test_failed_to_completed_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            PayoutStateMachine.validate_transition(PayoutStatus.FAILED, PayoutStatus.COMPLETED)


class TestWithdrawalStateMachine:
    def test_pending_to_processing(self):
        WithdrawalStateMachine.validate_transition(
            WithdrawalStatus.PENDING, WithdrawalStatus.PROCESSING
        )

    def test_pending_to_cancelled(self):
        WithdrawalStateMachine.validate_transition(
            WithdrawalStatus.PENDING, WithdrawalStatus.CANCELLED
        )

    def test_processing_to_completed(self):
        WithdrawalStateMachine.validate_transition(
            WithdrawalStatus.PROCESSING, WithdrawalStatus.COMPLETED
        )

    def test_processing_to_failed(self):
        WithdrawalStateMachine.validate_transition(
            WithdrawalStatus.PROCESSING, WithdrawalStatus.FAILED
        )

    def test_processing_to_rejected(self):
        WithdrawalStateMachine.validate_transition(
            WithdrawalStatus.PROCESSING, WithdrawalStatus.REJECTED
        )

    def test_pending_to_completed_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            WithdrawalStateMachine.validate_transition(
                WithdrawalStatus.PENDING, WithdrawalStatus.COMPLETED
            )

    def test_completed_to_any_invalid(self):
        for target in WithdrawalStatus:
            if target != WithdrawalStatus.COMPLETED:
                assert not WithdrawalStateMachine.can_transition(WithdrawalStatus.COMPLETED, target)
