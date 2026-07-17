# ADR 003: State Machine Validation at Service Layer

**Status:** Accepted  
**Context:** Entities (Sale, Payout, Withdrawal) have legal state transitions. Invalid transitions would cause financial inconsistencies.  
**Decision:** Implement state machine validation as pure functions in a separate module, invoked by services before state changes. Not in the model, not in the API layer.  
**Consequences:**
- + State logic is testable without database setup (pure Python, no SQLAlchemy)
- + Services can inspect transition legality without instantiating a state machine object
- − Services must remember to validate; no protection if a developer forgets to call validate_transition()
- − In production, this would be enforced at the database level via CHECK constraints as defense-in-depth
