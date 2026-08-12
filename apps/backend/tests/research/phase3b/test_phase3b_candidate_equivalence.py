"""Producer equivalence for the `ProducerCandidateSource`, on terminal outcomes.

One world of synthetic facts is driven through the historical Phase 2B path (DuckDB + the
orchestrator's `run_unit` semantics) and through the new parquet-backed source, and the two are
compared on what actually matters: the canonical `SignalDecisionRecord` identity where production
succeeds, and the exact refusal code where it does not.

Non-vacuity gates the whole file. `test_00_*` proves the fixture can actually score and that every
intended case is genuinely exercised; if the world degenerated so that everything refused as too
young, those tests fail and no equivalence assertion below can be read as evidence.
"""

from __future__ import annotations

import io

import pytest

pa = pytest.importorskip("pyarrow")
duckdb = pytest.importorskip("duckdb")
import pyarrow.parquet as pq  # noqa: E402

from app.research.mr002.phase3b import candidates as CS  # noqa: E402
from app.research.mr002.spq1.adapters.price_adapter import load_price_series  # noqa: E402
from app.research.mr002.spq1.calendar import RegisteredCalendar  # noqa: E402
from app.research.mr002.spq1.identities import InputIdentityRegistry  # noqa: E402
from app.research.mr002.spq1.phase2b.cutoff import et_close_cutoff_iso  # noqa: E402
from app.research.mr002.spq1.phase2b.sic_sector import (  # noqa: E402
    load_sic_map,
    resolve_sector,
    sector_etf,
)
from app.research.mr002.spq1.producer import (  # noqa: E402
    MarketData,
    ProductionRequest,
    SecurityData,
    produce_decision,
)
from app.research.mr002.spq1.refusals import SignalRefusal  # noqa: E402
from app.research.mr002.spq1.returns import CellStatus, arithmetic_total_returns  # noqa: E402
from tests.research.phase3b import fixtures_producer as F  # noqa: E402

CAL = RegisteredCalendar(tuple(F.SESSIONS))
CLOSE_T = et_close_cutoff_iso(F.SESSIONS[F.SCORE_T])
SIC_OBS_ROWS = F.sic_observation_rows(CLOSE_T)
EMITTED, REFUSED = "EMITTED", "REFUSED"


# --------------------------------------------------------------------------- the two worlds
def _to_parquet(table):
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return pq.read_table(io.BytesIO(buf.getvalue()))


def _tables():
    prices = F.price_rows()
    etfs = F.etf_rows()
    return {
        "prices": _to_parquet(
            pa.table(
                {
                    "ticker": [r[0] for r in prices],
                    "date": [r[1] for r in prices],
                    "open": [r[4] - 0.25 for r in prices],
                    "high": [r[2] + 1.0 for r in prices],
                    "low": [r[2] - 1.0 for r in prices],
                    "close": [r[4] for r in prices],
                    "closeadj": [r[2] for r in prices],
                    "closeunadj": [r[3] for r in prices],
                    "volume": [r[5] for r in prices],
                }
            )
        ),
        "etf_prices": _to_parquet(
            pa.table(
                {
                    "ticker": [r[0] for r in etfs],
                    "date": [r[1] for r in etfs],
                    "adjclose": [r[2] for r in etfs],
                }
            )
        ),
        "sic_mapping": _to_parquet(
            pa.table(
                {
                    "sic_start": [r[0] for r in F.SIC_MAP_ROWS],
                    "sic_end": [r[1] for r in F.SIC_MAP_ROWS],
                    "effective_from": [r[2] for r in F.SIC_MAP_ROWS],
                    "research_sector": [r[3] for r in F.SIC_MAP_ROWS],
                    "sector_etf": [r[4] for r in F.SIC_MAP_ROWS],
                }
            )
        ),
        "sic_observations": _to_parquet(
            pa.table(
                {
                    "cik": [r[0] for r in SIC_OBS_ROWS],
                    "accepted_utc": [r[1] for r in SIC_OBS_ROWS],
                    "sic": [r[2] for r in SIC_OBS_ROWS],
                    "accession": [r[3] for r in SIC_OBS_ROWS],
                }
            )
        ),
        "actions": _to_parquet(
            pa.table(
                {
                    "date": [F.SESSIONS[F.SCORE_T + 1]],
                    "ticker": ["HEALTHY"],
                    "action": ["dividend"],
                    "value": [0.40],
                }
            )
        ),
    }


def _duckdb():
    con = duckdb.connect(":memory:")
    con.execute(
        'create table prices (ticker varchar, "date" varchar, closeadj double, '
        "closeunadj double, close double, open double, volume double)"
    )
    con.executemany(
        "insert into prices values (?, ?, ?, ?, ?, ?, ?)",
        [(t, d, ca, cu, c, c - 0.25, v) for (t, d, ca, cu, c, v) in F.price_rows()],
    )
    con.execute('create table etf_prices (ticker varchar, "date" varchar, adjclose double)')
    con.executemany("insert into etf_prices values (?, ?, ?)", F.etf_rows())
    return con


def _registry() -> InputIdentityRegistry:
    ids = dict(F.OBSERVED_IDENTITIES)
    ids["registered_exchange_calendar"] = CAL.identity
    ids.update(F.GOVERNING)
    return InputIdentityRegistry(ids)


def _reference_outcome(symbol: str, t: int, config: str = "B") -> tuple[str, str]:
    """The historical Phase 2B path, mirroring `orchestrator.run_unit`."""
    con = _duckdb()
    sic_map = load_sic_map(F.SIC_MAP_ROWS)
    sic_obs: dict[int, list] = {}
    for cik, accepted, sic, acc in SIC_OBS_ROWS:
        sic_obs.setdefault(int(cik), []).append((accepted, sic, acc))

    etf_by_sector = {r.research_sector: r.sector_etf for r in sic_map}
    spy_ret, sector_ret = _reference_factors(con, etf_by_sector)
    lineage = F.lineage_registry()
    try:
        lineage.resolve_permanent_id(symbol, t)
        close_t = et_close_cutoff_iso(CAL.sessions[t])
        sector = resolve_sector(sic_map, sic_obs.get(F.CIK_BY_SYMBOL[symbol], []), close_t)
        sector_etf(sic_map, sector.sector_id)
        series = load_price_series(con, symbol, CAL)
        close = series["closeadj"]
        import numpy as np

        present = np.isfinite(close)
        first = int(np.argmax(present)) if present.any() else 0
        status = [
            CellStatus.PRESENT
            if present[i]
            else (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)
            for i in range(len(CAL))
        ]
        market = MarketData(CAL, spy_ret, sector_ret, dict(F.OBSERVED_IDENTITIES))
        security = SecurityData(
            symbol,
            arithmetic_total_returns(close),
            status,
            series["closeunadj"],
            series["volume"],
            [sector],
            [],
        )
        record = produce_decision(
            market,
            security,
            _registry(),
            lineage,
            ProductionRequest(CS.PROGRAM_ID, config, "LONG", t, close_t),
        )
        return EMITTED, record.record_identity
    except SignalRefusal as exc:
        return REFUSED, exc.code


def _reference_factors(con, etf_by_sector):
    import numpy as np

    rows = con.execute('select ticker, "date", adjclose from etf_prices').fetchall()
    series: dict[str, dict[str, float]] = {}
    for tk, d, v in rows:
        series.setdefault(str(tk), {})[str(d)] = float(v)

    def aligned(ticker):
        by = series.get(ticker, {})
        return np.array([by.get(s, np.nan) for s in CAL.sessions], dtype=np.float64)

    spy = arithmetic_total_returns(aligned(F.SPY))
    sector = {s: arithmetic_total_returns(aligned(e)) for s, e in sorted(etf_by_sector.items())}
    return spy, sector


def _source(units, config="B"):
    return CS.ProducerCandidateSource(
        calendar=CAL,
        units=[CS.Unit(s, t, "LONG", config) for s, t in units],
        lineage=F.lineage_registry(),
        cik_by_symbol=F.CIK_BY_SYMBOL,
        registry=_registry(),
        observed_identities=dict(F.OBSERVED_IDENTITIES),
        spy_ticker=F.SPY,
        # COMPONENT qualification: injects units/identity and carries no anchors table, so it
        # opts out of the earnings controls explicitly. Production qualification is
        # test_phase3b_entrypoint_qualification.py.
        eligibility_checks_by_symbol={},
    )


def _new_outcome(symbol: str, t: int, config: str = "B") -> tuple[str, str]:
    src = _source([(symbol, t)], config)
    pairs = src.candidates({"tables": _tables()})
    if pairs:
        return EMITTED, pairs[0][0].record_identity
    assert src.refusals, f"{symbol}: neither a record nor a recorded refusal"
    return REFUSED, src.refusals[0][2]


# Each case names the EXACT expected outcome. Asserting only EMITTED/REFUSED once let the
# factor-gap case refuse for an unrelated reason (a same-timestamp SIC conflict) while still
# reporting green - it was measuring something other than what it claimed.
CASES = {
    "healthy_scores": ("HEALTHY", EMITTED, None),
    "too_young_security": ("YOUNGSEC", REFUSED, "INELIGIBLE:OLS_WINDOW_INSUFFICIENT"),
    "unexplained_price_hole": ("HOLESEC", REFUSED, "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE"),
    "ambiguous_identity_mapping": (
        "AMBIGSEC",
        REFUSED,
        "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
    ),
    "pit_sector_boundary_change": ("BOUNDSEC", EMITTED, None),
    "factor_series_gap": (
        "GAPFACTOR",
        REFUSED,
        "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
    ),
}


# --------------------------------------------------------------------------- 00: non-vacuity
def test_00_fixture_warmup_is_sufficient_to_score():
    from app.research.mr002.spq1.constants import WARMUP_PRICE_OBSERVATIONS

    assert F.SCORE_T >= WARMUP_PRICE_OBSERVATIONS
    assert len(F.SESSIONS) > F.SCORE_T + 1, "no t+1 session for the enrichment stage"


def test_00_at_least_one_candidate_reaches_the_scoring_path():
    """If nothing scores, every equivalence assertion below compares refusals and proves nothing."""
    kind, identity = _new_outcome("HEALTHY", F.SCORE_T)
    assert kind == EMITTED, f"nothing scored: {identity}"
    assert len(identity) == 64


def test_00_every_intended_case_is_actually_exercised():
    for name, (sym, expected_kind, expected_code) in CASES.items():
        kind, value = _new_outcome(sym, F.SCORE_T)
        assert kind == expected_kind, f"{name}: expected {expected_kind}, saw {kind} ({value})"
        if expected_code is not None:
            assert value == expected_code, (
                f"{name}: refused for the WRONG reason - expected {expected_code}, got {value}"
            )
    kinds = {k for k, _c in ((_new_outcome(s, F.SCORE_T)[0], c) for s, _e, c in CASES.values())}
    assert kinds == {EMITTED, REFUSED}, "a suite of one outcome proves little"


def test_00_a_suite_of_only_window_refusals_would_be_caught():
    """The harness must reject a degenerate world, not merely tolerate it."""
    codes = {_new_outcome(sym, F.SCORE_T)[1] for sym, exp, _c in CASES.values() if exp == REFUSED}
    assert len(codes) > 1, f"every refusal collapsed to one code: {codes}"
    assert not all("OLS_WINDOW_INSUFFICIENT" in c for c in codes)


# --------------------------------------------------------------------------- the seven cases
@pytest.mark.parametrize("name", sorted(CASES))
def test_terminal_outcome_matches_the_phase2b_path(name):
    """Compare the canonical record identity, or the exact refusal code. Not intermediates."""
    symbol, expected, expected_code = CASES[name]
    ref_kind, ref_value = _reference_outcome(symbol, F.SCORE_T)
    new_kind, new_value = _new_outcome(symbol, F.SCORE_T)
    assert new_kind == ref_kind == expected, f"{name}: {new_kind} vs {ref_kind}"
    assert new_value == ref_value, f"{name}: {new_value} != {ref_value}"
    if expected_code is not None:
        assert new_value == expected_code, f"{name}: right kind, wrong reason: {new_value}"


def test_pit_sector_boundary_observation_at_the_cutoff_is_visible_and_later_is_not():
    """`accepted_utc <= close_t` - the boundary observation governs, the later one is invisible."""
    sic_map = load_sic_map(F.SIC_MAP_ROWS)
    obs = [(a, s, acc) for cik, a, s, acc in SIC_OBS_ROWS if cik == F.CIK_BY_SYMBOL["BOUNDSEC"]]
    sector = resolve_sector(sic_map, obs, CLOSE_T)
    assert sector.availability_timestamp == CLOSE_T
    assert "acc-bound-at-cutoff" in sector.source_evidence_identity
    assert "acc-bound-after" not in sector.source_evidence_identity


def test_eligibility_transition_at_the_boundary_session_matches_both_paths():
    """An eligibility rule that flips exactly at t must flip identically on both paths."""
    from app.research.mr002.spq1.eligibility import ExclusionCheck

    def check(excludes: bool) -> ExclusionCheck:
        return ExclusionCheck(
            rule_id="BOUNDARY-RULE",
            precedence_category="liquidity_or_price",
            excludes=excludes,
            observed_value="boundary",
            threshold="boundary",
            source_identity="fixture",
            availability_timestamp="2019-10-04T12:00:00Z",
            evidence_present=True,
        )

    for excludes in (False, True):
        src = _source([("HEALTHY", F.SCORE_T)])
        src.eligibility_checks_by_symbol = {"HEALTHY": [check(excludes)]}
        pairs = src.candidates({"tables": _tables()})
        assert pairs, f"excludes={excludes}: no record produced"
        status = pairs[0][0].decision_eligibility_status
        assert (status != "ELIGIBLE") == excludes, f"excludes={excludes} gave {status}"


def test_configurations_differ_only_by_the_frozen_z_entry_binding():
    """A/B/C are identical at production; the frozen Z_ENTRY mapping differentiates them later."""
    records = {}
    for config in ("A", "B", "C"):
        src = _source([("HEALTHY", F.SCORE_T)], config)
        pairs = src.candidates({"tables": _tables()})
        assert pairs, f"config {config} produced nothing"
        records[config] = pairs[0][0]

    base = records["B"].canonical()
    for config in ("A", "C"):
        other = records[config].canonical()
        differing = {k for k in base if base[k] != other[k]}
        assert differing == {"configuration_id", "candidate_id"}, differing

    # The differentiation lives in the BOUND EVALUATOR module, not in the producer. Read it from
    # the file rather than restating it, so this test tracks the in-image mapping.
    import os
    import re

    module = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "..",
        "docs",
        "review",
        "mr002",
        "evaluator",
        "mr002_valoos_portfolio_identity.py",
    )
    with open(os.path.abspath(module), encoding="utf-8") as fh:
        src = fh.read()
    literal = re.search(r"^Z_ENTRY\s*=\s*\{([^}]*)\}", src, re.M)
    assert literal, "Z_ENTRY literal not found in the bound evaluator module"
    mapping = {k: float(v) for k, v in re.findall(r'"([ABC])"\s*:\s*([0-9.]+)', literal.group(1))}
    assert mapping == {"A": 1.75, "B": 2.00, "C": 2.25}


# --------------------------------------------------------------------------- the close-t/t+1 seam
def test_producer_inputs_carry_no_t_plus_one_fact():
    """`SecurityData`/`MarketData` are calendar-wide, but the producer may consult only <= t.

    The structural guarantee is that no t+1 EXECUTION fact - open, distribution, corporate action -
    is reachable from the producer's inputs at all.
    """
    src = _source([("HEALTHY", F.SCORE_T)])
    pairs = src.candidates({"tables": _tables()})
    record = pairs[0][0]
    fields = record.canonical()
    for forbidden in ("official_open", "cash_distribution", "corporate_action", "gap", "open"):
        assert not any(forbidden in k for k in fields), f"{forbidden} reached the decision record"


def test_t_plus_one_facts_exist_only_on_the_enrichment_side():
    src = _source([("HEALTHY", F.SCORE_T)])
    (record, facts) = src.candidates({"tables": _tables()})[0]
    assert facts.requested_execution_session == record.decision_session + 1
    assert facts.official_open is not None
    assert facts.cash_distribution == pytest.approx(0.40)
    assert not hasattr(record, "official_open")
    assert not hasattr(record, "cash_distribution")


def test_the_distribution_is_read_from_the_t_plus_one_session_not_t():
    """A distribution on the DECISION session must not leak into the t+1 gap adjustment."""
    tables = _tables()
    src = _source([("HEALTHY", F.SCORE_T)])
    facts = src.candidates({"tables": tables})[0][1]
    assert facts.cash_distribution == pytest.approx(0.40)

    shifted = dict(tables)
    shifted["actions"] = _to_parquet(
        pa.table(
            {
                "date": [F.SESSIONS[F.SCORE_T]],  # the decision session, not t+1
                "ticker": ["HEALTHY"],
                "action": ["dividend"],
                "value": [0.40],
            }
        )
    )
    src2 = _source([("HEALTHY", F.SCORE_T)])
    facts2 = src2.candidates({"tables": shifted})[0][1]
    assert facts2.cash_distribution == 0.0, "a close-t distribution leaked into the t+1 adjustment"
