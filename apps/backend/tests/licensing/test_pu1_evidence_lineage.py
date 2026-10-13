"""PU-1: Evidence KPI/panel input lineage is traced per row; one restricted row restricts only
itself and the panel that is the most restrictive of its rows."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import app.licensing as lic
from app.licensing import evidence_lineage as lineage
from app.licensing.scopes import LicenseScope
from app.ops.kpis import KpiInputs, build_scorecard

BACKEND = Path(__file__).resolve().parents[2]
OWNER = "owner_generated_records"
MARKET = "alpaca_market_data"
FOOTER = lic.PERSONAL_FOOTER


def _zero_inputs() -> KpiInputs:
    return KpiInputs(
        reconciliation_runs=0,
        reconciliation_passes=0,
        reconciliation_discrepancies=0,
        replay_checked=0,
        replay_matched=0,
        orders_risk_passed=0,
        orders_rejected_by_risk=0,
        orders_rejected_by_broker=0,
        breaker_trips=0,
        breaker_resets=0,
        breaker_recovery_minutes=None,
        orders_submitted=0,
        fills_ingested=0,
        expected_snapshot_days=0,
        actual_snapshot_days=0,
    )


def test_replay_consistency_depends_on_marked_to_market_pnl_and_other_rows_do_not() -> None:
    rows = lineage.kpi_row_sources()
    assert rows["replay_consistency"] == (MARKET, OWNER)
    for key, srcs in rows.items():
        if key != "replay_consistency":
            assert srcs == (OWNER,), key
    assert lic.effective_scope(sources=rows["replay_consistency"]) is LicenseScope.PERSONAL
    assert lic.effective_scope(sources=rows["fill_success"]) is LicenseScope.COMMERCIAL_OK


def test_panel_lineage_confidence_is_market_dependent_strategies_is_not() -> None:
    assert lineage.confidence_sources() == (MARKET, OWNER)
    assert lineage.strategies_sources() == (OWNER,)
    assert lineage.kpi_scorecard_sources() == (MARKET, OWNER)


def test_every_scorecard_row_is_classified_and_every_input_has_a_trace() -> None:
    keys = {r["key"] for r in build_scorecard(_zero_inputs())}
    assert keys <= set(lineage.KPI_ROW_INPUTS)
    everything = [i for ins in lineage.KPI_ROW_INPUTS.values() for i in ins]
    everything += list(lineage.CONFIDENCE_INPUTS) + list(lineage.STRATEGIES_INPUTS)
    assert everything
    for i in everything:
        assert i.trace.strip(), i
        if isinstance(i, lineage.BrokerFieldInput):
            assert i.fields, i


def test_the_replay_row_traces_the_breaker_trip_recompute_end_to_end() -> None:
    inp = [
        i
        for i in lineage.KPI_ROW_INPUTS["replay_consistency"]
        if isinstance(i, lineage.BrokerFieldInput)
    ]
    assert len(inp) == 1 and inp[0].kind == "position" and inp[0].fields == ("unrealized_pl",)
    for needle in ("replay.py", "circuit_breaker.py", "position_sync.py", "unrealized_pnl_now"):
        assert needle in inp[0].trace, needle


async def test_a_row_with_market_data_lineage_restricts_only_itself_and_the_panel(
    client, monkeypatch
) -> None:
    # fill_success newly reads a marked-to-market field: only THAT row becomes PERSONAL
    inputs = dict(lineage.KPI_ROW_INPUTS)
    inputs["fill_success"] = (
        *inputs["fill_success"],
        lineage.BrokerFieldInput("position", ("market_value",), "test"),
    )
    # ... and replay is made owner-only so that this test isolates the injected row
    inputs["replay_consistency"] = (lineage.RecordInput("replay counters", "test"),)
    monkeypatch.setattr(lineage, "KPI_ROW_INPUTS", inputs)
    body = (await client.get("/api/v1/evidence/summary")).json()
    rows = {r["key"]: r for r in body["kpis"]["rows"]}
    assert rows["fill_success"]["license_scope"] == "PERSONAL"
    assert rows["fill_success"]["license_sources"] == [MARKET, OWNER]
    assert rows["fill_success"]["license_footer"] == FOOTER
    for key, row in rows.items():
        if key != "fill_success":
            assert row["license_scope"] == "COMMERCIAL_OK", key
            assert row["license_footer"] is None, key
    # the kpis panel is the most restrictive of its rows; an unrelated panel is untouched
    assert body["panels"]["kpis"]["license_scope"] == "PERSONAL"
    assert body["panels"]["strategies"]["license_scope"] == "COMMERCIAL_OK"


async def test_kpis_panel_is_presentable_only_when_every_row_is(client, monkeypatch) -> None:
    inputs = {k: (lineage.RecordInput("owner rows", "test"),) for k in lineage.KPI_ROW_INPUTS}
    monkeypatch.setattr(lineage, "KPI_ROW_INPUTS", inputs)
    body = (await client.get("/api/v1/evidence/summary")).json()
    assert body["panels"]["kpis"]["license_scope"] == "COMMERCIAL_OK"
    assert all(r["license_scope"] == "COMMERCIAL_OK" for r in body["kpis"]["rows"])
    # the confidence panel is derived separately and keeps its own (market-dependent) lineage
    assert body["panels"]["confidence"]["license_scope"] == "PERSONAL"


async def test_an_unclassified_kpi_row_is_unknown_and_blocks_the_panel(client, monkeypatch) -> None:
    inputs = dict(lineage.KPI_ROW_INPUTS)
    del inputs["breaker_recovery"]
    monkeypatch.setattr(lineage, "KPI_ROW_INPUTS", inputs)
    body = (await client.get("/api/v1/evidence/summary")).json()
    rows = {r["key"]: r for r in body["kpis"]["rows"]}
    assert rows["breaker_recovery"]["license_scope"] == "UNKNOWN"
    assert rows["breaker_recovery"]["license_footer"] == FOOTER
    assert body["panels"]["kpis"]["license_scope"] == "UNKNOWN"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_ops_kpis_report_marks_each_row_with_its_own_scope() -> None:
    mod = _load_script("ops_kpis")
    rows = build_scorecard(_zero_inputs())
    r = {
        "generated_at": "t",
        "git_sha": "x",
        "scope": {"kind": "platform"},
        "kpis": rows,
        "summary": {"ok": 0, "watch": 0, "n_a": len(rows)},
        "latency_note": "n",
    }
    md = mod._render(r)
    by_label = {k["label"]: k["key"] for k in rows}
    lines = {ln.split("|")[1].strip(): ln for ln in md.splitlines() if ln.startswith("| ")}
    for label, key in by_label.items():
        want = "PERSONAL" if key == "replay_consistency" else "COMMERCIAL_OK"
        assert lines[label].rstrip().endswith(f"| {want} |"), (label, lines[label])
    assert lic.PERMISSION_NOTE in md
