from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_HEAD = "0002_content_runs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VIDEO_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://video@127.0.0.1:5432/video_generation"
    )
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    pairing_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    session_days: int = Field(default=30, ge=1, le=90)
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "video-development"
    temporal_task_queue: str = "video-simulation-v1"
    simulation_step_seconds: int = Field(default=5, ge=1, le=60)
    outbox_poll_seconds: int = Field(default=1, ge=1, le=30)
    test_faults: bool = False

    @model_validator(mode="after")
    def restrict_fault_injection(self):
        if self.test_faults:
            from sqlalchemy.engine import make_url

            database = make_url(self.database_url.get_secret_value()).database
            if not database or not database.endswith("_test"):
                raise ValueError("Fault injection is restricted to a dedicated _test database")
        return self

    @field_validator("api_host")
    @classmethod
    def local_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("This local-only release must bind to 127.0.0.1")
        return value
