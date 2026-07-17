"""APScheduler setup and management.

The scheduler manages three periodic jobs:
1. Advance payout job (every 60 seconds)
2. Recovery job (every 5 minutes)
3. Settlement job (every hour)

Each job runs in its own thread to avoid blocking.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings


def setup_scheduler() -> BackgroundScheduler:
    """Create and configure the background scheduler.

    Returns a started scheduler instance. Call shutdown() on
    application exit to ensure graceful termination.
    """
    scheduler = BackgroundScheduler(daemon=True)

    # Import job functions (lazy import to avoid circular deps)
    from app.infra.background.jobs import (
        process_advance_payouts,
        recover_stuck_withdrawals,
        process_settlements,
    )
    from app.db.session import SessionLocal

    def _run_job(job_func):
        """Wrapper that creates a DB session for each job run."""
        db = SessionLocal()
        try:
            job_func(db)
        except Exception:
            import traceback

            traceback.print_exc()
        finally:
            db.close()

    # Advance payout job — every 60 seconds
    scheduler.add_job(
        _run_job,
        args=[process_advance_payouts],
        trigger=IntervalTrigger(seconds=settings.advance_payout_interval_seconds),
        id="advance_payout_job",
        name="Process pending advance payouts",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Recovery job — every 5 minutes
    scheduler.add_job(
        _run_job,
        args=[recover_stuck_withdrawals],
        trigger=IntervalTrigger(seconds=settings.recovery_interval_seconds),
        id="recovery_job",
        name="Recover stuck processing withdrawals",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # Settlement job — every hour
    scheduler.add_job(
        _run_job,
        args=[process_settlements],
        trigger=IntervalTrigger(seconds=settings.settlement_interval_seconds),
        id="settlement_job",
        name="Process pending settlements",
        replace_existing=True,
        misfire_grace_time=120,
    )

    scheduler.start()
    return scheduler
