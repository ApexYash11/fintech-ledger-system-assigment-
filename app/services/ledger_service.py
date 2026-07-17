"""Ledger service — manages creation of immutable ledger entries.

Every money movement in the system goes through this service,
ensuring consistent accounting.

Design decision: Why a separate service instead of direct repository calls?
1. Consistent entry creation: All entries follow the same pattern
2. Enforces immutability: No update/delete operations exposed
3. Centralized audit: Every entry creation can trigger audit logging
"""

from typing import Any

from app.core.enums import LedgerEntryType
from app.db.unit_of_work import UnitOfWork


class LedgerService:
    """Service for creating and querying ledger entries."""

    def record_movement(
        self,
        uow: UnitOfWork,
        user_id: Any,
        entry_type: LedgerEntryType,
        amount: float,
        reference_type: str,
        reference_id: Any,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Record a money movement in the immutable ledger.

        This is the single point of entry for all financial transactions.
        Every call creates:
        1. A ledger entry (immutable record)
        2. An update to the cached user balance

        Both happen within the same transaction (rollback if either fails).
        """
        # Create the immutable ledger entry
        entry = uow.ledger.create_entry(
            user_id=user_id,
            entry_type=entry_type,
            amount=amount,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
            idempotency_key=idempotency_key,
        )

        # Update the cached balance
        if amount > 0:
            uow.balances.update_balance(user_id, available_delta=amount)
        else:
            uow.balances.update_balance(user_id, available_delta=amount)

        # Audit log
        uow.audit.log(
            entity_type="LedgerEntry",
            entity_id=str(entry.id),
            action="created",
            new_values={
                "user_id": str(user_id),
                "entry_type": entry_type.value,
                "amount": amount,
                "reference_type": reference_type,
                "reference_id": str(reference_id),
            },
            idempotency_key=idempotency_key,
        )

        return {
            "entry_id": str(entry.id),
            "user_id": str(user_id),
            "entry_type": entry_type.value,
            "amount": amount,
            "balance_after": str(uow.balances.get_or_create(user_id).available_balance),
        }
