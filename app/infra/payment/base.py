"""Abstract payment gateway interface.

Defines the contract that all payment gateway implementations must follow.
This abstraction allows the system to:
1. Switch between payment providers without business logic changes
2. Test payout flows with a mock gateway
3. Implement provider-specific error handling in one place

The idempotency_key parameter on every method ensures the gateway
can deduplicate requests (most real gateways support this).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PayoutResult:
    """Result of a payout attempt to the payment gateway.

    Attributes:
        success: Whether the gateway accepted the payout
        reference: Gateway transaction ID (for reconciliation)
        error: Error message if the payout failed
        raw_response: Full gateway response (for debugging)
    """

    success: bool
    reference: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class GatewayStatusResult:
    """Result of checking a transaction status with the gateway.

    Attributes:
        status: confirmed, pending, failed, or not_found
        reference: Gateway transaction ID
        raw_response: Full gateway response
    """

    status: str
    reference: str
    raw_response: dict[str, Any] | None = None


class PaymentGateway(ABC):
    """Abstract payment gateway for payouts."""

    @abstractmethod
    def send_payout(
        self,
        user_id: str,
        amount: float,
        currency: str,
        idempotency_key: str,
    ) -> PayoutResult:
        """Send a payout to a user.

        The gateway uses the idempotency_key to ensure exactly-once
        processing. If the same key is sent twice, the gateway should
        return the same result without processing the payout again.
        """
        ...

    @abstractmethod
    def get_payout_status(self, reference: str) -> GatewayStatusResult:
        """Check the status of a previously submitted payout.

        Used by the recovery job to reconcile stuck transactions.
        """
        ...

    @abstractmethod
    def process_withdrawal(
        self,
        user_id: str,
        amount: float,
        currency: str,
        idempotency_key: str,
        bank_account: dict[str, Any] | None = None,
    ) -> PayoutResult:
        """Process a user withdrawal (payout to their bank account).

        The bank_account parameter contains the user's payout destination
        details (bank account, UPI ID, etc.).
        """
        ...

    @abstractmethod
    def get_withdrawal_status(self, reference: str) -> GatewayStatusResult:
        """Check the status of a withdrawal transaction."""
        ...
