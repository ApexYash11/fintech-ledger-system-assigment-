import uuid

from sqlalchemy import Column, String, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.enums import BrandStatus
from app.db.base import Base, TimestampMixin


class Brand(Base, TimestampMixin):
    """A brand whose products the affiliate promotes.

    Columns:
        id: UUID primary key
        name: Human-readable brand name
        code: Unique short code used in external systems
        status: ACTIVE or INACTIVE — soft disable without data loss
    """

    __tablename__ = "brands"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(SAEnum(BrandStatus), default=BrandStatus.ACTIVE, nullable=False)

    sales = relationship("Sale", back_populates="brand")
