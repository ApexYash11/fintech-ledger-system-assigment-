"""Domain exceptions for the payout management system.

Every business rule violation has a dedicated exception class.
This enables precise error handling at the API layer without
leaking implementation details.
"""


class DomainError(Exception):
    """Base for all domain errors."""

    def __init__(self, message: str, code: str = "domain_error"):
        self.code = code
        super().__init__(message)


class InsufficientBalanceError(DomainError):
    def __init__(self, user_id: str, available: float, requested: float):
        super().__init__(
            message=f"User {user_id} has insufficient balance. "
            f"Available: {available}, Requested: {requested}",
            code="insufficient_balance",
        )
        self.user_id = user_id
        self.available = available
        self.requested = requested


class InvalidStateTransitionError(DomainError):
    def __init__(self, entity_type: str, entity_id: str, from_status: str, to_status: str):
        super().__init__(
            message=f"Cannot transition {entity_type} {entity_id} "
            f"from {from_status} to {to_status}",
            code="invalid_state_transition",
        )
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.from_status = from_status
        self.to_status = to_status


class DuplicateIdempotencyKeyError(DomainError):
    def __init__(self, key: str):
        super().__init__(
            message=f"Idempotency key {key} has already been processed",
            code="duplicate_idempotency_key",
        )


class WithdrawalCooldownError(DomainError):
    def __init__(self, user_id: str, hours_remaining: float):
        super().__init__(
            message=f"User {user_id} must wait {hours_remaining:.1f} hours before next withdrawal",
            code="withdrawal_cooldown",
        )
        self.hours_remaining = hours_remaining


class EntityNotFoundError(DomainError):
    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            message=f"{entity_type} with id {entity_id} not found",
            code=f"{entity_type.lower()}_not_found",
        )


class PaymentGatewayError(DomainError):
    def __init__(self, message: str, gateway_txn_id: str | None = None):
        super().__init__(message=f"Payment gateway error: {message}", code="payment_gateway_error")
        self.gateway_txn_id = gateway_txn_id


class ConcurrentModificationError(DomainError):
    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            message=f"Concurrent modification detected for {entity_type} {entity_id}. "
            f"Retry the operation.",
            code="concurrent_modification",
        )


class AdvanceAlreadyPaidError(DomainError):
    def __init__(self, sale_id: str):
        super().__init__(
            message=f"Advance payout already exists for sale {sale_id}", code="advance_already_paid"
        )


class SaleAlreadyReconciledError(DomainError):
    def __init__(self, sale_id: str, current_status: str):
        super().__init__(
            message=f"Sale {sale_id} is already {current_status}", code="sale_already_reconciled"
        )


class InvalidAmountError(DomainError):
    def __init__(self, message: str):
        super().__init__(message=message, code="invalid_amount")


class UserNotActiveError(DomainError):
    def __init__(self, user_id: str):
        super().__init__(message=f"User {user_id} is not active", code="user_not_active")
