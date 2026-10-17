"""Settings read from environment variables (no secrets in the code)."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str
    celery_broker_url: str
    celery_result_backend: str
    api_key_hashes: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///disruption.db"),
            celery_broker_url=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            celery_result_backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
            api_key_hashes=frozenset(h.strip() for h in os.environ.get("API_KEY_HASHES", "").split(",") if h.strip()),
        )
