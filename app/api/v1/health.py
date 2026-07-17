"""Health check endpoint."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.api.v1.schemas import HealthResponse
from app.db.session import SessionLocal


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint.

    Returns basic information about the service status.
    Verifies database connectivity with a lightweight query.
    """
    from app.config import settings

    db_status = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    if db_status != "ok":
        raise HTTPException(
            status_code=503,
            detail=HealthResponse(
                status="degraded",
                version="0.1.0",
                environment=settings.environment,
            ).model_dump(),
        )

    return HealthResponse(
        status="ok",
        version="0.1.0",
        environment=settings.environment,
    )
