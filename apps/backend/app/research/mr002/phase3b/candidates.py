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
from .enrichment import _CORPORATE_ACTION_KINDS as _ECONOMIC_KINDS
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
    """A GLOBAL bridge failure: the run must not proceed.

    Reserved for the frozen global-integrity conditions - schema corruption, a registered column
    absent, an unloadable or unestablishable governed source, an empty enumeration. A condition
    that belongs to ONE unit is `CandidateRefused` below, not this.
    """


# --- the frozen ACTIONS semantic model ---------------------------------------------------------
# MR002_Phase3B_SemanticReconciliationMatrix_v1.3 (865064f5...). Six classes, three channels, one
# consuming channel per kind. The classes exist because the previous design answered "what kind is
# on this (ticker, session)?" once and used that single answer as the economic scalar, the published
# audit identity, the conflict subject AND the run's life-or-death condition. Three governed
# openings were spent on kinds that had no bearing on the economics they aborted.

# Channel 1. The authority is `enrichment._CORPORATE_ACTION_KINDS` itself, imported rather than
# restated: the set whose membership gates STOP_CORPORATE_ACTION must BE the set this classifies as
# economic, or the two can disagree.
ECONOMICALLY_ADJUDICATED: frozenset[str] = frozenset(_ECONOMIC_KINDS)
# Channel 2. Exclusive: delisted no longer occupies the economic scalar. A kind cannot hold two
# channels, and leaving it in both made acquisitionby+delisted a false composition conflict on 77
# development sessions while consuming one event twice.
TERMINAL_DELISTING: frozenset[str] = frozenset({"delisted"})
# Consumed UPSTREAM, before a candidate exists (crosswalk -> identity_adapter -> PitIdentityRegistry).
# Not audit-visible here: publishing it would double-consume one identity event.
UPSTREAM_IDENTITY_LINEAGE: frozenset[str] = frozenset({"tickerchangefrom", "tickerchangeto"})
# Channel 3 only. Recognized, auditable, identity-preserving, and OUT of the economic conflict guard.
# "Inert" cannot mean "no economic effect but still causes economic conflict".
EXPLICITLY_INERT: frozenset[str] = frozenset({"bankruptcy", "regulatorychange", "spunofffrom"})
# Channel 3 only, adjudicated separately from EXPLICITLY_INERT so the v1.1 membership of that class
# is not retroactively rewritten. LabelAdjudication v2.0 (5647549e...): informational issuer/security
# linkage; no t+1, economic or identity consequence; contributes no identity precedence of its own.
# Conditional on the vendor premise that relation.value is never populated - a populated value on a
# relevant session reverts the label to KNOWN_UNADJUDICATED for that unit (RELATION-VALUE-PREMISE).
KNOWN_INFORMATIONAL_LINKAGE: frozenset[str] = frozenset({"relation"})
# Observed in the governed feed, unadjudicated in Phase 3B. NEVER aliased: bankruptcyliquidation is
# not bankruptcy. Name similarity is not adjudication. (`relation` and `spinoff` left this set under
# LabelAdjudication v2.0; `spinoff` is now economic via the enrichment set, `relation` above.)
KNOWN_UNADJUDICATED: frozenset[str] = frozenset({"bankruptcyliquidation", "listed"})

REGISTERED_ACTION_VOCABULARY: frozenset[str] = (
    ECONOMICALLY_ADJUDICATED
    | TERMINAL_DELISTING
    | UPSTREAM_IDENTITY_LINEAGE
    | EXPLICITLY_INERT
    | KNOWN_INFORMATIONAL_LINKAGE
    | KNOWN_UNADJUDICATED
)

# --- the bridge refusal namespace --------------------------------------------------------------
# MR002_Phase3B_UnitRefusalGovernance_v1.0 (d03ae667...). Deliberately NOT SignalRefusal codes:
# `spq1/refusals.py` is a bound R-PROD producer module and cannot be extended without changing the
# producer contract. These are a different semantic class and live in the layer that owns them.
REFUSED_ACTION_COMPOSITION = "CANDIDATE_REFUSED:ACTION_COMPOSITION_UNRESOLVED"
REFUSED_ACTION_KIND = "CANDIDATE_REFUSED:ACTION_KIND_UNADJUDICATED"
REFUSED_IDENTITY = "CANDIDATE_REFUSED:IDENTITY_UNRESOLVED"

BRIDGE_REFUSAL_CODES = (REFUSED_ACTION_COMPOSITION, REFUSED_ACTION_KIND, REFUSED_IDENTITY)

# The discriminator on REFUSED_ACTION_KIND. It exists because the frozen gates treat these two
# irreconcilably - an unregistered label fails at incidence > 0, a known-unadjudicated one is gated
# at 1% / 5 symbols - so a single undifferentiated code makes the gates uncomputable. It separates
# WHY the unit was refused (semantics unavailable) from WHY they are unavailable.
VOCAB_KNOWN_UNADJUDICATED = "KNOWN_UNADJUDICATED"
VOCAB_UNKNOWN = "UNKNOWN_VOCABULARY"


class CandidateRefused(Exception):
    """A UNIT whose semantics cannot be established. Independent units continue.

    Still fail-closed - it just puts the refusal at the scope of the uncertainty. The whole-run
    alternative is what let a conflict on a ticker no candidate ever reached abort a research run.
    """

    def __init__(self, code: str, detail: str = "", vocabulary_state: str | None = None) -> None:
        if code not in BRIDGE_REFUSAL_CODES:
            raise AssertionError(f"unregistered bridge refusal code: {code}")
        self.code = code
        self.vocabulary_state = vocabulary_state
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def classify_action_kind(kind: str) -> str:
    """The closed six-class classifier. An unregistered label is UNKNOWN, never guessed at."""
    if kind in ECONOMICALLY_ADJUDICATED:
        return "ECONOMICALLY_ADJUDICATED"
    if kind in TERMINAL_DELISTING:
        return "TERMINAL_DELISTING"
    if kind in UPSTREAM_IDENTITY_LINEAGE:
        return "UPSTREAM_IDENTITY_LINEAGE"
    if kind in EXPLICITLY_INERT:
        return "EXPLICITLY_INERT"
    if kind in KNOWN_INFORMATIONAL_LINKAGE:
        return "KNOWN_INFORMATIONAL_LINKAGE"
    if kind in KNOWN_UNADJUDICATED:
        return "KNOWN_UNADJUDICATED"
    return "UNKNOWN_VOCABULARY"


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

    `dividend` ONLY - frozen. The owner correction 2026-08-17 (LabelAdjudication Corrigendum v1.0)
    ruled that the spinoffdividend dollar value is NOT AUTHORIZED to enter the registered gap's
    distribution term: whether that value is a cash distribution actually received by the holder,
    or a valuation/reference amount describing distributed stock, is a SEPARATE open
    economic-semantics finding (SPINOFF-GAP-SEMANTICS). The composite event recognition in
    `_resolve_actions` is unaffected.
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


def relation_value_keys(table: Any) -> frozenset[tuple[str, str]]:
    """Every (ticker, session) where a `relation` row carries a POPULATED value.

    RELATION-VALUE-PREMISE (Matrix v1.3): the relation adjudication is conditional on the vendor
    premise that relation.value is never populated (0/98 in the bounded evidence). A populated
    value is outside that premise, so the unit it is relevant to must refuse rather than have the
    row silently reinterpreted as informational.
    """
    cols = ("date", "ticker", "action", "value")
    missing = sorted(set(cols) - set(table.column_names))
    if missing:
        raise CandidateSourceRefused(f"actions: registered columns absent: {missing}")
    return frozenset(
        (str(ticker), str(date))
        for date, ticker, action, value in _rows(table, cols)
        if str(action) == "relation" and value is not None
    )


def actions_by_key(table: Any) -> dict[tuple[str, str], tuple[str, ...]]:
    """(ticker, session) -> every kind present on it, sorted. NO judgement is made here.

    This function used to collapse each key to one scalar and refuse the WHOLE RUN when a second
    row carried a different kind - before asking whether either kind had any execution meaning, and
    over the entire table rather than over sessions a candidate actually reaches. That is what spent
    the third governed opening, on ('BKR','2019-10-20'), a ticker whose universe membership was
    never established. Classification and refusal are now per unit, at `_facts()` time.
    """
    out: dict[tuple[str, str], set[str]] = {}
    for date, ticker, action in _rows(table, ("date", "ticker", "action")):
        out.setdefault((str(ticker), str(date)), set()).add(str(action))
    return {key: tuple(sorted(kinds)) for key, kinds in out.items()}


def delistings_by_ticker(table: Any) -> dict[str, str]:
    """ticker -> EARLIEST registered delisting session.

    Earliest, because the frozen predicate is AT OR BEFORE session(t+1) (`dataset.py:303`, ``ad <=
    d``), not equality with t+1: once a security is delisted it stays delisted, so the first such
    session is the one that decides the fact for every later execution session.
    """
    out: dict[str, str] = {}
    for date, ticker, action in _rows(table, ("date", "ticker", "action")):
        if str(action) not in TERMINAL_DELISTING:
            continue
        key, session = str(ticker), str(date)
        if key not in out or session < out[key]:
            out[key] = session
    return out


@dataclass
class ProducerCandidateSource:
    """Bridges decoded tables to the frozen producer, one unit at a time."""

    calendar: RegisteredCalendar
    registry: InputIdentityRegistry
    # None means CONSTRUCT from the governed tables. Component qualification may still supply
    # these directly; production qualification must not, and the entry point never does.
    units: list[Unit] | None = None
    lineage: PitIdentityRegistry | None = None
    cik_by_symbol: dict[str, int] | None = None
    observed_identities: dict[str, str] | None = None
    spy_ticker: str = "SPY"
    eligibility_checks_by_symbol: dict[str, list[ExclusionCheck]] | None = None
    # P9-shaped commitments. The adapter owns the table contract, so it decodes the governed bytes
    # itself rather than trusting a caller to have decoded them correctly.
    structural_manifest: dict | None = None
    reference_manifest: dict | None = None
    window_prefix: str = "validation"
    reference_prefix: str = "reference"

    # (symbol, t, code, vocabulary_state). Producer refusals carry a SignalRefusal code and a None
    # state; bridge refusals carry a CANDIDATE_REFUSED:* code. The two are counted separately in the
    # census, because "how much of the population did the producer drop" and "how much did the
    # bridge drop for want of semantics" are different questions.
    refusals: list[tuple[str, int, str, str | None]] = field(default_factory=list)
    units_accepted: int = 0
    # Every action kind on a session this run actually INSPECTED. Evidence only - it can never
    # abort a run. Note the limit this carries: a kind appearing exclusively on tickers or sessions
    # no unit touches is never seen here. That is the direct cost of unit scope and the correct
    # trade, but it means this evidences the inspected vocabulary, NOT the partition's.
    observed_action_kinds: set[str] = field(default_factory=set)
    ambiguous_symbols: tuple[str, ...] = ()
    tables_opened: tuple[str, ...] = ()

    def candidates(self, payloads: dict[str, Any]) -> list[tuple[Any, ExecutionFacts]]:
        """Produce (SignalDecisionRecord, ExecutionFacts) for every unit that survives production.

        A governed refusal is recorded and the unit is dropped - it never becomes a candidate - so
        the enrichment census counts only records the producer actually emitted.
        """
        tables = self._decode(payloads)
        self._construct_world(tables)
        sic_map = sic_map_from(tables["sic_mapping"])
        sic_obs = sic_observations_by_cik(tables["sic_observations"])
        etf_by_sector = {r.research_sector: r.sector_etf for r in sic_map}
        spy_ret, sector_ret = ASM.factor_returns(
            tables["etf_prices"], self.calendar, etf_by_sector, self.spy_ticker
        )
        series = ASM.security_series(tables["prices"], self.calendar)
        distributions = cash_distributions(tables["actions"])
        actions = actions_by_key(tables["actions"])
        delistings = delistings_by_ticker(tables["actions"])
        self._relation_valued = relation_value_keys(tables["actions"])
        prices = ASM.price_series_by_symbol(tables["prices"], self.calendar)

        market = ASM.market_data(
            self.calendar, spy_ret, sector_ret, dict(self.observed_identities or {})
        )
        out: list[tuple[Any, ExecutionFacts]] = []
        for unit in sorted(self.units, key=lambda u: (u.symbol, u.t)):
            # The catch encloses `_facts()` as well as `_produce()`. It previously stopped short of
            # it, so a per-unit semantic condition raised during fact assembly escaped as a
            # whole-run abort. Widening it is not enough - the boundary had to MOVE.
            try:
                record = self._produce(unit, market, series, sic_map, sic_obs)
                facts = self._facts(unit, prices, distributions, actions, delistings)
            except SignalRefusal as exc:
                self.refusals.append((unit.symbol, unit.t, exc.code, None))
                continue
            except CandidateRefused as exc:
                self.refusals.append((unit.symbol, unit.t, exc.code, exc.vocabulary_state))
                continue
            out.append((record, facts))
        self.units_accepted = len(out)
        return out

    def _construct_world(self, tables: dict[str, Any]) -> None:
        """Build units, identity and earnings controls from the governed tables.

        Anything already supplied is left alone - that is component qualification. Production
        supplies none of it, so the same code path that will run validation builds the world here.
        """
        if self.units is None:
            self.units = units_from_universe(tables["universe"], self.calendar)
        if self.cik_by_symbol is None:
            resolved = cik_by_symbol_from(tables["crosswalk"])
            self.cik_by_symbol = resolved.by_symbol
            self.ambiguous_symbols = resolved.ambiguous
        if self.lineage is None:
            self.lineage = lineage_from(tables["crosswalk"], self.calendar)
        if self.eligibility_checks_by_symbol is None:
            # REQUIRED, never optional. A missing anchors table must refuse rather than silently
            # disable the two frozen earnings controls - that silent-disable is the exact defect
            # Phase 2B shipped.
            if "anchors" not in tables:
                raise CandidateSourceRefused(
                    "anchors table absent: the frozen earnings controls cannot be applied"
                )
            self._anchors, self._anchor_availability = anchors_by_symbol(tables["anchors"])
        self.tables_opened = tuple(sorted(tables))

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
            # A per-symbol condition, refused at UNIT scope (frozen separately, not generalised
            # from the action-kind rulings). `cik_by_symbol_from` deliberately leaves an ambiguous
            # symbol unarbitrated so the caller can COUNT the affected securities - the intent was
            # always per-unit; only the implementation aborted the run.
            raise CandidateRefused(REFUSED_IDENTITY, f"no registered CIK for {unit.symbol}")
        sector = resolve_sector(sic_map, sic_obs.get(int(cik), []), close_t_iso)
        sector_etf(sic_map, sector.sector_id)  # refuses an unmapped sector
        checks = self._eligibility_checks(unit)
        security = ASM.security_data(series[unit.symbol], [sector], checks)
        request = ProductionRequest(
            PROGRAM_ID, unit.configuration_id, unit.side, unit.t, close_t_iso
        )
        return produce_decision(market, security, self.registry, self.lineage, request)

    def _eligibility_checks(self, unit: Unit) -> list:
        """The frozen earnings controls, constructed per unit from the governed anchors.

        Injected checks win when supplied, which is component qualification only; production
        supplies none, so the same code path that will run validation builds them here.
        """
        if self.eligibility_checks_by_symbol is not None:
            return self.eligibility_checks_by_symbol.get(unit.symbol, [])
        anchors = getattr(self, "_anchors", {}).get(unit.symbol, [])
        if not anchors:
            return []
        from .earnings_blackout import Calendar as BlackoutCalendar
        from .earnings_blackout import earnings_exclusion_checks

        return earnings_exclusion_checks(
            anchors,
            BlackoutCalendar(self.calendar.sessions),
            unit.t,
            getattr(self, "_anchor_availability", {}),
        )

    def _resolve_actions(
        self, unit: Unit, session_t1: str | None, kinds: tuple[str, ...]
    ) -> tuple[str | None, str | None]:
        """Route the kinds on this unit's relevant session into their exclusive channels.

        Returns (economic scalar kind, audit identity). Refuses the UNIT - never the run - when the
        semantics cannot be established. A row relevant to no unit is never seen here at all, which
        is the whole point of unit scope.
        """
        self.observed_action_kinds.update(kinds)
        if not kinds:
            return None, None

        by_class: dict[str, list[str]] = {}
        for kind in kinds:
            by_class.setdefault(classify_action_kind(kind), []).append(kind)

        if by_class.get("UNKNOWN_VOCABULARY"):
            raise CandidateRefused(
                REFUSED_ACTION_KIND,
                f"unregistered action kind(s) {by_class['UNKNOWN_VOCABULARY']} on "
                f"({unit.symbol}, {session_t1})",
                vocabulary_state=VOCAB_UNKNOWN,
            )
        # RELATION-VALUE-PREMISE (Matrix v1.3): a populated relation.value is outside the
        # adjudicated premise, so the label reverts to KNOWN_UNADJUDICATED for THIS unit - fail
        # closed, never silent reinterpretation.
        if by_class.get("KNOWN_INFORMATIONAL_LINKAGE") and (
            (unit.symbol, session_t1) in getattr(self, "_relation_valued", frozenset())
        ):
            raise CandidateRefused(
                REFUSED_ACTION_KIND,
                f"relation row with a populated value on ({unit.symbol}, {session_t1}) is outside "
                f"the adjudicated premise",
                vocabulary_state=VOCAB_KNOWN_UNADJUDICATED,
            )
        if by_class.get("KNOWN_UNADJUDICATED"):
            raise CandidateRefused(
                REFUSED_ACTION_KIND,
                f"unadjudicated action kind(s) {by_class['KNOWN_UNADJUDICATED']} on "
                f"({unit.symbol}, {session_t1})",
                vocabulary_state=VOCAB_KNOWN_UNADJUDICATED,
            )

        economic = by_class.get("ECONOMICALLY_ADJUDICATED", [])
        # SPINOFF-COMPOSITE (Matrix v1.3): the ONLY authorized composition. spinoff and
        # spinoffdividend on one relevant session are complementary records of ONE event - the
        # structural kind and its dollar denomination - and normalize to a single economic
        # consumption BEFORE the uniqueness guard. A value component without its structural event
        # is unresolved composition, never observed in the bounded evidence, and refuses.
        if "spinoffdividend" in economic:
            if "spinoff" in economic:
                economic = [k for k in economic if k != "spinoffdividend"]
            else:
                raise CandidateRefused(
                    REFUSED_ACTION_COMPOSITION,
                    f"spinoffdividend without its parent-side spinoff structural event on "
                    f"({unit.symbol}, {session_t1})",
                    vocabulary_state=None,
                )
        if len(economic) > 1:
            # No further composition semantics are defined and none is invented - no ordering, no
            # combined return. spinoff beside a DIFFERENT economic kind still refuses here.
            raise CandidateRefused(
                REFUSED_ACTION_COMPOSITION,
                f"differing economically adjudicated kinds {economic} on "
                f"({unit.symbol}, {session_t1})",
                vocabulary_state=None,
            )

        def identity_for(kind: str) -> str:
            return f"actions:{unit.symbol}:{session_t1}:{kind}"

        # Channel 3, the published audit identity. Precedence follows `_classify`'s own ordering -
        # delisting outranks corporate action - so the identity names the action that actually drove
        # the disposition rather than one that did not. Upstream lineage is never published here.
        # AUDIT-IDENTITY-PRECEDENCE extension (Matrix v1.3): informational linkage contributes no
        # precedence of its own, so it publishes only when it is the sole class present.
        delisting = by_class.get("TERMINAL_DELISTING", [])
        inert = by_class.get("EXPLICITLY_INERT", [])
        linkage = by_class.get("KNOWN_INFORMATIONAL_LINKAGE", [])
        identity = None
        if delisting:
            identity = identity_for(delisting[0])
        elif economic:
            identity = identity_for(economic[0])
        elif inert:
            identity = identity_for(sorted(inert)[0])
        elif linkage:
            identity = identity_for(sorted(linkage)[0])
        return (economic[0] if economic else None), identity

    def _facts(
        self, unit: Unit, prices: dict, distributions: dict, actions: dict, delistings: dict
    ) -> ExecutionFacts:
        """The permitted t+1 facts. Nothing here may bear on close t."""
        t1 = unit.t + 1
        arrays = prices[unit.symbol]
        beyond_window = t1 >= len(self.calendar)
        session_t1 = None if beyond_window else self.calendar.sessions[t1]
        kind, identity = self._resolve_actions(
            unit, session_t1, actions.get((unit.symbol, session_t1 or ""), ())
        )
        # Channel 2, at-or-before session(t+1). Beyond the window there is no t+1 session, so the
        # predicate cannot be evaluated and the fact is not asserted - a delisting is never inferred
        # from the absence of a session.
        delisted_on = delistings.get(unit.symbol)
        delisted = bool(session_t1 and delisted_on and delisted_on <= session_t1)
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
            delisted_at_or_before_t_plus_1=delisted,
            conservative_short_flag=unit.side == "SHORT",
        )

    # --- the mandatory unit-refusal census ------------------------------------------------------
    def refusal_census(self) -> dict[str, Any]:
        """Publish what unit-scope refusal costs, and gate it.

        This is a GOVERNED DELIVERABLE, not diagnostics. Once refusal moves from run scope to unit
        scope, an unpublished refusal is a silent population change: the run can report PASS while
        discarding a material share of candidates, which trades a visible abort for an invisible
        one. The reconciliation identity below is what makes silent shrinkage impossible.
        """
        enumerated = len(self.units or ())
        producer = [r for r in self.refusals if r[2] not in BRIDGE_REFUSAL_CODES]
        bridge = [r for r in self.refusals if r[2] in BRIDGE_REFUSAL_CODES]
        # The population the BRIDGE is responsible for. Publishing `units_enumerated` alongside is
        # what stops a reader seeing "1.2% refused" without knowing how much of the original
        # population had already disappeared upstream.
        eligible = enumerated - len(producer)

        by_code: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        symbols_by_reason: dict[str, set[str]] = {}
        for symbol, _t, code, state in bridge:
            by_code[code] = by_code.get(code, 0) + 1
            reason = f"{code}|{state}" if state else code
            by_reason[reason] = by_reason.get(reason, 0) + 1
            symbols_by_reason.setdefault(reason, set()).add(symbol)

        unregistered = sorted(self.observed_action_kinds - REGISTERED_ACTION_VOCABULARY)
        gates = self._evaluate_gates(eligible, by_reason, symbols_by_reason, unregistered)
        # Checked BEFORE the census is assembled, not read back out of it: the identity is the
        # control, and a control that reads its own output is the shape of check this package has
        # already been burned by once.
        balances = enumerated == len(producer) + len(bridge) + self.units_accepted
        if not balances:
            raise CandidateSourceRefused(
                f"unit reconciliation does not balance: {enumerated} != {len(producer)} + "
                f"{len(bridge)} + {self.units_accepted}"
            )
        census: dict[str, Any] = {
            "units_enumerated": enumerated,
            "units_producer_refused": len(producer),
            "eligible_candidate_units": eligible,
            "units_accepted": self.units_accepted,
            "units_bridge_refused": len(bridge),
            "units_bridge_refused_by_code": dict(sorted(by_code.items())),
            "units_bridge_refused_by_code_and_vocabulary_state": dict(sorted(by_reason.items())),
            "unique_symbols_affected_by_code": {
                r: len(s) for r, s in sorted(symbols_by_reason.items())
            },
            "fraction_refused_overall": (len(bridge) / eligible) if eligible else 0.0,
            "fraction_refused_by_reason": {
                r: (n / eligible if eligible else 0.0) for r, n in sorted(by_reason.items())
            },
            "observed_action_vocabulary": sorted(self.observed_action_kinds),
            "unregistered_action_kinds_observed": unregistered,
            "materiality_gate_results_by_reason": gates,
            "any_materiality_gate_breached": any(g["breached"] for g in gates.values()),
            "reconciliation": {
                "identity": (
                    "units_enumerated == units_producer_refused + units_bridge_refused + "
                    "units_accepted"
                ),
                "balances": balances,
            },
            "vocabulary_coverage_limit": (
                "the bridge inspects only rows relevant to a unit, so a kind appearing exclusively "
                "on tickers or sessions no unit reaches is NOT counted here. This evidences the "
                "INSPECTED vocabulary, never the partition's full vocabulary."
            ),
        }
        return census

    @staticmethod
    def _evaluate_gates(
        eligible: int,
        by_reason: dict[str, int],
        symbols_by_reason: dict[str, set[str]],
        unregistered: list[str],
    ) -> dict[str, dict[str, Any]]:
        """The frozen per-reason materiality gates.

        QUALIFICATION gates, not economic tolerances: they bound how much of the analyzable
        population may vanish into semantic uncertainty before the result stops being evidence. Each
        reason breaches on the DISJUNCTION of its two conditions.
        """
        out: dict[str, dict[str, Any]] = {}
        for reason, (max_fraction, max_symbols) in MATERIALITY_GATES.items():
            units = by_reason.get(reason, 0)
            symbols = len(symbols_by_reason.get(reason, ()))
            fraction = (units / eligible) if eligible else 0.0
            out[reason] = {
                "units": units,
                "unique_symbols": symbols,
                "fraction": fraction,
                "max_fraction": max_fraction,
                "max_unique_symbols": max_symbols,
                "breached": fraction > max_fraction or symbols > max_symbols,
            }
        # Unknown vocabulary is not ordinary attrition: a single unregistered label means the
        # vocabulary the whole classifier is keyed on is not closed. Provable on first occurrence -
        # but proving it never stops processing, because "isolated or systemic?" is the question
        # worth answering once the result is already inadmissible.
        unknown_units = by_reason.get(UNKNOWN_VOCABULARY_REASON, 0)
        out[UNKNOWN_VOCABULARY_REASON] = {
            "units": unknown_units,
            "unique_symbols": len(symbols_by_reason.get(UNKNOWN_VOCABULARY_REASON, ())),
            "unregistered_kinds_observed": unregistered,
            "max_incidence": 0,
            "breached": unknown_units > 0 or bool(unregistered),
        }
        return out


UNKNOWN_VOCABULARY_REASON = f"{REFUSED_ACTION_KIND}|{VOCAB_UNKNOWN}"

# MR002_Phase3B_UnitRefusalGovernance_v1.0: (max fraction of eligible units, max unique symbols).
# Identity is allowed a larger ceiling because unresolved crosswalk identity is an already-recognised
# property of the crosswalk - and it is still a ceiling.
MATERIALITY_GATES: dict[str, tuple[float, int]] = {
    REFUSED_ACTION_COMPOSITION: (0.01, 5),
    f"{REFUSED_ACTION_KIND}|{VOCAB_KNOWN_UNADJUDICATED}": (0.01, 5),
    REFUSED_IDENTITY: (0.02, 10),
}


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
