"""SCAN-001 premarket-data gate — increment (C) back-fill (ADR 0024).

After the close, attach each premarket candidate's **realized intraday outcome** (`E`/`CM`/`NM`)
to its evidence record, plus the eligible-field baseline, so the gate's forward replication can
be judged (increment D). Realized OHLC comes from **Alpaca daily bars** via the existing
``BarCache`` (ADR 0024 — the existing audited dependency, not a new feed). Read-only, advisory:
nothing here routes an order or imports an LLM (SCAN-001 §0a).

Split: ``compute_outcome`` and ``backfill_record`` are **pure** (record + realized bars → filled
record); ``fetch_realized_bars`` is the thin async Alpaca read; ``backfill_evidence`` orchestrates.
Coverage is **recorded** (``uncovered``), never silently dropped (ADR 0024 §Decision.3).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.factor_data import candidate_engine as ce
from app.services.premarket_evidence import persist_record, record_path

OutcomeBar = dict[str, float]  # {open, high, low, close}


def compute_outcome(atr_pct: float, bar: OutcomeBar) -> dict[str, float] | None:
    """Realized outcomes for one name from its daily bar — identical math to the validated
    research (``candidate_engine`` outcome fns). ``atr_pct`` is the premarket-recorded ATR.
    Returns None if the bar's open is unusable."""
    open_, high, low, close = (
        float(bar.get("open", 0.0)), float(bar.get("high", 0.0)),
        float(bar.get("low", 0.0)), float(bar.get("close", 0.0)),
    )
    if open_ <= 0:
        return None
    range_pct = ce.intraday_range_pct(high, low, open_)
    return {
        "E": round(ce.expansion_ratio(range_pct, atr_pct), 4),
        "CM": round(ce.capturable_move(open_, high, low), 4),
        "NM": round(ce.net_move(open_, close), 4),
        "range_pct": round(range_pct, 4),
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def backfill_record(
    record: dict[str, Any], bars_by_symbol: dict[str, OutcomeBar]
) -> dict[str, Any]:
    """Pure: fill ``record['outcomes']`` from realized bars — per-candidate outcomes, the eligible
    baseline means, the candidate-vs-field **edge**, and the coverage counts. Sets
    ``outcome_status`` to ``filled`` (≥1 candidate covered) or ``uncovered`` (none)."""
    out = dict(record)
    cand_outcomes: dict[str, dict[str, float]] = {}
    for c in record.get("candidates", []):
        o = compute_outcome(float(c.get("atr_pct", 0.0)), bars_by_symbol.get(c["symbol"], {}))
        if o is not None:
            cand_outcomes[c["symbol"]] = o
    base_E, base_CM = [], []
    for e in record.get("eligible", []):
        o = compute_outcome(float(e.get("atr_pct", 0.0)), bars_by_symbol.get(e["symbol"], {}))
        if o is not None:
            base_E.append(o["E"])
            base_CM.append(o["CM"])
    cand_E = [o["E"] for o in cand_outcomes.values()]
    cand_CM = [o["CM"] for o in cand_outcomes.values()]
    candidates_total = len(record.get("candidates", []))
    eligible_total = len(record.get("eligible", []))
    out["outcomes"] = {
        "candidates": cand_outcomes,
        "candidate_mean_E": round(_mean(cand_E), 4),
        "candidate_mean_CM": round(_mean(cand_CM), 4),
        "baseline_mean_E": round(_mean(base_E), 4),
        "baseline_mean_CM": round(_mean(base_CM), 4),
        "edge_E": round(_mean(cand_E) - _mean(base_E), 4),
        "edge_CM": round(_mean(cand_CM) - _mean(base_CM), 4),
        "coverage": {
            "candidates_covered": len(cand_outcomes), "candidates_total": candidates_total,
            "eligible_covered": len(base_E), "eligible_total": eligible_total,
        },
    }
    out["outcome_status"] = "filled" if cand_outcomes else "uncovered"
    return out


async def fetch_realized_bars(
    bar_cache: Any, symbols: list[str], asof: date
) -> dict[str, OutcomeBar]:
    """Thin Alpaca read (via BarCache): the ``asof`` daily bar per symbol → {open,high,low,close}.
    Best-effort and fail-soft — a symbol Alpaca doesn't cover (or that errors) is simply omitted,
    so ``backfill_record`` marks it uncovered. Never raises for a single bad symbol."""
    start = datetime(asof.year, asof.month, asof.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    out: dict[str, OutcomeBar] = {}
    for sym in {s.strip().upper() for s in symbols if s}:
        try:
            df = await bar_cache.get_bars(sym, "1Day", start, end)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        row = df.iloc[0]
        out[sym] = {"open": float(row["o"]), "high": float(row["h"]),
                    "low": float(row["l"]), "close": float(row["c"])}
    return out


async def backfill_evidence(
    bar_cache: Any, *, directory: str, asof: date
) -> dict[str, Any] | None:
    """Orchestration: load the ``asof`` record, fetch realized bars for its candidates + eligible
    field, back-fill, and persist. Returns the updated record, or None if no record exists for
    ``asof`` (a no-scan day). The ~16:30 ET job calls this (activation = deferred rebuild)."""
    import json
    import os

    path = record_path(directory, asof)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    symbols = [c["symbol"] for c in record.get("candidates", [])]
    symbols += [e["symbol"] for e in record.get("eligible", [])]
    bars = await fetch_realized_bars(bar_cache, symbols, asof)
    record = backfill_record(record, bars)
    persist_record(record, directory)
    return record
