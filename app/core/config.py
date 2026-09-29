from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables (and `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "docsearch"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://docsearch:docsearch@localhost:5432/docsearch"
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_echo: bool = False

    elasticsearch_url: str = "http://localhost:9200"
    # Public name of the index. It is an alias pointing to a concrete versioned
    # index, which lets us rebuild the index with zero downtime (see `reindex`).
    elasticsearch_index: str = "documents"
    elasticsearch_timeout: float = Field(default=10.0, gt=0)

    search_limit: int = Field(default=20, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
