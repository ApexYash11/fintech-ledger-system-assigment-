from sqlalchemy import select, insert
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

    def try_claim(self, key: str) -> bool:
        """Atomically claim an idempotency key.

        Uses INSERT OR IGNORE (SQLite) / INSERT ON CONFLICT DO NOTHING (PG).
        Returns True if this caller is the first to claim the key,
        False if the key was already claimed (duplicate request).
        """
        from sqlalchemy import text

        dialect = self.db.bind.dialect.name if self.db.bind else "sqlite"
        if dialect == "postgresql":
            stmt = text(
                "INSERT INTO idempotency_keys (key, response_status, response_body, created_at) "
                "VALUES (:key, 0, '', NOW()) "
                "ON CONFLICT (key) DO NOTHING"
            )
        else:
            stmt = text(
                "INSERT OR IGNORE INTO idempotency_keys (key, response_status, response_body, created_at) "
                "VALUES (:key, 0, '', datetime('now'))"
            )
        result = self.db.execute(stmt, {"key": key})
        self.db.flush()
        return result.rowcount > 0

    def claim_and_store(self, key: str, status_code: int, body: str = "") -> IdempotencyKey:
        """Atomically claim or update an idempotency key with response data.

        Uses INSERT OR REPLACE / UPSERT pattern.
        """
        from sqlalchemy import text

        entry = IdempotencyKey(
            key=key,
            response_status=status_code,
            response_body=body,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def store_response(self, key: str, status_code: int, body: str | None = None) -> None:
        """Update the response for an already-claimed idempotency key."""
        from sqlalchemy import text

        entry = self.get_by_key(key)
        if entry:
            entry.response_status = status_code
            entry.response_body = body or ""
            self.db.flush()
