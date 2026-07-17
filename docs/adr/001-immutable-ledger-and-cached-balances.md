# ADR 001: Immutable Ledger with Cached Balances

**Status:** Accepted  
**Context:** Every money movement must be auditable, but summing a ledger on every request is slow.  
**Decision:** Use an append-only ledger as source of truth, with a denormalized UserBalance table as a read cache.  
**Consequences:**
- + Strong audit trail: every transaction is recorded immutably
- + Fast balance lookups: O(1) instead of O(n) ledger scan
- − Cache drift: resolved by periodic background reconciliation and ledger double-check for large amounts
- − Write amplification: each money movement writes both ledger and cache
