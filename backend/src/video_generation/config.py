from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_HEAD = "0001_foundation"


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

    @field_validator("api_host")
    @classmethod
    def local_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("This local-only release must bind to 127.0.0.1")
        return value
