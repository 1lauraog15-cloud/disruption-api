"""Settings read from environment variables (no secrets in the code)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    celery_broker_url: str
    celery_result_backend: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///disruption.db"),
            celery_broker_url=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            celery_result_backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        )
