from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import BrandStatus
from app.db.models.brand import Brand
from app.db.repositories.base import BaseRepository


class BrandRepository(BaseRepository[Brand]):
    """Repository for Brand entity."""

    def __init__(self, db: Session):
        super().__init__(db, Brand)

    def get_by_code(self, code: str) -> Brand | None:
        """Find a brand by its short code."""
        stmt = select(Brand).where(Brand.code == code)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active(self, brand_id: str) -> Brand | None:
        """Get brand only if it is ACTIVE."""
        stmt = select(Brand).where(
            Brand.id == brand_id,
            Brand.status == BrandStatus.ACTIVE,
        )
        return self.db.execute(stmt).scalar_one_or_none()
