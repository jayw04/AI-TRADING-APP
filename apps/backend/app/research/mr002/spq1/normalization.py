"""R5 aggregation + single-pass z / sigma normalization (SIG-12..17, OWNER-A).

R5_t = sum of five CONSECUTIVE registered-session residuals eps[t-4..t]; never bridged across a
gap. z and sigma_resid are produced in ONE deterministic pass over the same 60 overlapping R5
values ending t-1 (current R5_t excluded), sharing one normalization-window identity and one
computation-record identity. No floor / clip / winsorization / imputation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import DDOF, R5_HORIZON, Z_NORM_OBS
from .identities import canonical_sha256
from .refusals import refuse

__all__ = ["r5_value", "NormalizedSignal", "normalize_signal"]


def r5_value(eps5: list[float]) -> float | None:
    """R5 from exactly five consecutive residuals; None if any is missing/non-finite."""
    if len(eps5) != R5_HORIZON:
        return None
    if any((v is None) or (not math.isfinite(v)) for v in eps5):
        return None
    return math.fsum(eps5)


@dataclass(frozen=True)
class NormalizedSignal:
    z: float
    sigma: float
    mu: float
    normalization_window_identity: str
    computation_record_identity: str


def _sample_mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    mean = math.fsum(values) / n
    var = math.fsum((v - mean) ** 2 for v in values) / (n - DDOF)
    return mean, math.sqrt(var)


def normalize_signal(
    r5_hist: list[float | None],
    r5_t: float | None,
    hist_session_ordinals: list[int],
) -> NormalizedSignal:
    """One-pass z/sigma over the 60 historical R5 ending t-1.

    ``r5_hist`` are R5_{t-60}..R5_{t-1}; ``r5_t`` is the current R5 (excluded from mu/sigma).
    """
    if r5_t is None or not math.isfinite(r5_t):
        raise refuse("INELIGIBLE:R5_WINDOW_INSUFFICIENT", "current R5_t unavailable")
    if len(r5_hist) != Z_NORM_OBS or any(
        (v is None) or (not math.isfinite(v)) for v in r5_hist
    ):
        raise refuse(
            "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT",
            f"need {Z_NORM_OBS} complete overlapping R5 ending t-1",
        )
    hist: list[float] = [float(v) for v in r5_hist if v is not None]  # all finite floats
    r5_now: float = float(r5_t)
    try:
        mu, sigma = _sample_mean_std(hist)
        sigma_finite = math.isfinite(sigma)
        z = (r5_now - mu) / sigma if (sigma_finite and sigma > 0.0) else float("nan")
        z_finite = math.isfinite(z)
    except OverflowError:
        raise refuse(
            "INTEGRITY_STOP:SIGMA_RESID_NONFINITE", "overflow in normalization pass"
        ) from None
    if not sigma_finite:
        raise refuse("INTEGRITY_STOP:SIGMA_RESID_NONFINITE", "non-finite sigma")
    if sigma <= 0.0:
        raise refuse("INELIGIBLE:ZSCORE_VARIANCE_INVALID", "zero-variance normalization window")
    if not z_finite:
        raise refuse("INTEGRITY_STOP:SIGMA_RESID_NONFINITE", "non-finite z")
    window_id = canonical_sha256(
        {"r5": [v.hex() for v in hist], "ordinals": list(hist_session_ordinals)}
    )
    comp_id = canonical_sha256(
        {
            "window_identity": window_id,
            "mu": mu.hex(),
            "sigma": sigma.hex(),
            "z": z.hex(),
            "r5_t": r5_now.hex(),
            "ddof": DDOF,
        }
    )
    return NormalizedSignal(
        z=z,
        sigma=sigma,
        mu=mu,
        normalization_window_identity=window_id,
        computation_record_identity=comp_id,
    )
