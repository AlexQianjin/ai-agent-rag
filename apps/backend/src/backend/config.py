"""Runtime settings loaded from the environment and an optional .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file() -> Path | None:
    """Find the repository .env without assuming a fixed directory depth."""
    start = Path(__file__).resolve().parent
    for directory in (start, *start.parents):
        if (directory / "docker-compose.yml").is_file() or (directory / "pnpm-workspace.yaml").is_file():
            candidate = directory / ".env"
            return candidate if candidate.is_file() else None
    cwd_env = Path.cwd() / ".env"
    return cwd_env if cwd_env.is_file() else None


ENV_FILE = _env_file()


def normalize_database_url(url: str) -> str:
    """Use the psycopg 3 driver for plain PostgreSQL URLs."""
    stripped = url.strip()
    if stripped.startswith("postgresql+psycopg://"):
        return stripped
    if stripped.startswith("postgresql://"):
        return "postgresql+psycopg://" + stripped.removeprefix("postgresql://")
    if stripped.startswith("postgres://"):
        return "postgresql+psycopg://" + stripped.removeprefix("postgres://")
    return stripped


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    auth_url: str = "http://127.0.0.1:3001"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    embedding_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"
    embedding_dimension: int = Field(default=1024, ge=1)
    embedding_timeout_seconds: float = Field(default=60, gt=0)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_retries: int = Field(default=3, ge=1, le=8)
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "documents"
    xai_api_key: str = ""
    llm_base_url: str = "https://api.x.ai/v1"
    llm_model: str = "grok-4.7"
    llm_timeout_seconds: float = Field(default=120, gt=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    hybrid_backfill: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        normalized = normalize_database_url(value)
        if not normalized:
            raise ValueError("DATABASE_URL is required")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
