"""State machines for Sale, Payout, and Withdrawal entities.

Each state machine defines:
- All valid states
- All legal transitions
- Guards (preconditions) for each transition

This centralises state validation logic so it can be unit-tested
independently of the service layer.
"""

from app.core.enums import (
    SaleStatus,
    PayoutStatus,
    WithdrawalStatus,
)


class SaleStateMachine:
    TRANSITIONS = {
        SaleStatus.PENDING: {SaleStatus.APPROVED, SaleStatus.REJECTED},
    }

    @classmethod
    def can_transition(cls, current: SaleStatus, target: SaleStatus) -> bool:
        return target in cls.TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: SaleStatus, target: SaleStatus) -> None:
        if not cls.can_transition(current, target):
            from app.core.exceptions import InvalidStateTransitionError

            raise InvalidStateTransitionError(
                entity_type="Sale",
                entity_id="",
                from_status=current.value,
                to_status=target.value,
            )


class PayoutStateMachine:
    TRANSITIONS = {
        PayoutStatus.PENDING: {PayoutStatus.COMPLETED, PayoutStatus.FAILED},
    }

    @classmethod
    def can_transition(cls, current: PayoutStatus, target: PayoutStatus) -> bool:
        return target in cls.TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: PayoutStatus, target: PayoutStatus) -> None:
        if not cls.can_transition(current, target):
            from app.core.exceptions import InvalidStateTransitionError

            raise InvalidStateTransitionError(
                entity_type="Payout",
                entity_id="",
                from_status=current.value,
                to_status=target.value,
            )


class WithdrawalStateMachine:
    TRANSITIONS = {
        WithdrawalStatus.PENDING: {WithdrawalStatus.PROCESSING, WithdrawalStatus.CANCELLED},
        WithdrawalStatus.PROCESSING: {
            WithdrawalStatus.COMPLETED,
            WithdrawalStatus.FAILED,
            WithdrawalStatus.REJECTED,
        },
    }

    @classmethod
    def can_transition(cls, current: WithdrawalStatus, target: WithdrawalStatus) -> bool:
        return target in cls.TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: WithdrawalStatus, target: WithdrawalStatus) -> None:
        if not cls.can_transition(current, target):
            from app.core.exceptions import InvalidStateTransitionError

            raise InvalidStateTransitionError(
                entity_type="Withdrawal",
                entity_id="",
                from_status=current.value,
                to_status=target.value,
            )
