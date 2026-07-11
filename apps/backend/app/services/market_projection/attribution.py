"""MKT-PROJ-001 attribution engine (design §10.2, FR-008).

Layer 2 of the AI design: driver attributions are COMPUTED here by the model
layer; the (optional, flag-gated) LLM in ``explain.py`` may only phrase this
payload. For the primary calibrated logistic the per-projection attribution is
exact: ``coefficient × standardized feature value`` toward the predicted class
(the calibrated wrapper preserves the base logistic's coefficients — Platt
rescales probabilities monotonically, so sign and ranking of contributions are
unchanged). Batch-level permutation importance covers the boosted secondary in
the evidence package.

Payload shape is frozen (FR-008): ``{feature, direction: supports_<LABEL>,
weight, value}``, top-N by |weight|.
"""

from __future__ import annotations

from typing import Any

import numpy as np

TOP_N_DRIVERS = 5


def _base_logistic(calibrated: Any) -> Any:
    """The fitted base LogisticRegression inside a CalibratedClassifierCV."""
    cc = calibrated.calibrated_classifiers_[0]
    est = getattr(cc, "estimator", None)
    # FrozenEstimator wraps the real model
    return getattr(est, "estimator", est)


def logistic_drivers(
    calibrated_logistic: Any,
    x_std_row: np.ndarray,
    columns: list[str],
    predicted_class: str,
    *,
    top_n: int = TOP_N_DRIVERS,
) -> list[dict[str, Any]]:
    """Exact per-projection attribution for the predicted class (coef × std value)."""
    base = _base_logistic(calibrated_logistic)
    classes = list(base.classes_)
    coef = base.coef_[classes.index(predicted_class)]
    contrib = coef * x_std_row
    order = np.argsort(-np.abs(contrib))[:top_n]
    return [
        {
            "feature": columns[i],
            "direction": f"supports_{predicted_class}" if contrib[i] > 0
            else f"against_{predicted_class}",
            "weight": round(float(abs(contrib[i])), 4),
            "value": round(float(x_std_row[i]), 4),
        }
        for i in order
        if abs(contrib[i]) > 0
    ]


def material_drivers(
    calibrated_logistic: Any,
    x_std_row: np.ndarray,
    columns: list[str],
    *,
    top_n: int = TOP_N_DRIVERS,
) -> list[dict[str, Any]]:
    """Move-risk drivers for the SERVED surface (owner rule: nothing directional).

    P(MATERIAL) rises exactly as the NEUTRAL logit falls, so the attribution is
    the negated NEUTRAL-class contribution — exact for the multinomial logistic.
    Direction values are ``raises_move_risk`` / ``lowers_move_risk`` only; no
    UP/DOWN vocabulary can appear downstream of this payload."""
    base = _base_logistic(calibrated_logistic)
    classes = list(base.classes_)
    contrib = -base.coef_[classes.index("NEUTRAL")] * x_std_row
    order = np.argsort(-np.abs(contrib))[:top_n]
    return [
        {
            "feature": columns[i],
            "direction": "raises_move_risk" if contrib[i] > 0 else "lowers_move_risk",
            "weight": round(float(abs(contrib[i])), 4),
            "value": round(float(x_std_row[i]), 4),
        }
        for i in order
        if abs(contrib[i]) > 0
    ]


def permutation_importance_material(
    predict_probs, rows: list[dict], columns_source, *, n_repeats: int = 5, seed: int = 42
) -> dict[str, float]:
    """Batch diagnostic for the evidence package: mean Brier(MATERIAL) degradation
    when one raw feature is shuffled across rows. Model-agnostic; operates on the
    raw feature dicts so the pipeline's imputation/indicators stay in the loop."""
    from app.services.market_projection.validate import brier_material

    rng = np.random.default_rng(seed)
    labels = [r["label"] for r in rows]
    base_score = brier_material(predict_probs(rows), labels)
    names = columns_source if isinstance(columns_source, (list, tuple)) else list(columns_source)
    out: dict[str, float] = {}
    for name in names:
        deltas = []
        values = [(r.get("features_json") or {}).get(name) for r in rows]
        for _ in range(n_repeats):
            perm = rng.permutation(len(rows))
            shuffled = []
            for i, r in enumerate(rows):
                feats = dict(r.get("features_json") or {})
                feats[name] = values[perm[i]]
                shuffled.append({**r, "features_json": feats})
            deltas.append(brier_material(predict_probs(shuffled), labels) - base_score)
        out[name] = round(float(np.mean(deltas)), 5)
    return out
