"""Registered deterministic OLS solver (SIG-10 / Ruling 2, preregistered).

One solver, float64, intercept included, no regularization / ridge / pseudodata / factor
dropping / alternate model. Rank deficiency or a numerically singular design fails closed to
INTEGRITY_STOP:OLS_DESIGN_SINGULAR. The solver identity and rank tolerance are the preregistered
constants ``SOLVER_IDENTITY`` / ``RANK_TOLERANCE``.
"""
from __future__ import annotations

import numpy as np

from .constants import RANK_TOLERANCE, SOLVER_IDENTITY
from .refusals import refuse

__all__ = ["registered_ols", "SOLVER_IDENTITY", "RANK_TOLERANCE"]


def registered_ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """OLS with intercept via the registered solver. Returns coefficients [a, b1, b2, ...].

    Design = [1 | X]. Uses numpy.linalg.lstsq (LAPACK gelsd / SVD) with rcond=RANK_TOLERANCE;
    a returned effective rank below the parameter count fails closed OLS_DESIGN_SINGULAR.
    """
    y = np.asarray(y, dtype=np.float64)
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    design = np.column_stack([np.ones(len(y), dtype=np.float64), X])
    n_params = design.shape[1]
    if not (np.all(np.isfinite(design)) and np.all(np.isfinite(y))):
        raise refuse("INTEGRITY_STOP:OLS_DESIGN_SINGULAR", "non-finite design or response")
    try:
        coef, _residuals, rank, _sv = np.linalg.lstsq(design, y, rcond=RANK_TOLERANCE)
    except np.linalg.LinAlgError as exc:  # pragma: no cover - defensive
        raise refuse("INTEGRITY_STOP:OLS_DESIGN_SINGULAR", f"lstsq failed: {exc}") from None
    if rank < n_params:
        raise refuse(
            "INTEGRITY_STOP:OLS_DESIGN_SINGULAR",
            f"rank-deficient design: effective rank {rank} < {n_params} params",
        )
    if not np.all(np.isfinite(coef)):
        raise refuse("INTEGRITY_STOP:OLS_DESIGN_SINGULAR", "non-finite coefficients")
    return np.asarray(coef, dtype=np.float64)
