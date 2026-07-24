"""Authoritative Account-4 probe (R5c-2b) — evidence, not assumption.

The probe reads the live application database read-only and refuses anything short of the conjunction
the platform actually encodes: a governed non-running status AND a schema-valid ACTIVE operational hold
with a recognized reason and a revision. No synthetic PAUSED status is invented anywhere; the raw status
is recorded verbatim and the safety verdict sits beside it.

Every `StrategyStatus` value the production schema defines is enumerated below, so a status added later
cannot be accepted by default.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.db.enums import StrategyStatus
from app.validation.account4_probe import (
    GOVERNED_NON_RUNNING_STATUSES,
    Account4ProbeError,
    assert_account4_unchanged,
    positions_digest,
    probe_account4,
)

STRATEGY_ID = 11
BROKER = "alpaca"
MODE = "paper"
HOLD_REASON = "AWAITING_PRODUCTION_SIZING_VALIDATION"


def _hold(*, status: str = "ACTIVE", reason: str = HOLD_REASON, rev: int = 2,
          schema_version: int = 1) -> str:
    return json.dumps({"schema_version": schema_version, "_rev": rev, "status": status,
                       "reason_code": reason, "effective_at": "2026-07-20T22:48:22Z",
                       "placed_by": "user:4"})


def _make_db(path: Path, *, account_id: int = 4, broker: str = BROKER, mode: str = MODE,
             status: str = "idle", hold: str | None = None, positions=(), open_orders=(),
             include_hold: bool = True) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, broker TEXT, mode TEXT, label TEXT);
        CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE strategy_state (id INTEGER PRIMARY KEY, strategy_id INTEGER, key TEXT, value TEXT);
        CREATE TABLE symbols (id INTEGER PRIMARY KEY, ticker TEXT);
        CREATE TABLE positions (id INTEGER PRIMARY KEY, account_id INTEGER, symbol_id INTEGER,
                                side TEXT, qty TEXT, market_value TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, account_id INTEGER, status TEXT);
        """)
    con.execute("INSERT INTO accounts VALUES (?, ?, ?, ?)",
                [account_id, broker, mode, "momentum-daily forward"])
    con.execute("INSERT INTO strategies VALUES (?, ?)", [STRATEGY_ID, status])
    if include_hold:
        con.execute("INSERT INTO strategy_state VALUES (1, ?, 'operational_hold', ?)",
                    [STRATEGY_ID, hold if hold is not None else _hold()])
    for i, (ticker, side, qty, market_value) in enumerate(positions, start=1):
        con.execute("INSERT INTO symbols VALUES (?, ?)", [i, ticker])
        con.execute("INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)",
                    [i, account_id, i, side, qty, market_value])
    for i, order_status in enumerate(open_orders, start=1):
        con.execute("INSERT INTO orders VALUES (?, ?, ?)", [i, account_id, order_status])
    con.commit()
    con.close()
    return path


@pytest.fixture
def db(tmp_path):
    return _make_db(tmp_path / "workbench.sqlite",
                    positions=[("MSFT", "long", "19", "5700.00"), ("F", "long", "450.0", "5000.00")],
                    open_orders=["filled", "canceled"])          # terminal orders are not open


def _probe(path, **kw):
    kw.setdefault("strategy_id", STRATEGY_ID)
    kw.setdefault("expected_broker", BROKER)
    kw.setdefault("expected_broker_mode", MODE)
    return probe_account4(path, **kw)


# ---- the passing state: idle + ACTIVE hold ---------------------------------------------------------

def test_idle_with_an_active_hold_is_safely_paused_and_held(db):
    p = _probe(db)
    assert p.account_id == 4 and p.broker == BROKER and p.broker_mode == MODE
    assert p.raw_strategy_status == "idle"                       # recorded verbatim
    assert p.strategy_non_running is True
    assert p.account4_operational_hold_active is True
    assert p.account4_is_safely_paused_and_held is True
    assert p.hold_reason_code == HOLD_REASON and p.hold_rev == 2 and p.hold_schema_version == 1
    assert p.open_order_count == 0                               # filled/canceled are terminal
    assert p.positions_count == 2 and len(p.positions_digest) == 64
    assert p.probed_at.endswith("Z") and len(p.comparison_digest) == 64


def test_no_synthetic_paused_status_appears_in_the_evidence(db):
    d = _probe(db).to_open_provenance()
    assert d["raw_strategy_status"] == "idle"
    assert "PAUSED" not in json.dumps(d).upper().replace("PAUSED_AND_HELD", "")
    # the raw fact and the derived verdict are separate keys
    assert {"strategy_non_running", "account4_operational_hold_active",
            "account4_is_safely_paused_and_held"} <= set(d)


def test_the_probe_feeds_the_commit_protocols_own_before_after_probe(db):
    commit_probe = _probe(db).to_commit_probe()
    assert commit_probe.hold_status == "ACTIVE"
    assert commit_probe.hold_reason_code == HOLD_REASON
    assert commit_probe.hold_rev == 2
    assert commit_probe.strategy_status == "idle"
    assert len(commit_probe.digest()) == 64


# ---- the status-to-safety mapping is governed and narrow --------------------------------------------

def test_the_governed_non_running_set_is_exactly_idle():
    assert GOVERNED_NON_RUNNING_STATUSES == frozenset({"idle"})


@pytest.mark.parametrize("status", sorted(s.value for s in StrategyStatus))
def test_every_known_status_is_adjudicated(status, tmp_path):
    """Enumerates EVERY StrategyStatus the schema defines: `idle` passes, everything else fails closed.
    A status added later is refused until adjudicated, never accepted by default."""
    path = _make_db(tmp_path / f"{status}.sqlite", status=status)
    if status in GOVERNED_NON_RUNNING_STATUSES:
        assert _probe(path).account4_is_safely_paused_and_held is True
    else:
        with pytest.raises(Account4ProbeError, match="non-running set"):
            _probe(path)


def test_an_unknown_future_status_fails_closed(tmp_path):
    path = _make_db(tmp_path / "future.sqlite", status="warming_up")
    with pytest.raises(Account4ProbeError, match="non-running set"):
        _probe(path)


def test_an_empty_status_fails_closed(tmp_path):
    path = _make_db(tmp_path / "empty.sqlite", status="")
    with pytest.raises(Account4ProbeError, match="no status recorded"):
        _probe(path)


# ---- the two failure directions the review named ----------------------------------------------------

def test_non_running_without_an_active_hold_fails(tmp_path):
    path = _make_db(tmp_path / "nohold.sqlite", status="idle", include_hold=False)
    with pytest.raises(Account4ProbeError, match="carries no operational hold"):
        _probe(path)


def test_a_cleared_hold_fails(tmp_path):
    path = _make_db(tmp_path / "cleared.sqlite", hold=_hold(status="CLEARED"))
    with pytest.raises(Account4ProbeError, match="not ACTIVE"):
        _probe(path)


def test_an_active_hold_over_a_running_status_fails(tmp_path):
    path = _make_db(tmp_path / "running.sqlite", status="paper", hold=_hold())
    with pytest.raises(Account4ProbeError, match="non-running set"):
        _probe(path)


def test_an_active_hold_over_a_transitional_status_fails(tmp_path):
    path = _make_db(tmp_path / "pending.sqlite", status="pending_live", hold=_hold())
    with pytest.raises(Account4ProbeError, match="non-running set"):
        _probe(path)


# ---- hold shape ------------------------------------------------------------------------------------

def test_an_unrecognized_hold_reason_fails(tmp_path):
    path = _make_db(tmp_path / "reason.sqlite", hold=_hold(reason="BECAUSE_I_SAID_SO"))
    with pytest.raises(Account4ProbeError, match="not a recognized governed"):
        _probe(path)


def test_a_missing_hold_revision_fails(tmp_path):
    blob = json.loads(_hold())
    del blob["_rev"]
    path = _make_db(tmp_path / "norev.sqlite", hold=json.dumps(blob))
    with pytest.raises(Account4ProbeError, match="no revision"):
        _probe(path)


def test_a_legacy_unversioned_hold_marker_fails(tmp_path):
    """The pre-schema marker (no schema_version) must not be read as a governed hold."""
    path = _make_db(tmp_path / "legacy.sqlite",
                    hold=json.dumps({"status": "PAUSED", "paused_at": "2026-07-20T22:48:22Z"}))
    with pytest.raises(Account4ProbeError, match="schema version"):
        _probe(path)


def test_an_unreadable_hold_fails(tmp_path):
    path = _make_db(tmp_path / "corrupt.sqlite", hold="{not json")
    with pytest.raises(Account4ProbeError, match="unreadable"):
        _probe(path)


# ---- identity, orders, and availability -------------------------------------------------------------

def test_a_broker_registration_mismatch_fails(db):
    with pytest.raises(Account4ProbeError, match="expects alpaca/live"):
        _probe(db, expected_broker_mode="live")


def test_a_missing_account_fails(tmp_path):
    path = _make_db(tmp_path / "acct.sqlite", account_id=9)
    with pytest.raises(Account4ProbeError, match="account 4 is not present"):
        _probe(path)


def test_a_missing_strategy_fails(db):
    with pytest.raises(Account4ProbeError, match="strategy 99 is not present"):
        _probe(db, strategy_id=99)


@pytest.mark.parametrize("status", ["pending_risk", "pending_submit", "submitted",
                                    "partially_filled"])
def test_an_open_order_on_the_live_book_fails(status, tmp_path):
    path = _make_db(tmp_path / f"order-{status}.sqlite", open_orders=[status])
    with pytest.raises(Account4ProbeError, match="open order"):
        _probe(path)


def test_a_missing_database_fails(tmp_path):
    with pytest.raises(Account4ProbeError, match="does not exist"):
        _probe(tmp_path / "absent.sqlite")


def test_the_probe_opens_the_database_read_only(db):
    """The probe cannot write to the live application database even if asked to."""
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("UPDATE strategies SET status = 'paper'")
    con.close()
    assert _probe(db).raw_strategy_status == "idle"               # unchanged


# ---- the positions digest is price-independent ------------------------------------------------------

def test_the_positions_digest_ignores_market_value(tmp_path):
    a = _make_db(tmp_path / "a.sqlite", positions=[("MSFT", "long", "19", "5700.00")])
    b = _make_db(tmp_path / "b.sqlite", positions=[("MSFT", "long", "19", "9999.99")])
    assert _probe(a).positions_digest == _probe(b).positions_digest


def test_the_positions_digest_is_stable_across_quantity_forms():
    assert positions_digest([("MSFT", "long", "19")]) == positions_digest([("msft", "LONG", "19.00")])
    assert positions_digest([("MSFT", "long", "19")]) != positions_digest([("MSFT", "long", "20")])
    assert positions_digest([("MSFT", "long", "19")]) != positions_digest([("MSFT", "short", "19")])


def test_the_positions_digest_is_order_independent():
    rows = [("F", "long", "450"), ("MSFT", "long", "19")]
    assert positions_digest(rows) == positions_digest(list(reversed(rows)))


def test_a_non_numeric_quantity_fails(tmp_path):
    path = _make_db(tmp_path / "qty.sqlite", positions=[("MSFT", "long", "many", "1")])
    with pytest.raises(Account4ProbeError, match="not a number"):
        _probe(path)


# ---- pre-decision vs pre-commit ---------------------------------------------------------------------

def test_identical_probes_are_accepted(db):
    assert_account4_unchanged(_probe(db), _probe(db))


def test_a_hold_revision_bump_between_probes_stops_the_session(tmp_path):
    path = _make_db(tmp_path / "rev.sqlite")
    before = _probe(path)
    con = sqlite3.connect(path)
    con.execute("UPDATE strategy_state SET value = ? WHERE key = 'operational_hold'", [_hold(rev=3)])
    con.commit()
    con.close()
    after = _probe(path)                                          # still individually safe
    assert after.account4_is_safely_paused_and_held is True
    with pytest.raises(Account4ProbeError, match="hold_rev"):
        assert_account4_unchanged(before, after)


def test_a_position_change_between_probes_stops_the_session(tmp_path):
    path = _make_db(tmp_path / "pos.sqlite", positions=[("MSFT", "long", "19", "1")])
    before = _probe(path)
    con = sqlite3.connect(path)
    con.execute("UPDATE positions SET qty = '20' WHERE symbol_id = 1")
    con.commit()
    con.close()
    with pytest.raises(Account4ProbeError, match="positions_digest"):
        assert_account4_unchanged(before, _probe(path))


def test_an_order_appearing_between_probes_stops_the_session(tmp_path):
    path = _make_db(tmp_path / "ord.sqlite")
    before = _probe(path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO orders VALUES (99, 4, 'submitted')")
    con.commit()
    con.close()
    with pytest.raises(Account4ProbeError):                       # the second probe refuses outright
        _probe(path)
    assert before.open_order_count == 0
