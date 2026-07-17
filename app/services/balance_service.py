"""Balance service — manages user balance calculations and caching.

The fundamental rule: the LEDGER is the source of truth.
UserBalance is always a cached/denormalized value.

Design decision: Why not always read from ledger?
- Performance: Summing ledger entries for every request is slow at scale
- Simplicity: Fast balance lookups for withdrawal eligibility checks

Tradeoff: There is a短暂 window where the cached balance may be stale.
This is acceptable because:
1. The cached balance is recalculated on every write within the same transaction
2. Periodic full-reconciliation jobs correct any drift
3. Withdrawal checks also verify against ledger sum for large amounts
"""

from decimal import Decimal
from typing import Any

from app.db.unit_of_work import UnitOfWork


class BalanceService:
    """Service for balance operations."""

    def get_balance(self, uow: UnitOfWork, user_id: Any) -> dict:
        """Get the user's current balance.

        Returns both cached and ledger-calculated balances.
        The ledger balance is the authoritative value.
        """
        from app.db.repositories.ledger_repo import LedgerRepository
        from app.db.repositories.balance_repo import BalanceRepository

        ledger_repo = LedgerRepository(uow.db)
        balance_repo = BalanceRepository(uow.db)

        ledger_balance = ledger_repo.get_user_balance(user_id)
        cached_balance = balance_repo.get_or_create(user_id)

        return {
            "user_id": str(user_id),
            "available_balance": cached_balance.available_balance,
            "pending_balance": cached_balance.pending_balance,
            "ledger_balance": ledger_balance,
            "currency": cached_balance.currency,
            "is_synced": abs(cached_balance.available_balance - ledger_balance) < 0.01,
        }

    def recalculate_balance(self, uow: UnitOfWork, user_id: Any) -> None:
        """Recalculate a user's cached balance from the ledger.

        Called periodically by a background job to correct any drift.
        """
        from app.db.repositories.ledger_repo import LedgerRepository
        from app.db.repositories.balance_repo import BalanceRepository

        ledger_repo = LedgerRepository(uow.db)
        balance_repo = BalanceRepository(uow.db)

        ledger_balance = ledger_repo.get_user_balance(user_id)
        balance = balance_repo.get_or_create(user_id)

        # We separate available vs pending based on ledger entry types
        # For simplicity, all completed entries go to available.
        # In production, pending payouts would go to pending_balance.
        balance.available_balance = max(0.0, ledger_balance)
        balance.pending_balance = 0.0

        from datetime import datetime, timezone

        balance.last_calculated_at = datetime.now(timezone.utc)

    def check_sufficient_balance(self, uow: UnitOfWork, user_id: Any, amount: float) -> bool:
        """Check if user has sufficient available balance for a withdrawal.

        For amounts above a threshold, double-check against the ledger
        to catch any cached balance drift.
        """
        from app.db.repositories.balance_repo import BalanceRepository
        from app.db.repositories.ledger_repo import LedgerRepository
        from app.config import settings

        balance_repo = BalanceRepository(uow.db)
        ledger_repo = LedgerRepository(uow.db)

        balance = balance_repo.get_or_create(user_id)
        if balance.available_balance >= amount:
            # For large withdrawals, verify against the ledger
            if amount >= settings.balance_check_threshold:
                ledger_balance = ledger_repo.get_user_balance(user_id)
                if ledger_balance < amount:
                    # Cache drift detected — trigger recalculation
                    self.recalculate_balance(uow, user_id)
                    return False
            return True
        return False
