"""Pydantic schemas for API request/response validation.

All money-related fields use float for simplicity.
In production, use a Decimal type to avoid floating-point issues.
"""

from datetime import datetime
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
    user_id: str
    brand_id: str
    external_id: str = Field(..., max_length=255)
    earnings: float = Field(..., gt=0)
    currency: str = "INR"


class SaleResponse(BaseModel):
    id: str
    user_id: str
    brand_id: str
    external_id: str
    earnings: float
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
    remaining_payout: float | None = None
    final_payout_id: str | None = None
    advance_recovered: bool = False
    advance_amount: float | None = None
    adjustment: float | None = None


# ─── Withdrawals ────────────────────────────────────────────


class WithdrawalRequest(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = "INR"


class WithdrawalResponse(BaseModel):
    id: str
    user_id: str
    amount: float
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
    available_balance: float
    pending_balance: float
    ledger_balance: float
    currency: str
    is_synced: bool


# ─── Health ─────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    environment: str = "development"
