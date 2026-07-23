"""CASH_OR_TBILL_RETURN — the absolute-return hurdle benchmark (PREREG v1.0 §6.2, §7 B).

FROZEN SOURCE (owner-ratified 2026-07-22):

    source_provider:     Federal Reserve Bank of St. Louis (FRED)
    underlying_source:   Board of Governors of the Federal Reserve System
    release:             H.15 Selected Interest Rates
    series_id:           DGS3MO
    series_title:        Market Yield on U.S. Treasury Securities at 3-Month Constant Maturity,
                         Quoted on an Investment Basis
    frequency:           Daily
    units:               Percent per annum
    quotation_basis:     Investment basis   (⟹ NO discount→investment conversion)
    seasonal_adjustment: Not seasonally adjusted

DTB3 is REJECTED for this program (discount basis → maturity-dependent conversion). DGS3MO avoids it.

FROZEN POINT-IN-TIME RULE (conservative, no same-day look-ahead):

    yield applied on trading session t = the latest valid DGS3MO observation dated STRICTLY BEFORE t.

This is a one-session publication lag. No prior observation ⟹ INVALID_DATA (never substitute zero) —
which is why the snapshot must begin ≥ 1 year before 2005 so the first eligible session always has a
prior value.

FROZEN ACCRUAL (amended 2026-07-22 — calendar-day ACT/365, not 1/252):

    y = DGS3MO_percent / 100
    cash-ledger session_return = (1 + y) ** (calendar_days_elapsed / 365) - 1
        where calendar_days_elapsed = calendar days since the previous valuation session
        (Friday→Monday = 3 days; weekends/holidays accrue on the carried-forward PIT yield).
    transaction costs = 0.

The 1/252 form is retained ONLY as a "252-session-equivalent" REPORTING helper for historical
equity-session comparisons — never for the actual cash ledger.

FROZEN CASH ECONOMICS (single rule): ALL uninvested strategy cash earns the identical PIT-lagged
DGS3MO cash return — the 20%-cap residual, cash when <5 names qualify, cash awaiting deployment, and
post-settlement sale proceeds. Cash must NOT earn interest before it is economically available
(settlement). So the cash benchmark and the production strategy use identical cash economics.

⚠ PENDING BINDING (owner-supplied, before the §7 A gate / forward window): the immutable DGS3MO CSV
snapshot, its SHA-256, and the observation cutoff. The loader is FAIL-CLOSED on the digest. The
snapshot must NOT auto-refresh during the forward run; any extension is append-only + separately
hashed + tied to a documented cutoff.

⚠ Construct/methodology only. NO forward performance computed until every benchmark SHA + the PREREG
§0 bindings are countersigned (§5.4 no-peeking). Validation must run with NO network access.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

BENCHMARK_ID = "CASH_OR_TBILL_RETURN"
SERIES_ID = "DGS3MO"
QUOTE_UNITS = "percent_per_annum_investment_basis"
DISCOUNT_TO_INVESTMENT_CONVERSION = "none"        # DGS3MO is already an investment yield
CALENDAR_DAYS_PER_YEAR = 365                       # ACT/365 cash accrual
SESSIONS_PER_YEAR_REPORTING = 252                  # reporting-equivalent ONLY
TRANSACTION_COSTS = 0.0
FRED_MISSING = "."                                 # FRED marks a missing observation with a period


class InvalidCashData(Exception):
    """No valid DGS3MO observation strictly before a session that needs one. Per the frozen rule the
    return is INVALID_DATA — it is NEVER substituted with zero."""


def cash_session_return(dgs3mo_percent: float, calendar_days_elapsed: int) -> float:
    """The FROZEN cash-ledger accrual: ACT/365 calendar-day compounding of the investment yield.

        y = dgs3mo_percent / 100
        return = (1 + y) ** (calendar_days_elapsed / 365) - 1
    """
    if calendar_days_elapsed < 0:
        raise ValueError("calendar_days_elapsed must be >= 0")
    y = dgs3mo_percent / 100.0
    return (1.0 + y) ** (calendar_days_elapsed / CALENDAR_DAYS_PER_YEAR) - 1.0


def session_equivalent_252(dgs3mo_percent: float) -> float:
    """REPORTING ONLY — a 252-session-equivalent daily rate for historical equity-session
    comparisons. NOT used for the cash ledger (which is ACT/365, see ``cash_session_return``)."""
    y = dgs3mo_percent / 100.0
    return (1.0 + y) ** (1.0 / SESSIONS_PER_YEAR_REPORTING) - 1.0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dgs3mo(path: Path, expected_sha256: str) -> dict[date, float]:
    """Parse a FRED DGS3MO snapshot (DATE,DGS3MO CSV), FAIL-CLOSED on the digest computed over the
    exact raw bytes. Missing observations ('.') are dropped and handled by carry-forward at accrual.
    Refuses an unverified/substituted series."""
    actual = _sha256(path)
    if actual != expected_sha256:
        raise ValueError(
            f"DGS3MO snapshot digest mismatch: expected {expected_sha256}, got {actual}. "
            f"Refusing to load an unverified/substituted series.")
    out: dict[date, float] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or "," not in line or line.lower().startswith(("date", "observation_date")):
            continue
        d_str, v_str = (p.strip() for p in line.split(",", 1))
        if v_str in (FRED_MISSING, ""):
            continue
        try:
            out[datetime.strptime(d_str, "%Y-%m-%d").date()] = float(v_str)
        except ValueError:
            continue
    return out


def pit_yield_asof(series: dict[date, float], session: date) -> float:
    """The DGS3MO yield (percent) applied on trading session ``session``: the latest valid observation
    dated STRICTLY BEFORE ``session`` (one-session lag, no same-day look-ahead). Carries over
    weekends/holidays/missing gaps. Raises ``InvalidCashData`` if none exists (never zero)."""
    prior = [d for d in series if d < session]
    if not prior:
        raise InvalidCashData(
            f"no DGS3MO observation strictly before {session.isoformat()} — INVALID_DATA "
            f"(the snapshot must begin >= 1 year before the first eligible session)")
    return series[max(prior)]


@dataclass(frozen=True)
class CashTbillBinding:
    """Owner-supplied provenance for the immutable DGS3MO snapshot — completed before the §7 A gate."""
    raw_file: str
    raw_file_sha256: str
    observation_cutoff: str                         # ISO — last observation the snapshot may use
    series_id: str = SERIES_ID
    quote_units: str = QUOTE_UNITS


def accrue_session_returns(binding: CashTbillBinding, valuation_sessions: list[date],
                           data_dir: Path) -> dict[date, float]:
    """Per-valuation-session cash return from the digest-verified DGS3MO snapshot, ACT/365 over the
    calendar days since the previous session, on the PIT-lagged (strictly-before) yield.

    The first session accrues 0 calendar days (no prior session to accrue from) but still REQUIRES a
    valid prior yield (else InvalidCashData). Computes the rate series only — no forward performance,
    no comparison (sealed until §0 countersign)."""
    series = load_dgs3mo(data_dir / binding.raw_file, binding.raw_file_sha256)
    cutoff = datetime.strptime(binding.observation_cutoff, "%Y-%m-%d").date()
    series = {d: v for d, v in series.items() if d <= cutoff}      # honor the observation cutoff
    out: dict[date, float] = {}
    prev: date | None = None
    for s in valuation_sessions:
        y = pit_yield_asof(series, s)                              # raises InvalidCashData if absent
        days = 0 if prev is None else (s - prev).days
        out[s] = cash_session_return(y, days)
        prev = s
    return out


def friday_to_monday_calendar_days(friday: date, monday: date) -> int:
    """Helper/illustration: calendar days across a weekend gap (Fri→Mon = 3)."""
    if not (friday.weekday() == 4 and monday.weekday() == 0):
        raise ValueError("expected a Friday and the following Monday")
    delta = (monday - friday).days
    assert delta == 3, delta
    return delta
