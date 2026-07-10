"""The six pre-registered baselines (pre-registration v1.1 §4, FR-005).

Each baseline maps (train rows → per-test-row class probabilities) using ONLY
training-window statistics plus the test row's own PIT features. The binding
gate compares the model against the BEST of these per metric — beating a
convenient baseline proves nothing (design §0.5).

Constructions are exactly the frozen §4 wording:

- #3/#4/#6 (signal-direction baselines): the predicted directional class gets
  ``h × (1 − P_neutral_uncond)`` where ``h`` is the training-window hit-rate of
  the rule among non-neutral train rows sharing the signal sign; the other
  directional class gets the remainder; NEUTRAL gets the unconditional
  training-window neutral rate.
- #5 (volatility clustering): P(MATERIAL) = the training-window material-day
  frequency within the test row's ATR20_pct quintile (quintile edges fitted on
  the training window); the UP/DOWN split of that mass follows the
  unconditional training-window direction rates.

Rows are plain dicts (the ``market_projection_training_rows`` shape):
``features_json`` + ``label``. No sklearn here — baselines are deterministic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.services.market_projection.schemas import Label, ProjectionType

Probs = dict[str, float]  # {"UP": p, "DOWN": p, "NEUTRAL": p}
Row = Mapping[str, Any]


def _rates(train: Sequence[Row]) -> Probs:
    n = max(1, len(train))
    counts = {lab.value: 0 for lab in Label}
    for r in train:
        if r.get("label") in counts:
            counts[r["label"]] += 1
    return {k: v / n for k, v in counts.items()}


def _feature(row: Row, key: str) -> float | None:
    v = (row.get("features_json") or {}).get(key)
    return float(v) if v is not None else None


# --- 1 & 2 ----------------------------------------------------------------------

def always_neutral(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    return [{"UP": 0.0, "DOWN": 0.0, "NEUTRAL": 1.0} for _ in test]


def unconditional(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    rates = _rates(train)
    return [dict(rates) for _ in test]


# --- 3 / 4 / 6: signal-direction baselines --------------------------------------

def _signal_direction(
    train: Sequence[Row], test: Sequence[Row], signal: Callable[[Row], float | None]
) -> list[Probs]:
    rates = _rates(train)
    p_neutral = rates["NEUTRAL"]
    # hit-rates of "signal sign predicts the move direction" among non-neutral train rows
    hits = {1: [0, 0], -1: [0, 0]}  # sign -> [hits, total]
    for r in train:
        s = signal(r)
        if s is None or s == 0 or r.get("label") not in ("UP", "DOWN"):
            continue
        sign = 1 if s > 0 else -1
        hits[sign][1] += 1
        predicted = "UP" if sign > 0 else "DOWN"
        hits[sign][0] += 1 if r["label"] == predicted else 0
    out: list[Probs] = []
    for r in test:
        s = signal(r)
        if s is None or s == 0:
            out.append(dict(rates))  # no signal → unconditional
            continue
        sign = 1 if s > 0 else -1
        h = (hits[sign][0] / hits[sign][1]) if hits[sign][1] else 0.5
        directional_mass = 1.0 - p_neutral
        picked, other = ("UP", "DOWN") if sign > 0 else ("DOWN", "UP")
        out.append({
            picked: h * directional_mass,
            other: (1.0 - h) * directional_mass,
            "NEUTRAL": p_neutral,
        })
    return out


def prior_day_direction(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    return _signal_direction(train, test, lambda r: _feature(r, "spy_ret_1d"))


def momentum_5d_direction(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    return _signal_direction(train, test, lambda r: _feature(r, "spy_ret_5d"))


def premarket_gap_direction(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    """PRE_OPEN_TODAY only (§4 #6): the 09:20 SPY gap sign."""
    return _signal_direction(train, test, lambda r: _feature(r, "spy_gap_pct_qf"))


# --- 5: volatility-clustering move-risk ------------------------------------------

def vol_clustering_move_risk(train: Sequence[Row], test: Sequence[Row]) -> list[Probs]:
    atr_train = [(_feature(r, "atr20_pct"), r.get("label")) for r in train]
    atr_vals = sorted(a for a, _ in atr_train if a is not None)
    rates = _rates(train)
    if len(atr_vals) < 25:
        return [dict(rates) for _ in test]
    edges = [atr_vals[int(len(atr_vals) * q / 5)] for q in range(1, 5)]  # quintile edges

    def quintile(a: float) -> int:
        return sum(a >= e for e in edges)

    material_rate_by_q: dict[int, list[int]] = {q: [0, 0] for q in range(5)}
    for a, lab in atr_train:
        if a is None or lab is None:
            continue
        q = quintile(a)
        material_rate_by_q[q][1] += 1
        material_rate_by_q[q][0] += 1 if lab in ("UP", "DOWN") else 0

    directional = rates["UP"] + rates["DOWN"]
    up_share = (rates["UP"] / directional) if directional > 0 else 0.5
    out: list[Probs] = []
    for r in test:
        a = _feature(r, "atr20_pct")
        if a is None:
            out.append(dict(rates))
            continue
        hit, tot = material_rate_by_q[quintile(a)]
        p_mat = (hit / tot) if tot else directional
        out.append({
            "UP": p_mat * up_share,
            "DOWN": p_mat * (1.0 - up_share),
            "NEUTRAL": 1.0 - p_mat,
        })
    return out


# --- registry ---------------------------------------------------------------------

def baselines_for(ptype: ProjectionType) -> dict[str, Callable[[Sequence[Row], Sequence[Row]], list[Probs]]]:
    """The pre-registered baseline set for a horizon (gap baseline is pre-open only)."""
    base: dict[str, Callable[[Sequence[Row], Sequence[Row]], list[Probs]]] = {
        "always_neutral": always_neutral,
        "unconditional": unconditional,
        "prior_day_direction": prior_day_direction,
        "momentum_5d_direction": momentum_5d_direction,
        "vol_clustering_move_risk": vol_clustering_move_risk,
    }
    if ptype == ProjectionType.PRE_OPEN_TODAY:
        base["premarket_gap_direction"] = premarket_gap_direction
    return base
