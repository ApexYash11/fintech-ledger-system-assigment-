from enum import Enum


class SaleStatus(str, Enum):
    """Status lifecycle for affiliate sales.

    PENDING -> APPROVED
    PENDING -> REJECTED

    Once a sale reaches APPROVED or REJECTED, it is terminal.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PayoutStatus(str, Enum):
    """Status lifecycle for payouts (advance + final).

    PENDING -> COMPLETED
    PENDING -> FAILED
    """

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PayoutType(str, Enum):
    """Distinguishes advance (10% of pending earnings) from
    final settlement (remaining balance after reconciliation)."""

    ADVANCE = "ADVANCE"
    FINAL_SETTLEMENT = "FINAL_SETTLEMENT"


class WithdrawalStatus(str, Enum):
    """Status lifecycle for withdrawal requests.

    PENDING -> PROCESSING -> COMPLETED
    PENDING -> CANCELLED
    PROCESSING -> FAILED       (money credited back)
    PROCESSING -> REJECTED     (money credited back)
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class LedgerEntryType(str, Enum):
    """Immutable classification for every money movement.

    Each entry type maps to exactly one business event.
    """

    ADVANCE_PAYOUT = "ADVANCE_PAYOUT"
    FINAL_PAYOUT = "FINAL_PAYOUT"
    WITHDRAWAL = "WITHDRAWAL"
    WITHDRAWAL_REVERSAL = "WITHDRAWAL_REVERSAL"
    NEGATIVE_ADJUSTMENT = "NEGATIVE_ADJUSTMENT"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class BrandStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
