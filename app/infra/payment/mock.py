"""Mock payment gateway for local development and testing.

Simulates a real payment gateway with configurable success/failure
rates and artificial latency.

For testing, callers can configure:
- success_rate: 0.0 to 1.0 (default 0.95 = 95% success)
- latency_ms: Simulated network latency (default 50ms)
"""

import random
import time
from typing import Any

from app.infra.payment.base import PaymentGateway, PayoutResult, GatewayStatusResult


class MockPaymentGateway(PaymentGateway):
    """Mock implementation of the payment gateway.

    Simulates realistic behavior:
    - 95% success rate (configurable)
    - ~50ms latency (configurable)
    - Stores transaction references for status checks
    """

    def __init__(
        self,
        success_rate: float = 0.95,
        latency_ms: int = 50,
    ):
        self.success_rate = success_rate
        self.latency_ms = latency_ms
        self._transactions: dict[str, dict[str, Any]] = {}

    def _simulate_latency(self) -> None:
        """Simulate network latency."""
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

    def _should_succeed(self) -> bool:
        """Determine if the operation should succeed based on success rate."""
        return random.random() < self.success_rate

    def send_payout(
        self,
        user_id: str,
        amount: float,
        currency: str,
        idempotency_key: str,
    ) -> PayoutResult:
        self._simulate_latency()

        # Check for duplicate (idempotency)
        if idempotency_key in self._transactions:
            existing = self._transactions[idempotency_key]
            return PayoutResult(
                success=existing["success"],
                reference=existing["reference"],
                error=existing.get("error"),
            )

        import uuid

        reference = f"mock_txn_{uuid.uuid4().hex[:12]}"
        success = self._should_succeed()

        self._transactions[idempotency_key] = {
            "success": success,
            "reference": reference,
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
        }

        if success:
            return PayoutResult(
                success=True,
                reference=reference,
                raw_response={"status": "completed", "txn_id": reference},
            )
        else:
            return PayoutResult(
                success=False,
                reference=reference,
                error="Gateway temporarily unavailable",
                raw_response={"status": "failed", "code": "GATEWAY_TIMEOUT"},
            )

    def get_payout_status(self, reference: str) -> GatewayStatusResult:
        """Check the status of a payout transaction."""
        for txn_data in self._transactions.values():
            if txn_data["reference"] == reference:
                return GatewayStatusResult(
                    status="confirmed" if txn_data["success"] else "failed",
                    reference=reference,
                    raw_response=txn_data,
                )
        return GatewayStatusResult(
            status="not_found",
            reference=reference,
        )

    def process_withdrawal(
        self,
        user_id: str,
        amount: float,
        currency: str,
        idempotency_key: str,
        bank_account: dict[str, Any] | None = None,
    ) -> PayoutResult:
        """Process a withdrawal (payout to user's bank account)."""
        self._simulate_latency()

        if idempotency_key in self._transactions:
            existing = self._transactions[idempotency_key]
            return PayoutResult(
                success=existing["success"],
                reference=existing["reference"],
                error=existing.get("error"),
            )

        import uuid

        reference = f"mock_wd_{uuid.uuid4().hex[:12]}"
        success = self._should_succeed()

        self._transactions[idempotency_key] = {
            "success": success,
            "reference": reference,
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
            "type": "withdrawal",
        }

        if success:
            return PayoutResult(
                success=True,
                reference=reference,
                raw_response={"status": "completed", "txn_id": reference},
            )
        else:
            return PayoutResult(
                success=False,
                reference=reference,
                error="Withdrawal failed: insufficient funds at gateway",
                raw_response={"status": "failed", "code": "INSUFFICIENT_FUNDS"},
            )

    def get_withdrawal_status(self, reference: str) -> GatewayStatusResult:
        """Check the status of a withdrawal transaction."""
        return self.get_payout_status(reference)
