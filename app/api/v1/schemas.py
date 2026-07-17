"""Pydantic schemas for API request/response validation.

Money fields use Decimal to avoid floating-point precision issues.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


# ─── Common ─────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"
    errors: list[dict[str, Any]] | None = None


class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int = 0
    skip: int = 0
    limit: int = 100


# ─── Users ──────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: str = Field(..., max_length=255)
    name: str = Field(..., max_length=255)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    status: str
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ─── Brands ─────────────────────────────────────────────────


class BrandCreate(BaseModel):
    name: str = Field(..., max_length=255)
    code: str = Field(..., max_length=50)


class BrandResponse(BaseModel):
    id: str
    name: str
    code: str
    status: str

    model_config = ConfigDict(from_attributes=True)


# ─── Sales ──────────────────────────────────────────────────


class SaleCreate(BaseModel):
    brand_id: str
    external_id: str = Field(..., max_length=255)
    earnings: Decimal = Field(..., gt=Decimal("0"))
    currency: str = "INR"


class SaleResponse(BaseModel):
    id: str
    user_id: str
    brand_id: str
    external_id: str
    earnings: Decimal
    status: str
    currency: str
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ─── Reconciliation ────────────────────────────────────────


class ReconciliationRequest(BaseModel):
    sale_id: str
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    notes: str | None = None


class ReconciliationResponse(BaseModel):
    sale_id: str
    status: str
    decision: str
    remaining_payout: Decimal | None = None
    final_payout_id: str | None = None
    advance_recovered: bool = False
    advance_amount: Decimal | None = None
    adjustment: Decimal | None = None


# ─── Withdrawals ────────────────────────────────────────────


class WithdrawalRequest(BaseModel):
    amount: Decimal = Field(..., gt=Decimal("0"))
    currency: str = "INR"


class WithdrawalResponse(BaseModel):
    id: str
    user_id: str
    amount: Decimal
    currency: str
    status: str
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WithdrawalAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|cancel|fail|complete)$")
    reason: str | None = None


# ─── Balance ────────────────────────────────────────────────


class BalanceResponse(BaseModel):
    user_id: str
    available_balance: Decimal
    pending_balance: Decimal
    ledger_balance: Decimal
    currency: str
    is_synced: bool


# ─── Health ─────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    environment: str = "development"
