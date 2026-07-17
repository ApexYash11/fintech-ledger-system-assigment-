import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.enums import UserStatus
from app.db.base import Base, TimestampMixin, VersionMixin


class User(Base, TimestampMixin, VersionMixin):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(SAEnum(UserStatus), default=UserStatus.ACTIVE, nullable=False, index=True)

    sales = relationship("Sale", back_populates="user", foreign_keys="Sale.user_id")
    payouts = relationship("Payout", back_populates="user")
    withdrawals = relationship("Withdrawal", back_populates="user")
    ledger_entries = relationship("LedgerEntry", back_populates="user")
    balance = relationship("UserBalance", uselist=False, back_populates="user")
