"""workbench-mcp settings.

Reads from the environment (matching the docker-compose service):
  - WORKBENCH_API_BASE — backend base URL (default http://127.0.0.1:8000)
  - WORKBENCH_MCP_KEY  — the bearer token (the per-user credential); REQUIRED
  - WBMCP_HOST / WBMCP_PORT — SSE bind (default 127.0.0.1:8766, parallel to
    P3's chart MCP on 8765)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    backend_url: str
    mcp_key: str
    host: str
    port: int
    timeout_s: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        backend_url=os.environ.get("WORKBENCH_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
        mcp_key=os.environ.get("WORKBENCH_MCP_KEY", ""),
        host=os.environ.get("WBMCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("WBMCP_PORT", "8766")),
        timeout_s=float(os.environ.get("WBMCP_TIMEOUT_S", "10")),
    )
