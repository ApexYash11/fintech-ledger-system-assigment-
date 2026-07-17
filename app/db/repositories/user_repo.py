from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entity.

    Extends BaseRepository with user-specific queries.
    """

    def __init__(self, db: Session):
        super().__init__(db, User)

    def get_by_email(self, email: str) -> User | None:
        """Find a user by email address."""
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_active(self, user_id: Any) -> User | None:
        """Get user only if they are ACTIVE."""
        from app.core.enums import UserStatus

        stmt = select(User).where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
        )
        return self.db.execute(stmt).scalar_one_or_none()
