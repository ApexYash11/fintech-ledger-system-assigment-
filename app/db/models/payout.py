import uuid

from sqlalchemy import Column, Float, ForeignKey, String, Enum as SAEnum, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.enums import PayoutStatus, PayoutType
from app.db.base import Base, TimestampMixin, VersionMixin


class Payout(Base, TimestampMixin, VersionMixin):
    __tablename__ = "payouts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sale_id = Column(String(36), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount = Column(Float, nullable=False)
    type = Column(SAEnum(PayoutType), nullable=False)
    status = Column(SAEnum(PayoutStatus), default=PayoutStatus.PENDING, nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    gateway_reference = Column(String(255), nullable=True)
    gateway_response = Column(String(1024), nullable=True)

    sale = relationship("Sale", back_populates="payouts")
    user = relationship("User", back_populates="payouts")

    __table_args__ = (
        UniqueConstraint("sale_id", "type", name="uq_payout_sale_type"),
        Index("ix_payouts_user_status", "user_id", "status"),
        Index("ix_payouts_status_created", "status", "created_at"),
    )
