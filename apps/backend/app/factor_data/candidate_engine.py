"""SCAN-001 — the Candidate Engine (Market Opportunity Discovery, v1 intraday profile).

PURE candidate-selection logic: given a per-symbol pre-open feature panel, apply the
frozen filters, rank, and build an **explainable Candidate Report** — each candidate
carries its filter scores, the reason it was selected, and a bounded confidence
(SCAN-001 §3a). No I/O, no store, no order routing: this is read-only research, and
the candidate set is *evidence*, not a trade signal.

Boundary (SCAN-001 §0a): this engine **selects** names. It does NOT decide entries,
exits, sizing, or risk — those are the downstream strategy programs' job.

Filter model:
  * Eligibility gates (must ALL pass): price floor, dollar-volume floor, no earnings
    today. Liquidity + safety — not "reasons to select", just admission.
  * Opportunity signals (≥1 must clear): Gap %, Relative Volume, ATR %. The drivers
    that make a name worth an intraday strategy's attention; the cleared ones are the
    candidate's ``reason``. (A labeled robustness tightening requires all three — H3
    attribution decides which actually earn their place.)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Frozen pre-registered thresholds (SCAN-001 §2) — conservative defaults, set before
# results, NOT tuned to a metric.
FILTERS: dict[str, float] = {
    "min_gap_pct": 3.0,             # |open − prev_close| / prev_close × 100 >
    "min_rvol": 2.0,                # volume / N-day avg volume >
    "min_atr_pct": 2.0,             # ATR(14) / price × 100 >
    "min_price": 10.0,              # price > $10
    "min_dollar_vol": 20_000_000.0,  # prev-day $-volume >
}

# The opportunity-driver signals (the "reason"); eligibility gates are separate.
_OPPORTUNITY_SIGNALS = ("Gap", "RVOL", "ATR")


@dataclass(frozen=True)
class Candidate:
    """One explainable row of the Candidate Report (SCAN-001 §3a)."""

    symbol: str
    rank: int
    gap_pct: float
    rvol: float
    atr_pct: float
    price: float
    dollar_vol: float
    reason: str          # which opportunity signals cleared, e.g. "Gap + RVOL + ATR"
    confidence: float    # bounded [0, 1], blended strength over the cleared signals
    score: float         # ranking composite

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---- pure feature functions ------------------------------------------------


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def gap_pct(open_: float, prev_close: float) -> float:
    """Open vs prior close, in %. (PIT note: a live 09:25 scan uses the premarket
    price; this prototype uses the official open as a ~5-min approximation.)"""
    return _safe_div(abs(open_ - prev_close), prev_close) * 100.0


def rvol(volume: float, avg_volume: float) -> float:
    """Today's volume relative to the trailing average (a daily-RVOL proxy; v1 uses
    true premarket volume)."""
    return _safe_div(volume, avg_volume)


def atr_pct(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> float:
    """ATR(n) as % of the last close. ``closes`` is prior closes aligned to highs/lows;
    needs n+1 bars. Wilder's true range, simple mean over the last n."""
    if len(highs) < n + 1 or len(lows) < n + 1 or len(closes) < n + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[-n:]) / n
    return _safe_div(atr, closes[-1]) * 100.0


def intraday_range_pct(high: float, low: float, open_: float) -> float:
    """The opportunity metric: realized intraday range (HOD−LOD) as % of the open —
    the movement an intraday strategy monetizes. This is the *outcome* (post-open),
    never a selection feature, so it cannot leak into the filters."""
    return _safe_div(high - low, open_) * 100.0


# ---- selection -------------------------------------------------------------


def is_eligible(feat: dict[str, Any], filters: dict[str, float] = FILTERS) -> bool:
    """Liquidity + safety admission: price floor, dollar-volume floor, no earnings today."""
    if feat.get("earnings_today"):
        return False
    return (
        feat.get("price", 0.0) > filters["min_price"]
        and feat.get("dollar_vol", 0.0) > filters["min_dollar_vol"]
    )


def opportunity_signals(feat: dict[str, Any], filters: dict[str, float] = FILTERS) -> list[str]:
    """Which opportunity drivers cleared their threshold — the candidate's ``reason``."""
    fired: list[str] = []
    if feat.get("gap_pct", 0.0) > filters["min_gap_pct"]:
        fired.append("Gap")
    if feat.get("rvol", 0.0) > filters["min_rvol"]:
        fired.append("RVOL")
    if feat.get("atr_pct", 0.0) > filters["min_atr_pct"]:
        fired.append("ATR")
    return fired


def confidence(feat: dict[str, Any], fired: list[str], filters: dict[str, float] = FILTERS) -> float:
    """Bounded [0, 1] transparent score — the mean, over the CLEARED signals, of how far
    each clears its threshold (capped at 2× = 1.0). NOT an opaque model output."""
    if not fired:
        return 0.0
    ratios: list[float] = []
    if "Gap" in fired:
        ratios.append(feat["gap_pct"] / filters["min_gap_pct"])
    if "RVOL" in fired:
        ratios.append(feat["rvol"] / filters["min_rvol"])
    if "ATR" in fired:
        ratios.append(feat["atr_pct"] / filters["min_atr_pct"])
    # 1× threshold → 0.0; ≥2× → 1.0 (linear in between), averaged over fired signals.
    norm = [min(1.0, max(0.0, (r - 1.0))) for r in ratios]
    return round(sum(norm) / len(norm), 4)


def _score(feat: dict[str, Any], fired: list[str], filters: dict[str, float]) -> float:
    """Ranking composite: signal count + the confidence magnitude (count dominates so
    a 3-signal name outranks a 1-signal name; confidence breaks ties)."""
    return len(fired) + confidence(feat, fired, filters)


def select_candidates(
    panel: list[dict[str, Any]],
    *,
    top_n: int = 15,
    filters: dict[str, float] = FILTERS,
    require_all_signals: bool = False,
) -> list[Candidate]:
    """Run the engine over a day's per-symbol feature panel → ranked top-N candidates.

    Each panel row needs: symbol, gap_pct, rvol, atr_pct, price, dollar_vol, and
    optionally earnings_today. Selection = eligible AND ≥1 opportunity signal (or all
    three when ``require_all_signals`` — the robustness tightening)."""
    scored: list[Candidate] = []
    for feat in panel:
        if not is_eligible(feat, filters):
            continue
        fired = opportunity_signals(feat, filters)
        if not fired or (require_all_signals and len(fired) < len(_OPPORTUNITY_SIGNALS)):
            continue
        scored.append(
            Candidate(
                symbol=feat["symbol"],
                rank=0,  # assigned after sort
                gap_pct=round(feat["gap_pct"], 4),
                rvol=round(feat["rvol"], 4),
                atr_pct=round(feat["atr_pct"], 4),
                price=round(feat["price"], 4),
                dollar_vol=round(feat["dollar_vol"], 2),
                reason=" + ".join(fired),
                confidence=confidence(feat, fired, filters),
                score=round(_score(feat, fired, filters), 4),
            )
        )
    # Rank: score desc, then dollar-vol desc as a stable liquidity tiebreak.
    scored.sort(key=lambda c: (-c.score, -c.dollar_vol, c.symbol))
    return [
        Candidate(**{**c.to_dict(), "rank": i + 1}) for i, c in enumerate(scored[:top_n])
    ]
