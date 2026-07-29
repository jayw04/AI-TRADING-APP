"""PERMATICKER_EFFECTIVE_INTERVAL_V1 — the identity contract, and every way it must fail closed.

The cases here are the ones that were established empirically against real vendor data on 2026-07-29
and are pinned so they cannot regress:

  * BNY←BK, FISV←FI, MRSH←MMC and KEEL←BITF are intra-lineage renames whose predecessor key the vendor
    RETIRED on retro-map. An earlier draft refused all four — an absent predecessor row is the ordinary
    case, not evidence of a lineage break, and treating it as one silently drops large-cap constituents.
  * ECHO is a genuine symbol reuse: metadata claims a continuous lifetime from 2008 while the price
    series holds a multi-year hole, because the corpus predates the rename.

Fixtures are synthetic and self-contained; the vendor-derived shapes are reproduced as named patterns
rather than by reading live data, so the suite pins BEHAVIOUR and never depends on what the vendor
happens to serve today.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from app.validation.security_lineage import (
    LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
    LineageRefusal,
    SecurityIdentityUnavailable,
    SessionLineageFilter,
    assess_bridge_risk,
    assess_universe,
    require_permanent_identifier,
    resolve_lineage,
)

# 60 consecutive weekday sessions — comfortably longer than the 20-session gap thresholds.
START = date(2026, 1, 5)


def _sessions(n: int = 60) -> list[date]:
    out, d = [], START
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


SESSIONS = _sessions()
SESSION = SESSIONS[-1]
LOOKBACK = SESSIONS[0]


class Store:
    """A minimal governed store: `sep`, `tickers`, `actions` with the columns the resolver reads."""

    def __init__(self, path):
        self.con = duckdb.connect(str(path))
        self.con.execute(
            "CREATE TABLE sep (ticker VARCHAR, date DATE, closeadj DOUBLE)")
        self.con.execute(
            "CREATE TABLE tickers (ticker VARCHAR, permaticker VARCHAR, firstpricedate DATE, "
            "lastpricedate DATE)")
        self.con.execute(
            "CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)")

    def security(self, ticker, perma, *, first=None, last=None, marks=None):
        self.con.execute("INSERT INTO tickers VALUES (?, ?, ?, ?)",
                         [ticker, perma, first or SESSIONS[0], last or SESSION])
        for d in (SESSIONS if marks is None else marks):
            self.con.execute("INSERT INTO sep VALUES (?, ?, 10.0)", [ticker, d])
        return self

    def rename(self, ticker, predecessor, on):
        self.con.execute("INSERT INTO actions VALUES (?, 'tickerchangefrom', ?, ?)",
                         [on, ticker, predecessor])
        return self


#: The governed session calendar is derived from `sep` itself, so a store must contain a full market
#: for the window to exist at all. Without this, a fixture holding only a late-starting security would
#: have a calendar that also starts late — and the resolver would correctly see no gap. Every real
#: corpus has thousands of names defining the calendar; this is the smallest faithful stand-in.
CALENDAR_ANCHOR = "MKT"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "lineage.duckdb")
    s.security(CALENDAR_ANCHOR, "P000")
    yield s
    s.con.close()


def _resolve(store, ticker):
    return resolve_lineage(store, ticker, session_date=SESSION, lookback_start=LOOKBACK)


# ── the retired-predecessor semantics that four large caps depend on ──────────────────────────────

class TestIntraLineageRename:
    @pytest.mark.parametrize("ticker,predecessor", [
        ("BNY", "BK"), ("FISV", "FI"), ("MRSH", "MMC"), ("KEEL", "BITF")])
    def test_a_retired_predecessor_with_continuous_history_stays_eligible(
            self, store, ticker, predecessor):
        """The vendor retro-maps the whole history onto the new symbol and RETIRES the old key, so the
        predecessor row is legitimately absent. Refusing on that alone drops real securities."""
        store.security(ticker, "P100").rename(ticker, predecessor, on=SESSIONS[30])
        decision = _resolve(store, ticker)
        assert decision.eligible, decision.detail
        assert decision.permaticker == "P100"

    def test_a_rename_within_one_lineage_is_valid_across_the_lookback(self, store):
        """The predecessor still exists AND resolves to the same permanent id."""
        store.security("NEW", "P200").rename("NEW", "OLD", on=SESSIONS[20])
        store.con.execute("INSERT INTO tickers VALUES ('OLD', 'P200', ?, ?)",
                          [SESSIONS[0], SESSIONS[20]])
        assert _resolve(store, "NEW").eligible


class TestCrossLineageReuse:
    def test_a_predecessor_resolving_to_another_permanent_id_is_refused(self, store):
        store.security("REUSED", "P300").rename("REUSED", "PRIOR", on=SESSIONS[25])
        store.con.execute("INSERT INTO tickers VALUES ('PRIOR', 'P999', ?, ?)",
                          [SESSIONS[0], SESSIONS[25]])
        decision = _resolve(store, "REUSED")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.LOOKBACK_CROSSES_LINEAGE

    def test_the_refusal_records_both_permanent_ids_and_the_boundary_date(self, store):
        """A boundary is the unit of the later Layer-2 repair, so it is recorded structurally."""
        store.security("REUSED", "P300").rename("REUSED", "PRIOR", on=SESSIONS[25])
        store.con.execute("INSERT INTO tickers VALUES ('PRIOR', 'P999', ?, ?)",
                          [SESSIONS[0], SESSIONS[25]])
        decision = _resolve(store, "REUSED")
        assert decision.permaticker == "P300"
        assert decision.predecessor_permaticker == "P999"
        assert decision.boundary_date == SESSIONS[25]
        assert decision.to_evidence()["boundary_date"] == SESSIONS[25].isoformat()

    def test_the_echo_shape_is_refused_for_metadata_price_disagreement(self, store):
        """Metadata claims a lifetime spanning the whole window; the series only starts late, because
        the earlier rows belong to the predecessor issuer."""
        store.security("ECHO", "193776", first=date(2008, 1, 2), marks=SESSIONS[40:])
        decision = _resolve(store, "ECHO")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.METADATA_PRICE_DISAGREE

    def test_an_internal_hole_the_metadata_does_not_explain_is_refused(self, store):
        store.security("HOLED", "P400", marks=SESSIONS[:10] + SESSIONS[45:])
        decision = _resolve(store, "HOLED")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.UNRESOLVED_REMAP_GAP


class TestPermanentIdentityIsMandatory:
    def test_a_store_without_the_column_refuses_rather_than_resolving(self, tmp_path):
        con = duckdb.connect(str(tmp_path / "legacy.duckdb"))
        con.execute("CREATE TABLE tickers (ticker VARCHAR, firstpricedate DATE, lastpricedate DATE)")
        with pytest.raises(SecurityIdentityUnavailable, match="permaticker"):
            require_permanent_identifier(con)
        con.close()

    def test_a_blank_permanent_id_refuses_that_lineage(self, store):
        store.security("NOID", None)
        decision = _resolve(store, "NOID")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.MISSING_PERMANENT_ID

    def test_two_simultaneously_active_lineages_are_refused(self, store):
        store.security("DUP", "P500")
        store.con.execute("INSERT INTO tickers VALUES ('DUP', 'P501', ?, ?)",
                          [SESSIONS[0], SESSION])
        decision = _resolve(store, "DUP")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.MULTIPLE_ACTIVE_LINEAGES

    def test_no_active_lineage_at_the_session_is_refused(self, store):
        store.security("GONE", "P600", last=SESSIONS[20], marks=SESSIONS[:21])
        decision = _resolve(store, "GONE")
        assert not decision.eligible
        assert decision.refusal is LineageRefusal.NO_ACTIVE_LINEAGE


class TestCallerShapeCannotChangeTheAnswer:
    def test_a_bare_connection_and_a_store_wrapper_agree(self, store):
        """Otherwise the identity contract would apply to production stores and silently NOT apply
        wherever a connection is passed directly — the same code path, two eligibility answers."""
        store.security("AAA", "P700")
        store.security("ECHO", "193776", first=date(2008, 1, 2), marks=SESSIONS[40:])

        class Wrapper:
            def __init__(self, con):
                self.con = con

        via_conn = assess_universe(store.con, ["AAA", "ECHO"],
                                   session_date=SESSION, lookback_start=LOOKBACK)
        via_store = assess_universe(Wrapper(store.con), ["AAA", "ECHO"],
                                    session_date=SESSION, lookback_start=LOOKBACK)
        assert via_conn.eligible_tickers == via_store.eligible_tickers == ("AAA",)
        assert via_conn.counts_by_refusal() == via_store.counts_by_refusal()


# ── the bridge check: only a two-sided hole can fabricate a return ────────────────────────────────

class TestProxyBridgeRisk:
    def _excluded(self, store, ticker):
        return assess_universe(store, [ticker], session_date=SESSION,
                               lookback_start=LOOKBACK).excluded

    def test_marks_only_before_the_hole_do_not_refuse(self, store):
        """An ordinary delisting: the series ends and `pct_change` yields NaN, dropped by skipna."""
        store.security("ENDED", "P800", last=SESSIONS[20], marks=SESSIONS[:21])
        risks = assess_bridge_risk(store, self._excluded(store, "ENDED"), window=SESSIONS)
        assert risks == ()

    def test_marks_only_after_the_hole_do_not_refuse(self, store):
        """An ordinary new listing — and ECHO's shape: no in-window prior value to bridge from."""
        store.security("ECHO", "193776", first=date(2008, 1, 2), marks=SESSIONS[40:])
        risks = assess_bridge_risk(store, self._excluded(store, "ECHO"), window=SESSIONS)
        assert risks == ()

    def test_a_nineteen_session_hole_with_marks_on_both_sides_does_not_refuse(self, store):
        hole = SESSIONS[20:39]                       # 19 sessions
        assert len(hole) == LINEAGE_BRIDGE_HOLE_MIN_SESSIONS - 1
        store.security("NEARLY", "P900", first=date(2008, 1, 2),
                       marks=SESSIONS[:20] + SESSIONS[39:])
        risks = assess_bridge_risk(store, self._excluded(store, "NEARLY"), window=SESSIONS)
        assert risks == ()

    def test_a_twenty_session_hole_with_marks_on_both_sides_refuses(self, store):
        hole = SESSIONS[20:40]                       # 20 sessions
        assert len(hole) == LINEAGE_BRIDGE_HOLE_MIN_SESSIONS
        store.security("BRIDGE", "P901", first=date(2008, 1, 2),
                       marks=SESSIONS[:20] + SESSIONS[40:])
        risks = assess_bridge_risk(store, self._excluded(store, "BRIDGE"), window=SESSIONS)
        assert len(risks) == 1
        risk = risks[0]
        assert risk.ticker == "BRIDGE"
        assert risk.permaticker == "P901"
        assert risk.hole_sessions == LINEAGE_BRIDGE_HOLE_MIN_SESSIONS
        assert risk.hole_start == SESSIONS[20]
        assert risk.hole_end == SESSIONS[39]
        assert risk.last_mark_before == SESSIONS[19]
        assert risk.first_mark_after == SESSIONS[40]

    def test_the_evidence_records_the_exact_boundary(self, store):
        store.security("BRIDGE", "P901", first=date(2008, 1, 2),
                       marks=SESSIONS[:20] + SESSIONS[40:])
        ev = assess_bridge_risk(store, self._excluded(store, "BRIDGE"),
                                window=SESSIONS)[0].to_evidence()
        assert ev["reason"] == "LINEAGE_BRIDGE_RISK"
        assert ev["marks_before"] is True and ev["marks_after"] is True
        assert ev["hole_sessions"] == LINEAGE_BRIDGE_HOLE_MIN_SESSIONS
        assert ev["last_mark_before"] == SESSIONS[19].isoformat()
        assert ev["first_mark_after"] == SESSIONS[40].isoformat()

    def test_only_lineage_excluded_names_are_examined(self, store):
        """A perfectly ordinary security is never a bridge candidate, whatever its gaps look like."""
        store.security("FINE", "P902")
        assert assess_bridge_risk(store, (), window=SESSIONS) == ()


# ── the containment point: nothing downstream may see a pre-filter candidate ──────────────────────

class TestFilterContainment:
    def test_excluded_names_never_leave_the_universe_callable(self, store):
        store.security("AAA", "P700")
        store.security("BBB", "P701")
        store.security("ECHO", "193776", first=date(2008, 1, 2), marks=SESSIONS[40:])

        filt = SessionLineageFilter(store, session_date=SESSION, lookback_start=LOOKBACK)
        wrapped = filt.wrap(lambda as_of, n: ["AAA", "ECHO", "BBB"][:n])

        assert wrapped(SESSION, 3) == ["AAA", "BBB"]        # ranking never sees ECHO
        assessment = filt.assessment()
        assert assessment.excluded_count == 1
        assert assessment.excluded[0].ticker == "ECHO"

    def test_raw_and_eligible_counts_stay_distinct_in_evidence(self, store):
        store.security("AAA", "P700")
        store.security("ECHO", "193776", first=date(2008, 1, 2), marks=SESSIONS[40:])

        filt = SessionLineageFilter(store, session_date=SESSION, lookback_start=LOOKBACK)
        filt.wrap(lambda as_of, n: ["AAA", "ECHO"])(SESSION, 2)
        ev = filt.assessment().to_evidence()

        assert ev["raw_universe_count"] == 2
        assert ev["lineage_eligible_universe_count"] == 1
        assert ev["excluded_count"] == 1
        assert ev["security_identity_contract"] == "PERMATICKER_EFFECTIVE_INTERVAL_V1"
        assert ev["excluded_by_reason"] == {"METADATA_PRICE_DISAGREE": 1}

    def test_every_exclusion_is_listed_not_sampled(self, store):
        """A truncated list would let a growing exclusion set hide behind a fixed window."""
        for i in range(30):
            store.security(f"BAD{i:02d}", f"P{i:03d}", first=date(2008, 1, 2), marks=SESSIONS[40:])
        names = [f"BAD{i:02d}" for i in range(30)]
        ev = assess_universe(store, names, session_date=SESSION,
                             lookback_start=LOOKBACK).to_evidence()
        assert ev["excluded_count"] == 30
        assert len(ev["excluded"]) == 30
