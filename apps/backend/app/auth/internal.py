"""Shared-secret auth for service-to-service calls (MCP server -> backend).

This is intentionally separate from `app.auth.stub.get_current_user`, which
identifies the human trader. Internal endpoints validate a process identity
via the `X-Workbench-Auth` header carrying `MCP_BACKEND_TOKEN`.
"""

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_workbench_auth(
    x_workbench_auth: str | None = Header(default=None, alias="X-Workbench-Auth"),
) -> None:
    expected = get_settings().mcp_backend_token
    if not x_workbench_auth or x_workbench_auth != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Workbench-Auth",
        )
