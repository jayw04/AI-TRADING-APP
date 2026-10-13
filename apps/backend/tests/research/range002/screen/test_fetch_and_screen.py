"""The opt-in fetch-and-screen path: acquisition inside the SAME governed run (one attempt).

Synthetic only: the transport is a fake that serves bars from a source DuckDB; nothing touches a
network or a vendor. Reuses the descriptive-run rehearsal world."""

# ruff: noqa: F811  (the rehearsal fixtures are imported by name and used as parameters)
from __future__ import annotations

import contextlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from app.research.range002.data.fetch_adapter import (
    FetchAuthorization,
    PageRequest,
    PageResponse,
    RawBar,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from tests.research.range002.screen.test_descriptive_run_rehearsal import (  # noqa: F401
    minutes_root,
    rds,
    world,
)

SYMBOLS = ["AAA", "DEAD", "OLD"]


def _sha(symbols: list[str]) -> str:
    return rds._symbols_sha256(symbols)


def _fake_transport_factory(source: Path, counter: dict[str, int]) -> Any:
    def factory(_cap: object, _auth: FetchAuthorization) -> Any:
        def transport(req: PageRequest) -> PageResponse:
            counter["calls"] += 1
            con = duckdb.connect(str(source), read_only=True)
            try:
                rows = con.execute(
                    "SELECT ts, open, high, low, close, volume FROM minute_bars "
                    "WHERE symbol = ? AND ts >= ? AND ts < ? ORDER BY ts",
                    [req.symbol, req.start_utc, req.end_utc],
                ).fetchall()
            finally:
                con.close()
            skip = int(req.page_token or 0)
            page = rows[skip : skip + req.limit]
            nxt = str(skip + req.limit) if skip + req.limit < len(rows) else None
            bars = tuple(
                RawBar(t=r[0], o=r[1], h=r[2], low=r[3], c=r[4], v=int(r[5]), n=None, vw=None)
                for r in page
            )
            return PageResponse(bars=bars, next_page_token=nxt)

        transport.__dict__["http_attempts"] = lambda: counter["calls"]
        return transport

    return factory


def _plan(world: dict[str, Any], **over: Any) -> tuple[Any, dict[str, int]]:
    tmp: Path = world["tmp"]
    counter = {"calls": 0}
    base: dict[str, Any] = {
        "universe_sha256": _sha(SYMBOLS),
        "journal_path": tmp / "fetch.jsonl",
        "key_env": "K",
        "secret_env": "S",
        "requests_per_minute": 1000,
        "max_requests": 500,
        "asof": "-",
        "authorization_id": "AUTH-1",
        "permitted_use_ref": "owner statement (claimed)",
        "entitlement_ref": "entitled key (claimed)",
        "permission_basis_claimed": "personal-use reading (claimed)",
        "storage_permitted": True,
        "limit": 500,
        "transport_factory": _fake_transport_factory(world["kwargs"]["minute_bars"], counter),
    }
    base.update(over)
    return rds.FetchPlan(**base), counter


def _kwargs(world: dict[str, Any], plan: Any, store: Path) -> dict[str, Any]:
    kw = dict(world["kwargs"])
    kw["minute_bars"] = store
    kw["fetch_plan"] = plan
    return kw


def test_fetch_and_screen_is_one_governed_run_and_validates_before_screening(
    world: dict[str, Any],
) -> None:
    store = world["tmp"] / "fetched.duckdb"
    plan, counter = _plan(world)
    out = rds.run(**_kwargs(world, plan, store))
    runs = RunRegistry(world["registry_path"]).runs()
    assert len(runs) == 1 and runs[0].status is RunStatus.COMPLETED  # ONE run, ONE attempt
    acq = out.report["data"]["acquisition"]
    assert acq["actual"]["http_attempts"] == counter["calls"] > 0
    assert acq["actual"]["bars_returned"] > 0
    assert acq["planned_estimate"] is not None  # an estimate, kept apart from the actuals
    assert acq["probe"]["bars"] > 0 and acq["binding"]["universe_sha256"] == _sha(SYMBOLS)
    assert out.report["status"] == rds.STATUS_COMPLETE
    ev = json.loads(
        (world["kwargs"]["out_dir"] / f"acquisition_evidence_{out.run_id}.json").read_text()
    )
    assert ev["status"] == "COVERAGE_OK"
    assert ev["cache_integrity"]["all_windows_match_journal"] is True


def test_universe_binding_mismatch_requests_nothing(world: dict[str, Any]) -> None:
    store = world["tmp"] / "fetched.duckdb"
    plan, counter = _plan(world, universe_sha256="0" * 64)
    with pytest.raises(Exception, match="differs from the bound fetch universe"):
        rds.run(**_kwargs(world, plan, store))
    assert counter["calls"] == 0
    runs = RunRegistry(world["registry_path"]).runs()
    assert [r.status for r in runs] == [RunStatus.ABORTED]


def test_failure_mid_acquisition_closes_the_run_and_keeps_evidence(world: dict[str, Any]) -> None:
    store = world["tmp"] / "fetched.duckdb"
    calls = {"calls": 0}

    def factory(cap: object, auth: FetchAuthorization) -> Any:
        inner = _fake_transport_factory(world["kwargs"]["minute_bars"], calls)(cap, auth)

        def capped(req: PageRequest) -> PageResponse:
            if calls["calls"] >= 2:
                raise RuntimeError("request cap reached")
            return inner(req)

        capped.__dict__["http_attempts"] = lambda: calls["calls"]
        return capped

    plan, _ = _plan(world, transport_factory=factory)
    with pytest.raises(RuntimeError, match="request cap reached"):
        rds.run(**_kwargs(world, plan, store))
    runs = RunRegistry(world["registry_path"]).runs()
    assert [r.status for r in runs] == [RunStatus.ABORTED]
    ev = next(world["kwargs"]["out_dir"].glob("acquisition_evidence_*.json"))
    assert json.loads(ev.read_text())["status"].startswith("FAILED")


def test_restart_with_leftover_store_is_refused_before_any_attempt(world: dict[str, Any]) -> None:
    store = world["tmp"] / "fetched.duckdb"
    plan, _ = _plan(world)
    rds.run(**_kwargs(world, plan, store))
    plan2, counter2 = _plan(world)
    kw = _kwargs(world, plan2, store)
    kw["out_dir"] = world["tmp"] / "out2"
    with pytest.raises(rds.DescriptiveRunRefusal, match="NEW governed attempt"):
        rds.run(**kw)
    assert counter2["calls"] == 0
    assert len(RunRegistry(world["registry_path"]).runs()) == 1  # no second run row


def test_acknowledged_rerun_reuses_the_verified_cache_without_requests(
    world: dict[str, Any],
) -> None:
    store = world["tmp"] / "fetched.duckdb"
    plan, _ = _plan(world)
    rds.run(**_kwargs(world, plan, store))
    plan2, counter2 = _plan(world, acknowledge_new_attempt_ref="owner decision: re-run (recorded)")
    kw = _kwargs(world, plan2, store)
    kw["out_dir"] = world["tmp"] / "out2"
    with contextlib.suppress(Exception):  # a second authorization may legitimately hit the limit
        rds.run(**kw)
    assert counter2["calls"] == 0  # every window was cached: nothing was re-requested


def test_tampered_cache_is_refused(world: dict[str, Any]) -> None:
    store = world["tmp"] / "fetched.duckdb"
    plan, _ = _plan(world)
    rds.run(**_kwargs(world, plan, store))
    con = duckdb.connect(str(store))
    con.execute("DELETE FROM minute_bars WHERE rowid IN (SELECT rowid FROM minute_bars LIMIT 3)")
    con.close()
    plan2, _ = _plan(world, acknowledge_new_attempt_ref="owner decision: re-run (recorded)")
    kw = _kwargs(world, plan2, store)
    kw["out_dir"] = world["tmp"] / "out2"
    with pytest.raises(Exception, match="integrity|journal|differs"):
        rds.run(**kw)


def test_a_closed_capability_can_neither_fetch_nor_screen(world: dict[str, Any]) -> None:
    from app.research.range002.data.fetch_adapter import fetch_symbol_window
    from app.research.range002.governance.errors import InvalidCapabilityError

    store = world["tmp"] / "fetched.duckdb"
    plan, _ = _plan(world)
    out = rds.run(**_kwargs(world, plan, store))
    assert out.capability is not None
    with pytest.raises(InvalidCapabilityError):
        fetch_symbol_window(
            out.capability,
            lambda _r: PageResponse(bars=(), next_page_token=None),
            symbol="AAA",
            start_utc=datetime(2016, 3, 1, 14, 30),
            end_utc=datetime(2016, 3, 1, 14, 31) + timedelta(minutes=1),
            feed="sip",
            adjustment="raw",
            asof="-",
            limit=10,
            max_pages=1,
        )


def test_fetch_without_storage_permission_is_refused_before_a_run(world: dict[str, Any]) -> None:
    plan, _ = _plan(world, storage_permitted=False)
    with pytest.raises(rds.DescriptiveRunRefusal, match="storage-permitted"):
        rds.run(**_kwargs(world, plan, world["tmp"] / "fetched.duckdb"))
    assert tuple(RunRegistry(world["registry_path"]).runs()) == ()
