"""Application configuration using pydantic-settings.

All configuration is loaded from environment variables / .env file.
No hardcoded configuration values in application code.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./data/ledger.db"

    # Application
    environment: str = "development"
    debug: bool = True

    # Business rules
    advance_payout_percentage: float = 0.10
    min_withdrawal_amount: float = 100.00
    withdrawal_cooldown_hours: int = 24

    # Batch processing
    batch_size: int = 100
    advance_payout_interval_seconds: int = 60
    recovery_interval_seconds: int = 300
    settlement_interval_seconds: int = 3600

    # Payment gateway
    payment_gateway: str = "mock"

    # Security
    admin_secret_key: str = "admin-secret-key"

    # Balance verification threshold — amounts at or above this trigger
    # a ledger double-check to catch cached balance drift
    balance_check_threshold: float = 10000.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
