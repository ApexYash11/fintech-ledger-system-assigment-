"""Background job implementations.

These jobs run on a schedule and perform batch processing of
business operations.

Error handling: Each job catches and logs exceptions per-item
so a single failure doesn't stop the entire batch.

Batching: Jobs process items in configurable batch sizes to
avoid memory issues and long-running transactions.
"""

from sqlalchemy.orm import Session

from app.config import settings
from app.core.enums import WithdrawalStatus


def process_advance_payouts(db: Session) -> dict:
    """Process pending sales and create advance payouts.

    Workflow:
    1. Query for pending sales without existing advance payouts
    2. For each sale, create an advance payout (10% of earnings)
    3. Create ledger entries and update balances
    4. Process payouts through the payment gateway

    Idempotency: Each sale is checked for existing advance payout
    before processing. Duplicate job runs are safe.

    Batching: Processes sales in pages of settings.batch_size using
    offset-based pagination. Loops until all pending sales are processed.
    """
    from app.db.repositories.sale_repo import SaleRepository
    from app.db.repositories.payout_repo import PayoutRepository
    from app.db.unit_of_work import UnitOfWork
    from app.services.payout_service import PayoutService
    from app.infra.payment.mock import MockPaymentGateway
    from app.core.enums import PayoutType

    payout_service = PayoutService()
    gateway = MockPaymentGateway()

    sale_repo = SaleRepository(db)
    uow = UnitOfWork(db)

    processed = 0
    errors = 0
    offset = 0

    while True:
        sales = sale_repo.get_pending_sales_batch(
            batch_size=settings.batch_size,
            offset=offset,
        )
        if not sales:
            break

        for sale in sales:
            try:
                uow = UnitOfWork(db)
                with uow:
                    payout_service.create_advance_payout(uow, str(sale.id))
                uow.commit()
                processed += 1
            except Exception as e:
                uow.rollback()
                errors += 1
                import logging

                logging.error(f"Failed to create advance payout for sale {sale.id}: {e}")

        offset += len(sales)

    # Process created payouts through gateway
    if processed > 0:
        try:
            payout_repo = PayoutRepository(db)
            pending_payouts = payout_repo.get_pending_payouts_batch(
                settings.batch_size,
                payout_type=PayoutType.ADVANCE,
            )
            for payout in pending_payouts:
                try:
                    result = gateway.send_payout(
                        user_id=str(payout.user_id),
                        amount=payout.amount,
                        currency="INR",
                        idempotency_key=payout.idempotency_key,
                    )
                    uow = UnitOfWork(db)
                    with uow:
                        if result.success:
                            payout_service.complete_payout(
                                uow,
                                str(payout.id),
                                gateway_reference=result.reference,
                            )
                        else:
                            payout_service.fail_payout(
                                uow,
                                str(payout.id),
                                error_message=result.error,
                            )
                    uow.commit()
                except Exception as e:
                    uow.rollback()
                    import logging

                    logging.error(f"Failed to process payout {payout.id}: {e}")
        except Exception as e:
            import logging

            logging.error(f"Failed to process payouts through gateway: {e}")

    return {
        "job": "advance_payout",
        "sales_processed": processed,
        "errors": errors,
    }


def recover_stuck_withdrawals(db: Session) -> dict:
    """Recover withdrawals stuck in PROCESSING status.

    Workflow:
    1. Query for withdrawals in PROCESSING for too long
    2. Check with payment gateway for actual status
    3. Update withdrawal status accordingly
    4. If gateway status is confirmed → complete withdrawal
    5. If gateway status is failed → fail withdrawal + reverse money
    6. If gateway has no record → mark for manual review

    This handles the case where:
    - The gateway processed but the callback/webhook was lost
    - The server crashed after sending to gateway but before saving
    - The gateway is slow to respond

    Batching: Processes up to settings.batch_size withdrawals per run.
    """
    from app.db.repositories.withdrawal_repo import WithdrawalRepository
    from app.db.unit_of_work import UnitOfWork
    from app.services.withdrawal_service import WithdrawalService
    from app.infra.payment.mock import MockPaymentGateway

    withdrawal_service = WithdrawalService()
    gateway = MockPaymentGateway()

    withdrawal_repo = WithdrawalRepository(db)
    uow = UnitOfWork(db)

    recovered = 0
    errors = 0

    withdrawals = withdrawal_repo.get_processing_withdrawals_batch(batch_size=settings.batch_size)

    for withdrawal in withdrawals:
        try:
            # Check with gateway if we have a reference
            if withdrawal.gateway_reference:
                gateway_status = gateway.get_withdrawal_status(withdrawal.gateway_reference)

                uow = UnitOfWork(db)
                with uow:
                    if gateway_status.status == "confirmed":
                        withdrawal_service.complete_withdrawal(
                            uow,
                            str(withdrawal.id),
                            gateway_reference=withdrawal.gateway_reference,
                        )
                    elif gateway_status.status == "failed":
                        withdrawal_service.fail_withdrawal(
                            uow,
                            str(withdrawal.id),
                            error_message="Gateway reported failure during recovery",
                        )
                    # If unknown, leave as PROCESSING for manual review
                uow.commit()
                recovered += 1
            else:
                # No gateway reference — this withdrawal was never sent
                # to the gateway. Fail it and reverse the money.
                uow = UnitOfWork(db)
                with uow:
                    withdrawal_service.fail_withdrawal(
                        uow,
                        str(withdrawal.id),
                        error_message="Recovery: No gateway reference found",
                    )
                uow.commit()
                recovered += 1

        except Exception as e:
            uow.rollback()
            errors += 1
            import logging

            logging.error(f"Failed to recover withdrawal {withdrawal.id}: {e}")

    return {
        "job": "recovery",
        "withdrawals_recovered": recovered,
        "errors": errors,
    }


def process_settlements(db: Session) -> dict:
    """Process pending final settlement payouts through the gateway.

    Called periodically to ensure settlement payouts (created during
    sale approval) are sent to the payment gateway.

    Only processes FINAL_SETTLEMENT payouts (excludes ADVANCE payouts
    which are handled by process_advance_payouts).

    Batching: Processes up to settings.batch_size payouts per run.
    """
    from app.db.repositories.payout_repo import PayoutRepository
    from app.db.unit_of_work import UnitOfWork
    from app.services.payout_service import PayoutService
    from app.infra.payment.mock import MockPaymentGateway
    from app.core.enums import PayoutType

    payout_service = PayoutService()
    gateway = MockPaymentGateway()
    payout_repo = PayoutRepository(db)

    processed = 0
    succeeded = 0
    failed_count = 0

    payouts = payout_repo.get_pending_payouts_batch(
        batch_size=settings.batch_size,
        payout_type=PayoutType.FINAL_SETTLEMENT,
    )

    for payout in payouts:
        try:
            result = gateway.send_payout(
                user_id=str(payout.user_id),
                amount=payout.amount,
                currency="INR",
                idempotency_key=payout.idempotency_key,
            )

            uow = UnitOfWork(db)
            with uow:
                if result.success:
                    payout_service.complete_payout(
                        uow,
                        str(payout.id),
                        gateway_reference=result.reference,
                    )
                    succeeded += 1
                else:
                    payout_service.fail_payout(
                        uow,
                        str(payout.id),
                        error_message=result.error,
                    )
                    failed_count += 1
            uow.commit()
            processed += 1

        except Exception as e:
            uow.rollback()
            failed_count += 1
            import logging

            logging.error(f"Failed to process settlement payout {payout.id}: {e}")

    return {
        "job": "settlement",
        "payouts_processed": processed,
        "succeeded": succeeded,
        "failed": failed_count,
    }
