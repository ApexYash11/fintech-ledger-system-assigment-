# Edge Cases and Error Handling

## Idempotency

### Problem
Network issues can cause clients to retry requests. Without idempotency, duplicate requests create duplicate sales, withdrawals, or payouts — causing financial errors.

### Solution: Three-Layer Idempotency

**Layer 1 — API Middleware**
The `idempotency_middleware` intercepts all POST/PUT/PATCH/DELETE requests with an `Idempotency-Key` header. On the first request, it processes normally and caches the response keyed by the idempotency key. On duplicate requests, it returns the cached response without processing.

```
Request 1 (Idempotency-Key: abc) → Process → Cache response → Return 201
Request 2 (Idempotency-Key: abc) → Cache hit → Return 201 (X-Idempotency-Replay: true)
```

**Layer 2 — Database Constraints**
All idempotency-dependent tables have UNIQUE constraints on their idempotency key columns:
- `payouts.idempotency_key` (UNIQUE)
- `withdrawals.idempotency_key` (UNIQUE)  
- `ledger_entries.idempotency_key` (UNIQUE)
- `sales.external_id` (UNIQUE — acts as idempotency for external tracking)

**Layer 3 — Application-Level Checks**
Services check for existing records before creating new ones:
- `sale_service`: Checks `external_id` uniqueness before creating sale
- `withdrawal_service`: Checks `idempotency_key` before creating withdrawal
- `payout_service`: Checks `(sale_id, type)` uniqueness before creating advance payout

### Key Design Decision: Idempotency Check Before Cooldown
In the withdrawal flow, the idempotency check runs BEFORE the cooldown check. This ensures that a duplicate idempotent request returns the existing withdrawal record rather than raising a cooldown error.

## Concurrent Modification

### Problem
Two admin users simultaneously reconcile the same sale. Without protection, both operations could succeed, resulting in double payment.

### Solution: Pessimistic Locking

Reconciliation uses `SELECT ... FOR UPDATE` to lock the sale row before processing:

```
Admin A: BEGIN → SELECT FOR UPDATE sale_123 → Sale is PENDING → Approve → COMMIT
Admin B: BEGIN → SELECT FOR UPDATE sale_123 → (waits for A's lock)
                   → A commits → B reads updated sale → Sale is APPROVED → Raise error
```

The lock ensures only one admin processes the sale. The second admin sees the updated status and gets `SaleAlreadyReconciledError`.

### Optimistic Locking (Version Column)
All mutable entities have a `version` column. Updates increment the version and include `WHERE version = :expected` in the UPDATE statement. If another transaction modified the row, the UPDATE affects zero rows, and the application retries.

## Compensating Transactions

### Problem
A withdrawal succeeds (balance deducted) but the payment gateway fails. The user's money is stuck in limbo.

### Solution
When a withdrawal fails or is rejected after balance deduction, the system creates a compensating transaction:

1. Original: `LedgerEntry(WITHDRAWAL, -1000)` + `UserBalance(available -= 1000)`
2. Fail: `Withdrawal(FAILED)` + `LedgerEntry(WITHDRAWAL_REVERSAL, +1000)` + `UserBalance(available += 1000)`

The reversal is a NEW entry, not a modification of the original. This preserves the audit trail. The net effect on the user's balance is zero, but both entries are visible in the ledger.

## Race Conditions

### Balance Check → Deduction Window
Between checking the balance and deducting it, another request could spend the same money. Mitigated by:
1. Balance deduction happens in the same transaction as the check
2. Withdrawal processing re-checks balance before sending to gateway
3. For large withdrawals (>10,000), balance is verified against the ledger sum

### Duplicate Advance Payouts
The advance payout background job checks `(sale_id, type)` uniqueness before creating the payout. If two job runs overlap, the second one will find the existing payout and skip.

## Boundary Conditions

### Minimum Withdrawal
- Amount < `MIN_WITHDRAWAL_AMOUNT` (100.00): Rejected with `InvalidAmountError`
- Amount = 0 or negative: Rejected with `InvalidAmountError`
- Amount exactly at minimum: Accepted

### Maximum Precision
All amounts use `float`. In production, use `Decimal` to avoid floating-point issues. Current tests verify amounts to 2 decimal places.

### Balance Never Negative
The `update_balance` method in `balance_repo` applies `max(0, ...)` guards. Ledger calculations also floor at zero.

### 24-Hour Cooldown
After a completed withdrawal, the user must wait 24 hours before requesting another. The cooldown is computed from the last withdrawal's `created_at` timestamp. SQLite returns naive datetimes, so the service explicitly sets `tzinfo=timezone.utc` before comparison.

## Error Recovery

### Stuck Withdrawals (PROCESSING > 5 min)
The recovery background job runs every 5 minutes:
1. Finds withdrawals stuck in PROCESSING
2. Checks the payment gateway for actual status
3. If confirmed → Complete the withdrawal
4. If failed → Fail it and reverse the money
5. If no gateway reference → Fail it (was never sent)

### Failed Payout Retry
Advance payout failures don't block the sale. The background job retries on the next run. Payouts remain PENDING until the gateway confirms or the recovery job intervenes.

### Database Transaction Rollbacks
Every service operation wraps multiple repository calls in a single UnitOfWork. If any step fails:
1. All changes are rolled back
2. The exception is logged
3. The API returns a 500 error with the error details

## Audit Trail

Every state change and financial operation is recorded in the `audit_logs` table:
- `entity_type` / `entity_id`: Which record changed
- `action`: What happened (created, reconciled, completed, failed, etc.)
- `old_values` / `new_values`: JSON snapshots before and after
- `changed_by`: Who made the change
- `idempotency_key`: Links audit entries to the triggering request
- `ip_address`: Client IP for security auditing

## SQLite-Specific Considerations

### UUID Storage
SQLite lacks a native UUID type. All UUID columns use `String(36)`. Model instances must pass `str(uuid.uuid4())` (not `uuid.uuid4()`) for primary keys.

### Datetime Timezone
SQLite doesn't preserve timezone info. Columns declared with `DateTime(timezone=True)` return naive `datetime` objects. Service code uses `.replace(tzinfo=timezone.utc)` on retrieved values before timezone-aware comparisons.

### Autobegin
SQLAlchemy 2.0 uses autobegin — a transaction starts implicitly on the first database operation. The UnitOfWork does NOT call `session.begin()` explicitly. Nested `with uow:` blocks use savepoints via `session.begin_nested()`.

### Foreign Keys
SQLite has foreign key enforcement OFF by default. The engine setup enables it via `PRAGMA foreign_keys=ON` on every new connection.

## Testing Edge Cases

| Test | What It Covers |
|---|---|
| `test_concurrent_approve_reject` | Two services simultaneously reconciling the same sale |
| `test_duplicate_advance_job` | Background job running twice for the same sale |
| `test_withdrawal_exact_minimum` | Withdrawal of exactly the minimum allowed amount |
| `test_withdrawal_below_minimum` | Withdrawal below the minimum threshold |
| `test_zero_withdrawal` | Withdrawal amount of zero |
| `test_negative_withdrawal` | Negative withdrawal amount |
| `test_balance_never_negative` | Balance floor at zero after multiple deductions |
| `test_idempotent_withdrawal_request` | Duplicate withdrawal request with same idempotency key |
| `test_ledger_entry_immutable` | Ledger entries cannot be modified after creation |
| `test_balance_sync` | Cached balance can be recalculated from ledger |
| `test_double_reconciliation_fails` | Same sale approved twice |
| `test_create_sale_duplicate_external_id` | Duplicate external ID rejected |
