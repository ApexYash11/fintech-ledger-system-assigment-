"""FastAPI application entry point.

Creates and configures the FastAPI application with:
- Route registration
- Middleware (CORS, idempotency, error handling)
- Background scheduler initialization
- Database table creation
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown.

    Startup:
    1. Create database tables (for SQLite dev — use Alembic in production)
    2. Start background scheduler

    Shutdown:
    1. Shutdown background scheduler gracefully
    """
    # Startup
    from app.db.base import Base
    from app.db.session import engine

    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)

    scheduler = None
    if settings.environment != "test":
        from app.infra.background.scheduler import setup_scheduler

        scheduler = setup_scheduler()

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="User Payout Management System",
    description="Production-inspired fintech ledger system for managing affiliate payouts",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Middleware ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def idempotency_middleware(request: Request, call_next):
    """Idempotency middleware — handles Idempotency-Key header.

    For POST/PUT/PATCH/DELETE requests with an Idempotency-Key:
    1. First request: Process normally, cache the response
    2. Duplicate request: Return cached response without processing

    This provides exactly-once semantics for the API layer.

    Uses the app's dependency overrides for DB session resolution,
    so tests can inject their own session via get_db override.
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return await call_next(request)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return await call_next(request)

    from app.db.session import get_db as _get_db
    from app.db.repositories.idempotency_repo import IdempotencyRepository

    db_resolver = request.app.dependency_overrides.get(_get_db, _get_db)
    db_gen = db_resolver()
    db = next(db_gen)
    try:
        repo = IdempotencyRepository(db)
        cached = repo.get_by_key(idempotency_key)
        if cached:
            import json

            return JSONResponse(
                status_code=cached.response_status,
                content=json.loads(cached.response_body) if cached.response_body else {},
                headers={"X-Idempotency-Replay": "true"},
            )
    finally:
        db_gen.close()

    response = await call_next(request)

    # Cache the response for future idempotent requests
    if response.status_code < 500:
        db_gen2 = db_resolver()
        db2 = next(db_gen2)
        try:
            repo = IdempotencyRepository(db2)
            import json

            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Re-create the response since we consumed the body
            response = JSONResponse(
                status_code=response.status_code,
                content=json.loads(body) if body else {},
                headers=dict(response.headers),
            )

            repo.store_response(
                key=idempotency_key,
                status_code=response.status_code,
                body=body.decode() if body else None,
            )
            db2.commit()
        except Exception:
            db2.rollback()
        finally:
            db_gen2.close()

    return response


@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Global error handling middleware.

    Catches unhandled exceptions and returns a consistent JSON error response.
    """
    try:
        return await call_next(request)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "internal_error"},
        )


# ─── Register Routers ──────────────────────────────────────

from app.api.v1 import sales, withdrawals, admin, users, health, brands

app.include_router(sales.router, prefix="/api/v1")
app.include_router(withdrawals.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(brands.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
