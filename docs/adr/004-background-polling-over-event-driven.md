# ADR 004: Background Polling over Event-Driven Processing

**Status:** Accepted  
**Context:** Payout processing and withdrawal recovery need asynchronous execution. Options: in-process polling (APScheduler) or event-driven (Kafka/RabbitMQ).  
**Decision:** Use APScheduler polling for the current single-node deployment.  
**Consequences:**
- + Zero infrastructure dependencies: everything in one process
- + Simple operations: one thing to deploy and monitor
- + Idempotent by design: polling makes naturally at-least-once processing
- − Polling latency: up to 60s between job runs (acceptable for current scale)
- − No ordering guarantees: payouts may be processed in creation-order only (offset-based)
- − Future: extract to Celery/Redis Queue at Phase 3, Kafka at Phase 5
