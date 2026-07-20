"""Daily arithmetic total returns + missing-observation dispositions (SIG-04/05/06, Correction 2).

Registered sessions only; no calendar arithmetic, forward-fill, interpolation, last-observation
carry, or silent row dropping. The four missing-input dispositions are distinct and never
collapse; ``RETURN_INPUT_MISSING`` is never emitted (retired, Correction 2).
"""
from __future__ import annotations

from enum import StrEnum

import numpy as np

from .refusals import SignalRefusal, refuse


class CellStatus(StrEnum):
    """Per-session status of a security's observation, aligned to the registered calendar."""

    PRESENT = "PRESENT"
    YOUNG = "YOUNG"                     # before the security's first registered listing
    HALT_WITH_EVIDENCE = "HALT_WITH_EVIDENCE"   # governed halt / market absence
    UNEXPLAINED_HOLE = "UNEXPLAINED_HOLE"       # missing close, no governed evidence


def arithmetic_total_returns(closeadj: np.ndarray) -> np.ndarray:
    """Arithmetic total returns r[s] = closeadj[s]/closeadj[s-1] - 1 (frozen V3 signal series).

    r[0] is NaN (no preceding price). Uses total-return-adjusted closes only.
    """
    closeadj = np.asarray(closeadj, dtype=np.float64)
    r = np.full(len(closeadj), np.nan, dtype=np.float64)
    if len(closeadj) >= 2:
        r[1:] = closeadj[1:] / closeadj[:-1] - 1.0
    return r


def classify_stock_window(statuses: list[CellStatus]) -> None:
    """Fail closed with the correct disposition when a needed stock cell is absent.

    Precedence within missing-stock handling: YOUNG (insufficient history) before an interior
    hole, because a young security simply has no history; a hole/absence is per-session.
    Returns None only when every needed cell is PRESENT.
    """
    if all(s == CellStatus.PRESENT for s in statuses):
        return
    if any(s == CellStatus.YOUNG for s in statuses):
        raise refuse(
            "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
            "security lacks required registered history (young/IPO)",
        )
    # Interior of an otherwise-listed window: an unexplained hole fails closed (integrity)
    # and must NOT be concealed as an ordinary exclusion (OWNER-C).
    if any(s == CellStatus.UNEXPLAINED_HOLE for s in statuses):
        raise refuse(
            "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE",
            "interior missing stock return without governed evidence",
        )
    if any(s == CellStatus.HALT_WITH_EVIDENCE for s in statuses):
        raise refuse(
            "INELIGIBLE:KNOWN_MARKET_ABSENCE",
            "missing close with governed halt/absence evidence",
        )


def require_factor_present(values: np.ndarray, which: str) -> None:
    """A missing SPY or sector-factor return is an input-identity refusal (never a stock
    ineligibility)."""
    if not np.all(np.isfinite(np.asarray(values, dtype=np.float64))):
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            f"missing/non-finite {which} factor return in the window",
        )


__all__ = [
    "CellStatus",
    "arithmetic_total_returns",
    "classify_stock_window",
    "require_factor_present",
    "SignalRefusal",
]
