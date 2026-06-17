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

    # --- Trading mode ---
    # `paper` (default) or `live`. Live additionally requires WORKBENCH_LIVE_ACK=I_UNDERSTAND.
    # Resolved by app/brokers/alpaca/credentials.py; see ADR 0002 and docs/runbook/live-mode.md.
    trading_mode: str = "paper"
    live_ack: str = ""

    # When True (default) the lifespan connects to Alpaca and starts the
    # WorkbenchScheduler. Tests set WORKBENCH_ALPACA_STARTUP_ENABLED=0 so they
    # don't need real creds and don't hit the broker network.
    alpaca_startup_enabled: bool = True

    # When True (default — conservative) /auth/login requires a valid TOTP code
    # in addition to the password. Set WORKBENCH_LOGIN_TOTP_REQUIRED=false to
    # log in with password only (single-user localhost convenience). This gates
    # the LOGIN step only; step-up TOTP on consequential actions (LIVE account
    # creation, strategy activation, LLM opt-in, live auto-dispatch) is always
    # enforced and is NOT affected by this flag.
    login_totp_required: bool = True

    # --- Alpaca credentials (not WORKBENCH_-prefixed) ---
    alpaca_paper_api_key: str = Field(default="", alias="ALPACA_PAPER_API_KEY")
    alpaca_paper_api_secret: str = Field(default="", alias="ALPACA_PAPER_API_SECRET")
    alpaca_live_api_key: str = Field(default="", alias="ALPACA_LIVE_API_KEY")
    alpaca_live_api_secret: str = Field(default="", alias="ALPACA_LIVE_API_SECRET")

    # --- Market data cache (P2 Session 1) ---
    # Resolved relative to apps/backend/. The Docker bind mount maps
    # ./apps/backend/bars_cache -> /app/bars_cache so host + container agree.
    bars_cache_root: str = "bars_cache"
    bars_cache_max_gb: float = 5.0

    # --- Agent (P3) ---
    # Empty key disables the agent; Session 3's runtime refuses to start a
    # session with a clear error message rather than crashing on the first
    # API call.
    anthropic_api_key: str = Field(
        default="",
        alias="ANTHROPIC_API_KEY",
        description="Anthropic API key. Empty disables the agent.",
    )
    agent_default_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="AGENT_DEFAULT_MODEL",
    )
    agent_daily_budget_usd: float = Field(
        default=2.0,
        alias="AGENT_DAILY_BUDGET_USD",
        description="Per-user daily budget cap across all agent sessions.",
    )
    # Server-side MCP connector URL passed to Anthropic so the model can call
    # workbench tools. Default points at the chart-data MCP's Streamable HTTP
    # endpoint (`/mcp`); the MCP runs `transport="streamable-http"` per ADR 0016
    # (the legacy SSE transport could not handshake with Anthropic's connector).
    # NOTE: Anthropic dispatches this URL from its own servers, so `127.0.0.1`
    # only works when the backend is reachable from the public internet (a
    # tunnel). Set AGENT_MCP_SERVER_URL="" to disable the connector (pure-chat
    # agent) when running locally without a tunnel — otherwise Anthropic 400s
    # every turn with "Connection error while communicating with MCP server".
    agent_mcp_server_url: str = Field(
        default="http://127.0.0.1:8765/mcp",
        alias="AGENT_MCP_SERVER_URL",
        description="MCP connector URL for the agent; empty disables it.",
    )

    # --- Factor data (P9 §1) ---
    # Nasdaq Data Link key for the Sharadar SEP/TICKERS/ACTIONS datatables, used
    # only by the read-only app/factor_data/ subsystem (ADR 0018). Adopted as a
    # Settings env-alias (NOT the encrypted CredentialStore) — see ADR 0018 §5;
    # printed as a length only, never logged. Empty disables ingestion.
    nasdaq_data_link_api_key: str = Field(
        default="",
        alias="NASDAQ_DATA_LINK_API_KEY",
        description="Nasdaq Data Link / Sharadar API key. Empty disables factor-data ingestion.",
    )
    # FMP (Financial Modeling Prep) key for the read-only fundamentals layer
    # (income/balance/cash-flow/ratios/key-metrics + delisted universe), used only
    # by app/factor_data/ (ADR 0018). Same Settings env-alias posture as the
    # Sharadar key (NOT the encrypted CredentialStore); printed as a length only,
    # never logged. Empty disables FMP ingestion. The provider targets FMP's
    # /stable API (the legacy /api/v3 + /v4 endpoints were retired 2026-08-31).
    fmp_api_key: str = Field(
        default="",
        alias="FMP_API_KEY",
        description="Financial Modeling Prep API key. Empty disables FMP fundamentals ingestion.",
    )
    # Local DuckDB point-in-time factor-data store. Resolved relative to
    # apps/backend/ (matches db_url / bars_cache_root). Lives under the
    # already-gitignored data/. Never commit the store or raw vendor pulls
    # (size + licensing, ADR 0018 §6).
    factor_data_db_path: str = "data/factor_data.duckdb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
