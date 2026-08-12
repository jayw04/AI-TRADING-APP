"""Synthetic source facts for producer equivalence: one world, both paths.

Sized so the producer can actually score. The required lead-in is longer than the 126-observation
stock warm-up, because the sector factor carries its own 60-session regression window - see the
MIN_SCORE_T derivation below. A fixture that is too short refuses every unit and would let a suite
pass while proving nothing.

Each security is built to exercise exactly one of the owner's seven cases, so a case that stops
being exercised shows up as a missing outcome rather than as silence.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app.research.mr002.spq1 import (
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from app.research.mr002.spq1.constants import (
    OLS_WINDOW,
    R5_HORIZON,
    WARMUP_PRICE_OBSERVATIONS,
    Z_NORM_OBS,
)
from app.research.mr002.spq1.security_identity import LineageRecord, PitIdentityRegistry

# Sizing is NOT just the stock warm-up. The producer needs u_sector[s] for every session in the
# z-normalisation window, and `sector_factor_at` itself regresses over s-60..s-1, so the earliest
# required s must still have 60 sessions behind it. The lead-in therefore stacks:
#
#     stock warm-up (126)  +  Z_NORM_OBS (60)  +  R5_HORIZON (5)  +  OLS_WINDOW (60)
#
# A fixture sized only to the 126-observation warm-up refuses every unit with
# SIGNAL_INPUT_IDENTITY_MISMATCH ("sector-ETF insufficient history") - which is how the first
# version of this fixture failed the non-vacuity gate.
MIN_SCORE_T = WARMUP_PRICE_OBSERVATIONS + Z_NORM_OBS + R5_HORIZON + OLS_WINDOW
N_SESSIONS = 320
SCORE_T = 260
assert SCORE_T >= MIN_SCORE_T, f"fixture would refuse every unit; need t >= {MIN_SCORE_T}"
assert N_SESSIONS > SCORE_T + 1, "no t+1 session for the enrichment stage"


def _sessions(n: int = N_SESSIONS) -> list[str]:
    out, day = [], date(2019, 10, 3)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


SESSIONS = _sessions()
SPY = "SPY"
XLK, XLF = "XLK", "XLF"

# --- securities, one per case -------------------------------------------------------------------
# HEALTHY  : scores cleanly - the case that proves the suite is not vacuous
# YOUNGSEC : listed after the warm-up window opens -> OLS_WINDOW_INSUFFICIENT
# HOLESEC  : an interior missing bar -> OLS_WINDOW_INCOMPLETE
# AMBIGSEC : two conflicting lineage successors at the same session -> IDENTITY_AMBIGUOUS
# BOUNDSEC : PIT sector observation accepted exactly at the close-t cutoff
# GAPFACTOR: healthy security whose SECTOR ETF has a hole in the window
SECURITIES = ("HEALTHY", "YOUNGSEC", "HOLESEC", "AMBIGSEC", "BOUNDSEC", "GAPFACTOR")

CIK_BY_SYMBOL = {
    "HEALTHY": 100,
    "YOUNGSEC": 101,
    "HOLESEC": 102,
    "AMBIGSEC": 103,
    "BOUNDSEC": 104,
    "GAPFACTOR": 105,
}

# GAPFACTOR sits in the sector whose ETF carries the hole.
SECTOR_ETF_BY_SYMBOL = {s: XLK for s in SECURITIES}
SECTOR_ETF_BY_SYMBOL["GAPFACTOR"] = XLF

YOUNG_FIRST_SESSION = SCORE_T - 20  # listed far too late for a 60-session window
HOLE_SESSION = SCORE_T - 10  # interior hole inside the needed window
FACTOR_GAP_SESSION = SCORE_T - 8  # missing sector-ETF bar inside the window


def _level(seed: int, i: int) -> float:
    """A deterministic, strictly positive, non-degenerate price path."""
    return 50.0 + seed * 7.0 + 10.0 * math.sin((i + seed) / 9.0) + i * 0.05


def price_rows() -> list[tuple[str, str, float | None, float | None, float | None, float | None]]:
    """(ticker, date, closeadj, closeunadj, close, volume); None means the bar is absent."""
    rows = []
    for seed, symbol in enumerate(SECURITIES):
        for i, session in enumerate(SESSIONS):
            if symbol == "YOUNGSEC" and i < YOUNG_FIRST_SESSION:
                continue
            if symbol == "HOLESEC" and i == HOLE_SESSION:
                continue
            ca = _level(seed + 1, i)
            rows.append((symbol, session, ca, ca * 0.92, ca * 0.97, 1_000_000.0 + i))
    return rows


def etf_rows() -> list[tuple[str, str, float | None]]:
    rows = []
    for seed, ticker in enumerate((SPY, XLK, XLF)):
        for i, session in enumerate(SESSIONS):
            if ticker == XLF and i == FACTOR_GAP_SESSION:
                continue  # the factor-series gap
            rows.append((ticker, session, _level(seed + 20, i)))
    return rows


SIC_MAP_ROWS = [
    (2000, 2999, None, "technology", XLK),
    (3000, 3999, None, "financials", XLF),
]


def sic_observation_rows(close_t_iso: str) -> list[tuple[int, str, str, str]]:
    """(cik, accepted_utc, sic, accession).

    BOUNDSEC carries an observation accepted EXACTLY at the close-t cutoff and a later one just
    after it. The frozen rule is `accepted_utc <= close_t`, so the boundary observation must win
    and the later one must be invisible - the distinction the case exists to test.
    """
    early = "2019-10-04T12:00:00Z"
    # GAPFACTOR is EXCLUDED from the generic technology row on purpose: giving it two different
    # SICs at the same acceptance timestamp made it refuse with SECTOR_EFFECTIVE_DATE_CONFLICT,
    # so the factor-series gap it exists to test was never reached. The case was silently
    # measuring something else.
    rows = [
        (cik, early, "2500", f"acc-{cik}")
        for sym, cik in CIK_BY_SYMBOL.items()
        if sym != "GAPFACTOR"
    ]
    rows.append((CIK_BY_SYMBOL["GAPFACTOR"], early, "3500", "acc-gapfactor-fin"))
    rows.append((CIK_BY_SYMBOL["BOUNDSEC"], close_t_iso, "2600", "acc-bound-at-cutoff"))
    rows.append((CIK_BY_SYMBOL["BOUNDSEC"], "2099-01-01T00:00:00Z", "3600", "acc-bound-after"))
    return rows


def lineage_registry() -> PitIdentityRegistry:
    """One clean successor per symbol, except AMBIGSEC which carries two conflicting successors."""
    lineage: dict[str, tuple[LineageRecord, ...]] = {}
    for symbol in SECURITIES:
        if symbol == "AMBIGSEC":
            lineage[symbol] = (
                LineageRecord(None, "PERM-AMBIG-A", 0, "ticker_change", True, "ev-a"),
                LineageRecord(None, "PERM-AMBIG-B", 0, "ticker_change", True, "ev-b"),
            )
        else:
            lineage[symbol] = (
                LineageRecord(None, f"PERM-{symbol}", 0, "ticker_change", True, f"ev-{symbol}"),
            )
    return PitIdentityRegistry(lineage)


OBSERVED_IDENTITIES = {
    "spy_total_return_series": "obs-spy",
    "sector_etf_source_series": "obs-etf",
    "sector_etf_proxy_mapping_table": "obs-map",
    "price_return_adjustment_policy": "obs-policy",
    "pit_sector_source": "obs-sector",
    "pit_identity_registry": "obs-identity",
    "eligibility_evidence_sources": "obs-eligibility",
}

GOVERNING = {
    "producer_code_version": PRODUCER_CODE_VERSION,
    "rule_census_identity": PHASE0_CENSUS_SHA256,
    "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
    "schema_identity": PHASE0_SCHEMA_SHA256,
}
