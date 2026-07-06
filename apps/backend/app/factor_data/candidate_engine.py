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

import math
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


# ---- v0.2 outcome metrics (de-tautologize + tradeability; SCAN-001 v0.2 §1) ----
# All are post-open OUTCOMES scored after selection — never fed back into the filters.


def expansion_ratio(range_pct: float, atr_pct: float) -> float:
    """H1′ — realized intraday range as a multiple of the name's OWN ATR. Normalizing
    by ATR removes the v0.1 tautology (we selected partly on ATR): >1 means the name
    expanded *beyond* the volatility we screened it for; ≈1 means it merely realized it."""
    return _safe_div(range_pct, atr_pct)


def trend_efficiency(open_: float, high: float, low: float, close: float) -> float:
    """H2 tradeability — fraction of the day's range that was NET directional travel.
    0 = pure round-trip chop (open==close), 1 = clean one-way trend (close at an extreme)."""
    return _safe_div(abs(close - open_), high - low)


def capturable_move(open_: float, high: float, low: float) -> float:
    """H2 tradeability — the best single-direction excursion from the open, in % (an MFE
    proxy): the move an intraday strategy could have targeted regardless of direction."""
    return _safe_div(max(high - open_, open_ - low), open_) * 100.0


def net_move(open_: float, close: float) -> float:
    """H2 tradeability — the one-way move that actually HELD to the close, in % (what an
    open-to-close hold would have captured). Distinct from capturable_move's best-case."""
    return _safe_div(abs(close - open_), open_) * 100.0


# ---- v0.3 regime classifiers (Operating-Envelope study; SCAN-001 v0.3 §1) ----
# Pure, PIT helpers that label a trading day's market + volatility regime from a
# broad-market proxy series. Frozen rules — NOT tuned to any result. The labels are a
# bucketing lens on the (already-validated) edge; they never touch selection.

MARKET_SMA_N = 200      # trend filter window (frozen)
MARKET_RET_N = 60       # trailing-return window for trend confirmation (frozen)
VOL_WINDOW = 21         # realized-vol lookback ≈ 1 month (frozen)
VOL_MEDIAN_WINDOW = 252  # trailing window for the high/low-vol median split (frozen)
_TRADING_DAYS_YEAR = 252


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def sma(values: list[float], n: int) -> float | None:
    """Simple moving average of the last ``n`` values; None if fewer than ``n``."""
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def trailing_return(values: list[float], n: int) -> float | None:
    """Return over the last ``n`` steps: values[-1] / values[-1-n] − 1; None if short."""
    if len(values) < n + 1 or values[-1 - n] == 0:
        return None
    return values[-1] / values[-1 - n] - 1.0


def realized_vol(returns: list[float], n: int = VOL_WINDOW) -> float | None:
    """Annualized realized volatility over the last ``n`` daily returns; None if short."""
    if len(returns) < n:
        return None
    window = returns[-n:]
    mean = sum(window) / n
    var = sum((r - mean) ** 2 for r in window) / (n - 1) if n > 1 else 0.0
    return math.sqrt(var) * math.sqrt(_TRADING_DAYS_YEAR)


def market_regime(levels: list[float]) -> str | None:
    """Frozen 3-state market regime from a proxy price-index series ``levels`` (oldest →
    newest, ending at the classification point). Bull/Bear require trend (vs SMA200) AND
    direction (60-day return sign) to agree; everything else is Sideways. None if history
    is insufficient (< SMA200 window)."""
    sma200 = sma(levels, MARKET_SMA_N)
    ret60 = trailing_return(levels, MARKET_RET_N)
    if sma200 is None or ret60 is None:
        return None
    level = levels[-1]
    if level > sma200 and ret60 > 0:
        return "bull"
    if level < sma200 and ret60 < 0:
        return "bear"
    return "sideways"


def vol_regime(vol_today: float | None, vol_history: list[float]) -> str | None:
    """Frozen 2-state volatility regime: today's realized vol vs the median of the trailing
    realized-vol series (a self-referential, era-adaptive split). None if either input is
    missing/empty."""
    if vol_today is None or not vol_history:
        return None
    return "high" if vol_today > _median(vol_history) else "low"


# ---- v0.4 Confidence Model (calibration + composability; SCAN-001 v0.4 §1) ----
# Pure helpers that turn the v0.3 Operating-Envelope heatmap into a per-candidate, per-day
# confidence number — and the frozen composite the model ships. No selection change: the
# candidate SET is unchanged (v0.2 H3 engine); these only attach a weighting/ranking lens.

# A regime needs at least this many PRIOR days before it emits a non-neutral Discovery
# Confidence (the v0.4 §1b warm-up floor; mirrors the v0.3 60-day minimum cell sample).
MIN_CONFIDENCE_DAYS = 60
NEUTRAL_CONFIDENCE = 1.0  # under warm-up: no down-weight (multiplying by 1.0 is a no-op)


def discovery_confidence(point: float, ci_low: float, p_value: float, ref: float) -> float:
    """Map a regime's edge statistics to a bounded **[0, 1]** Discovery Confidence using the
    **frozen v0.3 blend**, so v0.4's PIT numbers are directly comparable to the v0.3 heatmap.

    Branch logic is identical to the v0.3 ``_assign_envelope`` confidence:
      * ``point ≤ 0``                → 0.0 (a no-go regime contributes no confidence)
      * positive but CI not separated → ``0.4·(1 − p)`` (weak, separation-discounted)
      * positive and CI-separated     → ``0.5·(1 − p) + 0.5·magnitude``, magnitude = point/ref

    ``point`` is the regime's mean expansion edge, ``ci_low`` its lower 95% bound, ``p_value``
    the one-sided "edge > 0" p, and ``ref`` the normalizing reference (the largest separated
    regime's point). v0.4 supplies these point-in-time from PRIOR days only (§1b)."""
    if point <= 0:
        return 0.0
    sep = max(0.0, 1.0 - p_value)
    if ci_low <= 0:
        return round(0.4 * sep, 3)
    mag = min(1.0, max(0.0, point / ref)) if ref > 0 else 0.0
    return round(0.5 * sep + 0.5 * mag, 3)


def composite_confidence(opportunity_confidence: float, discovery_confidence_value: float) -> float:
    """The frozen v0.4 Confidence Model (§1c): the **product** of the two bounded [0, 1] terms —
    the per-candidate ``opportunity_confidence`` (Lever A, within-day) and the per-day
    ``discovery_confidence`` (Lever B, regime throttle). Product of two [0,1] terms → [0, 1].

    Inputs are clamped to [0, 1] defensively so a malformed feed can never push the composite
    out of range. This is a *weighting* key; it does not change which names are selected."""
    a = min(1.0, max(0.0, opportunity_confidence))
    b = min(1.0, max(0.0, discovery_confidence_value))
    return round(a * b, 4)


# ---- v0.5 ATR-decoupled confidence (de-tautologized; SCAN-001 v0.5 §1a) -----


def confidence_gr(feat: dict[str, Any], filters: dict[str, float] = FILTERS) -> float:
    """The v0.5 **ATR-decoupled** confidence: the bounded [0, 1] opportunity confidence over the
    cleared **Gap and RVOL** signals ONLY — ATR is excluded.

    Rationale (SCAN-001 v0.5 §0): the realized outcomes are ATR-coupled (high-ATR names move more,
    near-mechanically — the v0.1 tautology), and the full ``confidence`` blends ATR in, which is why
    v0.4 found it *inverse* to the ATR-normalized expansion `E`. Stripping ATR out isolates the
    **non-mechanical** part of the signal (Gap + RVOL strength) so a calibration test can ask whether
    that part predicts a de-tautologized outcome. ATR still drives *selection* (the engine is frozen);
    this changes only the *confidence number under test*."""
    fired = opportunity_signals(feat, filters, active_signals=("Gap", "RVOL"))
    return confidence(feat, fired, filters)


# ---- selection -------------------------------------------------------------


def is_eligible(feat: dict[str, Any], filters: dict[str, float] = FILTERS) -> bool:
    """Liquidity + safety admission: price floor, dollar-volume floor, no earnings today."""
    if feat.get("earnings_today"):
        return False
    return (
        feat.get("price", 0.0) > filters["min_price"]
        and feat.get("dollar_vol", 0.0) > filters["min_dollar_vol"]
    )


def opportunity_signals(
    feat: dict[str, Any],
    filters: dict[str, float] = FILTERS,
    active_signals: tuple[str, ...] = _OPPORTUNITY_SIGNALS,
) -> list[str]:
    """Which opportunity drivers cleared their threshold — the candidate's ``reason``.

    ``active_signals`` restricts which drivers can fire — the H3 attribution lever: pass
    ``("ATR",)`` for the ATR-only screen, ``("Gap", "ATR")`` for ATR+Gap, etc. A driver
    not in ``active_signals`` is ignored even if it would have cleared."""
    fired: list[str] = []
    if "Gap" in active_signals and feat.get("gap_pct", 0.0) > filters["min_gap_pct"]:
        fired.append("Gap")
    if "RVOL" in active_signals and feat.get("rvol", 0.0) > filters["min_rvol"]:
        fired.append("RVOL")
    if "ATR" in active_signals and feat.get("atr_pct", 0.0) > filters["min_atr_pct"]:
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
    active_signals: tuple[str, ...] = _OPPORTUNITY_SIGNALS,
) -> list[Candidate]:
    """Run the engine over a day's per-symbol feature panel → ranked top-N candidates.

    Each panel row needs: symbol, gap_pct, rvol, atr_pct, price, dollar_vol, and
    optionally earnings_today. Selection = eligible AND ≥1 opportunity signal (or all
    active when ``require_all_signals`` — the robustness tightening). ``active_signals``
    restricts the drivers (the H3 attribution lever — see ``opportunity_signals``)."""
    scored: list[Candidate] = []
    for feat in panel:
        if not is_eligible(feat, filters):
            continue
        fired = opportunity_signals(feat, filters, active_signals)
        if not fired or (require_all_signals and len(fired) < len(active_signals)):
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
