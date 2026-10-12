"""End-to-end SYNTHETIC rehearsal of the descriptive run command through the decision API.

Everything is synthetic: a tiny daily snapshot (one delisted-later name, one reused ticker), a
minute_bars table with one completely missing symbol-day, a frozen spec carrying an approved
decision whose minutes file is written and hashed under a temp minutes root, and a ledger bound
to that decision. ``run(...)`` is the same code the CLI calls. Nothing here is a result.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import pytest

from app.research.range002.governance import errors as gov_errors
from app.research.range002.governance.results_guard import require_capability
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from app.research.range002.spec import decision as decision_module
from app.research.range002.spec.hashing import file_sha256
from app.research.range002.spec.loader import SpecHashMismatchError
from tests.research.range002.governance.conftest import (  # noqa: F401  (autouse manifest seam)
    DECIDED_LEDGER,
    new_registry,
    synthetic_manifest,
)
from tests.research.range002.screen.conftest import minutes_flat, mk, or_bars, synth_payload
from tests.research.range002.spec._fixtures import (
    MINUTES_BYTES,
    MINUTES_RELPATH,
    SYNTH_MANIFEST_PATH,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402
import run_descriptive_screen as rds  # noqa: E402

COMMON = "Domestic Common Stock"
CODE_SHA = "a" * 40
SEVEN = [
    {"id": "TIME", "family": "time", "params": {}},
    {"id": "R1", "family": "fixed_r", "params": {"r_multiple": 1.0}},
    {"id": "R2", "family": "fixed_r", "params": {"r_multiple": 2.0}},
    {"id": "R3", "family": "fixed_r", "params": {"r_multiple": 3.0}},
    {"id": "TRAIL", "family": "trailing", "params": {"trail_r": 1.0}},
    {"id": "SCALE_EOD", "family": "scale_out", "params": {"remainder": "eod"}},
    {"id": "SCALE_TRAIL", "family": "scale_out", "params": {"remainder": "trail", "trail_r": 1.0}},
]
SESSIONS = [
    date(2016, 3, 1),
    date(2016, 3, 2),
    date(2016, 3, 3),
    date(2016, 3, 4),
    date(2016, 3, 7),
]
MISSING = ("OLD", date(2016, 3, 3))
_ET, _UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")


def _weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _write_daily(
    path: Path,
    *,
    with_table_column: bool = True,
    dead_last: str = "2016-04-15",
    action_rows: tuple[tuple[str, str, str], ...] = (),
) -> None:
    con = duckdb.connect(str(path))
    tcol = '"table" VARCHAR, ' if with_table_column else ""
    con.execute(
        f"CREATE TABLE tickers({tcol}permaticker VARCHAR, ticker VARCHAR, category VARCHAR, "
        "isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE)"
    )
    rows = [
        ("P1", "AAA", "N", "2010-01-04", "2026-02-27"),
        ("P2", "BBB", "N", "2010-01-04", "2026-02-27"),
        ("P3", "CCC", "N", "2010-01-04", "2026-02-27"),
        ("P4", "DEAD", "Y", "2010-01-04", dead_last),  # delisted LATER
        ("P5", "OLD", "Y", "2010-01-04", "2015-12-31"),  # old issuer of a reused ticker
        ("P6", "OLD", "N", "2016-01-04", "2026-02-27"),  # new issuer
    ]
    for perma, tick, gone, first, last in rows:
        vals = (["SEP"] if with_table_column else []) + [perma, tick, COMMON, gone, first, last]
        marks = ", ".join("?" for _ in vals)
        con.execute(f"INSERT INTO tickers VALUES ({marks})", vals)
    con.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, "
        "volume DOUBLE)"
    )
    for tick, px, vol in [
        ("AAA", 100.0, 1_000_000),
        ("DEAD", 50.0, 1_000_000),
        ("OLD", 40.0, 1_000_000),
        ("BBB", 30.0, 100_000),
        ("CCC", 20.0, 100_000),
    ]:
        for d in _weekdays(date(2016, 1, 4), date(2016, 2, 29)):
            con.execute("INSERT INTO sep VALUES (?, ?, ?, ?, ?)", [tick, d, px, px, vol])
    con.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    for day, action, ticker in action_rows:
        con.execute("INSERT INTO actions VALUES (?, ?, ?, NULL)", [day, action, ticker])
    con.close()


def _manifest_for(snapshot: Path) -> str:
    return json.dumps(
        {
            "schema": "range002.snapshot_manifest.v1",
            "source": "synthetic",
            "extracted_at_utc": "2026-10-12T00:00:00Z",
            "method": "synthetic test export",
            "cross_table_consistent": True,
            "consistency_basis": "single synthetic build",
            "tables": {
                name: {
                    "rows": 1,
                    "min_date": None,
                    "max_date": None,
                    "columns": list(cols),
                    "files": [{"path": snapshot.name, "sha256": file_sha256(snapshot)}],
                }
                for name, cols in (
                    (
                        "tickers",
                        (
                            "permaticker",
                            "ticker",
                            "category",
                            "isdelisted",
                            "firstpricedate",
                            "lastpricedate",
                        ),
                    ),
                    ("sep", ("ticker", "date", "close", "closeunadj", "volume")),
                    ("actions", ("date", "action", "ticker", "contraticker")),
                )
            },
        }
    )


def _bars(breakout: bool) -> list[Any]:
    if not breakout:
        return or_bars() + minutes_flat("10:00", "15:59", 10.05)
    return (
        or_bars()
        + minutes_flat("10:00", "10:04", 10.05)
        + [mk("10:05", 10.09, 10.20, 10.08, 10.18)]
        + minutes_flat("10:06", "15:59", 10.30)
    )


def _write_minutes(path: Path, *, dead_until: date | None = None) -> None:
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    rows: list[tuple[Any, ...]] = []
    for i, d in enumerate(SESSIONS):
        for j, sym in enumerate(("AAA", "DEAD", "OLD")):
            if (sym, d) == MISSING:
                continue
            if sym == "DEAD" and dead_until is not None and d > dead_until:
                continue  # the name stops printing; WHY is not asserted by the data
            for b in _bars(breakout=(i + j) % 2 == 0):
                local = datetime.combine(d, b.start, tzinfo=_ET)
                ts = local.astimezone(_UTC).replace(tzinfo=None)
                rows.append((sym, ts, b.open, b.high, b.low, b.close, b.volume, "raw"))
    frame = pd.DataFrame(  # one bulk insert: row-wise executemany is very slow in DuckDB
        rows, columns=["symbol", "ts", "open", "high", "low", "close", "volume", "basis"]
    )
    con.register("frame", frame)
    con.execute("INSERT INTO minute_bars SELECT * FROM frame")
    con.close()


@pytest.fixture
def minutes_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "minutes_root"
    (root / MINUTES_RELPATH).parent.mkdir(parents=True)
    (root / MINUTES_RELPATH).write_bytes(MINUTES_BYTES)
    monkeypatch.setattr(decision_module, "_MINUTES_ROOT", root)
    return root


def _freeze(tmp: Path, payload: dict[str, Any], name: str = "frozen.json") -> Path:
    draft = tmp / f"draft_{name}"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp / name
    freeze_spec.freeze(draft, out, manifest_path=SYNTH_MANIFEST_PATH)
    return out


def _edit(frozen: Path, mutate: Any, name: str) -> Path:
    doc = json.loads(frozen.read_text(encoding="utf-8"))
    mutate(doc)
    out = frozen.parent / name
    out.write_text(json.dumps(doc), encoding="utf-8")
    return out


@pytest.fixture
def world(tmp_path: Path, minutes_root: Path) -> dict[str, Any]:
    snap = tmp_path / "daily.duckdb"
    _write_daily(snap)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(_manifest_for(snap), encoding="utf-8")
    minutes = tmp_path / "minutes.duckdb"
    _write_minutes(minutes)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(DECIDED_LEDGER, encoding="utf-8")
    payload = synth_payload(exits__candidates=copy.deepcopy(SEVEN))
    frozen = _freeze(tmp_path, payload)
    registry_path = tmp_path / "runs.jsonl"
    new_registry(registry_path)
    return {
        "tmp": tmp_path,
        "frozen": frozen,
        "registry_path": registry_path,
        "kwargs": {
            "spec_path": frozen,
            "registry_path": registry_path,
            "exposure_ledger_path": ledger,
            "daily_snapshot": snap,
            "snapshot_manifest": manifest,
            "minute_bars": minutes,
            "minute_feed": "sip",
            "minute_ts_convention": "start",
            "date_start": "2016-03-01",
            "date_end": "2016-03-07",
            "partition": "DEVELOPMENT_SELECTION",
            "table_filter": "SEP",
            "lookback_calendar_days": 40,
            "coverage_threshold": 0.90,
            "equity": 100_000.0,
            "tick": 0.01,
            "code_sha": CODE_SHA,
            "out_dir": tmp_path / "out",
            "delisting_actions": (),
            "provenance": {"vendor_export": "synthetic-v0"},
        },
    }


def _runs(world: dict[str, Any]) -> tuple[Any, ...]:
    return RunRegistry(world["registry_path"]).runs()


def _assert_no_open(world: dict[str, Any]) -> None:
    assert [r for r in _runs(world) if r.status is RunStatus.OPEN] == []


# --- the positive rehearsal -----------------------------------------------------------------


def test_descriptive_run_end_to_end(world: dict[str, Any]) -> None:
    out = rds.run(**world["kwargs"])
    rep = json.loads(out.report_json.read_text(encoding="utf-8"))
    assert out.report_md.is_file()

    # all seven candidates, base and stress, in the report
    assert list(rep["candidates"]) == [c["id"] for c in SEVEN]
    for summary in rep["candidates"].values():
        assert {"base", "stress", "unexecutable_exits"} <= set(summary)
        assert summary["inferential_status"] == "NON_INFERENTIAL_DESCRIPTIVE"

    # the completely missing symbol-day stays in the denominator
    cov = rep["coverage"]
    assert cov["expected"] == 15 and cov["denominator"] == 15 and cov["observed"] == 14
    assert cov["missing_no_data"] == 1 and cov["coverage_rate"] < 1.0
    assert cov["by_year"]["2016"] == {"expected": 15, "observed": 14}
    assert rep["funnel"]["eligible"] == 14
    assert rep["funnel"]["reconciliation"]["missing_symbol_days"] == 1
    assert rep["status"] == rds.STATUS_COMPLETE
    assert rep["funnel"]["states"]["ENTERED"] > 0

    # labels, provenance and disclosures
    assert rep["label"] == "NON_INFERENTIAL_DESCRIPTIVE"
    assert "not preregistered confirmation" in rep["label_sentence"]
    assert rep["spec"]["sha256"] == out.report["spec"]["sha256"]
    assert rep["spec"]["baseline_id"] == "SYNTH-BASELINE-1"
    assert rep["spec"]["strategy_version"] == "SYNTH-V1"
    assert rep["decision_reference"]["minutes_path"] == MINUTES_RELPATH
    assert rep["decision_reference"]["decision"] == "approved"
    assert rep["authorized_range"] == {"start": "2016-03-01", "end": "2016-03-07"}
    assert rep["run"]["partition"] == "DEVELOPMENT_SELECTION"
    assert rep["data"]["provenance"] == {"vendor_export": "synthetic-v0"}
    assert rep["data"]["universe_scopes"] == ["PIT_FULL"]
    assert rep["execution_disclosure"]["execution_realism"] == "NOT_MODELLED"
    assert rep["unavailable_exit_valuation"]["rule"] == "WORSE_OF_LAST_CLOSE_AND_INITIAL_STOP"
    assert rep["or_completeness"]["of_expected"] is not None
    assert rep["exposure_note"]
    md = out.report_md.read_text(encoding="utf-8")
    assert "NON_INFERENTIAL_DESCRIPTIVE" in md and "TRAIL" in md and "SCALE_TRAIL" in md
    # the reused ticker was attributed to the new issuer; the delisted-later name is a member
    month = rep["universe_months"][0]
    assert month["members"] == 3 and month["identity_one_row_per_ticker"] is False

    # registry: exactly one run, COMPLETED, digest = sha256 of the report bytes
    (run_state,) = _runs(world)
    assert run_state.run_id == out.run_id and run_state.status is RunStatus.COMPLETED
    assert run_state.audit_pack_sha256 == out.report_sha256
    assert out.report_sha256 == file_sha256(out.report_json)
    # the capability is dead once the run is closed
    with pytest.raises(gov_errors.InvalidCapabilityError):
        require_capability(out.capability)


def test_coverage_below_threshold_is_a_defect_without_a_verdict(world: dict[str, Any]) -> None:
    kw = dict(world["kwargs"], coverage_threshold=0.98)
    out = rds.run(
        **kw,
        statistics_config={
            "mean_block_days": 2.0,
            "reps": 50,
            "seed": 1,
            "confidence": 0.9,
            "alpha": 0.1,
        },
    )
    rep = out.report
    assert rep["status"] == rds.STATUS_DEFECT
    assert "DEFECT" in rep["defect_note"] and "no strategy conclusion" in rep["defect_note"]
    assert rep["optional_bootstrap"] is None  # never computed on defective coverage
    assert len(rep["candidates"]) == 7  # the report is still written
    (run_state,) = _runs(world)
    assert run_state.status is RunStatus.COMPLETED


def test_optional_bootstrap_is_separate_when_coverage_is_sound(world: dict[str, Any]) -> None:
    kw = dict(world["kwargs"], coverage_threshold=0.90)
    out = rds.run(
        **kw,
        statistics_config={
            "mean_block_days": 2.0,
            "reps": 50,
            "seed": 1,
            "confidence": 0.9,
            "alpha": 0.1,
        },
    )
    boot = out.report["optional_bootstrap"]
    assert boot["separate_from_descriptive_tables"] is True and boot["preregistered"] is False
    assert set(boot["mean_net_r_intervals"]) == {c["id"] for c in SEVEN}


# --- dry plan -------------------------------------------------------------------------------


def test_dry_plan_reads_no_bars_and_opens_no_run(
    world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    kw = world["kwargs"]
    ghost = world["tmp"] / "no_such_minutes.duckdb"  # any bar access would fail on this path
    p = rds.plan(
        spec_path=kw["spec_path"],
        date_start="2016-03-01",
        date_end="2016-03-07",
        partition="DEVELOPMENT_SELECTION",
        daily_snapshot=kw["daily_snapshot"],
        minute_bars=ghost,
    )
    assert p["mode"] == "DRY_PLAN_NO_BAR_READ" and p["would_be_refused"] is False
    assert p["sessions_in_range"] == 5 and p["expected_symbol_days_upper_bound"] == 15
    assert p["universe_months"] == ["2016-03-01"]
    assert p["request_scope"]["partition"] == "DEVELOPMENT_SELECTION"
    assert p["decision_reference"]["minutes_sha256"]
    assert _runs(world) == ()  # no run row

    argv = [
        "--spec", str(kw["spec_path"]), "--registry", str(kw["registry_path"]),
        "--exposure-ledger", str(kw["exposure_ledger_path"]),
        "--daily-snapshot", str(kw["daily_snapshot"]),
        "--snapshot-manifest", str(kw["snapshot_manifest"]), "--minute-bars", str(ghost),
        "--minute-feed", "sip", "--minute-ts-convention", "start",
        "--date-start", "2016-03-01", "--date-end", "2016-03-07",
        "--partition", "DEVELOPMENT_SELECTION", "--table-filter", "SEP",
        "--lookback-calendar-days", "40", "--coverage-threshold", "0.9",
        "--equity", "100000", "--tick", "0.01", "--code-sha", CODE_SHA,
        "--out-dir", str(world["tmp"] / "cli_out"), "--no-delisting-evidence", "--dry-plan",
    ]  # fmt: skip
    assert rds.main(argv) == rds.EXIT_OK
    assert json.loads(capsys.readouterr().out)["spec_sha256"] == p["spec_sha256"]
    assert _runs(world) == ()
    assert not (world["tmp"] / "cli_out").exists()


# --- refusals -------------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["revise", "defer", "stop"])
def test_non_approved_decision_is_refused_and_aborted(world: dict[str, Any], verdict: str) -> None:
    bad = _edit(world["frozen"], lambda d: d["decision"].update(decision=verdict), "bad.json")
    with pytest.raises(gov_errors.DecisionNotApprovedError):
        rds.run(**dict(world["kwargs"], spec_path=bad))
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]
    assert not (world["tmp"] / "out").exists()


def test_build_only_scope_is_refused(world: dict[str, Any]) -> None:
    def build_only(d: dict[str, Any]) -> None:
        d["decision"].update(scope=["build"], partitions=[])

    bad = _edit(world["frozen"], build_only, "buildonly.json")
    with pytest.raises(gov_errors.DecisionScopeError):
        rds.run(**dict(world["kwargs"], spec_path=bad))
    _assert_no_open(world)


def test_partition_not_covered_is_refused(world: dict[str, Any]) -> None:
    bad = _edit(
        world["frozen"], lambda d: d["decision"].update(partitions=["REPLAY_RNG001"]), "part.json"
    )
    with pytest.raises(gov_errors.DecisionPartitionError):
        rds.run(**dict(world["kwargs"], spec_path=bad))
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]


def test_spec_edited_after_the_decision_is_refused(world: dict[str, Any]) -> None:
    bad = _edit(world["frozen"], lambda d: d["universe"].update(n=4), "edited.json")
    with pytest.raises(SpecHashMismatchError):
        rds.run(**dict(world["kwargs"], spec_path=bad))
    assert _runs(world) == ()  # refused before any run row existed


def test_minutes_edited_after_the_decision_is_refused(
    world: dict[str, Any], minutes_root: Path
) -> None:
    (minutes_root / MINUTES_RELPATH).write_bytes(MINUTES_BYTES + b"edited later\n")
    with pytest.raises(gov_errors.DecisionMinutesMismatchError):
        rds.run(**world["kwargs"])
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]


@pytest.mark.parametrize(
    ("start", "end"),
    [("2015-12-01", "2016-03-07"), ("2016-03-01", "2020-03-31")],
)
def test_date_range_outside_the_partition_is_refused(
    world: dict[str, Any], start: str, end: str
) -> None:
    with pytest.raises(gov_errors.PartitionNotAuthorizedError):
        rds.run(**dict(world["kwargs"], date_start=start, date_end=end))
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]


def test_holdout_dates_are_refused_before_a_run_row_exists(world: dict[str, Any]) -> None:
    with pytest.raises(rds.DescriptiveRunRefusal, match="holdout"):
        rds.run(**dict(world["kwargs"], date_start="2022-01-01", date_end="2022-03-31"))
    assert _runs(world) == ()


@pytest.mark.parametrize("partition", ["HOLDOUT", "DEVELOPMENT_CONFIRMATION", "PAPER"])
def test_unreachable_partitions_are_refused_before_anything_is_written(
    world: dict[str, Any], partition: str
) -> None:
    with pytest.raises(rds.DescriptiveRunRefusal):
        rds.run(**dict(world["kwargs"], partition=partition))
    assert _runs(world) == ()


def test_grain_blocker_aborts_the_run(world: dict[str, Any]) -> None:
    tmp = world["tmp"]
    collapsed = tmp / "collapsed" / "daily.duckdb"
    collapsed.parent.mkdir()
    _write_daily(collapsed, with_table_column=False)
    # one row per ticker (drop the reused-ticker pair's old issuer): reuse is unobservable
    con = duckdb.connect(str(collapsed))
    con.execute("DELETE FROM tickers WHERE permaticker = 'P5'")
    con.close()
    manifest = collapsed.parent / "manifest.json"
    manifest.write_text(_manifest_for(collapsed), encoding="utf-8")
    kw = dict(world["kwargs"], daily_snapshot=collapsed, snapshot_manifest=manifest)
    with pytest.raises(Exception, match="DATA-INTEGRITY BLOCKER"):
        rds.run(**kw)
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]


def test_tampered_snapshot_fails_manifest_verification_before_a_run_opens(
    world: dict[str, Any],
) -> None:
    snap = world["kwargs"]["daily_snapshot"]
    snap.write_bytes(snap.read_bytes() + b"x")
    with pytest.raises(rds.DescriptiveRunRefusal, match="manifest verification"):
        rds.run(**world["kwargs"])
    assert _runs(world) == ()


def test_data_defect_in_minutes_aborts_the_run(world: dict[str, Any]) -> None:
    con = duckdb.connect(str(world["kwargs"]["minute_bars"]))
    con.execute("UPDATE minute_bars SET basis = 'split_adjusted' WHERE symbol = 'AAA'")
    con.close()
    with pytest.raises(Exception, match="basis"):
        rds.run(**world["kwargs"])
    _assert_no_open(world)
    assert [r.status for r in _runs(world)] == [RunStatus.ABORTED]
    assert not (world["tmp"] / "out" / "report.json").exists()


def test_existing_report_is_never_overwritten(world: dict[str, Any]) -> None:
    out = world["kwargs"]["out_dir"]
    out.mkdir()
    (out / "report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(rds.DescriptiveRunRefusal, match="never overwritten"):
        rds.run(**world["kwargs"])
    assert _runs(world) == ()


# --- the coverage denominator: a final price date alone never shrinks it -----------------------


def _delist_world(
    tmp: Path, minutes_root: Path, *, actions: tuple[tuple[str, str, str], ...]
) -> dict[str, Any]:
    snap = tmp / "daily_delist.duckdb"
    _write_daily(snap, dead_last="2016-03-03", action_rows=actions)
    manifest = tmp / "manifest_delist.json"
    manifest.write_text(_manifest_for(snap), encoding="utf-8")
    minutes = tmp / "minutes_delist.duckdb"
    _write_minutes(minutes, dead_until=date(2016, 3, 3))
    ledger = tmp / "ledger.json"
    ledger.write_text(DECIDED_LEDGER, encoding="utf-8")
    frozen = _freeze(tmp, synth_payload(exits__candidates=copy.deepcopy(SEVEN)))
    registry_path = tmp / "runs.jsonl"
    new_registry(registry_path)
    return {
        "spec_path": frozen, "registry_path": registry_path, "exposure_ledger_path": ledger,
        "daily_snapshot": snap, "snapshot_manifest": manifest, "minute_bars": minutes,
        "minute_feed": "sip", "minute_ts_convention": "start",
        "date_start": "2016-03-01", "date_end": "2016-03-07", "partition": "DEVELOPMENT_SELECTION",
        "table_filter": "SEP", "lookback_calendar_days": 40, "coverage_threshold": 0.50,
        "equity": 100_000.0, "tick": 0.01, "code_sha": CODE_SHA, "out_dir": tmp / "out",
        "delisting_actions": (), "provenance": {"vendor_export": "synthetic-v0"},
    }  # fmt: skip


def test_a_final_price_date_alone_does_not_shrink_the_denominator(
    tmp_path: Path, minutes_root: Path
) -> None:
    kw = _delist_world(tmp_path, minutes_root, actions=())
    cov = rds.run(**kw).report["coverage"]
    # DEAD's metadata says its last price date is 2016-03-03, but no listing EVIDENCE is supplied:
    # its two later symbol-days stay expected, and show up as missing (with the OLD gap: 3 missing)
    assert cov["expected"] == 15 and cov["denominator"] == 15
    assert cov["legitimate_exclusions"] == {}
    assert cov["observed"] == 12


def test_a_delisting_event_dated_after_the_decision_day_excludes_later_days_only(
    tmp_path: Path, minutes_root: Path
) -> None:
    kw = _delist_world(tmp_path, minutes_root, actions=(("2016-03-03", "delisted", "DEAD"),))
    kw["delisting_actions"] = ("delisted",)
    cov = rds.run(**kw).report["coverage"]
    assert cov["expected"] == 15
    assert cov["legitimate_exclusions"] == {"DELISTED_BEFORE_DAY": 2}  # 03-04 and 03-07 only
    assert cov["denominator"] == 13 and cov["observed"] == 12


def test_an_event_that_predates_the_decision_day_belongs_to_an_earlier_issuer(
    tmp_path: Path, minutes_root: Path
) -> None:
    # 'OLD' is a REUSED ticker: its earlier issuer was delisted 2015-12-31, long before the
    # 2016-02-29 decision day. That event must not remove the new issuer's symbol-days.
    kw = _delist_world(tmp_path, minutes_root, actions=(("2015-12-31", "delisted", "OLD"),))
    kw["delisting_actions"] = ("delisted",)
    cov = rds.run(**kw).report["coverage"]
    assert cov["legitimate_exclusions"] == {} and cov["denominator"] == 15


def test_an_unlisted_action_string_is_never_assumed(tmp_path: Path, minutes_root: Path) -> None:
    kw = _delist_world(tmp_path, minutes_root, actions=(("2016-03-03", "delisted", "DEAD"),))
    kw["delisting_actions"] = ("some_other_string",)  # the exact vendor string is the owner's input
    cov = rds.run(**kw).report["coverage"]
    assert cov["legitimate_exclusions"] == {} and cov["denominator"] == 15


# --- PU-1: the runner's reports are personal-use, labelled, and never exportable ---------------


def test_reports_carry_pu1_footer_and_sidecars_and_json_bytes_are_unstamped(
    world: dict[str, Any], tmp_path: Path
) -> None:
    from app.licensing.envelope import scope_of_file, sidecar_path
    from app.licensing.gate import PersonalScopeBlocked
    from app.licensing.output import export_file_for_external_use

    out = rds.run(**world["kwargs"])
    footer = "PERSONAL USE ONLY — not for presentation (PU-1)"
    assert footer in out.report_md.read_text(encoding="utf-8")
    # report.json is hashed into the run registry and is never altered by labelling
    assert footer not in out.report_json.read_text(encoding="utf-8")
    assert out.report_sha256 == file_sha256(out.report_json)
    for artifact in (out.report_json, out.report_md):
        assert sidecar_path(artifact).is_file()
        assert scope_of_file(artifact).blocks_presentation
        with pytest.raises(PersonalScopeBlocked):
            export_file_for_external_use(artifact, tmp_path / "out" / artifact.name)
