"""Admin API endpoints — reconciliation and management.

All admin endpoints require admin authentication.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies import (
    get_idempotency_key,
    get_client_ip,
    get_admin_user,
    get_uow,
)
from app.api.v1.schemas import (
    ReconciliationRequest,
    ReconciliationResponse,
    WithdrawalAction,
    ErrorResponse,
)
from app.core.exceptions import DomainError
from app.db.unit_of_work import UnitOfWork
from app.services.reconciliation_service import ReconciliationService
from app.services.withdrawal_service import WithdrawalService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reconcile", response_model=ReconciliationResponse)
def reconcile_sale(
    req: ReconciliationRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    idempotency_key: str | None = Depends(get_idempotency_key),
    admin_user: Any = Depends(get_admin_user),
):
    """Reconcile a pending sale to APPROVED or REJECTED.

    This is a CRITICAL financial operation:
    - APPROVED: Remaining payout = Earnings - Advance Paid
    - REJECTED: Advance becomes negative adjustment
    """
    try:
        service = ReconciliationService()
        with uow:
            result = service.reconcile_sale(
                uow=uow,
                sale_id=req.sale_id,
                admin_id=str(admin_user.id),
                decision=req.decision,
                notes=req.notes,
                idempotency_key=idempotency_key,
                ip_address=get_client_ip(request),
            )
        uow.commit()
        return result
    except DomainError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        uow.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-sales", response_model=dict)
def list_pending_sales(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    uow: UnitOfWork = Depends(get_uow),
    admin_user: Any = Depends(get_admin_user),
):
    """List all pending sales needing reconciliation."""
    service = ReconciliationService()
    items = service.get_pending_sales(uow, skip=skip, limit=limit)
    return {"items": items, "skip": skip, "limit": limit, "total": len(items)}


@router.get("/withdrawals", response_model=dict)
def list_withdrawals(
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    uow: UnitOfWork = Depends(get_uow),
    admin_user: Any = Depends(get_admin_user),
):
    """List all withdrawals (admin view)."""
    from app.db.repositories.withdrawal_repo import WithdrawalRepository

    repo = WithdrawalRepository(uow.db)
    withdrawals = repo.list_all(skip=skip, limit=limit)

    items = [
        {
            "id": str(w.id),
            "user_id": str(w.user_id),
            "amount": w.amount,
            "currency": w.currency,
            "status": w.status.value,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in withdrawals
    ]
    return {"items": items, "skip": skip, "limit": limit, "total": len(items)}


@router.post("/withdrawals/{withdrawal_id}/action", response_model=dict)
def process_withdrawal_action(
    withdrawal_id: str,
    action: WithdrawalAction,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    idempotency_key: str | None = Depends(get_idempotency_key),
    admin_user: Any = Depends(get_admin_user),
):
    """Process an admin action on a withdrawal.

    Actions:
    - process: Move to PROCESSING status
    - complete: Mark as COMPLETED
    - reject: Reject the withdrawal (money credited back)
    - fail: Fail the withdrawal (money credited back)
    """
    from app.core.enums import WithdrawalStatus

    service = WithdrawalService()

    try:
        with uow:
            if action.action == "process":
                result = service.process_withdrawal(
                    uow,
                    withdrawal_id,
                    admin_id=str(admin_user.id),
                    ip_address=get_client_ip(request),
                )
            elif action.action == "complete":
                result = service.complete_withdrawal(
                    uow,
                    withdrawal_id,
                    idempotency_key=idempotency_key,
                )
            elif action.action == "reject":
                result = service.reject_withdrawal(
                    uow,
                    withdrawal_id,
                    admin_id=str(admin_user.id),
                    reason=action.reason,
                    idempotency_key=idempotency_key,
                )
            elif action.action == "fail":
                result = service.fail_withdrawal(
                    uow,
                    withdrawal_id,
                    error_message=action.reason,
                    idempotency_key=idempotency_key,
                )
            else:
                raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
        uow.commit()
        return result
    except DomainError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        uow.rollback()
        raise HTTPException(status_code=500, detail=str(e))
