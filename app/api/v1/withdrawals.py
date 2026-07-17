"""User withdrawal API endpoints.

Thin controllers — delegate to WithdrawalService.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies import (
    get_idempotency_key,
    get_client_ip,
    get_current_user,
    get_uow,
)
from app.api.v1.schemas import WithdrawalRequest, WithdrawalResponse, ErrorResponse
from app.core.exceptions import DomainError
from app.db.unit_of_work import UnitOfWork
from app.services.withdrawal_service import WithdrawalService

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("", status_code=201)
def request_withdrawal(
    withdrawal_data: WithdrawalRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    idempotency_key: str | None = Depends(get_idempotency_key),
    current_user: Any = Depends(get_current_user),
):
    """Request a withdrawal of available balance.

    The withdrawal enters PENDING status. The 24-hour cooldown
    is enforced between successful withdrawals.

    Idempotency: Use Idempotency-Key header to prevent duplicate requests.
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required for withdrawal requests",
        )

    try:
        service = WithdrawalService()
        with uow:
            result = service.request_withdrawal(
                uow=uow,
                user_id=str(current_user.id),
                amount=withdrawal_data.amount,
                currency=withdrawal_data.currency,
                idempotency_key=idempotency_key,
                ip_address=get_client_ip(request),
            )
        uow.commit()
        return result
    except DomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        uow.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{withdrawal_id}")
def get_withdrawal(
    withdrawal_id: str,
    uow: UnitOfWork = Depends(get_uow),
    current_user: Any = Depends(get_current_user),
):
    """Get withdrawal details."""
    service = WithdrawalService()
    result = service.get_withdrawal(uow, withdrawal_id)
    if not result:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    return result


@router.get("")
def list_withdrawals(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    uow: UnitOfWork = Depends(get_uow),
    current_user: Any = Depends(get_current_user),
):
    """List withdrawals for the current user."""
    from app.db.repositories.withdrawal_repo import WithdrawalRepository

    repo = WithdrawalRepository(uow.db)
    withdrawals = repo.get_by_user(str(current_user.id), skip=skip, limit=limit)

    items = [
        {
            "id": str(w.id),
            "amount": w.amount,
            "currency": w.currency,
            "status": w.status.value,
            "error_message": w.error_message,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in withdrawals
    ]
    return {"items": items, "skip": skip, "limit": limit, "total": len(items)}


@router.post("/{withdrawal_id}/cancel")
def cancel_withdrawal(
    withdrawal_id: str,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    idempotency_key: str | None = Depends(get_idempotency_key),
    current_user: Any = Depends(get_current_user),
):
    """Cancel a pending withdrawal.

    Only possible while withdrawal is in PENDING status.
    Money is credited back to available balance.
    """
    try:
        service = WithdrawalService()
        with uow:
            result = service.cancel_withdrawal(
                uow=uow,
                withdrawal_id=withdrawal_id,
                user_id=str(current_user.id),
                idempotency_key=idempotency_key,
            )
        uow.commit()
        return result
    except DomainError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        uow.rollback()
        raise HTTPException(status_code=500, detail=str(e))
