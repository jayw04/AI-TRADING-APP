"""MR-002 Increment 3 — strict synthetic candidate validation (synthetic only).

Validates SyntheticCandidate records, computes ONLY the inverse-vol q_i = 1/registered_sigma_resid
(RC-1), cross-checks any candidate-provided inverse at the frozen rel_tol 1e-12, and binds the A/B/C
configuration identity (PR-20; Z_entry only). Increment 3 NEVER estimates residuals/z/volatility,
reconstructs the 60-session window, or reconstructs eligibility histories — those arrive as registered
candidate fields. Fail-closed with INTEGRITY_STOP / REFUSED codes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mr002_valoos_portfolio_identity import Z_ENTRY

INVERSE_VOL_REL_TOL = 1e-12       # RC-1 frozen tolerance for the evidence-only candidate inverse
ELIGIBILITY = ("ELIGIBLE", "INELIGIBLE")

REQUIRED = ("candidate_id", "permanent_security_id", "signal_origin_session", "decision_session",
            "symbol", "side", "registered_signal_value", "registered_sigma_resid", "sector_id",
            "beta", "eligibility_status", "eligibility_evidence_identity", "configuration_id",
            "official_next_open_price", "trailing_adv_dollars")


class CandidateIntegrityStop(Exception):
    """INTEGRITY_STOP — a candidate field failed validation."""


class CandidateRefused(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — candidate/execution identity divergence."""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    permanent_security_id: str
    signal_origin_session: int
    decision_session: int
    symbol: str
    side: str
    registered_signal_value: float          # residual z
    registered_sigma_resid: float           # > 0, finite; NOT computed here
    sector_id: str
    beta: float
    eligibility_status: str                 # ELIGIBLE | INELIGIBLE
    eligibility_evidence_identity: str
    configuration_id: str                   # A | B | C
    official_next_open_price: float
    trailing_adv_dollars: float
    inverse_vol_weight: float               # q_i = 1 / registered_sigma_resid (derived here)


def _num(v, code: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CandidateIntegrityStop(f"{code}:{v!r}")
    f = float(v)
    if not math.isfinite(f):
        raise CandidateIntegrityStop(f"{code}:{v!r}")
    return f


def _sid(v, code: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise CandidateIntegrityStop(f"{code}:{v!r}")
    return v


def validate_candidate(rec: dict, *, config_id: str) -> Candidate:
    """Validate one candidate record for the active configuration. Returns a frozen Candidate with the
    derived inverse-vol weight; fail-closed on any invalid field."""
    for k in REQUIRED:
        if k not in rec:
            raise CandidateIntegrityStop(f"CANDIDATE_MISSING_FIELD:{k}")
    if not isinstance(rec["candidate_id"], str) or not rec["candidate_id"]:
        raise CandidateIntegrityStop("CANDIDATE_ID_INVALID")
    if rec["configuration_id"] not in Z_ENTRY:
        raise CandidateIntegrityStop(f"CANDIDATE_CONFIG_INVALID:{rec['configuration_id']}")
    if rec["configuration_id"] != config_id:
        raise CandidateRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_CONFIG_MISMATCH:{rec['configuration_id']}!={config_id}")
    if rec["side"] not in ("long", "short"):
        raise CandidateIntegrityStop(f"CANDIDATE_SIDE_INVALID:{rec['side']}")
    if rec["eligibility_status"] not in ELIGIBILITY:
        raise CandidateIntegrityStop(f"CANDIDATE_ELIGIBILITY_INVALID:{rec['eligibility_status']}")

    sigma = rec["registered_sigma_resid"]
    if isinstance(sigma, bool) or not isinstance(sigma, (int, float)) or not math.isfinite(float(sigma)) or float(sigma) <= 0.0:
        raise CandidateIntegrityStop(f"CANDIDATE_SIGMA_RESID_INVALID:{sigma!r}")
    q = 1.0 / float(sigma)                                # RC-1: the ONLY derivation Increment 3 does
    if "registered_inverse_vol_weight" in rec:           # evidence only; recompute + cross-check
        cand_inv = rec["registered_inverse_vol_weight"]
        if isinstance(cand_inv, bool) or not isinstance(cand_inv, (int, float)) or \
           not math.isclose(float(cand_inv), q, rel_tol=INVERSE_VOL_REL_TOL, abs_tol=0.0):
            raise CandidateIntegrityStop(f"CANDIDATE_INVERSE_VOL_MISMATCH:{cand_inv!r}!=1/{sigma}")

    z = _num(rec["registered_signal_value"], "CANDIDATE_SIGNAL_INVALID")
    beta = _num(rec["beta"], "CANDIDATE_BETA_INVALID")
    price = _num(rec["official_next_open_price"], "CANDIDATE_PRICE_INVALID")
    if price <= 0.0:
        raise CandidateIntegrityStop(f"CANDIDATE_PRICE_INVALID:{price}")
    adv = _num(rec["trailing_adv_dollars"], "CANDIDATE_ADV_INVALID")
    if adv < 0.0:
        raise CandidateIntegrityStop(f"CANDIDATE_ADV_INVALID:{adv}")
    for s in ("symbol", "sector_id", "permanent_security_id", "eligibility_evidence_identity"):
        if not isinstance(rec[s], str) or not rec[s]:
            raise CandidateIntegrityStop(f"CANDIDATE_{s.upper()}_INVALID")

    return Candidate(
        candidate_id=rec["candidate_id"], permanent_security_id=rec["permanent_security_id"],
        signal_origin_session=_sid(rec["signal_origin_session"], "CANDIDATE_SIGNAL_ORIGIN_INVALID"),
        decision_session=_sid(rec["decision_session"], "CANDIDATE_DECISION_SESSION_INVALID"),
        symbol=rec["symbol"], side=rec["side"], registered_signal_value=z,
        registered_sigma_resid=float(sigma), sector_id=rec["sector_id"], beta=beta,
        eligibility_status=rec["eligibility_status"],
        eligibility_evidence_identity=rec["eligibility_evidence_identity"],
        configuration_id=rec["configuration_id"], official_next_open_price=price,
        trailing_adv_dollars=adv, inverse_vol_weight=q)


def validate_candidates(records: list, *, config_id: str) -> list:
    out, ids = [], set()
    for rec in records:
        c = validate_candidate(rec, config_id=config_id)
        if c.candidate_id in ids:
            raise CandidateRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:DUPLICATE_CANDIDATE_ID:{c.candidate_id}")
        ids.add(c.candidate_id)
        out.append(c)
    return out


def assert_candidate_execution_identity(candidate: Candidate, market_open: float, market_adv: float,
                                        scheduled_next_open_session: int, market_nav: float,
                                        construction_nav: float) -> None:
    """Clarification #2: the candidate's evidence-bound price/ADV must match the session-market values
    the Increment-2 execution consumes (symbol/decision-session already carried on the candidate).
    Any disagreement -> REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_EXECUTION_INPUT_MISMATCH."""
    if candidate.decision_session + 1 != scheduled_next_open_session:
        raise CandidateRefused(
            f"REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_EXECUTION_INPUT_MISMATCH:next_open:{candidate.decision_session + 1}!={scheduled_next_open_session}")
    if float(candidate.official_next_open_price) != float(market_open):
        raise CandidateRefused(
            f"REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_EXECUTION_INPUT_MISMATCH:price:{candidate.official_next_open_price}!={market_open}")
    if float(candidate.trailing_adv_dollars) != float(market_adv):
        raise CandidateRefused(
            f"REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_EXECUTION_INPUT_MISMATCH:adv:{candidate.trailing_adv_dollars}!={market_adv}")
    if float(market_nav) != float(construction_nav):
        raise CandidateRefused(
            f"REFUSED_CODE_OR_DATA_IDENTITY:CANDIDATE_EXECUTION_INPUT_MISMATCH:nav:{market_nav}!={construction_nav}")
