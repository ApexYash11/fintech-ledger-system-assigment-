"""Payment gateway abstraction.

Strategy pattern allows swapping payment providers without
changing business logic. The mock gateway is used for development
and testing.
"""

from app.config import settings
from app.infra.payment.base import PaymentGateway, PayoutResult, GatewayStatusResult


def create_gateway(gateway_type: str | None = None) -> PaymentGateway:
    """Factory: returns the appropriate PaymentGateway implementation.

    Args:
        gateway_type: 'mock', 'stripe', 'razorpay', etc.
                      Defaults to settings.payment_gateway.

    Returns:
        A PaymentGateway implementation.
    """
    gateway_type = gateway_type or settings.payment_gateway

    if gateway_type == "mock":
        from app.infra.payment.mock import MockPaymentGateway

        return MockPaymentGateway()

    raise ValueError(f"Unknown payment gateway: {gateway_type}")
