"""P11 §1 — the /api/v1/ops/state endpoint is mounted and auth-gated.

The resolver's logic is unit-tested in tests/ops/; here we only confirm the route exists
(not 404) and requires auth (not reachable unauthenticated). The authed 200-shape is
covered by the session's manual smoke on the running stack.
"""

from __future__ import annotations

import pytest


@pytest.mark.real_auth
async def test_ops_state_route_mounted_and_auth_gated(client) -> None:
    resp = await client.get("/api/v1/ops/state")
    assert resp.status_code != 404, "route not mounted"
    assert resp.status_code in (401, 403), f"expected auth gate, got {resp.status_code}"
