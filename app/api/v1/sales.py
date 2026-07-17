"""Sale API endpoints.

Thin controllers — no business logic, just:
1. Parse/validate request
2. Call service
3. Format response
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dependencies import (
    get_idempotency_key,
    get_client_ip,
    get_current_user,
    get_uow,
)
from app.api.v1.schemas import SaleCreate, SaleResponse, ErrorResponse
from app.core.exceptions import DomainError
from app.db.unit_of_work import UnitOfWork
from app.services.sale_service import SaleService

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("", response_model=dict, status_code=201)
def create_sale(
    sale_data: SaleCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    idempotency_key: str | None = Depends(get_idempotency_key),
    current_user: Any = Depends(get_current_user),
):
    """Create a new pending affiliate sale.

    The sale enters PENDING status. An advance payout will be
    created by the background job.

    Idempotency: Use Idempotency-Key header to prevent duplicate sales.
    """
    try:
        service = SaleService()
        with uow:
            result = service.create_sale(
                uow=uow,
                user_id=sale_data.user_id,
                brand_id=sale_data.brand_id,
                external_id=sale_data.external_id,
                earnings=sale_data.earnings,
                currency=sale_data.currency,
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


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(
    sale_id: str,
    uow: UnitOfWork = Depends(get_uow),
    current_user: Any = Depends(get_current_user),
):
    """Get details of a specific sale."""
    service = SaleService()
    result = service.get_sale(uow, sale_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sale not found")
    return result


@router.get("", response_model=dict)
def list_sales(
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    uow: UnitOfWork = Depends(get_uow),
    current_user: Any = Depends(get_current_user),
):
    """List sales for the current user."""
    service = SaleService()
    items = service.list_user_sales(
        uow,
        user_id=str(current_user.id),
        status=status,
        skip=skip,
        limit=limit,
    )
    return {"items": items, "skip": skip, "limit": limit, "total": len(items)}
