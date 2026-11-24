"""Application settings loaded from environment variables and optional .env."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    app_name: str = Field(default="AgentOS", min_length=1)
    environment: str = Field(default="development", min_length=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    task_database_path: Path = Path("data/tasks.sqlite3")
    checkpoint_database_path: Path = Path("data/checkpoints.sqlite3")

    @field_validator("task_database_path", "checkpoint_database_path")
    @classmethod
    def resolve_database_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def separate_databases(self) -> Self:
        if self.task_database_path == self.checkpoint_database_path:
            raise ValueError("Task and checkpoint databases must use separate files")
        return self
