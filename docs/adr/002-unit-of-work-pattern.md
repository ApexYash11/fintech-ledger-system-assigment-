# ADR 002: Unit of Work Pattern

**Status:** Accepted  
**Context:** Financial operations span multiple entities (sale + payout + ledger + balance). Without atomicity, partial failures create inconsistent state.  
**Decision:** Use the Unit of Work pattern to wrap multi-repository operations in a single database transaction.  
**Consequences:**
- + Atomic commits across entities within a single request
- + Consistent rollback on any failure
- − Transaction scope must be carefully bounded to avoid long-held locks
- − Does not protect against cross-request coordination failures (handled by idempotency + recovery jobs)
