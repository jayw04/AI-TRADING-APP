"""Per-user market grants. A user may have US, China A-share, or both.

``users.market_access`` stores ``us``, ``cn``, or ``us,cn``. An empty value, or any token other
than those two, grants nothing: a bad row is refused rather than treated as US. Enforcement is
on the backend. The UI hides the other market; it is not the check.

This lives next to the session dependency so the markets research package stays imported only
by its read-only router.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

US = "us"
CN = "cn"
GRANT_IDS = (US, CN)
_GRANT_SET = frozenset(GRANT_IDS)
_API_GRANT = {"us_equity": US, "cn_ashare": CN}


def parse_market_access(raw: str | None) -> frozenset[str]:
    """Grants in a stored value. Anything unexpected yields no grants."""
    if not raw:
        return frozenset()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or any(p not in _GRANT_SET for p in parts):
        return frozenset()
    return frozenset(parts)


def canonical_market_access(raw: str) -> str:
    """Validate an operator-supplied value and return the stored form."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or any(p not in _GRANT_SET for p in parts):
        raise ValueError("markets must be 'us', 'cn', or 'us,cn'")
    return ",".join(g for g in GRANT_IDS if g in parts)


def grant_for_api_id(api_id: str) -> str | None:
    return _API_GRANT.get(api_id)


def require_market(market: str):
    """FastAPI dependency: 403 MARKET_FORBIDDEN when the session lacks ``market``."""
    if market not in _GRANT_SET:
        raise ValueError(f"unknown market grant {market!r}")

    from app.auth.stub import CurrentUser, get_current_user

    async def _require(user: CurrentUser = Depends(get_current_user)) -> None:  # noqa: B008
        if market not in user.markets:
            raise HTTPException(
                status_code=403,
                detail={"code": "MARKET_FORBIDDEN", "market": market},
            )

    return _require
