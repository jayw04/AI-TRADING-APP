from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WORKBENCH_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    db_url: str = "sqlite+aiosqlite:///./data/workbench.sqlite"
    log_level: str = "INFO"
    dev_user_email: str = "jay@globalcomplyai.com"
    version: str = "0.0.1"

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    ws_heartbeat_seconds: float = 5.0

    mcp_backend_token: str = Field(default="change-me-shared-secret", alias="MCP_BACKEND_TOKEN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
