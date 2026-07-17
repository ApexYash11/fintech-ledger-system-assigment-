"""Pytest configuration and shared fixtures.

Provides:
- Test database setup/teardown
- Factory fixtures for creating test data
- Unit of Work fixture for service tests
"""

import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.enums import (
    UserStatus,
    BrandStatus,
    SaleStatus,
    PayoutStatus,
    PayoutType,
    WithdrawalStatus,
    Currency,
)
from app.db.base import Base
from app.db.models.user import User
from app.db.models.brand import Brand
from app.db.models.sale import Sale
from app.db.models.payout import Payout
from app.db.models.withdrawal import Withdrawal
from app.db.models.ledger import LedgerEntry
from app.db.models.user_balance import UserBalance
from app.db.models.idempotency import IdempotencyKey
from app.db.models.audit_log import AuditLog
from app.infra.payment.mock import MockPaymentGateway

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine (in-memory SQLite)."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    connection = test_engine.connect()
    session = Session(bind=connection)
    yield session
    session.close()
    connection.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI test client with overridden dependencies."""
    from fastapi import Depends
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ─── Factory Fixtures ──────────────────────────────────────


@pytest.fixture
def user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid.uuid4()),
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        name="Test User",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create a test admin user."""
    admin = User(
        id=str(uuid.uuid4()),
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        name="Admin User",
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


@pytest.fixture
def brand(db_session: Session) -> Brand:
    """Create a test brand."""
    brand = Brand(
        id=str(uuid.uuid4()),
        name="Test Brand",
        code=f"BRAND_{uuid.uuid4().hex[:6]}",
        status=BrandStatus.ACTIVE,
    )
    db_session.add(brand)
    db_session.commit()
    return brand


@pytest.fixture
def pending_sale(db_session: Session, user: User, brand: Brand) -> Sale:
    """Create a pending sale."""
    sale = Sale(
        id=str(uuid.uuid4()),
        user_id=user.id,
        brand_id=brand.id,
        external_id=f"EXT_{uuid.uuid4().hex}",
        earnings=1000.00,
        status=SaleStatus.PENDING,
    )
    db_session.add(sale)
    db_session.commit()
    return sale


@pytest.fixture
def advance_payout(db_session: Session, pending_sale: Sale, user: User) -> Payout:
    """Create an advance payout for a pending sale."""
    payout = Payout(
        id=str(uuid.uuid4()),
        sale_id=pending_sale.id,
        user_id=user.id,
        amount=100.00,
        type=PayoutType.ADVANCE,
        status=PayoutStatus.COMPLETED,
        idempotency_key=f"advance_{pending_sale.id}",
    )
    db_session.add(payout)
    db_session.commit()
    return payout


@pytest.fixture
def user_balance(db_session: Session, user: User) -> UserBalance:
    """Create a user balance with available funds."""
    balance = UserBalance(
        id=str(uuid.uuid4()),
        user_id=user.id,
        available_balance=5000.00,
        pending_balance=0.0,
    )
    db_session.add(balance)
    db_session.commit()
    return balance


@pytest.fixture
def payment_gateway() -> MockPaymentGateway:
    """Create a mock payment gateway with 100% success."""
    return MockPaymentGateway(success_rate=1.0, latency_ms=0)


@pytest.fixture
def unit_of_work(db_session: Session):
    """Provide a UnitOfWork instance."""
    from app.db.unit_of_work import UnitOfWork

    return UnitOfWork(db_session)
