# System Architecture

## High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                       FastAPI Application                    │
├───────────────┬──────────────────────┬──────────────────────┤
│  API Layer     │   Service Layer      │   Infrastructure     │
│  (routes.py)   │   (services/)        │   (infra/)           │
├───────────────┼──────────────────────┼──────────────────────┤
│  sales        │  SaleService         │  Background Scheduler │
│  withdrawals  │  WithdrawalService   │  ├─ Advance Payouts  │
│  admin        │  ReconciliationSvc   │  ├─ Recovery Job     │
│  users        │  PayoutService       │  └─ Settlement Job   │
│  brands       │  BalanceService      │                      │
│  health       │  LedgerService       │  Payment Gateway     │
├───────────────┼──────────────────────┼──────────────────────┤
│              Database Layer (UnitOfWork)                    │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┐   │
│  │ Users  │ Brands │ Sales  │Payouts │Withdr. │Ledger  │   │
│  └────────┴────────┴────────┴────────┴────────┴────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Entity Relationship Diagram

```
┌──────────┐   1:N   ┌──────────┐   1:N   ┌───────────┐
│   User   │◄────────│  Sale    │◄────────│  Payout   │
├──────────┤         ├──────────┤         ├───────────┤
│ id (PK)  │         │ id (PK)  │         │ id (PK)   │
│ email    │         │ user_id  │         │ sale_id   │
│ name     │         │ brand_id │         │ user_id   │
│ status   │         │ earnings │         │ amount    │
└────┬─────┘         │ status   │         │ type      │
     │               │ external_id        │ status    │
     │               └──────────┘         │ idem_key  │
     │                                     └───────────┘
     │ 1:1
┌────┴──────────┐   1:N   ┌──────────────┐
│ UserBalance   │◄────────│ LedgerEntry  │
├───────────────┤         ├──────────────┤
│ user_id (FK)  │         │ id (PK)      │
│ avail_balance │         │ user_id      │
│ pend_balance  │         │ entry_type   │
│ currency      │         │ amount       │
└───────────────┘         │ reference_id │
                          │ idem_key     │
     ┌──────────┐         └──────────────┘
     │Withdrawal│
     ├──────────┤         ┌──────────────┐
     │ id (PK)  │         │  AuditLog    │
     │ user_id  │         ├──────────────┤
     │ amount   │         │ entity_type  │
     │ status   │         │ entity_id    │
     │ idem_key │         │ action       │
     └──────────┘         │ old_values   │
                          │ new_values   │
                          └──────────────┘
```

## State Machines

### Sale States
```
         ┌──────────┐
         │ PENDING  │
         └────┬─────┘
        ┌─────┴──────┐
        ▼            ▼
  ┌──────────┐ ┌──────────┐
  │ APPROVED │ │ REJECTED │  (terminal)
  └──────────┘ └──────────┘
```

### Payout States
```
         ┌──────────┐
         │ PENDING  │
         └────┬─────┘
        ┌─────┴──────┐
        ▼            ▼
  ┌──────────┐ ┌──────────┐
  │COMPLETED │ │  FAILED  │  (terminal)
  └──────────┘ └──────────┘
```

### Withdrawal States
```
         ┌──────────┐
         │ PENDING  │
         └────┬─────┘
     ┌───────┼─────────┐
     ▼       ▼         │
┌──────────┐ ┌──────────┐ │
│PROCESSING│ │CANCELLED │ │
└─────┬────┘ └──────────┘ │
  ┌───┼─────────┐         │
  ▼   ▼         ▼         │
┌────┐ ┌────┐ ┌──────┐    │
│COMP│ │FAIL│ │REJECT│    │
└────┘ └────┘ └──────┘    │
                          │
                          │
                   (terminal states)
```

## Transaction Flow: Sale Lifecycle

```
1. User creates sale via API → Sale(PENDING)
2. Background job: Advance Payout
   ├─ Create Payout(ADVANCE, PENDING)
   ├─ Create LedgerEntry(ADVANCE_PAYOUT, +amount)
   ├─ Update UserBalance(available += amount)
   └─ Send to Payment Gateway → Payout(COMPLETED|FAILED)
3. Admin reconciles sale
   ├─ APPROVED:
   │   ├─ Sale(APPROVED)
   │   ├─ Create Payout(FINAL_SETTLEMENT, PENDING)
   │   ├─ Create LedgerEntry(FINAL_PAYOUT, +remaining)
   │   └─ Send to Payment Gateway
   └─ REJECTED:
       ├─ Sale(REJECTED)
       ├─ Create LedgerEntry(NEGATIVE_ADJUSTMENT, -advance)
       └─ Update UserBalance(available -= advance)
```

## Transaction Flow: Withdrawal

```
1. User requests withdrawal → Withdrawal(PENDING)
   ├─ Check cooldown (24h since last withdrawal)
   ├─ Check balance (available >= amount)
   ├─ Deduct from UserBalance(available -= amount)
   └─ Create LedgerEntry(WITHDRAWAL, -amount)
2. Admin processes withdrawal → Withdrawal(PROCESSING)
3a. Gateway completes → Withdrawal(COMPLETED)
3b. Gateway fails → Withdrawal(FAILED)
    └─ Compensating: LedgerEntry(WITHDRAWAL_REVERSAL, +amount)
    └─ Restore: UserBalance(available += amount)
```

## Key Design Patterns

### Unit of Work
All database operations within a single business transaction use the UnitOfWork pattern. Multiple repository operations are committed atomically. If any operation fails, all changes are rolled back.

### Optimistic Locking
Every entity has a `version` column incremented on each update. Before updating, the application checks that the version matches the expected value. This prevents lost updates under concurrent access.

### Compensating Transactions
When a financial operation fails after partial processing (e.g., withdrawal fails after balance deduction), a compensating transaction reverses the effects. The original entry remains in the ledger for audit purposes.

### CQRS-like Separation
- **Ledger** is the write-optimized source of truth (append-only)
- **UserBalance** is a read-optimized cache (denormalized, periodically reconciled)

### Background Job Pattern
Jobs use the UnitOfWork pattern and catch per-item exceptions so a single failure doesn't block the entire batch. Each job is idempotent and can be safely re-run.

### Payment Gateway Abstraction
`PaymentGateway` abstract base class defines the contract. `MockPaymentGateway` simulates realistic behavior (latency, failures). In production, swap in a Stripe/RazorPay adapter without changing business logic.

## Database Schema Notes

- All UUID primary keys use `String(36)` for SQLite compatibility
- `DateTime(timezone=True)` columns store UTC timestamps
- SQLite enforces foreign keys via `PRAGMA foreign_keys=ON`
- WAL mode enabled for better concurrent read performance
