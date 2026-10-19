"""Runtime settings loaded from the environment and an optional .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
