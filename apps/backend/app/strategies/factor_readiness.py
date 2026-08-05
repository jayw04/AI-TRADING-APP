"""Synchronous factor-readiness gate, evaluated AT dispatch.

WHY THIS EXISTS. On 2026-08-03 the production factor-refresh producer was stopped.
The freshness watchdog stayed green for a full day, then alerted — and alerting is
all it did. The chain was::

    readiness FAIL -> non-zero exit + SNS alert -> [MISSING] -> dispatch proceeds

Detection without a veto is not an interlock. This module is the missing step: a
factor-consuming strategy must not be *entered* when the factor data behind its
decision is not demonstrably current.

⚠ The failure this prevents is silent, not loud. ``FactorAccessor._resolve_as_of``
clamps a future ``as_of`` **down** to the store's latest price date, so a stale
store does not empty the ranking pool and make the books hold — it silently rewinds
the decision date and the books rank and trade on old factors. Sizing meanwhile
uses live bars, so the orders look plausible. Nothing raises.

This is the same shape as the 2026-07-13 incident that produced
``_is_dispatchable_now``: a condition that must prevent DISPATCH, not merely spoil
the orders that follow.

WHAT IT CHECKS, and what it deliberately does not claim. Everything here is
recomputed in-process from the same artifacts the strategies read:

- the factor store's own frontier (``sep`` max date and ``tickers.lastpricedate``);
- the sealed universe artifact written by ``factor-refresh.sh`` **only** after a
  staging verification passed and the swap completed (see #606), which is what
  makes it evidence of a *successful generation* rather than merely of a run.

**Producer liveness is NOT verifiable from inside the container** — the systemd
timer is on the host. If a readiness artifact is present it is consumed and its
producer verdict honoured; if it is absent the gate still runs on what it can
prove, and records ``producer_liveness_verified=False`` so the evidence never
overstates what was checked.

FAIL CLOSED, always. Anything missing, unreadable, stale, or inconsistent blocks
dispatch. A factor store we cannot interrogate is not permission to trade on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

#: A liquid ranked name trades every session; tolerate only a long weekend. Matches
#: ``DEFAULT_MAX_LAG_DAYS`` in ``scripts/factor_refresh.py``.
DEFAULT_MAX_LAG_DAYS = 4

#: How old the optional readiness artifact may be before it stops counting as
#: evidence *for this dispatch*. A verdict from last week says nothing about now.
DEFAULT_READINESS_MAX_AGE_HOURS = 26


@dataclass(frozen=True)
class ReadinessVerdict:
    """The outcome of one gate evaluation. ``ok`` is the only thing dispatch reads."""

    ok: bool
    reason: str
    checks: dict[str, Any] = field(default_factory=dict)

    def as_log(self) -> dict[str, Any]:
        return {"readiness_ok": self.ok, "readiness_reason": self.reason, **self.checks}


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def evaluate_factor_readiness(
    *,
    store_path: str | Path,
    sealed_path: str | Path,
    readiness_path: str | Path | None = None,
    now: datetime | None = None,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    readiness_max_age_hours: int = DEFAULT_READINESS_MAX_AGE_HOURS,
) -> ReadinessVerdict:
    """Decide whether factor-consuming dispatch may proceed. NEVER raises.

    Totality is a safety property here, not tidiness: this runs inside the dispatch
    path, and a gate that throws would take out the caller rather than refuse the
    trade. Every path returns a verdict.
    """
    try:
        return _evaluate(
            store_path=store_path,
            sealed_path=sealed_path,
            readiness_path=readiness_path,
            now=now,
            max_lag_days=max_lag_days,
            readiness_max_age_hours=readiness_max_age_hours,
        )
    except Exception as exc:  # noqa: BLE001 — a gate must refuse, never explode
        return ReadinessVerdict(
            ok=False,
            reason=f"readiness evaluation failed: {type(exc).__name__}",
            checks={"producer_liveness_verified": False},
        )


def _evaluate(
    *,
    store_path: str | Path,
    sealed_path: str | Path,
    readiness_path: str | Path | None,
    now: datetime | None,
    max_lag_days: int,
    readiness_max_age_hours: int,
) -> ReadinessVerdict:
    now = now or datetime.now(UTC)
    checks: dict[str, Any] = {"producer_liveness_verified": False}

    def block(reason: str) -> ReadinessVerdict:
        return ReadinessVerdict(ok=False, reason=reason, checks=checks)

    # --- 1. the store's own frontier, read fresh ---------------------------
    store = Path(store_path)
    if not store.exists():
        return block(f"factor store absent at {store}")
    try:
        import duckdb

        con = duckdb.connect(str(store), read_only=True)
        try:
            sep_row = con.execute("SELECT max(date) FROM sep").fetchone()
            lpd_row = con.execute("SELECT max(lastpricedate) FROM tickers").fetchone()
            sep_max = _as_date(sep_row[0]) if sep_row else None
            lpd_max = _as_date(lpd_row[0]) if lpd_row else None
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — unreadable store must block, not crash
        return block(f"factor store unreadable: {type(exc).__name__}")

    checks["sep_max"] = str(sep_max)
    checks["lastpricedate_max"] = str(lpd_max)
    if sep_max is None:
        return block("factor store has no SEP rows")

    # The effective frontier is the EARLIER of the two: a lagging lastpricedate
    # removes names from the ranking pool entirely, which is worse than ranking
    # them on old data (2026-07-06).
    frontier = min(d for d in (sep_max, lpd_max) if d is not None)
    checks["effective_frontier"] = str(frontier)

    lag_days = (now.date() - frontier).days
    checks["lag_days"] = lag_days
    if lag_days > max_lag_days:
        return block(
            f"factor data is {lag_days}d stale (frontier {frontier}, tolerance {max_lag_days}d)"
        )

    # --- 2. a sealed SUCCESSFUL generation must exist ----------------------
    sealed = Path(sealed_path)
    if not sealed.exists():
        return block(f"sealed universe artifact absent at {sealed}")
    try:
        doc = json.loads(sealed.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return block(f"sealed universe artifact unreadable: {type(exc).__name__}")

    sealed_as_of = _as_date(doc.get("as_of"))
    checks["sealed_as_of"] = str(sealed_as_of)
    checks["sealed_universe_count"] = (doc.get("counts") or {}).get("total")
    if sealed_as_of is None:
        return block("sealed universe artifact has no as_of")

    # The seal advances only after verification AND swap, so a seal older than the
    # store's own frontier means the current data was never blessed by a passing run.
    if sealed_as_of < frontier:
        return block(
            f"sealed generation {sealed_as_of} predates the store frontier {frontier}: "
            "current data was not produced by a verified run"
        )
    sealed_lag = (now.date() - sealed_as_of).days
    checks["sealed_lag_days"] = sealed_lag
    if sealed_lag > max_lag_days:
        return block(f"sealed generation is {sealed_lag}d old (tolerance {max_lag_days}d)")

    # --- 3. optional producer-liveness verdict ----------------------------
    if readiness_path is not None:
        rp = Path(readiness_path)
        if rp.exists():
            try:
                rdoc = json.loads(rp.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                return block(f"readiness artifact unreadable: {type(exc).__name__}")
            evaluated = rdoc.get("evaluated_at_utc")
            ts = None
            try:
                ts = datetime.fromisoformat(str(evaluated).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return block("readiness artifact has no parseable evaluated_at_utc")
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age_h = (now - ts).total_seconds() / 3600.0
            checks["readiness_age_hours"] = round(age_h, 2)
            if age_h > readiness_max_age_hours:
                return block(
                    f"readiness verdict is {age_h:.1f}h old (max {readiness_max_age_hours}h): "
                    "stale relative to this dispatch"
                )
            verdict = str(rdoc.get("overall_readiness", "")).upper()
            checks["overall_readiness"] = verdict
            checks["producer_liveness_verified"] = True
            if verdict != "PASS":
                return block(f"producer readiness verdict is {verdict or 'ABSENT'}")

    return ReadinessVerdict(ok=True, reason="factor data is current and verified", checks=checks)
