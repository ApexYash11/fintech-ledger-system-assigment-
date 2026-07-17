"""Background job infrastructure.

Uses APScheduler for cron-like periodic job execution.
Jobs implement the Outbox pattern for reliable processing.

Design decision: Why APScheduler instead of Celery/Arq?
1. Simpler setup — no message broker (Redis/RabbitMQ) required
2. Suitable for single-node deployments
3. For an intern assignment, this demonstrates the concept without
   introducing infrastructure complexity
4. Can be replaced with Celery/Arq/Temporal when scaling to multi-node

Tradeoff: APScheduler doesn't provide exactly-once guarantees.
Mitigation: Each job is idempotent (checks for existing work before
processing), and we use database transactions for atomicity.
"""
