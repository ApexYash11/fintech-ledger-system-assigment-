import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Enum as SAEnum, Text
from sqlalchemy.orm import relationship

from app.core.enums import SaleStatus, Currency
from app.db.base import Base, TimestampMixin, VersionMixin


class Sale(Base, TimestampMixin, VersionMixin):
    """An affiliate sale record.

    Every sale enters as PENDING. An admin later reconciles it
    to APPROVED or REJECTED.

    Columns:
        id: UUID primary key
        user_id: FK to the affiliate who earned this sale
        brand_id: FK to the brand/product
        external_id: Unique ID from the external tracking system (prevents duplicates)
        earnings: The gross commission amount from this sale
        currency: ISO 4217 currency code
        status: PENDING -> APPROVED | REJECTED
        reconciled_by: FK to the admin who performed reconciliation
        reconciled_at: When reconciliation happened
        notes: Optional admin notes about the reconciliation decision

    Indexes:
        (user_id, status): Find pending/approved sales for a user
        (status, created_at): Batch processing of pending sales for advance payouts
        (external_id): UNIQUE — deduplication against external system
    """

    __tablename__ = "sales"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    brand_id = Column(
        String(36), ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_id = Column(String(255), unique=True, nullable=False)
    earnings = Column(Float, nullable=False)
    currency = Column(String(3), default=Currency.INR.value, nullable=False)
    status = Column(SAEnum(SaleStatus), default=SaleStatus.PENDING, nullable=False, index=True)
    reconciled_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="sales", foreign_keys=[user_id])
    brand = relationship("Brand", back_populates="sales")
    payouts = relationship("Payout", back_populates="sale")
    reconciler = relationship("User", foreign_keys=[reconciled_by])

    __table_args__ = (
        # Composite index for querying user's sales by status
        __table_args__.__class__(
            Index("ix_sales_user_status", "user_id", "status"),
            Index("ix_sales_status_created", "status", "created_at"),
        )
        if False
        else ()
    )


# Import Index at module level for SQLAlchemy
from sqlalchemy import Index

Sale.__table_args__ = (
    Index("ix_sales_user_status", "user_id", "status"),
    Index("ix_sales_status_created", "status", "created_at"),
)
