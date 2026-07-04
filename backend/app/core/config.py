"""Core configuration module using Pydantic Settings."""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://djs_user:djs_password@localhost:5432/djs_db"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Job Scheduling & Worker
    JOB_LEASE_DURATION_SECONDS: int = 30
    JOB_LEASE_RENEW_INTERVAL_SECONDS: int = 10
    DEFAULT_MAX_ATTEMPTS: int = 3

    WORKER_NAME: str = "worker-default"
    WORKER_CONCURRENCY: int = 5
    WORKER_POLL_INTERVAL_MS: int = 500
    WORKER_HEARTBEAT_INTERVAL_SECONDS: int = 10
    WORKER_SHUTDOWN_GRACE_SECONDS: int = 15
    WORKER_STALE_THRESHOLD_SECONDS: int = 30
    REAPER_INTERVAL_SECONDS: int = 15

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @model_validator(mode="after")
    def validate_worker_settings(self) -> "Settings":
        """Validate worker and lease interval relationships."""
        if self.JOB_LEASE_DURATION_SECONDS <= self.JOB_LEASE_RENEW_INTERVAL_SECONDS:
            raise ValueError("JOB_LEASE_DURATION_SECONDS must exceed JOB_LEASE_RENEW_INTERVAL_SECONDS")
        if self.WORKER_STALE_THRESHOLD_SECONDS <= self.WORKER_HEARTBEAT_INTERVAL_SECONDS:
            raise ValueError("WORKER_STALE_THRESHOLD_SECONDS must exceed WORKER_HEARTBEAT_INTERVAL_SECONDS")
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
