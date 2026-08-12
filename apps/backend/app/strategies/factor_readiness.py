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
timer is on the host. It is therefore published: ``deploy/aws/factor-freshness.sh``
writes ``_factor_readiness.json`` into the shared data volume on every run, and this
gate REQUIRES it (``readiness_required=True``, the default).

⚠ That requirement is the whole point, and it was deliberately made unconditional.
When this module first shipped (#621) the artifact was optional: absent meant
"producer liveness not verified" and dispatch proceeded anyway. That reproduces the
original 2026-08-03 defect in a subtler form — a check that *silently stops
checking* rather than failing. A broken or unrun publisher must halt the books, not
quietly downgrade the gate to the two things it can still see.

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
    readiness_required: bool = True,
    now: datetime | None = None,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    readiness_max_age_hours: int = DEFAULT_READINESS_MAX_AGE_HOURS,
) -> ReadinessVerdict:
    """Decide whether factor-consuming dispatch may proceed. NEVER raises.

    Totality is a safety property here, not tidiness: this runs inside the dispatch
    path, and a gate that throws would take out the caller rather than refuse the
    trade. Every path returns a verdict.

    ``readiness_required`` DEFAULTS TO TRUE and production never passes it. It exists
    to make the requirement explicit and testable, not to make it configurable: the
    only supported caller is the dispatch path, and there the artifact is mandatory.
    ``test_engine_never_makes_the_readiness_artifact_optional`` pins that.
    """
    try:
        return _evaluate(
            store_path=store_path,
            sealed_path=sealed_path,
            readiness_path=readiness_path,
            readiness_required=readiness_required,
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
    readiness_required: bool,
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
    # `lastpricedate` is not optional context: dollar_volume_universe FILTERS on it,
    # so a store that cannot report it cannot be shown to be current. Falling back to
    # SEP alone would silently reduce the two-sided frontier to one side — exactly the
    # blind spot this gate exists to remove.
    if lpd_max is None:
        return block("factor store has no tickers.lastpricedate frontier")

    # The effective frontier is the EARLIER of the two: a lagging lastpricedate
    # removes names from the ranking pool entirely, which is worse than ranking
    # them on old data (2026-07-06).
    frontier = min(sep_max, lpd_max)
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

    # --- 3. the producer-liveness verdict, REQUIRED ------------------------
    # Written by deploy/aws/factor-freshness.sh on every watchdog run (weekdays 07:00 ET),
    # atomically, PASS or FAIL. Absent means one of: the watchdog has not run since this
    # host was provisioned, its timer is dead, or it could not write to the data volume.
    # None of those is evidence that the producer is alive, so none of them may pass.
    checks["readiness_required"] = readiness_required
    if readiness_path is None:
        if readiness_required:
            return block("readiness artifact is required but no path was configured")
        return ReadinessVerdict(
            ok=True, reason="factor data is current (producer liveness NOT verified)", checks=checks
        )

    rp = Path(readiness_path)
    checks["readiness_path"] = str(rp)
    if not rp.exists():
        if readiness_required:
            return block(
                f"producer readiness artifact absent at {rp}: producer liveness is "
                "unproven, and unproven is not permission to trade"
            )
        return ReadinessVerdict(
            ok=True, reason="factor data is current (producer liveness NOT verified)", checks=checks
        )

    try:
        rdoc = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return block(f"readiness artifact unreadable: {type(exc).__name__}")
    evaluated = rdoc.get("evaluated_at_utc")
    try:
        ts = datetime.fromisoformat(str(evaluated).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return block("readiness artifact has no parseable evaluated_at_utc")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    age_h = (now - ts).total_seconds() / 3600.0
    checks["readiness_age_hours"] = round(age_h, 2)
    # A verdict stamped in the future never ages out, so it would be permanent permission
    # to dispatch — the one way this check could fail OPEN. Host and container share a
    # clock, so an hour of tolerance is already generous; beyond that the timestamp is
    # wrong, and a wrong timestamp is not evidence.
    if age_h < -1:
        return block(
            f"readiness verdict is dated {abs(age_h):.1f}h in the FUTURE: "
            "a verdict that cannot age out is not evidence of liveness"
        )
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
