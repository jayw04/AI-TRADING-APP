"""SPQ-1 Phase 2B-2 request-identity collision rule tests (MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1).

Proves the governed pre-production collision rule: when >1 distinct request symbol resolves provisionally
to the same (session, permanent_security_id), ALL claimants terminate as an UNRESOLVED
INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS (no winner, no signal), the claimed id survives only as
diagnostics, resolved-key duplicates stay zero, and detection happens before any producer call.

Synthetic scenarios need no DB. The real-data regression fixtures (AGN/AGN1, CB/CB1, DD/DD1) require the
registered development DBs and are skipped when absent.
"""
from __future__ import annotations

import contextlib
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
CR_PATH = REPO / "docs" / "review" / "mr002" / "spq1" / "phase2b" / "collision_rule.py"
RESEARCH = REPO / "apps" / "backend" / "data" / "mr002_research.duckdb"
PROV = REPO / "apps" / "backend" / "data" / "mr002_provenance.duckdb"


def _load_collision_rule():
    spec = importlib.util.spec_from_file_location("collision_rule", CR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CR = _load_collision_rule()
from app.research.mr002.spq1.refusals import SignalRefusal  # noqa: E402


class FakeLineage:
    def __init__(self, mapping):
        self.m = mapping  # (symbol, t) -> permsec ; value "RAISE" -> SignalRefusal ; missing -> ""

    def resolve_permanent_id(self, symbol, t):  # noqa: ANN001
        v = self.m.get((symbol, t))
        if v == "RAISE":
            raise SignalRefusal("INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS", "lineage ambiguous")
        return v or ""


class FakeCalendar:
    def __init__(self, sessions):
        self.sessions = sessions


class FakeCtx:
    def __init__(self, lineage, sessions):
        self.lineage = lineage
        self.calendar = FakeCalendar(sessions)


def _resolver(mapping):
    return FakeLineage(mapping).resolve_permanent_id


# ---------------- synthetic scenarios (no DB) ----------------

def test_two_symbols_same_provisional_id_both_stop():
    m = {("AGN", 5): "P1", ("AGN1", 5): "P1"}
    collisions, groups = CR.detect_request_identity_collisions([("AGN", 5), ("AGN1", 5)], _resolver(m))
    assert set(collisions) == {(5, "AGN"), (5, "AGN1")}
    assert groups == {(5, "P1"): ["AGN", "AGN1"]}
    for k in collisions:
        assert collisions[k]["claimed_permanent_security_id"] == "P1"
        assert collisions[k]["collision_cardinality"] == 2


def test_neither_colliding_request_produces_a_signal_record(monkeypatch):
    called = []
    monkeypatch.setattr(CR.ORCH, "run_unit", lambda ctx, s, t: called.append((s, t)))
    ctx = FakeCtx(FakeLineage({("A", 3): "P", ("B", 3): "P"}), ["d0", "d1", "d2", "d3"])
    results, _content, rows = CR.run_shard_governed(ctx, [("A", 3), ("B", 3)])
    assert called == []                                   # run_unit NEVER called for colliding requests
    assert all(r.disposition == "INTEGRITY_STOP" and r.code == CR.COLLISION_CODE for r in results)
    assert all(r.record_identity is None and r.decision_eligibility_status is None for r in results)


def test_claimed_permanent_id_only_in_diagnostics(monkeypatch):
    monkeypatch.setattr(CR.ORCH, "run_unit", lambda ctx, s, t: pytest.fail("run_unit must not be called"))
    ctx = FakeCtx(FakeLineage({("A", 2): "PSEC-9", ("B", 2): "PSEC-9"}), ["d0", "d1", "d2"])
    results, _content, rows = CR.run_shard_governed(ctx, [("A", 2), ("B", 2)])
    for r in results:
        assert r.permanent_security_id == ""             # terminal record carries NO resolved id
    for row in rows:
        assert row["claimed_permanent_security_id"] == "PSEC-9"   # claimed id retained only as diagnostic
        assert row["terminal_key"][1].startswith("UNRESOLVED:")


def test_resolved_key_duplicate_count_zero_and_request_key_complete(monkeypatch):
    monkeypatch.setattr(CR.ORCH, "run_unit", lambda ctx, s, t: pytest.fail("run_unit must not be called"))
    ctx = FakeCtx(FakeLineage({("A", 1): "P", ("B", 1): "P"}), ["d0", "d1"])
    results, _c, _rows = CR.run_shard_governed(ctx, [("A", 1), ("B", 1)])
    assert len(results) == 2                              # one terminal record per request (complete)
    term = [r.terminal_key() for r in results if r.permanent_security_id]
    assert len(term) == len(set(term))                   # resolved-key duplicates = 0 (both unresolved)
    req = [(r.decision_session, r.symbol) for r in results]
    assert sorted(req) == [(1, "A"), (1, "B")]


def test_input_symbol_order_does_not_affect_membership_or_hash(monkeypatch):
    monkeypatch.setattr(CR.ORCH, "run_unit", lambda ctx, s, t: pytest.fail("no producer for colliding"))
    ctx = FakeCtx(FakeLineage({("A", 4): "P", ("B", 4): "P"}), ["d"] * 5)
    r1, c1, _ = CR.run_shard_governed(ctx, [("A", 4), ("B", 4)])
    r2, c2, _ = CR.run_shard_governed(ctx, [("B", 4), ("A", 4)])
    assert c1 == c2                                       # content hash order-independent
    col1, _ = CR.detect_request_identity_collisions([("A", 4), ("B", 4)], _resolver({("A", 4): "P", ("B", 4): "P"}))
    col2, _ = CR.detect_request_identity_collisions([("B", 4), ("A", 4)], _resolver({("A", 4): "P", ("B", 4): "P"}))
    assert set(col1) == set(col2)


def test_collisions_across_separate_sessions_handled_independently():
    m = {("A", 1): "P", ("B", 1): "P", ("A", 2): "P", ("B", 2): "P"}
    collisions, groups = CR.detect_request_identity_collisions(
        [("A", 1), ("B", 1), ("A", 2), ("B", 2)], _resolver(m))
    assert set(groups) == {(1, "P"), (2, "P")}           # two independent per-session groups
    assert len(collisions) == 4


def test_same_permsec_nonoverlapping_sessions_is_not_a_collision():
    # A holds P at session 1; B holds P at session 2 (different sessions) -> NOT a collision
    m = {("A", 1): "P", ("B", 2): "P"}
    collisions, groups = CR.detect_request_identity_collisions([("A", 1), ("B", 2)], _resolver(m))
    assert collisions == {} and groups == {}


def test_three_symbol_collision_stops_all_three():
    m = {("A", 7): "P", ("B", 7): "P", ("C", 7): "P"}
    collisions, groups = CR.detect_request_identity_collisions(
        [("A", 7), ("B", 7), ("C", 7)], _resolver(m))
    assert groups == {(7, "P"): ["A", "B", "C"]}
    assert set(collisions) == {(7, "A"), (7, "B"), (7, "C")}
    assert all(collisions[k]["collision_cardinality"] == 3 for k in collisions)


def test_independent_resolution_failure_is_not_a_false_collision():
    # A resolves to P; B independently fails resolution -> NOT a collision with A
    m = {("A", 1): "P", ("B", 1): "RAISE"}
    collisions, groups = CR.detect_request_identity_collisions([("A", 1), ("B", 1)], _resolver(m))
    assert collisions == {} and groups == {}


def test_detection_precedes_producer_calls(monkeypatch):
    """A colliding request must never reach run_unit; a non-colliding one must."""
    seen = []
    monkeypatch.setattr(CR.ORCH, "run_unit",
                        lambda ctx, s, t: seen.append((s, t)) or CR.ORCH.UnitResult(
                            "P-ok", s, t, "SIGNAL_DECISION_RECORD_EMITTED", None, "ELIGIBLE", "rec"))
    ctx = FakeCtx(FakeLineage({("A", 1): "P", ("B", 1): "P", ("C", 1): "Punique"}),
                  ["d0", "d1"])
    _results, _c, rows = CR.run_shard_governed(ctx, [("A", 1), ("B", 1), ("C", 1)])
    assert seen == [("C", 1)]                             # only the non-colliding request hit run_unit
    assert {r["request_symbol"] for r in rows} == {"A", "B"}


# ---------------- real-data regression fixtures ----------------

@pytest.mark.skipif(not (RESEARCH.exists() and PROV.exists()),
                    reason="registered development DBs absent (local-only)")
def test_real_data_known_collision_pairs():
    """AGN/AGN1, CB/CB1, DD/DD1 each resolve to one permsec during their transition -> a real collision."""
    import os
    import tempfile

    import duckdb

    from app.research.mr002.spq1.adapters import REGISTERED_RESEARCH_DB, abs_path
    from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger

    ORCH = CR.ORCH
    pairs = {"AGN/AGN1": ("PSEC-198103", ["AGN", "AGN1"]),
             "CB/CB1": ("PSEC-199850", ["CB", "CB1"]),
             "DD/DD1": ("PSEC-199769", ["DD", "DD1"])}
    tickers = sorted({"AAPL"} | {t for _, syms in pairs.values() for t in syms})
    r = duckdb.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
    ciks = sorted({int(c[0]) for c in r.execute(
        "select distinct cik from crosswalk where ticker = ANY(?)", [tickers]).fetchall()})
    r.close()
    tmp = os.path.join(tempfile.gettempdir(), "mr002_2b2_collision_fixture.duckdb")
    if os.path.exists(tmp):
        os.remove(tmp)
    led = OpenedObjectLedger()
    con, guard, src, snap_path, snap_sha = ORCH.materialize_run_input(tmp, tickers, ciks, led)
    ctx = ORCH.build_context(con, guard, tickers, ciks, src, snap_path, snap_sha)
    cal = ctx.calendar.sessions
    resolve = ctx.lineage.resolve_permanent_id
    try:
        for _label, (permsec, syms) in pairs.items():
            # scan the whole dev window for a session where both syms resolve to the same permsec
            found = None
            for t in range(len(cal)):
                r0, r1 = None, None
                with contextlib.suppress(SignalRefusal):
                    r0 = resolve(syms[0], t)
                with contextlib.suppress(SignalRefusal):
                    r1 = resolve(syms[1], t)
                if r0 and r0 == r1:
                    found = (t, r0)
                    break
            assert found is not None, f"expected a collision session for {syms}"
            collisions, groups = CR.detect_request_identity_collisions(
                [(syms[0], found[0]), (syms[1], found[0])], resolve)
            assert (found[0], found[1]) in groups
            assert found[1] == permsec, f"{syms} claimed {found[1]} != registered {permsec}"
            assert set(collisions) == {(found[0], syms[0]), (found[0], syms[1])}
    finally:
        con.close()
        src.close()
