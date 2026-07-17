import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Enum as SAEnum, Text, Index
from sqlalchemy.orm import relationship

from app.core.enums import WithdrawalStatus, Currency
from app.db.base import Base, TimestampMixin, VersionMixin


class Withdrawal(Base, TimestampMixin, VersionMixin):
    __tablename__ = "withdrawals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default=Currency.INR.value, nullable=False)
    status = Column(
        SAEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING, nullable=False, index=True
    )
    idempotency_key = Column(String(255), unique=True, nullable=False)
    gateway_reference = Column(String(255), nullable=True)
    gateway_response = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="withdrawals")

    __table_args__ = (
        Index("ix_withdrawals_user_created", "user_id", "created_at"),
        Index("ix_withdrawals_user_status", "user_id", "status"),
        Index("ix_withdrawals_status_created", "status", "created_at"),
    )
