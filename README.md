# User Payout Management System

Production-inspired fintech ledger system for managing affiliate payouts. Built with FastAPI, SQLAlchemy 2.0, and SQLite.

## Features

- **Sale Management** — Track affiliate sales through pending → approved/rejected lifecycle
- **Advance Payouts** — 10% advance on pending sales, processed via background jobs
- **Final Settlements** — Remaining balance paid on sale approval
- **Withdrawals** — User-initiated withdrawals with 24-hour cooldown and idempotency
- **Immutable Ledger** — Every money movement recorded in an append-only journal
- **Cached Balances** — Denormalized balances with ledger as source of truth
- **Idempotency** — Exactly-once semantics for all money-moving operations
- **State Machines** — Explicit state transitions with validation
- **Optimistic Locking** — Version-based concurrency control
- **Background Jobs** — APScheduler-based advance payout, recovery, and settlement jobs
- **Audit Logging** — Every state change and money movement is logged

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

## Configuration

All configuration via `.env` file or environment variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/ledger.db` | Database connection string |
| `ENVIRONMENT` | `development` | Runtime environment |
| `DEBUG` | `true` | Enable debug logging |
| `ADVANCE_PAYOUT_PERCENTAGE` | `0.10` | Percentage of earnings paid as advance |
| `MIN_WITHDRAWAL_AMOUNT` | `100.00` | Minimum withdrawal amount |
| `WITHDRAWAL_COOLDOWN_HOURS` | `24` | Cooldown between withdrawals |
| `BATCH_SIZE` | `100` | Batch size for background jobs |

## API Reference

### Users

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/users` | Create user |
| GET | `/api/v1/users/me` | Get current user |
| GET | `/api/v1/users/me/balance` | Get user balance |

### Brands (Admin)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/brands` | Create brand |
| GET | `/api/v1/brands` | List brands |

### Sales

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/sales` | Create sale |
| GET | `/api/v1/sales/{id}` | Get sale |
| GET | `/api/v1/sales` | List user sales |

### Withdrawals

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/withdrawals` | Request withdrawal |
| GET | `/api/v1/withdrawals/{id}` | Get withdrawal |
| GET | `/api/v1/withdrawals` | List user withdrawals |
| POST | `/api/v1/withdrawals/{id}/cancel` | Cancel pending withdrawal |

### Admin

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/admin/reconcile` | Reconcile a sale (APPROVED/REJECTED) |
| GET | `/api/v1/admin/pending-sales` | List pending sales |
| GET | `/api/v1/admin/withdrawals` | List all withdrawals |
| POST | `/api/v1/admin/withdrawals/{id}/action` | Process withdrawal (process/complete/reject/fail) |

### Auth Headers

| Header | Description |
|---|---|
| `X-User-Id` | User ID (mock auth) |
| `X-Admin-Key` | Admin key: `admin-secret-key` |
| `Idempotency-Key` | Unique request key (required for POST operations) |

## Project Structure

```
├── app/
│   ├── api/v1/          # Route handlers (thin controllers)
│   ├── core/            # Enums, exceptions, state machines
│   ├── db/
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── repositories/ # Data access layer
│   │   ├── base.py      # Declarative base + mixins
│   │   ├── session.py   # Engine + session factory
│   │   └── unit_of_work.py
│   ├── infra/
│   │   ├── audit/       # Audit logging
│   │   ├── background/  # APScheduler jobs
│   │   └── payment/     # Payment gateway abstraction
│   ├── services/        # Business logic layer
│   ├── config.py        # pydantic-settings configuration
│   └── main.py          # FastAPI app + middleware
├── migrations/          # Alembic database migrations
├── tests/               # Pytest test suite
├── docs/                # Documentation
├── .env                 # Environment variables
├── alembic.ini          # Alembic configuration
├── pyproject.toml       # Project metadata
└── requirements.txt     # Python dependencies
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_services.py -v
```

Test categories:
- **State Machine Tests** (17) — Pure logic, no database
- **Service Tests** (16) — Business logic with database
- **Edge Case Tests** (10) — Boundary conditions and concurrency
- **API Tests** (11) — Full HTTP request/response cycle

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed system design, entity relationships, state machines, and transaction flows.

## Edge Cases

See [docs/edge_cases.md](docs/edge_cases.md) for idempotency, concurrent modification, compensating transactions, and error recovery strategies.
