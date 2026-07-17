"""Health check endpoint."""

from fastapi import APIRouter

from app.api.v1.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint.

    Returns basic information about the service status.
    In production, this would check DB connectivity, queue health, etc.
    """
    from app.config import settings

    return HealthResponse(
        status="ok",
        version="0.1.0",
        environment=settings.environment,
    )
