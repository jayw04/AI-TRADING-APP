"""SCAN-001 premarket-data gate — increment (B): the read-only live premarket scan.

At ~09:25 ET this joins the **real** pre-market gappers (the #221 read-only reader) to the
historical store, builds the frozen Candidate Engine's feature panel (via the increment-A
adapter), runs the engine, and returns an **advisory Candidate Report**.

Boundary (SCAN-001 §0a + gate plan §4): **read-only, fail-soft, no order path, no LLM.** The
candidate set is *evidence*, not a signal — it never reaches the OrderRouter. A missing/stale/
malformed gappers file degrades to an empty report; the scan is a no-op, never raises.

Honest scope (gate plan §0b): the gappers universe (small/mid-cap Yahoo gainers) differs from
the top-200/500 liquid universe the engine was validated on, and RVOL is a premarket-vs-daily
proxy (see ``premarket_adapter``). The report therefore surfaces the ``gappers_in`` →
``store_covered`` → ``eligible_panel`` → candidate funnel so the §0b eligibility-overlap is
visible, not hidden.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.factor_data import candidate_engine as ce
from app.factor_data import premarket_adapter as pa
from app.services.premarket_gappers import read_gappers_for

# Prior daily bars to pull per symbol: enough for ATR(14) + the 20-day volume average + slack.
_LOOKBACK_BARS = pa.ATR_N + pa.RVOL_LOOKBACK + 5


def store_features_for(
    con: Any, symbols: list[str], asof: date
) -> dict[str, dict[str, Any]]:
    """Historical join: per symbol, the store features from daily bars **strictly before**
    ``asof`` (PIT). Returns ``{symbol: store_feat}`` only for symbols with enough coverage;
    uncovered/short-history symbols are omitted (the gate plan §0b drop). Thin I/O wrapper
    around the pure ``premarket_adapter.features_from_bars``."""
    syms = [s for s in {s.strip() for s in symbols} if s]
    if not syms:
        return {}
    placeholders = ",".join("?" for _ in syms)
    rows = con.execute(
        f"SELECT ticker, high, low, close, volume FROM sep "  # noqa: S608 (params bound below)
        f"WHERE ticker IN ({placeholders}) AND date < ? ORDER BY ticker, date",
        [*syms, asof],
    ).fetchall()
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for ticker, high, low, close, volume in rows:
        by_symbol.setdefault(ticker, []).append(
            {"high": high, "low": low, "close": close, "volume": volume}
        )
    out: dict[str, dict[str, Any]] = {}
    for sym, bars in by_symbol.items():
        feat = pa.features_from_bars(bars[-_LOOKBACK_BARS:])
        if feat is not None:
            out[sym] = feat
    return out


def run_premarket_scan(store: Any, *, asof: date, top_n: int = 15) -> dict[str, Any]:
    """Build the advisory Candidate Report from ``asof``'s real premarket gappers + the store.

    Point-in-time on both sides: the gappers are ``asof``'s own snapshot (``read_gappers_for``
    — ADR 0041 native-wins precedence, but never a neighbouring day's file) and the store join
    uses bars strictly before ``asof``.

    Read-only and fail-soft: if ``asof`` has no gappers file in either directory (the screener
    did not run, or the external sync was late), the report is empty — ``date``/``scanned_at``/
    ``gappers_source`` None, ``stale`` True, zero candidates — rather than falling back to the
    most recent scan. That fallback used to record the previous day's candidates under today's
    ``asof``, injecting a duplicate into the gate's forward series; an empty report instead
    back-fills to ``outcome_status: "uncovered"`` and is correctly excluded from the verdict.
    Never raises into a caller."""
    payload = read_gappers_for(asof)
    gappers = payload.get("gappers") or []
    if not isinstance(gappers, list):
        gappers = []
    symbols = [str(g.get("symbol") or "").strip() for g in gappers if g.get("symbol")]
    store_features = store_features_for(store.con, symbols, asof) if symbols else {}
    panel = pa.premarket_panel(gappers, store_features)
    # the eligible FIELD (passes the engine's $10 / $20M / no-earnings gates) is the
    # candidate-vs-baseline reference (gate plan §1); persisted with each name's ATR so the
    # back-fill (ADR 0024) can compute its realized E/CM. Candidates are the top-N of this field.
    eligible = [r for r in panel if ce.is_eligible(r)]
    candidates = ce.select_candidates(panel, top_n=top_n)
    return {
        "date": payload.get("date"),
        "scanned_at": payload.get("scanned_at"),
        # input provenance (ADR 0041): "box_native_alpaca_v1" | "external_scanner" | None.
        # Persisted with the gate record so the SCAN-001 verdict analysis can segment the
        # accrual by source instead of silently mixing universes.
        "gappers_source": payload.get("source"),
        "stale": bool(payload.get("stale", True)),
        # the §0b funnel — gappers in → store-covered → engine-eligible → selected
        "gappers_in": len(gappers),
        "store_covered": len(store_features),
        "eligible_panel": len(panel),
        "eligible_count": len(eligible),
        "candidate_count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
        # baseline field for the edge (symbol + ATR only — outcomes back-filled post-close)
        "eligible": [{"symbol": r["symbol"], "atr_pct": r["atr_pct"]} for r in eligible],
        "note": "advisory — candidate set is evidence, not a signal (SCAN-001 §0a); RVOL is a "
                "premarket-vs-daily proxy; gappers universe ≠ the validated liquid universe.",
    }
