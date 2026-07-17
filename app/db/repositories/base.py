"""Base repository with common CRUD operations.

Follows the Repository pattern:
- Each repository wraps a single ORM model
- Provides collection-like interface (get, add, update, delete)
- Does NOT contain business logic
- Does NOT commit transactions (delegates to Unit of Work)
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundError

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Generic repository with common database operations.

    Type parameter ModelType is the SQLAlchemy model class.
    """

    def __init__(self, db: Session, model_class: type[ModelType]):
        self.db = db
        self.model_class = model_class

    def get(self, entity_id: Any) -> ModelType | None:
        """Get entity by primary key. Returns None if not found."""
        return self.db.get(self.model_class, entity_id)

    def get_or_raise(self, entity_id: Any) -> ModelType:
        """Get entity by primary key or raise EntityNotFoundError."""
        entity = self.get(entity_id)
        if entity is None:
            raise EntityNotFoundError(
                entity_type=self.model_class.__name__,
                entity_id=str(entity_id),
            )
        return entity

    def get_for_update(self, entity_id: Any) -> ModelType | None:
        """Get entity with SELECT FOR UPDATE (row-level lock).

        Used within transactions to prevent concurrent modifications.
        SQLAlchemy handles dialect-specific rendering (uses FOR UPDATE
        on PostgreSQL, silently ignored on SQLite which uses BEGIN IMMEDIATE).
        """
        stmt = (
            select(self.model_class)
            .where(self.model_class.id == entity_id)  # type: ignore[attr-defined]
            .with_for_update()
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, entity: ModelType) -> ModelType:
        """Add a new entity to the session (does not commit)."""
        self.db.add(entity)
        self.db.flush()
        return entity

    def update(self, entity: ModelType, updates: dict[str, Any]) -> ModelType:
        """Update entity fields from a dictionary.

        Enforces optimistic locking: if the model has a 'version' column,
        the version in the database must match the entity's current version.
        Increments version on success.
        """
        if hasattr(entity, "version") and entity.version is not None:
            current_version = entity.version
            stmt = (
                update(self.model_class)
                .where(
                    self.model_class.id == entity.id,  # type: ignore[attr-defined]
                    self.model_class.version == current_version,
                )
                .values(**updates, version=current_version + 1)
            )
            result = self.db.execute(stmt)
            if result.rowcount == 0:
                raise OptimisticLockError(
                    entity_type=self.model_class.__name__,
                    entity_id=str(entity.id),
                    expected_version=current_version,
                )
            self.db.flush()
            return self.get(entity.id)

        for key, value in updates.items():
            setattr(entity, key, value)
        if hasattr(entity, "version"):
            entity.version += 1
        self.db.flush()
        return entity

    def delete(self, entity: ModelType) -> None:
        """Mark entity for deletion (does not commit)."""
        self.db.delete(entity)
        self.db.flush()

    def list_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """List entities with pagination."""
        stmt = select(self.model_class).offset(skip).limit(limit)
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def count(self) -> int:
        """Total count of entities."""
        stmt = select(self.model_class)
        return self.db.execute(stmt).scalar() or 0


class OptimisticLockError(Exception):
    """Raised when an optimistic lock version mismatch is detected."""

    def __init__(self, entity_type: str, entity_id: str, expected_version: int):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected_version = expected_version
        super().__init__(
            f"{entity_type} {entity_id}: version mismatch. "
            f"Expected version {expected_version} but database has changed."
        )
