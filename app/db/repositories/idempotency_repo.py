from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.idempotency import IdempotencyKey
from app.db.repositories.base import BaseRepository


class IdempotencyRepository(BaseRepository[IdempotencyKey]):
    """Repository for idempotency key tracking.

    Stores the response for each idempotency key so that
    duplicate requests can return the cached response.
    """

    def __init__(self, db: Session):
        super().__init__(db, IdempotencyKey)

    def get_by_key(self, key: str) -> IdempotencyKey | None:
        """Look up a previously stored idempotency key."""
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    def store_response(self, key: str, status_code: int, body: str | None = None) -> IdempotencyKey:
        """Store the response for a given idempotency key."""
        entry = IdempotencyKey(
            key=key,
            response_status=status_code,
            response_body=body or "",
        )
        self.db.add(entry)
        self.db.flush()
        return entry
