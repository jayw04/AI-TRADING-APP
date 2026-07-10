"""Walk-forward validation harness for MKT-PROJ-001 (FR-007; pre-reg §3/§4/§7, design §13/§14).

Frozen design, implemented literally:

- **Folds**: anchored expanding window; first train window ≥3 years; each test
  fold 6 months; roll 6 months; all OOS folds pooled. Random splits are not
  implemented at all — they are not a fallback, they are forbidden.
- **Metrics** (magnitude and direction always separate): Brier for
  MATERIAL-vs-NEUTRAL is the SINGLE primary Move-Risk metric; log-loss
  (probabilities clipped to [1e-6, 1−1e-6]) / ECE / reliability are secondary.
  Directional metrics only exist when the §14 floor is met (≥100 non-neutral
  OOS calls with ≥50 UP and ≥50 DOWN) — otherwise the directional verdict is
  the literal ``insufficient_sample`` and no CI is computed.
- **CIs**: stationary block bootstrap over the OOS day sequence (block 10
  trading days, 2,000 resamples, seed 42, 95% two-sided) on the metric delta
  vs the best baseline.

numpy-only (no sklearn) so the §2 baseline-only evidence run has no model
dependencies. The §3 model plugs into the same ``predictors`` interface.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

import numpy as np

Probs = dict[str, float]
Row = Mapping[str, Any]
Predictor = Callable[[Sequence[Row], Sequence[Row]], list[Probs]]

CLIP = 1e-6
FIRST_TRAIN_YEARS = 3
TEST_MONTHS = 6
BLOCK_LEN = 10
N_BOOT = 2000
SEED = 42
ECE_BINS = 10
# "Elevated move-risk call" definition used by the frozen 10–60% coverage gate.
# P(MATERIAL) >= 0.5 — i.e. a material move is the model's modal view. Flagged
# to the owner with the §2 evidence (a display-threshold choice, frozen before
# any evidence run is interpreted).
ELEVATED_CALL_MIN_P = 0.5


# --- folds ---------------------------------------------------------------------

def walk_forward_folds(dates: Sequence[date]) -> list[tuple[list[int], list[int]]]:
    """Anchored expanding folds over a sorted unique date sequence."""
    if not dates:
        return []
    start = dates[0]
    folds: list[tuple[list[int], list[int]]] = []
    test_start = date(start.year + FIRST_TRAIN_YEARS, start.month, 1)
    while test_start <= dates[-1]:
        test_end = _add_months(test_start, TEST_MONTHS)
        train_idx = [i for i, d in enumerate(dates) if d < test_start]
        test_idx = [i for i, d in enumerate(dates) if test_start <= d < test_end]
        if train_idx and test_idx:
            folds.append((train_idx, test_idx))
        test_start = test_end
    return folds


def _add_months(d: date, months: int) -> date:
    y, m = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


# --- probability metrics ---------------------------------------------------------

def _p_material(p: Probs) -> float:
    return float(p.get("UP", 0.0) + p.get("DOWN", 0.0))


def _y_material(label: str) -> float:
    return 1.0 if label in ("UP", "DOWN") else 0.0


def brier_material(probs: Sequence[Probs], labels: Sequence[str]) -> float:
    return float(np.mean([( _p_material(p) - _y_material(y)) ** 2 for p, y in zip(probs, labels, strict=True)]))


def log_loss_material(probs: Sequence[Probs], labels: Sequence[str]) -> float:
    p = np.clip([_p_material(q) for q in probs], CLIP, 1 - CLIP)
    y = np.array([_y_material(label) for label in labels])
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece_material(probs: Sequence[Probs], labels: Sequence[str], bins: int = ECE_BINS) -> float:
    p = np.array([_p_material(q) for q in probs])
    y = np.array([_y_material(label) for label in labels])
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if mask.sum():
            ece += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(ece)


def auc_material(probs: Sequence[Probs], labels: Sequence[str]) -> float | None:
    """Rank-based (Mann-Whitney) AUC for the MATERIAL classification.

    Uses MIDRANKS for ties — with tied scores (e.g. a constant-probability
    baseline) ordinal ranks silently encode array order and fabricate
    discrimination; midranks give the correct 0.5."""
    p = np.array([_p_material(q) for q in probs])
    y = np.array([_y_material(label) for label in labels])
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    combined = np.concatenate([pos, neg])
    order = combined.argsort(kind="mergesort")
    ranks = np.empty(len(combined))
    ranks[order] = np.arange(1, len(combined) + 1)
    for val in np.unique(combined):
        mask = combined == val
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def elevated_coverage(probs: Sequence[Probs]) -> float:
    return float(np.mean([_p_material(p) >= ELEVATED_CALL_MIN_P for p in probs]))


def brier_three_class(probs: Sequence[Probs], labels: Sequence[str]) -> float:
    total = 0.0
    for p, y in zip(probs, labels, strict=True):
        for cls in ("UP", "DOWN", "NEUTRAL"):
            total += (p.get(cls, 0.0) - (1.0 if y == cls else 0.0)) ** 2
    return float(total / max(1, len(labels)))


def log_loss_three_class(probs: Sequence[Probs], labels: Sequence[str]) -> float:
    vals = [np.clip(p.get(y, 0.0), CLIP, 1 - CLIP) for p, y in zip(probs, labels, strict=True)]
    return float(-np.mean(np.log(vals)))


# --- directional metrics (§13.2 + the §14 floor) ---------------------------------

def _called_class(p: Probs) -> str:
    return max(("UP", "DOWN", "NEUTRAL"), key=lambda c: p.get(c, 0.0))


def directional_metrics(
    probs: Sequence[Probs], labels: Sequence[str], realized: Sequence[float | None]
) -> dict[str, Any]:
    calls = [(_called_class(p), y, r) for p, y, r in zip(probs, labels, realized, strict=True)]
    non_neutral = [(c, y, r) for c, y, r in calls if c in ("UP", "DOWN")]
    up_calls = [(c, y, r) for c, y, r in non_neutral if c == "UP"]
    down_calls = [(c, y, r) for c, y, r in non_neutral if c == "DOWN"]

    floor_met = len(non_neutral) >= 100 and len(up_calls) >= 50 and len(down_calls) >= 50
    out: dict[str, Any] = {
        "non_neutral_calls": len(non_neutral),
        "up_calls": len(up_calls),
        "down_calls": len(down_calls),
        "sample_floor_met": floor_met,
    }
    # Design §7.2 diagnostic (NOT the gate): direction skill GIVEN a material day —
    # among days that realized material, did P(UP) vs P(DOWN) point the right way?
    # Reported regardless of the call floor because it conditions on realized
    # outcomes, not on the model choosing to call.
    material_days = [
        (p, y) for p, y in zip(probs, labels, strict=True) if y in ("UP", "DOWN")
    ]
    if material_days:
        correct = sum(
            1 for p, y in material_days
            if (p.get("UP", 0.0) >= p.get("DOWN", 0.0)) == (y == "UP")
        )
        out["conditional_direction_accuracy_on_material"] = correct / len(material_days)
        out["material_days"] = len(material_days)
    if not floor_met:
        out["verdict"] = "insufficient_sample"  # §14: no CI may be computed or displayed
        return out

    def precision(calls_: list, cls: str) -> float | None:
        return (sum(1 for _, y, _ in calls_ if y == cls) / len(calls_)) if calls_ else None

    out["up_precision"] = precision(up_calls, "UP")
    out["down_precision"] = precision(down_calls, "DOWN")
    out["balanced_accuracy"] = float(np.mean([v for v in (out["up_precision"], out["down_precision"]) if v is not None]))
    out["false_positive_rate"] = float(
        sum(1 for c, y, _ in non_neutral if y == "NEUTRAL") / len(non_neutral)
    )
    out["directional_precision"] = float(
        sum(1 for c, y, _ in non_neutral if y == c) / len(non_neutral)
    )
    out["mean_realized_after_up"] = float(np.mean([r for _, _, r in up_calls if r is not None]))
    out["mean_realized_after_down"] = float(np.mean([r for _, _, r in down_calls if r is not None]))
    out["confusion"] = {
        f"{c}->{y}": sum(1 for c2, y2, _ in calls if c2 == c and y2 == y)
        for c in ("UP", "DOWN", "NEUTRAL") for y in ("UP", "DOWN", "NEUTRAL")
    }
    return out


# --- block bootstrap --------------------------------------------------------------

def block_bootstrap_delta_ci(
    metric: Callable[[Sequence[Probs], Sequence[str]], float],
    probs_a: Sequence[Probs],
    probs_b: Sequence[Probs],
    labels: Sequence[str],
    *,
    block_len: int = BLOCK_LEN,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> dict[str, float]:
    """95% CI for metric(A) − metric(B) via stationary block bootstrap over the
    pooled OOS day sequence. Negative delta = A better, for loss-like metrics."""
    n = len(labels)
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_boot)
    idx_all = np.arange(n)
    for b in range(n_boot):
        idx: list[int] = []
        while len(idx) < n:
            start = int(rng.integers(0, n))
            length = int(rng.geometric(1.0 / block_len))
            idx.extend(idx_all[(start + np.arange(length)) % n])
        idx = idx[:n]
        la = [labels[i] for i in idx]
        deltas[b] = metric([probs_a[i] for i in idx], la) - metric([probs_b[i] for i in idx], la)
    point = metric(probs_a, labels) - metric(probs_b, labels)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"delta": float(point), "ci_low": float(lo), "ci_high": float(hi)}


# --- orchestration -----------------------------------------------------------------

def run_walk_forward(
    rows: Sequence[Row],
    predictors: Mapping[str, Predictor],
    *,
    magnitude_baselines: Sequence[str],
    directional_baselines: Sequence[str],
    model_name: str | None = None,
) -> dict[str, Any]:
    """Pooled OOS evaluation of every predictor over the anchored folds.

    ``rows``: valid training rows for ONE horizon, sorted by date. When
    ``model_name`` is given (§3), its Brier/directional-precision deltas vs the
    BEST baseline get block-bootstrap CIs — the frozen binding gates."""
    rows = sorted(rows, key=lambda r: r["date"])
    dates = [r["date"] for r in rows]
    folds = walk_forward_folds(dates)
    oos: dict[str, list[Probs]] = {name: [] for name in predictors}
    oos_idx: list[int] = []
    for train_idx, test_idx in folds:
        train = [rows[i] for i in train_idx]
        test = [rows[i] for i in test_idx]
        for name, fn in predictors.items():
            oos[name].extend(fn(train, test))
        oos_idx.extend(test_idx)

    labels = [str(rows[i]["label"]) for i in oos_idx]
    realized = [rows[i].get("realized_return") for i in oos_idx]

    per: dict[str, Any] = {}
    for name, probs in oos.items():
        per[name] = {
            "brier_material": brier_material(probs, labels),          # PRIMARY (move-risk)
            "log_loss_material": log_loss_material(probs, labels),    # secondary, clipped
            "ece_material": ece_material(probs, labels),
            "auc_material": auc_material(probs, labels),
            "elevated_coverage": elevated_coverage(probs),
            "brier_three_class": brier_three_class(probs, labels),
            "log_loss_three_class": log_loss_three_class(probs, labels),
            "directional": directional_metrics(probs, labels, realized),
        }

    best_magnitude = min(magnitude_baselines, key=lambda n: per[n]["brier_material"])
    dir_candidates = [
        n for n in directional_baselines if per[n]["directional"].get("directional_precision") is not None
    ]
    best_directional = max(
        dir_candidates, key=lambda n: per[n]["directional"]["directional_precision"]
    ) if dir_candidates else None

    out: dict[str, Any] = {
        "folds": len(folds),
        "oos_days": len(labels),
        "oos_start": str(rows[oos_idx[0]]["date"]) if oos_idx else None,
        "oos_end": str(rows[oos_idx[-1]]["date"]) if oos_idx else None,
        "elevated_call_min_p": ELEVATED_CALL_MIN_P,
        "predictors": per,
        "best_magnitude_baseline": best_magnitude,
        "best_directional_baseline": best_directional,
    }
    if model_name is not None and model_name in per:
        out["move_risk_gate"] = {
            "vs": best_magnitude,
            "brier_delta_ci": block_bootstrap_delta_ci(
                brier_material, oos[model_name], oos[best_magnitude], labels
            ),
            "ece_guardrail_ok": per[model_name]["ece_material"]
            <= per[best_magnitude]["ece_material"] + 0.02,
            "coverage_in_band": 0.10 <= per[model_name]["elevated_coverage"] <= 0.60,
        }
    return out
