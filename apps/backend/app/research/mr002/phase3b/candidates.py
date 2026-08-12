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
from . import parquet as PQ
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
    # P9-shaped commitments. The adapter owns the table contract, so it decodes the governed bytes
    # itself rather than trusting a caller to have decoded them correctly.
    structural_manifest: dict | None = None
    reference_manifest: dict | None = None
    window_prefix: str = "validation"
    reference_prefix: str = "reference"

    refusals: list[tuple[str, int, str]] = field(default_factory=list)

    def candidates(self, payloads: dict[str, Any]) -> list[tuple[Any, ExecutionFacts]]:
        """Produce (SignalDecisionRecord, ExecutionFacts) for every unit that survives production.

        A governed refusal is recorded and the unit is dropped - it never becomes a candidate - so
        the enrichment census counts only records the producer actually emitted.
        """
        tables = self._decode(payloads)
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

    def _decode(self, payloads: dict[str, Any]) -> dict[str, Any]:
        """Decode the governed bytes against the precommitted structural manifests.

        Accepts already-decoded tables only when no manifest is supplied, which is the qualification
        path for suites that build tables directly; the governed run always supplies manifests, so
        the decode control is never skipped where it matters.
        """
        if self.structural_manifest is None:
            if "tables" not in payloads:
                raise CandidateSourceRefused("no structural manifest and no decoded tables")
            return payloads["tables"]
        tables = PQ.decode_all(payloads, self.structural_manifest, prefix=self.window_prefix)
        if self.reference_manifest is not None:
            tables.update(
                PQ.decode_all(payloads, self.reference_manifest, prefix=self.reference_prefix)
            )
        return tables

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


# --- production construction: the inputs the tests used to inject ------------------------------
# These close the fixture-injection gap. Each derives from a committed source column, and each
# refuses rather than defaulting, so a missing governed input stops the run instead of silently
# producing a smaller or differently-shaped world.

UNIVERSE_COLUMNS = (
    "universe_month",
    "ticker",
    "permaticker",
    "in_long_universe",
    "in_short_universe",
)
CROSSWALK_COLUMNS = (
    "permaticker",
    "ticker",
    "cik",
    "effective_from",
    "effective_to",
    "relationship_type",
)
ANCHOR_COLUMNS = (
    "ticker",
    "cik",
    "accession",
    "session_date",
    "availability_class",
    "is_amendment_origin",
    "acceptance_utc",
)


def _require(table: Any, name: str, columns: tuple[str, ...]) -> None:
    missing = sorted(set(columns) - set(table.column_names))
    if missing:
        raise CandidateSourceRefused(f"{name}: registered columns absent: {missing}")


def units_from_universe(
    universe: Any, calendar: RegisteredCalendar, *, configuration_id: str = "B"
) -> list[Unit]:
    """Enumerate the governed (symbol, decision-session) units from the registered universe.

    A universe row states membership for a reconstitution MONTH; a unit exists for every registered
    session in that month for which the security is on the stated side. Sides are enumerated
    separately because the frozen entry rule is side-specific.
    """
    _require(universe, "universe", UNIVERSE_COLUMNS)
    sessions_by_month: dict[str, list[int]] = {}
    for ordinal, session in enumerate(calendar.sessions):
        sessions_by_month.setdefault(session[:7], []).append(ordinal)

    units: list[Unit] = []
    for month, ticker, _perma, long_ok, short_ok in _rows(universe, UNIVERSE_COLUMNS[:5]):
        for ordinal in sessions_by_month.get(str(month)[:7], []):
            if long_ok:
                units.append(Unit(str(ticker), ordinal, "LONG", configuration_id))
            if short_ok:
                units.append(Unit(str(ticker), ordinal, "SHORT", configuration_id))
    if not units:
        raise CandidateSourceRefused("universe enumerated no units")
    return sorted(units, key=lambda u: (u.symbol, u.t, u.side))


@dataclass(frozen=True)
class CikResolution:
    """Resolved symbol->CIK map plus the symbols left UNRESOLVED because they conflict."""

    by_symbol: dict[str, int]
    ambiguous: tuple[str, ...]


def cik_by_symbol_from(crosswalk: Any) -> CikResolution:
    """Symbol -> CIK. A symbol resolving to more than one CIK is left UNRESOLVED, never arbitrated.

    Ambiguity is returned rather than silently dropped: a unit whose symbol is ambiguous will fail
    to resolve a CIK and refuse, which is the governed outcome, and the caller can count how many
    securities that affected instead of wondering where they went.
    """
    _require(crosswalk, "crosswalk", CROSSWALK_COLUMNS)
    seen: dict[str, set[int]] = {}
    for _perma, ticker, cik, _f, _t, _rel in _rows(crosswalk, CROSSWALK_COLUMNS):
        if cik is None:
            continue
        seen.setdefault(str(ticker), set()).add(int(cik))
    return CikResolution(
        by_symbol={t: next(iter(c)) for t, c in seen.items() if len(c) == 1},
        ambiguous=tuple(sorted(t for t, c in seen.items() if len(c) > 1)),
    )


def lineage_from(crosswalk: Any, calendar: RegisteredCalendar) -> PitIdentityRegistry:
    """Build the PIT identity registry from the registered crosswalk intervals.

    The permanent security id is the permaticker. An interval effective before the window opens is
    admitted at ordinal 0; conflicting successors at one ordinal are left for
    `resolve_permanent_id` to refuse, which is where ambiguity is already governed.
    """
    from ..spq1.security_identity import LineageRecord

    _require(crosswalk, "crosswalk", CROSSWALK_COLUMNS)
    import bisect

    lineage: dict[str, list[LineageRecord]] = {}
    for perma, ticker, _cik, eff_from, _eff_to, rel in _rows(crosswalk, CROSSWALK_COLUMNS):
        start = str(eff_from)[:10] if eff_from is not None else calendar.sessions[0]
        # First registered session on or after the interval start. An interval that opens before
        # the window is effective from ordinal 0; one that opens after the window closes has no
        # session and is dropped. RegisteredCalendar exposes no such lookup, so bisect the
        # ascending session list rather than assume a method that does not exist.
        ordinal = bisect.bisect_left(calendar.sessions, start)
        if ordinal >= len(calendar.sessions):
            continue
        lineage.setdefault(str(ticker), []).append(
            LineageRecord(
                predecessor_permanent_id=None,
                successor_permanent_id=f"PSEC-{int(perma)}",
                effective_session_ordinal=int(ordinal),
                corporate_action_type=str(rel or "ticker_change"),
                history_continuity_authorized=True,
                source_evidence_identity=f"crosswalk:{perma}:{ticker}",
            )
        )
    if not lineage:
        raise CandidateSourceRefused("crosswalk produced no lineage records")
    return PitIdentityRegistry(
        {t: tuple(sorted(r, key=lambda x: x.effective_session_ordinal)) for t, r in lineage.items()}
    )


def anchors_by_symbol(anchors: Any) -> tuple[dict[str, list], dict[str, str]]:
    """Anchors per symbol plus the availability timestamp per accession.

    Both are needed: the interval machinery consumes the anchor, and `evaluate_eligibility` PIT-
    selects on the availability timestamp, so an anchor with no timestamp must refuse rather than
    silently become always-available.
    """
    from .earnings_blackout import Anchor as EarningsAnchor

    _require(anchors, "anchors", ANCHOR_COLUMNS)
    by_symbol: dict[str, list] = {}
    availability: dict[str, str] = {}
    for ticker, cik, accession, session_date, cls, is_amd, accepted in _rows(
        anchors, ANCHOR_COLUMNS
    ):
        by_symbol.setdefault(str(ticker), []).append(
            EarningsAnchor(
                int(cik),
                str(ticker),
                str(accession),
                str(session_date)[:10],
                str(cls),
                bool(is_amd),
            )
        )
        if accepted is None:
            raise CandidateSourceRefused(f"anchor {accession} has no acceptance timestamp")
        availability[str(accession)] = str(accepted)
    return by_symbol, availability
