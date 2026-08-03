"""Stage-C reconciliation runner tests (ADR 0043 successor WS5).

Identity must be read first and must gate everything after it, denied operations
must dispatch nothing, and a partial record must never appear at the published
path. Assertions are on dispatch counts and call order, not on "no order was
submitted".

No live Alpaca call is made in this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.brokers import adr0043_reconcile as R
from app.brokers.factory import BrokerCredentialRef

ACCOUNT = "PA3E97RWHKQZ"
OTHER = "PA34USW0Q8UO"
COMMIT = "ed604d49ef9e6bb34ff755de67f542b6a3f38c23"
DIGEST = "sha256:825ac35561f543e1d68ad83e5ceb9e8d0ed696ad3dc09b7035159165413a8dcb"


class Settings:
    """The exact approved Stage-C posture. Subclasses below break one field each."""

    broker_access_mode = "read_only"
    strategy_execution_enabled = False
    scheduler_enabled = False
    alpaca_startup_enabled = False
    broker_expected_account_id = ACCOUNT


class Sender:
    """Per-path stub that records every dispatch in order."""

    def __init__(self, account_number=ACCOUNT, fail_on=None, status=200):
        self.calls: list[tuple[str, str]] = []
        self.account_number = account_number
        self.fail_on = fail_on
        self.status = status

    def __call__(self, method, url, *, headers, timeout):
        path = url.split("alpaca.markets", 1)[-1].split("?", 1)[0]
        self.calls.append((method, path))
        if self.fail_on and self.fail_on in path:
            raise ConnectionError("simulated transport failure")
        body: object
        if path == "/v2/account":
            body = {
                "account_number": self.account_number,
                "equity": "100000",
                "last_equity": "100000",
                "cash": "100000",
                "portfolio_value": "100000",
                "position_market_value": "0",
            }
        else:
            body = []
        return self.status, {}, json.dumps(body).encode()

    @property
    def paths(self):
        return [p for _, p in self.calls]


def _cred():
    return BrokerCredentialRef(
        source="test",
        fingerprint="ffab8796516a",
        resolve=lambda: ("k", "s"),
        secret_fingerprint="c2cab6509f1b",
    )


def _run(sender, *, expected=ACCOUNT, settings=None, credential=..., commit=COMMIT, digest=DIGEST):
    return R.reconcile(
        settings=settings or Settings(),
        credential=_cred() if credential is ... else credential,
        expected_account_id=expected,
        base_url="https://paper-api.alpaca.markets",
        sender=sender,
        source_commit=commit,
        image_digest=digest,
        run_id="fixedrun",
        now=lambda: "2026-08-03T00:00:00Z",
    )


@pytest.fixture
def ws5_env(monkeypatch):
    """Apply the approved Stage-C posture, and guarantee the cached Settings
    cannot leak into other tests — get_settings is lru_cached, so clearing on
    the way *out* matters as much as on the way in."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("WORKBENCH_BROKER_ACCESS_MODE", "read_only")
    monkeypatch.setenv("WORKBENCH_STRATEGY_EXECUTION_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_ALPACA_STARTUP_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID", ACCOUNT)
    try:
        yield
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------- sequence


def test_account_is_always_the_first_call():
    s = Sender()
    _run(s)
    assert s.paths[0] == "/v2/account"


def test_successful_run_makes_exactly_four_approved_calls_in_order():
    s = Sender()
    ev, disp = _run(s)
    assert disp == R.READY
    assert s.paths == ["/v2/account", "/v2/positions", "/v2/orders", "/v2/account/activities"]
    assert ev["approved_calls_in_order"] == R.APPROVED_CALL_ORDER
    assert ev["transport_dispatch_count"] == 4


def test_call_order_is_deterministic_across_runs():
    a, b = Sender(), Sender()
    _run(a)
    _run(b)
    assert a.paths == b.paths


# ---------------------------------------------------------------- identity gate


def test_mismatch_produces_exactly_one_transport_call():
    s = Sender(account_number=OTHER)
    ev, disp = _run(s)
    assert disp == R.REFUSED
    assert len(s.calls) == 1, "reads continued past an identity mismatch"
    assert s.paths == ["/v2/account"]
    assert ev["returned_account_id"] == OTHER
    assert "account_identity_mismatch" in ev["failure_code"]


def test_account_failure_prevents_all_later_calls():
    s = Sender(fail_on="/v2/account")
    ev, disp = _run(s)
    assert disp == R.INCONCLUSIVE
    assert s.paths == ["/v2/account"]
    assert ev["positions_count"] is None


def test_later_read_failure_is_inconclusive_not_ready():
    s = Sender(fail_on="/v2/orders")
    ev, disp = _run(s)
    assert disp == R.INCONCLUSIVE
    assert "read_failed" in ev["failure_code"]


# ---------------------------------------------------------------- policy


def test_disabled_mode_refuses_with_zero_dispatches():
    class Off(Settings):
        broker_access_mode = ""

    s = Sender()
    ev, disp = _run(s, settings=Off())
    assert disp == R.REFUSED
    assert len(s.calls) == 0, "a denied client still reached the network"
    assert ev["transport_dispatch_count"] == 0


def test_trading_mode_is_refused_by_the_governed_factory():
    class Trading(Settings):
        broker_access_mode = "trading"

    s = Sender()
    _, disp = _run(s, settings=Trading())
    assert disp == R.REFUSED
    assert len(s.calls) == 0


def test_mutation_attempt_count_is_zero_and_no_mutation_is_reachable():
    from app.brokers.exceptions import BrokerOperationDenied
    from app.brokers.readonly_client import ReadOnlyBrokerClient

    s = Sender()
    ev, _ = _run(s)
    assert ev["mutation_attempt_count"] == 0
    c = ReadOnlyBrokerClient.__new__(ReadOnlyBrokerClient)
    for op in ("submit_order", "cancel_order", "close_all_positions", "reset_paper_account"):
        with pytest.raises(BrokerOperationDenied):
            getattr(c, op)()


# ---------------------------------------------------------------- isolation


def _imported_names(module) -> set[str]:
    """Every module and symbol the runner actually imports, via AST.

    Text-grepping the source would trip on the docstring, which deliberately
    *names* the surfaces this module avoids. Imports are the real control.
    """
    import ast

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(a.name for a in node.names)
    return names


def test_runner_imports_no_legacy_broker_surface():
    """The absence is the control; assert it on the import graph, not on prose."""
    imported = _imported_names(R)
    for banned in (
        "AlpacaAdapter",
        "BrokerRegistry",
        "TradeUpdatesStream",
        "TradingClient",
        "alpaca",
        "alpaca.trading",
        "app.brokers.alpaca",
        "app.brokers.registry",
        "app.brokers.alpaca.adapter",
        "app.brokers.alpaca.streaming",
        "load_credentials",
    ):
        assert banned not in imported, f"runner imports legacy broker surface: {banned}"
    assert not any(n.startswith("alpaca") for n in imported), f"alpaca SDK imported: {imported}"


def test_runner_imports_only_the_governed_broker_modules():
    imported = _imported_names(R)
    broker = {n for n in imported if n.startswith("app.brokers")}
    assert broker <= {"app.brokers.exceptions", "app.brokers.factory"}, broker


def test_runner_obtains_its_client_only_through_the_factory():
    src = Path(R.__file__).read_text(encoding="utf-8")
    assert "get_broker_client" in src
    assert "GovernedTransport(" not in src, "runner must not build transport directly"


def test_runner_performs_no_sql_or_migration():
    src = Path(R.__file__).read_text(encoding="utf-8")
    for banned in ("sqlite", "alembic", "sessionmaker", "create_engine", "uvicorn"):
        assert banned not in src.lower(), f"runner references {banned}"


def test_no_secret_appears_in_the_evidence():
    s = Sender()
    ev, _ = _run(s)
    blob = json.dumps(ev)
    assert '"k"' not in blob and 'secret": "s"' not in blob
    assert ev["credential_key_fingerprint"] == "ffab8796516a"
    assert ev["credential_secret_fingerprint"] == "c2cab6509f1b"


# ---------------------------------------------------------------- evidence


def test_evidence_is_labelled_non_authoritative():
    ev, _ = _run(Sender())
    assert ev["authoritative_start_a_baseline"] is False
    assert ev["equity"] == "100000"


def test_evidence_is_deterministic_except_normalised_fields():
    a, _ = _run(Sender())
    b, _ = _run(Sender())
    assert a == b, "evidence differs between identical runs"


def test_write_evidence_is_atomic_and_hashes_the_record(tmp_path):
    ev, _ = _run(Sender())
    out = tmp_path / "nested" / "recon.json"
    digest = R.write_evidence(ev, out)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["artifact_sha256"] == digest
    assert list(tmp_path.rglob("*.partial")) == [], "a partial file survived publication"


def test_partial_evidence_is_not_published(tmp_path):
    bad = {"run_id": None, "terminal_disposition": None}
    out = tmp_path / "recon.json"
    with pytest.raises(ValueError, match="incomplete"):
        R.write_evidence(bad, out)
    assert not out.exists(), "an incomplete record was published"


def test_failed_write_leaves_no_file_at_the_published_path(tmp_path, monkeypatch):
    ev, _ = _run(Sender())
    out = tmp_path / "recon.json"
    monkeypatch.setattr(
        R.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError):
        R.write_evidence(ev, out)
    assert not out.exists()
    assert list(tmp_path.glob("*.partial")) == []


# ---------------------------------------------------------------- exit codes


def test_exit_codes_distinguish_the_three_dispositions():
    assert R.EXIT_CODES[R.READY] == 0
    assert R.EXIT_CODES[R.REFUSED] == 2
    assert R.EXIT_CODES[R.INCONCLUSIVE] == 3
    assert len(set(R.EXIT_CODES.values())) == 3


def test_main_exit_code_and_message_on_missing_credentials(tmp_path, monkeypatch, ws5_env, capsys):
    """Exit code and operator-facing message, distinct from the artifact test below."""
    for var in (R.ENV_KEY, R.ENV_SECRET, R.ENV_ACCOUNT):
        monkeypatch.delenv(var, raising=False)
    rc = R.main(
        ["--output", str(tmp_path / "x.json"), "--source-commit", COMMIT, "--image-digest", DIGEST]
    )
    assert rc == R.EXIT_CODES[R.REFUSED]
    assert "REFUSED" in capsys.readouterr().out


def test_runner_does_not_use_the_colliding_paper_7_names():
    """The _7 slot collides with Workbench account 7 / strategy 9; only the
    comment explaining that may mention it, never the operative constants."""
    for const in (R.ENV_KEY, R.ENV_SECRET, R.ENV_ACCOUNT):
        assert "ALPACA_PAPER_7" not in const
        assert const.startswith("ADR0043_SUCCESSOR_CANARY_")
    assert R.ENV_KEY == "ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY"


# ------------------------------------------------- provenance binding (fail closed)


@pytest.mark.parametrize(
    "commit",
    [
        "",
        "ed604d49",
        "ED604D49EF9E6BB34FF755DE67F542B6A3F38C23",
        "zz604d49" + "0" * 32,
        COMMIT + "0",
    ],
)
def test_missing_or_malformed_source_commit_refuses_with_zero_dispatches(commit):
    s = Sender()
    ev, disp = _run(s, commit=commit)
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert ev["transport_dispatch_count"] == 0
    assert ev["failure_code"].startswith("provenance_binding_missing_or_invalid")


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "sha256:825ac355",
        "825ac35561f543e1d68ad83e5ceb9e8d0ed696ad3dc09b7035159165413a8dcb",
        "sha512:" + "a" * 64,
        "sha256:" + "A" * 64,
    ],
)
def test_missing_or_malformed_image_digest_refuses_with_zero_dispatches(digest):
    s = Sender()
    ev, disp = _run(s, digest=digest)
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert ev["failure_code"].startswith("provenance_binding_missing_or_invalid")


def test_provenance_refusal_still_writes_an_artifact(tmp_path):
    ev, disp = _run(Sender(), commit="")
    out = tmp_path / "r.json"
    R.write_evidence(ev, out)
    assert disp == R.REFUSED and out.exists()
    assert json.loads(out.read_text())["terminal_disposition"] == R.REFUSED


# ------------------------------------------------- runtime posture (all four gates)


@pytest.mark.parametrize("mode", ["", "disabled", "trading", "READ_ONLY ", "readonly"])
def test_any_access_mode_other_than_read_only_refuses(mode):
    class S(Settings):
        broker_access_mode = mode

    s = Sender()
    ev, disp = _run(s, settings=S())
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert ev["failure_code"].startswith("unsafe_runtime_posture")


@pytest.mark.parametrize(
    "field", ["strategy_execution_enabled", "scheduler_enabled", "alpaca_startup_enabled"]
)
def test_any_enabled_execution_gate_refuses(field):
    S = type("S", (Settings,), {field: True})
    s = Sender()
    ev, disp = _run(s, settings=S())
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert field in ev["failure_code"]


@pytest.mark.parametrize("truthy", ["false", "0", 0, 1, None])
def test_ambiguous_boolean_coercions_are_refused(truthy):
    """A string "false" must not be accepted as the boolean False."""
    S = type("S", (Settings,), {"alpaca_startup_enabled": truthy})
    s = Sender()
    _, disp = _run(s, settings=S())
    assert disp == R.REFUSED
    assert len(s.calls) == 0


def test_alpaca_startup_enabled_is_actually_checked():
    """Regression: this gate was passed to nothing in the first implementation."""
    assert "alpaca_startup_enabled" in R.REQUIRED_POSTURE
    S = type("S", (Settings,), {"alpaca_startup_enabled": True})
    assert R.check_runtime_posture(S()) is not None


# ------------------------------------------------- credential / account refusals


def test_missing_credentials_refuse_with_an_artifact_and_no_secrets():
    s = Sender()
    ev, disp = _run(s, credential=None)
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert ev["failure_code"].startswith("missing_credentials")
    assert ev["credential_key_fingerprint"] == ""
    assert ev["credential_secret_fingerprint"] == ""
    blob = json.dumps(ev)
    for secret_value in ('"k"', '"s"', "ffab8796516a", "c2cab6509f1b"):
        assert secret_value not in blob, f"credential material leaked: {secret_value}"


def test_missing_expected_account_refuses_with_an_artifact():
    s = Sender()
    ev, disp = _run(s, expected="")
    assert disp == R.REFUSED
    assert len(s.calls) == 0
    assert ev["failure_code"].startswith("missing_expected_account")


def test_main_writes_a_refusal_artifact_when_credentials_are_absent(tmp_path, monkeypatch, ws5_env):
    """The early-return path that produced no evidence at all is closed."""
    for var in (R.ENV_KEY, R.ENV_SECRET, R.ENV_ACCOUNT):
        monkeypatch.delenv(var, raising=False)
    out = tmp_path / "recon.json"
    rc = R.main(["--output", str(out), "--source-commit", COMMIT, "--image-digest", DIGEST])
    assert rc == R.EXIT_CODES[R.REFUSED]
    assert out.exists(), "a post-parse refusal produced no artifact"
    rec = json.loads(out.read_text())
    assert rec["terminal_disposition"] == R.REFUSED
    assert rec["transport_dispatch_count"] == 0
    assert rec["credential_key_fingerprint"] == ""
    assert "artifact_sha256" in rec


def test_main_returns_inconclusive_when_the_artifact_cannot_be_written(
    tmp_path, monkeypatch, ws5_env
):
    """The only path that may legitimately leave no artifact."""
    monkeypatch.setattr(
        R, "write_evidence", lambda *a, **k: (_ for _ in ()).throw(OSError("ro fs"))
    )
    rc = R.main(
        ["--output", str(tmp_path / "x.json"), "--source-commit", COMMIT, "--image-digest", DIGEST]
    )
    assert rc == R.EXIT_CODES[R.INCONCLUSIVE]
