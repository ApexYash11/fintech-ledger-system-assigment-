"""Brand API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_admin_user, get_uow
from app.api.v1.schemas import BrandCreate, BrandResponse
from app.core.enums import BrandStatus
from app.db.unit_of_work import UnitOfWork

router = APIRouter(prefix="/brands", tags=["brands"])


@router.post("", response_model=BrandResponse, status_code=201)
def create_brand(
    brand_data: BrandCreate,
    uow: UnitOfWork = Depends(get_uow),
    admin_user: Any = Depends(get_admin_user),
):
    """Create a new brand (admin only)."""
    from app.db.models.brand import Brand
    import uuid

    existing = uow.brands.get_by_code(brand_data.code)
    if existing:
        raise HTTPException(status_code=400, detail="Brand code already exists")

    brand = Brand(
        id=str(uuid.uuid4()),
        name=brand_data.name,
        code=brand_data.code,
        status=BrandStatus.ACTIVE,
    )
    with uow:
        uow.brands.add(brand)
    uow.commit()

    return BrandResponse(
        id=str(brand.id),
        name=brand.name,
        code=brand.code,
        status=brand.status.value,
    )


@router.get("", response_model=list[BrandResponse])
def list_brands(
    uow: UnitOfWork = Depends(get_uow),
):
    """List all brands."""
    brands = uow.brands.list_all()
    return [
        BrandResponse(
            id=str(b.id),
            name=b.name,
            code=b.code,
            status=b.status.value,
        )
        for b in brands
    ]
