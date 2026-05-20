from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    backend_url: str = "http://127.0.0.1:8000"
    backend_token: str = "change-me-shared-secret"
    request_timeout_s: float = 10.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
