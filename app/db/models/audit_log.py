import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, Index

from app.db.base import Base


class AuditLog(Base):
    """Immutable audit trail for every state-changing operation.

    Every create, update, or delete operation on a business entity
    creates an audit log entry. This provides full traceability for
    compliance and debugging.

    Columns:
        id: Auto-incrementing INTEGER PK (sequential for easy ordering)
        entity_type: The type of entity (sale, withdrawal, payout, etc.)
        entity_id: The UUID of the affected entity
        action: What happened (created, status_changed, etc.)
        old_values: JSON string of the entity before the change
        new_values: JSON string of the entity after the change
        changed_by: UUID of the user who made the change (null for system actions)
        ip_address: Client IP for security auditing
        idempotency_key: Links audit entries to idempotent operations
        created_at: When the audit entry was created

    Indexes:
        (entity_type, entity_id): Find all changes to a specific entity
        (created_at): Time-based queries for compliance reviews
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    changed_by = Column(String(36), nullable=True)
    ip_address = Column(String(45), nullable=True)
    idempotency_key = Column(String(255), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created_at", "created_at"),
    )
