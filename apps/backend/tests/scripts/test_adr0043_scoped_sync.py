"""The ADR-0043 scoped sync must be narrow BY CONSTRUCTION, not by configuration.

``ADR0043_RUNTIME_TARGET_BINDING_MISMATCH`` happened because a correct default was silently
overridden by the deployed environment. So these tests do not merely check that the tool behaves on
a well-formed host — they check that the *shape* of the module forecloses the failure: the target is
unreachable from the environment, there is no loop, no scheduler, no registry, and no mutating
broker method. A behavioural test alone would pass on a module one edit away from being wrong again.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

import pytest

from app.services.day_change_basis import (
    BROKER_LAST_EQUITY,
    PRIOR_SESSION_CLOSE_PROXY,
    UNAVAILABLE,
    DayChange,
)
from scripts import adr0043_scoped_sync as mod
from scripts.adr0043_scoped_sync import (
    EXPECTED_BROKER_ACCOUNT,
    FORBIDDEN_BROKER_ACCOUNTS,
    SCOPED_ACCOUNT_ID,
    SCOPED_USER_ID,
    ScopedSyncRefused,
    assess_broker_identity,
    assess_position_manifest,
    count_open_orders,
    normalize_account_snapshot,
    scoped_sync,
)
from scripts.adr0043_session_open import ReadOnlyBrokerView, SessionOpenRefused, check_flat

SOURCE = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _strip_prose(tree: ast.Module) -> str:
    """The module's own source, with comments and docstrings removed.

    The structural checks below search for forbidden constructs by name, and the module *documents*
    every one of them — it explains why it does not use ``BrokerRegistry``, why the scheduler is not
    the answer, why the target is not ``os.environ``. Searching the raw file would flag that prose
    and, worse, would pressure a future author to delete the explanation to make a test pass. So the
    checks run against code only.
    """
    clone = ast.parse(ast.unparse(tree))
    for node in ast.walk(clone):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(clone)


CODE = _strip_prose(TREE)


# ---------------------------------------------------------------------------- property 1
def test_target_is_frozen_constants_not_environment():
    assert SCOPED_USER_ID == 3
    assert SCOPED_ACCOUNT_ID == 3


def test_module_reads_no_environment_variable_at_all():
    """The defect was an env override. The strongest available control is that the module never
    consults the environment, so there is nothing for a host to override."""
    offenders = [
        ast.dump(node)
        for node in ast.walk(TREE)
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}
    ]
    assert offenders == [], f"the scoped sync must not read the environment: {offenders}"
    assert "os.environ" not in CODE
    assert "getenv" not in CODE


# ---------------------------------------------------------------------------- property 2
def test_credentials_are_requested_for_the_frozen_user_only():
    """``credentials_for_mode`` must be called with the constant, never with a value derived from a
    row, an argument, or the environment."""
    factory = inspect.getsource(mod.build_scoped_adapter)
    assert 'credentials_for_mode("paper", SCOPED_USER_ID, sf)' in factory
    # The registry decrypts every user's credentials in load_all(); it must not appear in code.
    assert "BrokerRegistry" not in CODE


def test_registry_is_never_imported():
    imported = {
        alias.name
        for node in ast.walk(TREE)
        if isinstance(node, ast.ImportFrom | ast.Import)
        for alias in node.names
    }
    assert "BrokerRegistry" not in imported


# ---------------------------------------------------------------------------- property 3
def test_expected_broker_account_is_accepted():
    ok, detail = assess_broker_identity(EXPECTED_BROKER_ACCOUNT)
    assert ok, detail


@pytest.mark.parametrize("number", sorted(FORBIDDEN_BROKER_ACCOUNTS))
def test_forbidden_broker_account_is_refused_by_name(number):
    ok, detail = assess_broker_identity(number)
    assert not ok
    assert number in detail
    assert "FORBIDDEN" in detail


def test_account_1_broker_account_is_in_the_forbidden_set():
    """Naming it is the point: a mismatch report must say *whose* account was nearly synced."""
    assert "PA3QRX9KSPXA" in FORBIDDEN_BROKER_ACCOUNTS


@pytest.mark.parametrize("number", [None, "", "   ", "PA00000000000", "pa34usw0q8uo"])
def test_unknown_or_missing_broker_account_is_refused(number):
    ok, _ = assess_broker_identity(number)
    assert not ok, f"{number!r} must not be accepted as the account-3 broker identity"


# ---------------------------------------------------------------------------- property 5 / 6
def test_there_is_no_account_loop():
    """No ``for`` in this module may iterate accounts. The loops that exist iterate the (already
    manifest-gated) position list and the stale-symbol list, both of which are account-3 scoped."""
    assert "sync_all" not in CODE
    assert "select(Account)" not in CODE
    # Every SQL statement that names a scoped table must bind the account. Unparsed code puts each
    # statement on one line, so the whole WHERE clause travels with the FROM.
    lines = CODE.splitlines()
    for stmt in ("FROM accounts ", "FROM accounts_state", "FROM positions", "FROM risk_reservations"):
        for line_no, line in enumerate(lines, start=1):
            if stmt in line:
                assert "account_id = :a" in line or "WHERE id = :a" in line, (
                    f"unscoped read of {stmt!r} at line {line_no}: {line}"
                )


def test_every_sql_write_is_bound_to_account_three():
    """The stale-position DELETE is the one statement a sync is most likely to write unscoped."""
    for line in CODE.splitlines():
        if "DELETE FROM" in line:
            assert "account_id = :a" in line, f"unscoped delete: {line}"


def test_no_scheduler_is_constructed():
    assert "scheduler" not in CODE.lower()
    assert "apscheduler" not in CODE.lower()


# ---------------------------------------------------------------------------- property 7
def test_read_only_broker_allows_exactly_the_three_read_methods():
    class Spy:
        def get_account(self):
            return {"account_number": EXPECTED_BROKER_ACCOUNT}

        def get_positions(self):
            return []

        def list_orders(self):
            return []

        def submit_order(self, *a, **k):  # pragma: no cover - must never be reached
            raise AssertionError("submit_order was reachable")

        def close_position(self, *a, **k):  # pragma: no cover
            raise AssertionError("close_position was reachable")

    proxy = ReadOnlyBrokerView(Spy())
    assert proxy.get_account()["account_number"] == EXPECTED_BROKER_ACCOUNT
    assert proxy.get_positions() == []
    assert proxy.list_orders() == []


@pytest.mark.parametrize(
    "method",
    ["submit_order", "close_position", "cancel_order", "close_all_positions", "replace_order",
     "connect", "disconnect", "credentials"],
)
def test_read_only_broker_refuses_every_other_attribute(method):
    """The proxy is the one shared with ``adr0043_session_open``, so it raises that tool's refusal
    — which is why the scoped sync catches the BASE class rather than only its own subclass."""

    class Spy:
        pass

    proxy = ReadOnlyBrokerView(Spy())
    with pytest.raises(SessionOpenRefused, match="read-only allowlist"):
        getattr(proxy, method)


# ---------------------------------------------------------------------------- property 9
def test_frozen_manifest_accepts_exactly_msft_19_long():
    ok, detail = assess_position_manifest([{"symbol": "MSFT", "qty": "19", "side": "long"}])
    assert ok, detail


@pytest.mark.parametrize(
    ("positions", "why"),
    [
        ([], "an empty book is not the manifest"),
        ([{"symbol": "MSFT", "qty": "18", "side": "long"}], "wrong quantity"),
        ([{"symbol": "MSFT", "qty": "20", "side": "long"}], "wrong quantity"),
        ([{"symbol": "MSFT", "qty": "19", "side": "short"}], "wrong side"),
        ([{"symbol": "AAPL", "qty": "19", "side": "long"}], "wrong symbol"),
        (
            [
                {"symbol": "MSFT", "qty": "19", "side": "long"},
                {"symbol": "IEUS", "qty": "5", "side": "long"},
            ],
            "an extra leg",
        ),
    ],
)
def test_frozen_manifest_refuses_any_other_book(positions, why):
    ok, detail = assess_position_manifest(positions)
    assert not ok, why
    assert "does not match the frozen Phase-0 manifest" in detail


def test_a_position_with_no_symbol_is_refused_on_its_own_terms():
    """Refused before the comparison: an unnamed position cannot be shown equal or unequal to the
    manifest, and treating it as "not MSFT" would report the wrong reason."""
    ok, detail = assess_position_manifest([{"symbol": "", "qty": "19", "side": "long"}])
    assert not ok
    assert "no symbol" in detail


def test_open_orders_refuse_the_run():
    """"Nothing in flight" is the SHARED check_flat, so the scoped sync and the session-open tool
    refuse a non-flat account under one name and one code."""
    with pytest.raises(SessionOpenRefused, match="open orders or held reservations"):
        check_flat(1, 0)


def test_held_reservations_refuse_the_run():
    with pytest.raises(SessionOpenRefused, match="open orders or held reservations"):
        check_flat(0, 2)


def test_a_flat_account_passes_the_shared_check():
    assert check_flat(0, 0) == {"open_orders": 0, "held_reservations": 0, "clean": True}


def test_refusal_never_offers_to_normalize():
    """The message must tell the operator to investigate, not imply the tool could fix it."""
    _, detail = assess_position_manifest([{"symbol": "MSFT", "qty": "5", "side": "long"}])
    assert "does not normalize" in detail


def test_count_open_orders_ignores_terminal_statuses():
    orders = [
        {"status": "filled"},
        {"status": "canceled"},
        {"status": "expired"},
        {"status": "new"},
        {"status": "PARTIALLY_FILLED"},
    ]
    assert count_open_orders(orders) == 2
    assert count_open_orders(None) == 0


# ---------------------------------------------------------------------------- normalizer parity
def test_normalizer_matches_the_sweep_service_exactly():
    """The local copy exists so the looping sweep is not one import away (property 5). This pins it
    against the service so the copy cannot drift into a different accounts_state mapping."""
    from app.services.account_sync import _normalize_account

    raw = {
        "cash": "1234.56",
        "equity": "10250.00",
        "last_equity": "10000.00",
        "buying_power": "20500.00",
        "portfolio_value": "10250.00",
        "daytrade_count": 2,
        "status": "ACTIVE",
        "pattern_day_trader": False,
        "trading_blocked": False,
        "account_blocked": False,
    }
    assert normalize_account_snapshot(raw) == _normalize_account(raw)


def test_no_broker_baseline_is_unmeasured_not_the_whole_book():
    """A zero ``last_equity`` has no baseline. ``equity - 0`` would report the ENTIRE book as
    today's change, and this column feeds the legacy daily-loss basis — so it is UNAVAILABLE, and
    the label, not the number, is the truth (#495)."""
    out = normalize_account_snapshot({"equity": "100", "last_equity": "0"})
    assert out["day_change_basis"] == UNAVAILABLE
    assert out["day_change"] == D(0)
    assert out["day_change_pct"] == D(0)


def test_a_broker_baseline_is_labelled_as_such():
    out = normalize_account_snapshot({"equity": "10250", "last_equity": "10000"})
    assert out["day_change_basis"] == BROKER_LAST_EQUITY
    assert out["day_change"] == D(250)


@pytest.mark.asyncio
async def test_the_prior_close_proxy_is_resolved_for_account_three_only():
    """The proxy fallback mirrors the sweep's, scoped by the constant — a preview or a write must
    never reach another account's equity-snapshot history."""
    seen: list[int] = []

    async def fake_proxy(session, account_id, equity, now):
        seen.append(account_id)
        return None

    payload = normalize_account_snapshot({"equity": "100", "last_equity": "0"})
    with mock.patch.object(mod, "prior_session_close_proxy", fake_proxy):
        await mod.resolve_day_change(object(), payload, datetime(2026, 7, 27, tzinfo=UTC))
    assert seen == [SCOPED_ACCOUNT_ID]
    assert payload["day_change_basis"] == UNAVAILABLE


@pytest.mark.asyncio
async def test_a_resolved_proxy_replaces_the_unmeasured_placeholder():
    async def fake_proxy(session, account_id, equity, now):
        return DayChange(
            day_change=D(25),
            day_change_pct=D("0.0025"),
            basis=PRIOR_SESSION_CLOSE_PROXY,
            baseline_equity=D(9975),
        )

    payload = normalize_account_snapshot({"equity": "10000", "last_equity": "0"})
    with mock.patch.object(mod, "prior_session_close_proxy", fake_proxy):
        await mod.resolve_day_change(object(), payload, datetime(2026, 7, 27, tzinfo=UTC))
    assert payload["day_change_basis"] == PRIOR_SESSION_CLOSE_PROXY
    assert payload["day_change"] == D(25)


@pytest.mark.asyncio
async def test_a_broker_baseline_is_never_overwritten_by_the_proxy():
    async def fake_proxy(session, account_id, equity, now):  # pragma: no cover
        raise AssertionError("the proxy must not run when the broker supplied a baseline")

    payload = normalize_account_snapshot({"equity": "10250", "last_equity": "10000"})
    with mock.patch.object(mod, "prior_session_close_proxy", fake_proxy):
        await mod.resolve_day_change(object(), payload, datetime(2026, 7, 27, tzinfo=UTC))
    assert payload["day_change_basis"] == BROKER_LAST_EQUITY


@pytest.mark.asyncio
async def test_a_failing_snapshot_read_leaves_the_basis_unavailable():
    """It never invents a number to fill the gap, and it never aborts the sync."""

    async def boom(session, account_id, equity, now):
        raise RuntimeError("equity_snapshots unreadable")

    payload = normalize_account_snapshot({"equity": "100", "last_equity": "0"})
    with mock.patch.object(mod, "prior_session_close_proxy", boom):
        await mod.resolve_day_change(object(), payload, datetime(2026, 7, 27, tzinfo=UTC))
    assert payload["day_change_basis"] == UNAVAILABLE
    assert payload["day_change"] == D(0)


# ---------------------------------------------------------------------------- end-to-end behaviour
class _FakeResult:
    def __init__(self, value):
        self._value = value

    def mappings(self):
        return self

    def first(self):
        return self._value[0] if isinstance(self._value, list) and self._value else self._value

    def all(self):
        return self._value if isinstance(self._value, list) else [self._value]

    def scalars(self):
        return self

    def scalar(self):
        return self._value


class _FakeSession:
    """Records every statement and its binds, so a test can assert what was touched."""

    def __init__(self, responses, log):
        self._responses = responses
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.log.append((sql, dict(params or {})))
        for needle, value in self._responses:
            if needle in sql:
                return _FakeResult(value)
        return _FakeResult(None)

    async def commit(self):
        self.log.append(("COMMIT", {}))


def _session_factory(responses, log):
    def factory():
        return _FakeSession(responses, log)

    return factory


HEALTHY_RESPONSES = [
    ("FROM accounts WHERE id", {"id": 3, "user_id": 3, "broker": "alpaca", "mode": "paper"}),
    ("COUNT(*) FROM risk_reservations", 0),
    ("FROM accounts_state WHERE account_id", None),
    ("FROM positions p", []),
]


class _HealthyBroker:
    def get_account(self):
        return {
            "account_number": EXPECTED_BROKER_ACCOUNT,
            "equity": "10000",
            "last_equity": "10000",
            "cash": "500",
            "status": "ACTIVE",
        }

    def get_positions(self):
        return [{"symbol": "MSFT", "qty": "19", "side": "long"}]

    def list_orders(self):
        return [{"status": "filled"}]


async def _healthy_factory(sf):
    return ReadOnlyBrokerView(_HealthyBroker())


@pytest.mark.asyncio
async def test_dry_run_performs_every_check_and_writes_nothing():
    log: list = []
    ev = await scoped_sync(sf=_session_factory(HEALTHY_RESPONSES, log), adapter_factory=_healthy_factory, commit=False)
    assert ev["outcome"] == "DRY_RUN_NO_WRITE"
    assert [c["name"] for c in ev["checks"]] == [
        "account_row_binding",
        "broker_identity",
        "frozen_manifest",
        "account_flat",
    ]
    assert all(c["result"] == "PASS" for c in ev["checks"])
    assert not any(sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql, _ in log)
    assert not any(sql == "COMMIT" for sql, _ in log)


@pytest.mark.asyncio
async def test_evidence_records_the_broker_surface_actually_reached():
    """From the shared proxy's own call log — the evidence states which broker methods were reached,
    rather than only asserting which ones were not."""
    ev = await scoped_sync(
        sf=_session_factory(HEALTHY_RESPONSES, []), adapter_factory=_healthy_factory, commit=False
    )
    assert ev["broker_calls"] == ["get_account", "get_positions", "list_orders"]


@pytest.mark.asyncio
async def test_every_bind_in_the_run_names_account_three_only():
    """Property 4 and 8, read straight off the statement log: no statement may carry another id."""
    log: list = []
    await scoped_sync(sf=_session_factory(HEALTHY_RESPONSES, log), adapter_factory=_healthy_factory, commit=False)
    for sql, params in log:
        for key in ("a", "account_id"):
            if key in params:
                assert params[key] == SCOPED_ACCOUNT_ID, f"{sql} bound {key}={params[key]}"
        assert 1 not in {params.get("a"), params.get("account_id")}, f"account 1 reached by: {sql}"


@pytest.mark.asyncio
async def test_wrong_broker_account_refuses_before_reading_positions():
    class WrongBroker(_HealthyBroker):
        def get_account(self):
            return {"account_number": "PA3QRX9KSPXA"}

        def get_positions(self):  # pragma: no cover - must never be reached
            raise AssertionError("positions were read from the wrong broker account")

    async def factory(sf):
        return ReadOnlyBrokerView(WrongBroker())

    log: list = []
    with pytest.raises(ScopedSyncRefused, match="FORBIDDEN"):
        await scoped_sync(sf=_session_factory(HEALTHY_RESPONSES, log), adapter_factory=factory, commit=True)
    assert not any(sql == "COMMIT" for sql, _ in log)


@pytest.mark.asyncio
async def test_manifest_mismatch_refuses_even_with_commit():
    class DriftedBroker(_HealthyBroker):
        def get_positions(self):
            return [{"symbol": "MSFT", "qty": "17", "side": "long"}]

    async def factory(sf):
        return ReadOnlyBrokerView(DriftedBroker())

    log: list = []
    with pytest.raises(ScopedSyncRefused, match="frozen Phase-0 manifest"):
        await scoped_sync(sf=_session_factory(HEALTHY_RESPONSES, log), adapter_factory=factory, commit=True)
    assert not any(sql == "COMMIT" for sql, _ in log)


@pytest.mark.asyncio
async def test_account_row_bound_to_another_user_refuses_before_credentials_load():
    responses = [
        ("FROM accounts WHERE id", {"id": 3, "user_id": 1, "broker": "alpaca", "mode": "paper"}),
    ]

    async def factory(sf):  # pragma: no cover - must never be reached
        raise AssertionError("credentials were loaded despite a wrong account binding")

    with pytest.raises(ScopedSyncRefused, match="belongs to user 1"):
        await scoped_sync(sf=_session_factory(responses, []), adapter_factory=factory, commit=True)


@pytest.mark.asyncio
async def test_a_raw_adapter_from_the_factory_is_refused():
    """The read-only proxy is not optional. A factory returning a bare adapter must not run."""

    async def factory(sf):
        return _HealthyBroker()

    with pytest.raises(ScopedSyncRefused, match="must return a ReadOnlyBrokerView"):
        await scoped_sync(sf=_session_factory(HEALTHY_RESPONSES, []), adapter_factory=factory, commit=True)


@pytest.mark.asyncio
async def test_a_refusal_still_writes_the_evidence_file(tmp_path):
    """A finding that exists only on a terminal that has since scrolled away is not evidence."""

    class DriftedBroker(_HealthyBroker):
        def get_positions(self):
            return [{"symbol": "MSFT", "qty": "17", "side": "long"}]

    async def factory(sf):
        return ReadOnlyBrokerView(DriftedBroker())

    out = tmp_path / "refusal.json"
    with pytest.raises(ScopedSyncRefused):
        await scoped_sync(
            sf=_session_factory(HEALTHY_RESPONSES, []),
            adapter_factory=factory,
            commit=True,
            out=out,
        )
    assert out.exists()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["outcome"] == "REFUSED"
    assert "frozen Phase-0 manifest" in doc["refusal"]
    # The checks that DID pass are part of the record, not discarded with the failure.
    names = {c["name"]: c["result"] for c in doc["checks"]}
    assert names["account_row_binding"] == "PASS"
    assert names["broker_identity"] == "PASS"
    assert names["frozen_manifest"] == "FAIL"


@pytest.mark.asyncio
async def test_a_successful_dry_run_writes_the_evidence_file(tmp_path):
    out = tmp_path / "dryrun.json"
    await scoped_sync(
        sf=_session_factory(HEALTHY_RESPONSES, []),
        adapter_factory=_healthy_factory,
        commit=False,
        out=out,
    )
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["outcome"] == "DRY_RUN_NO_WRITE"
    assert doc["target"]["account_id"] == SCOPED_ACCOUNT_ID
    assert doc["target"]["expected_broker_account"] == EXPECTED_BROKER_ACCOUNT


@pytest.mark.asyncio
async def test_live_mode_account_is_refused():
    responses = [
        ("FROM accounts WHERE id", {"id": 3, "user_id": 3, "broker": "alpaca", "mode": "live"}),
    ]

    async def factory(sf):  # pragma: no cover
        raise AssertionError("a live account reached credential load")

    with pytest.raises(ScopedSyncRefused, match="paper-only"):
        await scoped_sync(sf=_session_factory(responses, []), adapter_factory=factory, commit=True)
