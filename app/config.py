from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    api_key: str = "test-api-key"

    log_level: str = "INFO"

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 100

    webhook_timeout_seconds: float = 10.0
    webhook_max_retries: int = 3


settings = Settings()
