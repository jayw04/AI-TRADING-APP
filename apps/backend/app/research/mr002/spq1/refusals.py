"""Frozen SPQ-1 refusal taxonomy (Phase-0 census v1.1, Correction 2).

Three emittable classes — INTEGRITY_STOP, REFUSED_CODE_OR_DATA_IDENTITY, INELIGIBLE — plus a
single DEPRECATED_NON_EMITTABLE code (``RETURN_INPUT_MISSING``) that must NEVER be raised. The
four missing-input dispositions are deliberately distinct and cannot collapse into one another:

  INELIGIBLE:OLS_WINDOW_INSUFFICIENT          security lacks required registered history (IPO/young)
  INELIGIBLE:KNOWN_MARKET_ABSENCE             missing close WITH governed halt/absence evidence
  INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE        interior hole WITHOUT governed evidence (fails closed)
  REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH   missing SPY / sector factor / identity
"""
from __future__ import annotations

INTEGRITY_STOP = "INTEGRITY_STOP"
REFUSED_CODE_OR_DATA_IDENTITY = "REFUSED_CODE_OR_DATA_IDENTITY"
INELIGIBLE = "INELIGIBLE"
DEPRECATED_NON_EMITTABLE = "DEPRECATED_NON_EMITTABLE"

# Fully-qualified code -> class. The single source of truth for coverage checks.
REFUSAL_CODES: dict[str, str] = {
    # --- REFUSED_CODE_OR_DATA_IDENTITY ---
    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH": REFUSED_CODE_OR_DATA_IDENTITY,
    # --- INTEGRITY_STOP ---
    "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH": INTEGRITY_STOP,
    "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE": INTEGRITY_STOP,
    "INTEGRITY_STOP:OLS_DESIGN_SINGULAR": INTEGRITY_STOP,
    "INTEGRITY_STOP:RESIDUAL_NONFINITE": INTEGRITY_STOP,
    "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT": INTEGRITY_STOP,
    "INTEGRITY_STOP:SIGMA_RESID_NONFINITE": INTEGRITY_STOP,
    "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT": INTEGRITY_STOP,
    "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS": INTEGRITY_STOP,
    "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": INTEGRITY_STOP,
    # --- INELIGIBLE ---
    "INELIGIBLE:OLS_WINDOW_INSUFFICIENT": INELIGIBLE,
    "INELIGIBLE:KNOWN_MARKET_ABSENCE": INELIGIBLE,
    "INELIGIBLE:R5_WINDOW_INSUFFICIENT": INELIGIBLE,
    "INELIGIBLE:ZSCORE_VARIANCE_INVALID": INELIGIBLE,
    "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING": INELIGIBLE,
    "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING": INELIGIBLE,
    "INELIGIBLE:ADV_WINDOW_INSUFFICIENT": INELIGIBLE,
}

# Retired (Correction 2). Present for coverage proof that it is NEVER emitted; not in REFUSAL_CODES.
DEPRECATED_CODES: dict[str, str] = {
    "DEPRECATED_NON_EMITTABLE:RETURN_INPUT_MISSING": DEPRECATED_NON_EMITTABLE,
}


class SignalRefusal(Exception):
    """A governed refusal. ``code`` is the fully-qualified ``CLASS:NAME`` string."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code in DEPRECATED_CODES:
            raise AssertionError(
                f"deprecated non-emittable refusal code raised: {code} (Correction 2)"
            )
        if code not in REFUSAL_CODES:
            raise AssertionError(f"unknown refusal code: {code}")
        self.code = code
        self.code_class = REFUSAL_CODES[code]
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def refuse(code: str, detail: str = "") -> SignalRefusal:
    """Construct (not raise) a governed refusal — callers ``raise refuse(...)``."""
    return SignalRefusal(code, detail)
