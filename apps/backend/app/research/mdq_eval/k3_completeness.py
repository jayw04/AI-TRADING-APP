"""K3 — data completeness. The frozen metric, implemented exactly as registered.

## The registered definition, quoted rather than paraphrased

    K3 — data completeness: missing-bar rate reduced >= 50% vs IEX on the qualification universe.
    Frozen metric definition (2026-08-15, tightened per plan v0.3 section 4.2): the comparison grid
    `U` is the UNION of `(symbol, session_date, minute_ts)` keys observed by either feed within the
    Phase-A bar window (04:00-16:00 ET) — minutes where NEITHER feed reports a bar are outside `U`.
    Per feed: `missing_rate_f = 1 - observed_keys_f / |U|`. K3 is met when
    `(missing_rate_IEX - missing_rate_SIP) / missing_rate_IEX >= 0.50`. If `missing_rate_IEX = 0`,
    K3 is NOT EVALUABLE on that grid — no division, no artificial pass. Raw row-count ratios are
    DIAGNOSTIC ONLY, and the pre-registration smoke may not be used to choose or tune this definition.

Four properties of that definition are load-bearing, and each is a way this could quietly go wrong:

1. **The grid is a union, not a product.** Building `U` as symbols x minutes would count minutes no
   feed ever reported — halts, thin premarket, a symbol that did not trade — as "missing" for both
   feeds, inflating both rates with fictional gaps.
2. **`missing_rate_IEX = 0` is NOT EVALUABLE, not a pass.** With no IEX gaps there is no reduction to
   measure. Dividing by zero, or short-circuiting to PASS because SIP is "at least as good", would
   manufacture a criterion met.
3. **Row counts are diagnostic only.** More SIP rows is not the metric; the metric is *keys present on
   the shared grid*. The 2026-08-14 smoke showed ~46% more SIP rows and is explicitly inadmissible.
4. **The window is 04:00-16:00 ET**, premarket + RTH. Bars outside it are not part of the grid.

⚠ This module computes; it does not decide admissibility. An evidentiary result requires tokens from
`mdq_eval.gate`, and without them the result is returned labelled as a diagnostic.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.research.mdq_eval.gate import validate_tokens
from app.research.mdq_eval.results import AdmissibilityToken, KOutcome, KResult

ET = ZoneInfo("America/New_York")

CRITERION = "K3"
THRESHOLD = "(missing_rate_IEX - missing_rate_SIP) / missing_rate_IEX >= 0.50"
DEFINITION_SOURCE = (
    "MDQ-001 Registration v1.0 section 4, K3 — frozen 2026-08-15 per plan v0.3 section 4.2"
)
#: Phase-A bar window: premarket + RTH. Postmarket is deliberately not collected.
WINDOW_START_ET = time(4, 0)
WINDOW_END_ET = time(16, 0)
REDUCTION_THRESHOLD = 0.50

IEX = "iex"
SIP = "sip"


class K3InputError(RuntimeError):
    """The inputs cannot support the frozen metric. Fails closed rather than approximating it."""


def _bars_path(root: Path, feed: str, session: date) -> Path:
    return Path(root) / feed / session.isoformat() / "bars" / "bars_1min.parquet"


def _minute_key(ts: Any, session: date) -> tuple[str, str] | None:
    """Normalise a bar timestamp to `(session_date, minute_ts)` in ET, or None if outside the window.

    ⚠ Truncation to the minute is explicit. Bars are one-minute bars, but a stray sub-minute component
    would otherwise split one grid cell into two and count the same minute as both observed and
    missing.
    """
    parsed: datetime
    if isinstance(ts, str):
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, datetime):
        parsed = ts
    else:  # pandas.Timestamp and friends
        coerced = getattr(ts, "to_pydatetime", lambda: None)()
        if not isinstance(coerced, datetime):
            raise K3InputError(f"unusable bar timestamp {ts!r}")
        parsed = coerced
    if parsed.tzinfo is None:
        raise K3InputError(
            f"naive bar timestamp {ts!r}; the grid is defined in ET and a naive value would be "
            f"silently reinterpreted by the local zone"
        )
    local = parsed.astimezone(ET)
    if local.date() != session:
        return None
    if not (WINDOW_START_ET <= local.time() < WINDOW_END_ET):
        return None
    return (local.date().isoformat(), local.replace(second=0, microsecond=0).time().isoformat())


def observed_keys(root: Path | str, feed: str, session: date) -> set[tuple[str, str, str]]:
    """`(symbol, session_date, minute_ts)` keys this feed actually reported inside the window."""
    path = _bars_path(Path(root), feed, session)
    if not path.is_file():
        raise K3InputError(
            f"no bar file for feed {feed} session {session} at {path}; K3 needs both feeds' bars, "
            f"and an absent file is not an empty feed"
        )
    import pandas as pd

    frame = pd.read_parquet(path)
    for column in ("symbol", "ts"):
        if column not in frame.columns:
            raise K3InputError(f"{path} has no {column!r} column; schema is not the Phase-A bar schema")

    keys: set[tuple[str, str, str]] = set()
    for symbol, ts in zip(frame["symbol"], frame["ts"], strict=True):
        minute = _minute_key(ts, session)
        if minute is None:
            continue
        keys.add((str(symbol), minute[0], minute[1]))
    return keys


def evaluate_k3(
    root: Path | str,
    sessions: Sequence[date],
    *,
    tokens: Iterable[AdmissibilityToken] | None = None,
    diagnostic: bool = False,
) -> KResult:
    """Compute K3 over one or more sessions on the union grid.

    Pass `tokens` from `mdq_eval.gate.require_admissible` for an evidentiary result. Pass
    `diagnostic=True` to get a labelled number without them — useful while developing, and never
    admissible as evidence.
    """
    if not sessions:
        raise K3InputError("K3 needs at least one session")
    sessions = sorted(set(sessions))

    if tokens is None and not diagnostic:
        raise K3InputError(
            "K3 requires admissibility tokens for an evidentiary result. Obtain them from "
            "mdq_eval.gate.require_admissible, or pass diagnostic=True to get an explicitly "
            "non-evidentiary number."
        )
    token_records = validate_tokens(root, sessions, tokens) if tokens is not None else ()

    iex_keys: set[tuple[str, str, str]] = set()
    sip_keys: set[tuple[str, str, str]] = set()
    per_session: dict[str, dict[str, int]] = {}
    for session in sessions:
        s_iex = observed_keys(root, IEX, session)
        s_sip = observed_keys(root, SIP, session)
        iex_keys |= s_iex
        sip_keys |= s_sip
        per_session[session.isoformat()] = {
            "iex_observed_keys": len(s_iex),
            "sip_observed_keys": len(s_sip),
            "union_keys": len(s_iex | s_sip),
        }

    union = iex_keys | sip_keys
    grid = len(union)
    measures: dict[str, Any] = {
        "grid_keys_U": grid,
        "iex_observed_keys": len(iex_keys),
        "sip_observed_keys": len(sip_keys),
        "per_session": per_session,
        "window_et": f"{WINDOW_START_ET.isoformat()}-{WINDOW_END_ET.isoformat()}",
        "grid_construction": "union of (symbol, session_date, minute_ts) observed by EITHER feed",
    }

    if grid == 0:
        return KResult(
            criterion=CRITERION, outcome=KOutcome.NOT_EVALUABLE, threshold=THRESHOLD,
            detail=("the union grid U is empty — neither feed reported a bar inside the Phase-A "
                    "window on these sessions, so there is no grid on which to measure completeness"),
            measures=measures, sessions=tuple(s.isoformat() for s in sessions),
            evidentiary=bool(token_records), tokens=token_records,
            definition_source=DEFINITION_SOURCE,
        )

    missing_iex = 1.0 - (len(iex_keys) / grid)
    missing_sip = 1.0 - (len(sip_keys) / grid)
    measures["missing_rate_iex"] = missing_iex
    measures["missing_rate_sip"] = missing_sip

    if missing_iex == 0.0:
        # Registered explicitly: no division, no artificial pass.
        return KResult(
            criterion=CRITERION, outcome=KOutcome.NOT_EVALUABLE, threshold=THRESHOLD,
            detail=("missing_rate_IEX = 0 on this grid, so there is no IEX gap to reduce and the "
                    "reduction ratio is undefined. The frozen definition makes this NOT EVALUABLE "
                    "— no division, no artificial pass"),
            measures=measures, sessions=tuple(s.isoformat() for s in sessions),
            evidentiary=bool(token_records), tokens=token_records,
            definition_source=DEFINITION_SOURCE,
        )

    reduction = (missing_iex - missing_sip) / missing_iex
    measures["reduction"] = reduction
    measures["reduction_threshold"] = REDUCTION_THRESHOLD
    # Diagnostic only, and labelled as such so it can never be read as the metric.
    measures["diagnostic_row_count_ratio_note"] = (
        "raw row-count ratios are DIAGNOSTIC ONLY under the frozen definition and are not the metric"
    )

    met = reduction >= REDUCTION_THRESHOLD
    return KResult(
        criterion=CRITERION,
        outcome=KOutcome.PASS if met else KOutcome.FAIL,
        threshold=THRESHOLD,
        detail=(
            f"missing_rate_IEX={missing_iex:.6f}, missing_rate_SIP={missing_sip:.6f}, "
            f"reduction={reduction:.6f} {'>=' if met else '<'} {REDUCTION_THRESHOLD} on a union grid "
            f"of {grid} (symbol, session_date, minute_ts) keys"
        ),
        measures=measures,
        sessions=tuple(s.isoformat() for s in sessions),
        evidentiary=bool(token_records),
        tokens=token_records,
        definition_source=DEFINITION_SOURCE,
    )
