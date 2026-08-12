"""The `ProducerCandidateSource`: the last semantic bridge before the frozen producer.

Equivalence here is achieved by **reuse, not by mirroring**. The Phase 2B sector resolution, the
ET close cutoff and the PIT identity registry are pure functions over rows, so this module calls
*the same code* rather than reimplementing its rules. Identical code cannot drift from itself, and
every one of those modules is bound in the execution roster.

What this module does add is the bridge from decoded parquet tables to those functions' inputs, and
the construction of the t+1 `ExecutionFacts` the enrichment stage consumes. Both are held to the
same standard as the price assembly: no implicit default, no coercion, and an ambiguity refused
rather than resolved by preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..spq1.calendar import RegisteredCalendar
from ..spq1.eligibility import ExclusionCheck
from ..spq1.identities import InputIdentityRegistry
from ..spq1.phase2b.cutoff import et_close_cutoff_iso
from ..spq1.phase2b.sic_sector import SicMapRow, load_sic_map, resolve_sector, sector_etf
from ..spq1.producer import ProductionRequest, produce_decision
from ..spq1.refusals import SignalRefusal
from ..spq1.security_identity import PitIdentityRegistry
from . import assembly as ASM
from .enrichment import ExecutionFacts

PROGRAM_ID = "MR-002"

# Closed reference mapping: every reference table column consumed here has one registered purpose.
REFERENCE_COLUMN_PURPOSE: dict[tuple[str, str], str] = {
    ("sic_mapping", "sic_start"): "SIC range lower bound",
    ("sic_mapping", "sic_end"): "SIC range upper bound",
    ("sic_mapping", "effective_from"): "registered effective date (NULL = always-effective)",
    ("sic_mapping", "research_sector"): "registered sector id",
    ("sic_mapping", "sector_etf"): "registered sector proxy ticker",
    ("sic_observations", "cik"): "PIT SIC subject key",
    ("sic_observations", "accepted_utc"): "PIT availability timestamp",
    ("sic_observations", "sic"): "point-in-time SIC",
    ("sic_observations", "accession"): "source evidence identity",
    ("actions", "date"): "corporate-action session",
    ("actions", "ticker"): "corporate-action subject",
    ("actions", "action"): "corporate-action kind",
    ("actions", "value"): "cash distribution amount",
}


@dataclass(frozen=True)
class Unit:
    """One (symbol, decision session) request, the frozen logical unit of production."""

    symbol: str
    t: int
    side: str = "LONG"
    configuration_id: str = "B"


class CandidateSourceRefused(Exception):
    """A bridge input that cannot be assembled under the frozen rules."""


def _rows(table: Any, columns: tuple[str, ...]) -> list[tuple]:
    cols = [table.column(c).to_pylist() for c in columns]
    return list(zip(*cols, strict=True))


def sic_map_from(table: Any) -> list[SicMapRow]:
    """Reuse the frozen loader; only the row extraction is new."""
    cols = ("sic_start", "sic_end", "effective_from", "research_sector", "sector_etf")
    missing = sorted(set(cols) - set(table.column_names))
    if missing:
        raise CandidateSourceRefused(f"sic_mapping: registered columns absent: {missing}")
    return load_sic_map(_rows(table, cols))


def sic_observations_by_cik(table: Any) -> dict[int, list[tuple]]:
    """(accepted_utc, sic, accession) per CIK, in the shape the frozen resolver expects."""
    cols = ("cik", "accepted_utc", "sic", "accession")
    missing = sorted(set(cols) - set(table.column_names))
    if missing:
        raise CandidateSourceRefused(f"sic_observations: registered columns absent: {missing}")
    out: dict[int, list[tuple]] = {}
    for cik, accepted, sic, accession in _rows(table, cols):
        out.setdefault(int(cik), []).append((accepted, sic, accession))
    return out


def cash_distributions(table: Any) -> dict[tuple[str, str], float]:
    """(ticker, session) -> summed cash distribution, for the registered economic gap.

    Summed rather than last-wins: two distributions on one session are two distributions, and
    silently keeping one would understate the adjustment the gap filter depends on.
    """
    cols = ("date", "ticker", "action", "value")
    missing = sorted(set(cols) - set(table.column_names))
    if missing:
        raise CandidateSourceRefused(f"actions: registered columns absent: {missing}")
    out: dict[tuple[str, str], float] = {}
    for date, ticker, action, value in _rows(table, cols):
        if str(action) != "dividend" or value is None:
            continue
        key = (str(ticker), str(date))
        out[key] = out.get(key, 0.0) + float(value)
    return out


def corporate_actions(table: Any) -> dict[tuple[str, str], tuple[str, str]]:
    """(ticker, session) -> (kind, identity). A session carrying two different kinds is refused."""
    cols = ("date", "ticker", "action")
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for date, ticker, action in _rows(table, cols):
        key = (str(ticker), str(date))
        kind = str(action)
        if key in out and out[key][0] != kind:
            raise CandidateSourceRefused(
                f"conflicting corporate-action kinds for {key}: {out[key][0]} and {kind}"
            )
        out[key] = (kind, f"actions:{ticker}:{date}:{kind}")
    return out


@dataclass
class ProducerCandidateSource:
    """Bridges decoded tables to the frozen producer, one unit at a time."""

    calendar: RegisteredCalendar
    units: list[Unit]
    lineage: PitIdentityRegistry
    cik_by_symbol: dict[str, int]
    registry: InputIdentityRegistry
    observed_identities: dict[str, str]
    spy_ticker: str = "SPY"
    eligibility_checks_by_symbol: dict[str, list[ExclusionCheck]] | None = None

    refusals: list[tuple[str, int, str]] = field(default_factory=list)

    def candidates(self, payloads: dict[str, Any]) -> list[tuple[Any, ExecutionFacts]]:
        """Produce (SignalDecisionRecord, ExecutionFacts) for every unit that survives production.

        A governed refusal is recorded and the unit is dropped - it never becomes a candidate - so
        the enrichment census counts only records the producer actually emitted.
        """
        tables = payloads["tables"]
        sic_map = sic_map_from(tables["sic_mapping"])
        sic_obs = sic_observations_by_cik(tables["sic_observations"])
        etf_by_sector = {r.research_sector: r.sector_etf for r in sic_map}
        spy_ret, sector_ret = ASM.factor_returns(
            tables["etf_prices"], self.calendar, etf_by_sector, self.spy_ticker
        )
        series = ASM.security_series(tables["prices"], self.calendar)
        distributions = cash_distributions(tables["actions"])
        actions = corporate_actions(tables["actions"])
        prices = ASM.price_series_by_symbol(tables["prices"], self.calendar)

        market = ASM.market_data(self.calendar, spy_ret, sector_ret, self.observed_identities)
        out: list[tuple[Any, ExecutionFacts]] = []
        for unit in sorted(self.units, key=lambda u: (u.symbol, u.t)):
            try:
                record = self._produce(unit, market, series, sic_map, sic_obs)
            except SignalRefusal as exc:
                self.refusals.append((unit.symbol, unit.t, exc.code))
                continue
            out.append((record, self._facts(unit, prices, distributions, actions)))
        return out

    def _produce(self, unit: Unit, market: Any, series: dict, sic_map: list, sic_obs: dict) -> Any:
        close_t_iso = et_close_cutoff_iso(self.calendar.sessions[unit.t])
        self.lineage.resolve_permanent_id(unit.symbol, unit.t)  # refuses ambiguity, never picks
        cik = self.cik_by_symbol.get(unit.symbol)
        if cik is None:
            raise CandidateSourceRefused(f"no registered CIK for {unit.symbol}")
        sector = resolve_sector(sic_map, sic_obs.get(int(cik), []), close_t_iso)
        sector_etf(sic_map, sector.sector_id)  # refuses an unmapped sector
        checks = (self.eligibility_checks_by_symbol or {}).get(unit.symbol, [])
        security = ASM.security_data(series[unit.symbol], [sector], checks)
        request = ProductionRequest(
            PROGRAM_ID, unit.configuration_id, unit.side, unit.t, close_t_iso
        )
        return produce_decision(market, security, self.registry, self.lineage, request)

    def _facts(
        self, unit: Unit, prices: dict, distributions: dict, actions: dict
    ) -> ExecutionFacts:
        """The permitted t+1 facts. Nothing here may bear on close t."""
        t1 = unit.t + 1
        arrays = prices[unit.symbol]
        beyond_window = t1 >= len(self.calendar)
        session_t1 = None if beyond_window else self.calendar.sessions[t1]
        kind, identity = actions.get((unit.symbol, session_t1 or ""), (None, None))
        open_t1 = None if beyond_window else _finite(arrays["open"][t1])
        close_t = _finite(arrays["close"][unit.t])
        distribution = distributions.get((unit.symbol, session_t1 or ""), 0.0)

        # Constructibility is DERIVED, never assumed. The registered economic gap is
        # (open_t+1 + distribution) / close_t - 1 on the split-adjusted pair, so the adjusted open
        # is constructible exactly when both legs are present. A split needs no extra term: open
        # and close share the back-adjusted split basis, so a split between them is already
        # neutralised. A dividend needs the ACTIONS value, which is 0.0 when none is registered -
        # a genuine absence of distribution, not a missing input.
        constructible = open_t1 is not None and close_t is not None

        return ExecutionFacts(
            requested_execution_session=t1,
            actual_source_session=None if beyond_window else t1,
            official_open=open_t1,
            close_t=close_t,
            cash_distribution=distribution,
            official_open_source_identity=None
            if beyond_window
            else f"prices:{unit.symbol}:{session_t1}",
            corporate_action_identity=identity,
            corporate_action_kind=kind,
            adjusted_open_constructible=constructible,
            conservative_short_flag=unit.side == "SHORT",
        )


def _finite(value: float) -> float | None:
    import math

    return None if value is None or not math.isfinite(float(value)) else float(value)
