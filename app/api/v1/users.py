"""User management API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user, get_uow
from app.api.v1.schemas import UserCreate, UserResponse, BalanceResponse
from app.core.enums import UserStatus
from app.core.exceptions import DomainError
from app.db.unit_of_work import UnitOfWork
from app.services.balance_service import BalanceService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    user_data: UserCreate,
    uow: UnitOfWork = Depends(get_uow),
):
    """Create a new user."""
    from app.db.models.user import User
    import uuid

    existing = uow.users.get_by_email(user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        name=user_data.name,
        status=UserStatus.ACTIVE,
    )
    with uow:
        uow.users.add(user)
    uow.commit()

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        status=user.status.value,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: Any = Depends(get_current_user),
):
    """Get the current user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        status=current_user.status.value,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


@router.get("/me/balance", response_model=BalanceResponse)
def get_balance(
    uow: UnitOfWork = Depends(get_uow),
    current_user: Any = Depends(get_current_user),
):
    """Get the current user's balance.

    Returns both cached and ledger-calculated balances.
    """
    service = BalanceService()
    return service.get_balance(uow, str(current_user.id))
