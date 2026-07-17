"""Unit of Work pattern for managing database transactions.

The UoW ensures that multiple repository operations are committed
atomically. If any operation fails, all changes are rolled back.

This is critical for financial transactions where we need to:
1. Create a payout record
2. Create a ledger entry
3. Update the user's cached balance

All three must succeed or none should be applied.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.balance_repo import BalanceRepository
from app.db.repositories.brand_repo import BrandRepository
from app.db.repositories.idempotency_repo import IdempotencyRepository
from app.db.repositories.ledger_repo import LedgerRepository
from app.db.repositories.payout_repo import PayoutRepository
from app.db.repositories.sale_repo import SaleRepository
from app.db.repositories.user_repo import UserRepository
from app.db.repositories.withdrawal_repo import WithdrawalRepository


class UnitOfWork:
    """Coordinates multiple repository operations within a single transaction.

    Usage:
        uow = UnitOfWork(db_session)
        with uow:
            sale = uow.sales.get_for_update(sale_id)
            uow.payouts.add(payout)
            uow.ledger.create_entry(...)
            uow.commit()
    """

    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.sales = SaleRepository(db)
        self.payouts = PayoutRepository(db)
        self.withdrawals = WithdrawalRepository(db)
        self.brands = BrandRepository(db)
        self.ledger = LedgerRepository(db)
        self.balances = BalanceRepository(db)
        self.audit = AuditRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self._depth = 0

    def __enter__(self) -> "UnitOfWork":
        self._depth += 1
        if self._depth > 1:
            self.db.begin_nested()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._depth -= 1
        if exc_type is not None:
            self.db.rollback()

    def commit(self) -> None:
        """Commit the current transaction."""
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self.db.rollback()

    def flush(self) -> None:
        """Flush pending changes to DB without committing.

        Useful for getting generated IDs before commit.
        """
        self.db.flush()


@contextmanager
def unit_of_work(db: Session) -> Generator[UnitOfWork, None, None]:
    """Context manager for UnitOfWork.

    Ensures proper cleanup even if an exception occurs.
    """
    uow = UnitOfWork(db)
    try:
        with uow:
            yield uow
            uow.commit()
    except Exception:
        uow.rollback()
        raise
