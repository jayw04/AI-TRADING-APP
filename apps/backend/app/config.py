from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LossControlMode(StrEnum):
    """ADR 0043 PR4 — how the persisted loss-control state machine participates in the risk path.

    An explicit tri-state (not booleans), independent of the two baseline flags.

    * ``OFF``     — the state machine is not consulted; behaviour is identical to pre-PR4 code.
    * ``SHADOW``  — the state machine is evaluated and its transitions persisted, comparison evidence
                    is emitted, but the LEGACY decision stays authoritative (never changes accept/refuse).
    * ``ENFORCE`` — the state-machine outcome is authoritative at its gate, combined with the rest of
                    the engine by the normative precedence ladder (it never *weakens* a stricter result).
    """

    OFF = "OFF"
    SHADOW = "SHADOW"
    ENFORCE = "ENFORCE"


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

    # Single-active-scheduler invariant (ADR 0032). When True (default) this host
    # ARMS its scheduler: it starts the recurring jobs (syncs, strategy rebalances,
    # backups) and resumes strategies on boot — i.e. it dispatches orders. Set
    # WORKBENCH_SCHEDULER_ENABLED=false to run a DISARMED standby (e.g. the laptop
    # after cutover to AWS): the process stays up and serves the API/UI, but starts
    # no scheduler and registers no strategies, so it dispatches no automated orders.
    # The default preserves today's single-host behavior — the laptop is unchanged
    # unless this is explicitly set false. Never have two ARMED hosts pointed at the
    # same Alpaca paper accounts.
    scheduler_enabled: bool = True

    # When True (default — conservative) /auth/login requires a valid TOTP code
    # in addition to the password. Set WORKBENCH_LOGIN_TOTP_REQUIRED=false to
    # log in with password only (single-user localhost convenience). This gates
    # the LOGIN step only; step-up TOTP on consequential actions (LIVE account
    # creation, strategy activation, LLM opt-in, live auto-dispatch) is always
    # enforced and is NOT affected by this flag.
    login_totp_required: bool = True

    # ADR 0043 §D3 — SHADOW session-baseline capture in the account-sync path. When True, each
    # account-sync poll captures/reuses the immutable per-session baseline (risk_session_baselines)
    # and emits shadow evidence — but changes NO risk decision (no daily-loss basis, no state
    # machine, no breaker). Default FALSE: this adds a broker list_orders() poll while no baseline
    # exists, so it must be enabled deliberately in the intended deployment config rather than
    # activating everywhere on merge. Enforcement (baseline as the daily-loss basis) is a later,
    # separately-gated increment.
    session_baseline_shadow_enabled: bool = False

    # ADR 0043 §D3 — ENFORCEMENT: when True the risk engine's daily-loss gates PREFER the persisted
    # session baseline over the drifting last_equity basis (with a compatibility fallback chain).
    # SEPARATE from the shadow flag on purpose: shadow controls baseline *production + evidence*;
    # this controls whether enforcement *uses* it. Enforcement must never implicitly enable capture.
    # Default FALSE. Roll out only after ≥1 full regular session of shadow evidence is reviewed
    # (capture on + enforcement off = observation; capture on + enforcement on = authoritative).
    # Flag off is byte-for-byte the legacy daily-loss behaviour.
    session_baseline_enforcement_enabled: bool = False

    # ADR 0043 PR4 — how the persisted loss-control STATE MACHINE participates in the risk path
    # (WORKBENCH_LOSS_CONTROL_MODE = OFF | SHADOW | ENFORCE). Default OFF (pre-PR4 behaviour).
    # INDEPENDENT of the two baseline flags above: none of the three implicitly enables another. A
    # valid observation config is capture=on, enforcement=off, mode=SHADOW; the authoritative config
    # is capture=on, enforcement=on, mode=ENFORCE.
    loss_control_mode: LossControlMode = LossControlMode.OFF

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

    # --- Pre-market gappers (read-only ingest of the external scanner) ---
    # Directory holding ``premarket_gappers_<date>.json`` files produced by the
    # sibling ``claude-trading-view`` scanner. Mounted read-only into the
    # container (see docker-compose). Read-only/advisory — never an order signal.
    premarket_gappers_dir: str = "/app/premarket_gappers"

    # --- SCAN-001 Production Validation Gate evidence (ADR 0024) ---
    # Persistent directory for the forward-evidence records the ~09:25 ET premarket
    # scan writes and the ~16:30 ET back-fill updates (one JSON per trading day).
    # Under the gitignored data/ root so the scan -> back-fill -> verdict chain spans
    # the day across restarts. Read-only/advisory — never an order signal.
    premarket_gate_evidence_dir: str = "data/premarket_gate_evidence"

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
    # Local DuckDB store for the Research Engine subsystem (P10 Phase 2): the
    # experiment/strategy/dataset/feature/artifact registries + transition log.
    # Separate from the factor-data store — the Research Engine is its own
    # subsystem (read-only-derived; never committed). Backend-relative.
    research_db_path: str = "data/research.duckdb"

    # --- SEC EDGAR alternative data (corporate events; ADR 0027, DCAP-005) ---
    # EDGAR is free/public (no key). SEC fair-access requires a DESCRIPTIVE User-Agent
    # (org + contact email) and <=10 req/s. An EMPTY user-agent DISABLES ingestion —
    # never an un-throttled anonymous fetch. Read-only, off the order path.
    sec_edgar_user_agent: str = Field(
        default="",
        alias="SEC_EDGAR_USER_AGENT",
        description="SEC fair-access User-Agent ('Org Name contact@example.com'). Empty disables EDGAR.",
    )
    sec_edgar_rate_limit_per_sec: float = 8.0  # conservative under SEC's 10/s ceiling
    # Local DuckDB point-in-time corporate-event store (the reusable Event Store,
    # event-type-agnostic). Backend-relative, under the gitignored data/. Never committed.
    event_store_path: str = "data/event_store.duckdb"

    # --- Quiver Quant alternative data (Government Contracts first; ADR 0037, DCAP-007) ---
    # A single Quiver API token (sent as 'Authorization: Token <key>'). Settings env-alias,
    # NOT the encrypted CredentialStore — same read-only posture as the Sharadar/FMP keys
    # (ADR 0018 §5); printed as a length only, never logged. Empty DISABLES Quiver ingestion,
    # never an unauthenticated fetch. Off the order path.
    quiver_api_key: str = Field(
        default="",
        alias="QUIVER_API_KEY",
        description="Quiver Quant API token (Hobbyist). Empty disables Quiver alt-data ingestion.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
