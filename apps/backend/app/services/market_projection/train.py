"""MKT-PROJ-001 §3 — the frozen model pipeline (pre-registration v1.2 §6/§6a, FR-006).

Everything here is the freeze, executed literally:

- **Feature pipeline (§6a)**: features in the frozen manifest order → binary
  missingness indicators for the FIVE pre-enumerated structurally-missing
  fields → median imputation fitted on the TRAINING WINDOW ONLY → standardization
  fitted on the same training window → fitted parameters carried forward to
  validation/test. No target-aware, full-sample, cross-window, or post-hoc
  imputation. Unexpected missingness in any non-enumerated required feature is a
  data-quality failure: the training builder already excludes such rows, and the
  pipeline asserts it never silently imputes one.
- **Primary model (§6)**: LogisticRegression(C=1.0, l2, max_iter=1000) on
  standardized features, Platt-calibrated. **Secondaries**:
  HistGradientBoostingClassifier(max_iter=200, lr=0.1, early_stopping=False,
  random_state=42), isotonic-calibrated; and the simple average ensemble.
- **Time-respecting calibration ONLY (§6)**: within each training window the
  base model fits on the earlier 80% and the calibrator on the FINAL CONTIGUOUS
  20%; the test fold is strictly future. No random K-fold calibration exists in
  this module.

The trained pipelines plug into ``validate.run_walk_forward`` as ordinary
predictors, so the §3 evidence uses byte-identical fold/metric/gate machinery
to the §2 baselines.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.services.market_projection.schemas import (
    PRECLOSE_FEATURES,
    PREOPEN_FEATURES,
    Label,
    ProjectionType,
)

SEED = 42
CALIBRATION_TAIL = 0.20  # final contiguous share of the train window (frozen)
CLASSES = (Label.UP.value, Label.DOWN.value, Label.NEUTRAL.value)

# §6a pre-enumerated structurally-missing fields → binary missingness indicators.
# ONLY these may be imputed as by-design missing; any other None is a
# data-quality failure (the §1 builder excludes such rows upstream).
STRUCTURAL_MISSING_FIELDS = (
    "spy_gap_pct_qf",
    "qqq_gap_pct_qf",
    "iwm_gap_pct_qf",
    "spy_late_day_ret",
    "spy_volume_vs_20d_tod",
)


def manifest_for(ptype: ProjectionType) -> tuple[str, ...]:
    return PREOPEN_FEATURES if ptype == ProjectionType.PRE_OPEN_TODAY else PRECLOSE_FEATURES


@dataclass
class FeaturePipeline:
    """§6a transform: manifest order → indicators → train-median impute → standardize."""

    manifest: tuple[str, ...]
    medians: np.ndarray | None = None
    means: np.ndarray | None = None
    stds: np.ndarray | None = None

    @property
    def columns(self) -> list[str]:
        indicators = [f"{f}_missing" for f in self.manifest if f in STRUCTURAL_MISSING_FIELDS]
        return list(self.manifest) + indicators

    def _raw(self, rows: Sequence[dict]) -> np.ndarray:
        mat = np.full((len(rows), len(self.manifest)), np.nan)
        for i, r in enumerate(rows):
            feats = r.get("features_json") or {}
            for j, name in enumerate(self.manifest):
                v = feats.get(name)
                if v is not None:
                    mat[i, j] = float(v)
        return mat

    def fit_transform(self, rows: Sequence[dict]) -> np.ndarray:
        raw = self._raw(rows)
        self.medians = np.nanmedian(raw, axis=0)
        x = self._assemble(raw)
        self.means = x.mean(axis=0)
        self.stds = x.std(axis=0)
        self.stds[self.stds == 0] = 1.0
        return (x - self.means) / self.stds

    def transform(self, rows: Sequence[dict]) -> np.ndarray:
        if self.medians is None or self.means is None or self.stds is None:
            raise RuntimeError("pipeline not fitted")
        return (self._assemble(self._raw(rows)) - self.means) / self.stds

    def _assemble(self, raw: np.ndarray) -> np.ndarray:
        assert self.medians is not None
        cols = [np.where(np.isnan(raw[:, j]), self.medians[j], raw[:, j])
                for j in range(raw.shape[1])]
        for j, name in enumerate(self.manifest):
            if name in STRUCTURAL_MISSING_FIELDS:
                cols.append(np.isnan(raw[:, j]).astype(float))
        x = np.column_stack(cols)
        # a column that was all-NaN in train has a NaN median; treat as 0 post-impute
        return np.nan_to_num(x, nan=0.0)


def _calibrated(base: Any, method: str, x_cal: np.ndarray, y_cal: np.ndarray) -> Any:
    """Calibrate a FITTED base model on the held-out contiguous tail (§6)."""
    from sklearn.calibration import CalibratedClassifierCV

    try:  # sklearn >= 1.6
        from sklearn.frozen import FrozenEstimator

        calib = CalibratedClassifierCV(FrozenEstimator(base), method=method)
    except ImportError:  # pragma: no cover - sklearn < 1.6
        calib = CalibratedClassifierCV(base, method=method, cv="prefit")
    calib.fit(x_cal, y_cal)
    return calib


@dataclass
class TrainedModels:
    pipeline: FeaturePipeline
    logistic: Any          # Platt-calibrated — THE primary (pre-reg §6)
    boosted: Any           # isotonic-calibrated secondary
    classes: tuple[str, ...] = CLASSES

    def _probs(self, model: Any, x: np.ndarray) -> list[dict[str, float]]:
        p = model.predict_proba(x)
        order = list(model.classes_)
        return [{c: float(row[order.index(c)]) if c in order else 0.0 for c in CLASSES}
                for row in p]

    def predict_logistic(self, rows: Sequence[dict]) -> list[dict[str, float]]:
        return self._probs(self.logistic, self.pipeline.transform(rows))

    def predict_boosted(self, rows: Sequence[dict]) -> list[dict[str, float]]:
        return self._probs(self.boosted, self.pipeline.transform(rows))

    def predict_ensemble(self, rows: Sequence[dict]) -> list[dict[str, float]]:
        a, b = self.predict_logistic(rows), self.predict_boosted(rows)
        return [{c: (pa[c] + pb[c]) / 2 for c in CLASSES} for pa, pb in zip(a, b, strict=True)]


def fit_models(train_rows: Sequence[dict], ptype: ProjectionType) -> TrainedModels:
    """Fit the frozen pipeline + models on one training window (temporal order
    assumed — the §1 rows are date-sorted; the calibration tail is the final
    contiguous 20%)."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    rows = sorted(train_rows, key=lambda r: r["date"])
    split = max(1, int(len(rows) * (1 - CALIBRATION_TAIL)))
    fit_rows, cal_rows = rows[:split], rows[split:]
    if not cal_rows:  # degenerate tiny window
        fit_rows, cal_rows = rows, rows

    pipeline = FeaturePipeline(manifest_for(ptype))
    x_fit = pipeline.fit_transform(fit_rows)
    y_fit = np.array([r["label"] for r in fit_rows])
    x_cal = pipeline.transform(cal_rows)
    y_cal = np.array([r["label"] for r in cal_rows])

    logistic = LogisticRegression(C=1.0, penalty="l2", max_iter=1000)
    logistic.fit(x_fit, y_fit)
    boosted = HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, early_stopping=False, random_state=SEED
    )
    boosted.fit(x_fit, y_fit)

    return TrainedModels(
        pipeline=pipeline,
        logistic=_calibrated(logistic, "sigmoid", x_cal, y_cal),
        boosted=_calibrated(boosted, "isotonic", x_cal, y_cal),
    )


def model_predictors(ptype: ProjectionType) -> dict[str, Any]:
    """Walk-forward predictor closures: each fold fits fresh on that fold's train
    window (the harness passes (train, test)) — no state leaks across folds."""
    def _make(which: str):
        def predict(train: Sequence[dict], test: Sequence[dict]) -> list[dict[str, float]]:
            models = fit_models(train, ptype)
            return getattr(models, f"predict_{which}")(test)
        return predict

    return {
        "model_logistic": _make("logistic"),   # the gate model (pre-reg §6)
        "model_boosted": _make("boosted"),
        "model_ensemble": _make("ensemble"),
    }
