"""SPQ-1 Phase 2B-1 orchestration qualification (real dev data; small unit set).

Skips if the registered development DBs are absent. Proves the terminal-disposition contract,
determinism, shard/merge invariance, restart safety, the PIT sector sentinel, and import isolation.
No signal value is inspected.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
RESEARCH = REPO / "apps" / "backend" / "data" / "mr002_research.duckdb"
PROV = REPO / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
pytestmark = pytest.mark.skipif(
    not (RESEARCH.exists() and PROV.exists()), reason="registered development DBs not present")

from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger  # noqa: E402
from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402
from app.research.mr002.spq1.phase2b import (  # noqa: E402
    EMITTED,
    INELIGIBLE,
    INTEGRITY_STOP,
    REFUSED,
)
from app.research.mr002.spq1.phase2b import orchestrator as ORCH  # noqa: E402
from app.research.mr002.spq1.phase2b.sic_sector import resolve_sector  # noqa: E402
from app.research.mr002.spq1.refusals import DEPRECATED_CODES, REFUSAL_CODES  # noqa: E402

TK = ["AAPL", "MSFT"]
CK = [320193, 789019]
TERMINAL = {EMITTED, INELIGIBLE, INTEGRITY_STOP, REFUSED}


def _ctx(tmp):
    led = OpenedObjectLedger()
    con, guard, src = ORCH.materialize_run_input(str(tmp), TK, CK, led)
    ctx = ORCH.build_context(con, guard, TK, CK, src)
    return ctx, con, src, led


def test_terminal_contract_and_reconciliation(tmp_path):
    ctx, con, src, led = _ctx(tmp_path / "a.duckdb")
    sessions = [1699, 1400, 50]
    units = [(p, t) for t in sessions for p in ctx.securities]
    results, _ = ORCH.run_shard(ctx, units)
    con.close()
    src.close()
    assert len(results) == len(units)
    assert all(r.disposition in TERMINAL for r in results)             # exactly one, valid
    assert len({r.key() for r in results}) == len(results)             # no duplicate unit
    assert all(r.code is None or r.code in REFUSAL_CODES for r in results)
    assert not any(r.code in DEPRECATED_CODES for r in results)        # deprecated never emitted
    disp = Counter(r.disposition for r in results)
    assert disp[EMITTED] > 0 and disp[INELIGIBLE] > 0                   # warm-up early + emit late


def test_determinism_and_shard_merge_invariance(tmp_path):
    ctx, con, src, _ = _ctx(tmp_path / "b.duckdb")
    units = [(p, t) for t in (1690, 1699) for p in ctx.securities]
    r1, h1 = ORCH.run_shard(ctx, units)
    _, h2 = ORCH.run_shard(ctx, units)
    con.close()
    src.close()
    assert h1 == h2                                                     # repeat run byte-identical
    merged_single = canonical_sha256([u.as_row() for u in ORCH.merge([r1])])
    merged_multi = canonical_sha256(
        [u.as_row() for u in ORCH.merge([[u for u in r1 if u.decision_session == 1690],
                                         [u for u in r1 if u.decision_session == 1699]])])
    assert merged_single == merged_multi                               # shard-partitioned == single


def test_restart_atomic_non_overwriting(tmp_path):
    ctx, con, src, _ = _ctx(tmp_path / "c.duckdb")
    units = [(p, 1699) for p in ctx.securities]
    results, content = ORCH.run_shard(ctx, units)
    con.close()
    src.close()
    path = str(tmp_path / "shard.json")
    ORCH.publish_shard(results, content, path)
    with pytest.raises(FileExistsError):
        ORCH.publish_shard(results, content, path)                     # completed shard non-overwritable
    assert list(tmp_path.glob("*.partial")) == []


def test_pit_sector_sentinel_excluded(tmp_path):
    ctx, con, src, _ = _ctx(tmp_path / "d.duckdb")
    aapl = next(v for v in ctx.securities.values() if v["symbol"] == "AAPL")
    cutoff = ctx.calendar.sessions[1699] + "T21:00:00Z"
    base = resolve_sector(ctx.sic_map, aapl["sic_obs"], cutoff)
    poisoned = list(aapl["sic_obs"]) + [("2099-01-01 00:00:00+00:00", "6199")]
    after = resolve_sector(ctx.sic_map, poisoned, cutoff)
    con.close()
    src.close()
    assert base.sector_id == after.sector_id                           # future obs cannot change sector


def test_et_close_cutoff_dst_correct():
    from app.research.mr002.spq1.phase2b.cutoff import et_close_cutoff_iso
    assert et_close_cutoff_iso("2015-01-15") == "2015-01-15T21:00:00Z"   # EST -> 21:00Z
    assert et_close_cutoff_iso("2015-07-15") == "2015-07-15T20:00:00Z"   # EDT -> 20:00Z
    assert et_close_cutoff_iso("2015-03-09") == "2015-03-09T20:00:00Z"   # after spring-forward
    # a summer 20:30Z availability is AFTER the 20:00Z EDT close -> excluded (would have leaked at 21:00Z)
    assert et_close_cutoff_iso("2015-07-15") < "2015-07-15T20:30:00Z"


def test_phase2b_code_identity_binds_all_execution_modules():
    from app.research.mr002.spq1.phase2b import orchestrator as O
    ident = O.code_identity()
    assert set(ident) == {"__init__.py", "cutoff.py", "sic_sector.py", "orchestrator.py"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in ident.values())
    O.verify_code_identity(dict(ident))                                  # matches -> ok
    with pytest.raises(RuntimeError):
        O.verify_code_identity({**ident, "orchestrator.py": "0" * 64})   # drift -> refuse


def test_no_orderpath_or_performance_imports():
    pkg = REPO / "apps" / "backend" / "app" / "research" / "mr002" / "spq1" / "phase2b"
    forbidden = re.compile(
        r"\b(order_router|broker|app\.services|app\.risk|requests|boto3|sklearn|matplotlib|"
        r"scipy\.stats|portfolio|order_router)\b")
    for src_file in pkg.glob("*.py"):
        for lineno, line in enumerate(src_file.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("import ", "from ")):
                assert not forbidden.search(line), f"{src_file.name}:{lineno} forbidden: {line}"
