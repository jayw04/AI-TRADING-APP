from functools import lru_cache

from pydantic import Field
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
    # Per-user bearer token the user-scoped read endpoints (GET /api/v1/account,
    # /positions, /orders, /strategies, ...) require — the backend resolves it to
    # the owning user (app/auth/stub.py::_resolve_from_bearer_token). Reuses the
    # same WORKBENCH_MCP_KEY the workbench-mcp (8766) presents; both read-only MCP
    # servers authenticate as the same user. The `backend_token` shared secret
    # above stays for the unauthenticated /internal/ping only. validation_alias
    # reads the UNPREFIXED env var (not MCP_MCP_KEY) so it matches the .env name.
    mcp_key: str = Field(default="", validation_alias="WORKBENCH_MCP_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
