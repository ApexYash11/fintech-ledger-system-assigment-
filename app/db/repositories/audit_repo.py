from typing import Any

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog entity."""

    def __init__(self, db: Session):
        super().__init__(db, AuditLog)

    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        old_values: dict | str | None = None,
        new_values: dict | str | None = None,
        changed_by: str | None = None,
        ip_address: str | None = None,
        idempotency_key: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        import json

        def _serialize(v: dict | str | None) -> str | None:
            if v is None:
                return None
            if isinstance(v, dict):
                return json.dumps(v, default=str)
            return v

        entry = AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            old_values=_serialize(old_values),
            new_values=_serialize(new_values),
            changed_by=str(changed_by) if changed_by else None,
            ip_address=ip_address,
            idempotency_key=idempotency_key,
        )
        self.db.add(entry)
        self.db.flush()
        return entry
