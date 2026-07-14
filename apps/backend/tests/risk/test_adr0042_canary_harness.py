"""ADR 0042 canary harness — the three gate-blocking defects, as regression tests.

Each test here corresponds to a defect that produced, or would have produced, an invalid canary
result. None of them is about the risk engine; all of them are about the harness lying.
"""

from __future__ import annotations

import importlib
import os
from decimal import Decimal as D

import pytest


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("ADR0042_CHECKPOINT", str(tmp_path / "state.json"))
    monkeypatch.setenv("ADR0042_LOCKFILE", str(tmp_path / "canary.lock"))
    import scripts.adr0042_canary_lib as m

    return importlib.reload(m)


# ---------------------------------------------------------------- defect 1: unprotected flatten
def test_every_leg_is_protected(lib):
    """The old churn flattened EVERY position, destroying the F/MSFT legs the post-lock
    assertions depend on — a RED with nothing to do with the risk engine.

    The invariant that prevents it: every leg must be in PROTECTED.
    """
    legs = {s for s, _ in lib.LEGS}
    assert legs, "no legs configured"
    assert legs <= set(lib.PROTECTED), (
        f"legs {legs - set(lib.PROTECTED)} are NOT protected — the churn would flatten them"
    )


def test_churn_symbols_are_disjoint_from_protected(lib):
    """A churn symbol that is also a leg would be bought and sold every cycle, so the leg could
    not survive to the assertions."""
    assert not (set(lib.CHURN_SYMBOLS) & set(lib.PROTECTED)), (
        "a churn symbol is also protected; the churn cannot both trade it and preserve it"
    )


# ---------------------------------------------------------------- defect 2: expiring deadline
def test_the_deadline_is_relative_not_a_calendar_date(lib):
    """The old script hard-coded `2026-07-13 19:50 UTC`. It silently expired, and every run after
    that date aborted on the first cycle. A test that expires on a calendar is not a test."""
    from datetime import UTC, datetime

    cp = lib.Checkpoint.load()
    deadline = datetime.fromisoformat(cp.deadline_at)
    assert deadline > datetime.now(UTC), "the deadline must resolve to the FUTURE"

    remaining = (deadline - datetime.now(UTC)).total_seconds() / 60
    assert remaining == pytest.approx(lib.BUDGET_MINUTES, rel=0.05), (
        "the deadline must be derived from the relative budget, not a fixed date"
    )


# ---------------------------------------------------------------- defect 3: cap-blind sizing
def test_sizing_respects_the_position_notional_cap(lib):
    """The old churn asked for a fixed $24k regardless of the account's caps, was refused with
    POSITION_CAP_QTY, and churned uselessly. Sizing must be DERIVED from the limits."""
    limits = lib.Limits(
        max_position_qty=None,
        max_position_notional=D("10000"),
        max_gross_exposure=None,
        max_daily_loss=D("3000"),
        max_orders_per_day=None,
    )
    shares = lib.admissible_shares(
        price=D("100"), limits=limits, gross_used=D(0),
        buying_power=D("1000000"), ceiling=D("25000"),
    )
    assert shares == D("100"), f"$10k cap at $100 => 100 shares, got {shares}"


def test_sizing_respects_the_quantity_cap(lib):
    limits = lib.Limits(
        max_position_qty=D("50"), max_position_notional=None, max_gross_exposure=None,
        max_daily_loss=D("3000"), max_orders_per_day=None,
    )
    shares = lib.admissible_shares(
        price=D("10"), limits=limits, gross_used=D(0),
        buying_power=D("1000000"), ceiling=D("25000"),
    )
    assert shares == D("50")


def test_sizing_respects_remaining_gross_exposure_and_buying_power(lib):
    limits = lib.Limits(
        max_position_qty=None, max_position_notional=None,
        max_gross_exposure=D("100000"), max_daily_loss=D("3000"), max_orders_per_day=None,
    )
    # 90k of the 100k gross cap is already used, so only 10k remains -> 100 shares at $100.
    shares = lib.admissible_shares(
        price=D("100"), limits=limits, gross_used=D("90000"),
        buying_power=D("1000000"), ceiling=D("25000"),
    )
    assert shares == D("100")

    # Buying power binds instead.
    shares = lib.admissible_shares(
        price=D("100"), limits=limits, gross_used=D(0),
        buying_power=D("2500"), ceiling=D("25000"),
    )
    assert shares == D("25")


def test_sizing_returns_zero_when_no_capacity_remains(lib):
    """Zero, not a negative or a fixed fallback — the caller turns this into
    BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS rather than churning against rejections."""
    limits = lib.Limits(
        max_position_qty=None, max_position_notional=None,
        max_gross_exposure=D("100000"), max_daily_loss=D("3000"), max_orders_per_day=None,
    )
    shares = lib.admissible_shares(
        price=D("100"), limits=limits, gross_used=D("100000"),
        buying_power=D("1000000"), ceiling=D("25000"),
    )
    assert shares == D(0)


# ---------------------------------------------------------------- defect 4: fragile execution
def test_the_checkpoint_survives_a_restart(lib):
    cp = lib.Checkpoint.load()
    cp.cycles = 7
    cp.phase = "CHURN"
    cp.legs_established = True
    cp.save()

    reloaded = lib.Checkpoint.load()
    assert reloaded.cycles == 7
    assert reloaded.phase == "CHURN"
    assert reloaded.legs_established is True
    assert reloaded.deadline_at == cp.deadline_at, "a resume must not silently extend the budget"


def test_two_harness_processes_cannot_run_at_once(lib):
    """Two concurrent harness invocations is EXACTLY the condition that produced the cross-process
    double reservation on 2026-07-14 (my own operator error). The harness must refuse."""
    held = lib.SingleInstance()
    held.__enter__()
    try:
        with pytest.raises(lib.CanaryRefused, match="another canary process"):
            lib.SingleInstance().__enter__()
    finally:
        held.__exit__()

    # and the lock is released afterwards, so a legitimate rerun is not blocked forever
    with lib.SingleInstance():
        pass
    assert not lib.LOCKFILE.exists()


def test_evidence_binds_provenance_and_fails_without_it(lib, monkeypatch):
    """"Ran from committed code" is worthless unless tied to the deployed container."""
    monkeypatch.delenv("ADR0042_COMMIT_SHA", raising=False)
    monkeypatch.delenv("ADR0042_IMAGE_DIGEST", raising=False)
    ev = lib.Evidence(phase="TEST")
    assert ev.doc["commit_sha"] is None
    assert ev.doc["image_digest"] is None

    monkeypatch.setenv("ADR0042_COMMIT_SHA", "abc123")
    monkeypatch.setenv("ADR0042_IMAGE_DIGEST", "sha256:deadbeef")
    monkeypatch.setenv("ADR0042_DEPLOYED_AT", "2026-07-15T13:30:00Z")
    ev = lib.Evidence(phase="TEST")
    assert ev.doc["commit_sha"] == "abc123"
    assert ev.doc["image_digest"] == "sha256:deadbeef"
    assert ev.doc["policy_version"] == "0042.1"


def test_a_failed_assertion_fails_the_gate(lib):
    ev = lib.Evidence(phase="TEST")
    ev.assert_("a", True, "fine")
    assert ev.passed()
    ev.assert_("b", False, "not fine")
    assert not ev.passed(), "one failed assertion must fail the whole canary"


def test_the_concurrency_worker_is_a_separate_process_not_a_coroutine():
    """GUARDS THE GUARD.

    The old canary fired its two concurrent reductions with `asyncio.gather` INSIDE ONE PROCESS,
    where the per-account `asyncio.Lock` serialised them — so the assertion passed while the
    cross-process hole stayed open. It would have returned GREEN on exactly the defect it existed
    to catch.

    The replacement must spawn real OS processes. This test reads the source and refuses to let it
    quietly regress to `asyncio.gather`.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).parents[2] / "scripts" / "adr0042_canary_run.py"
    text = src.read_text(encoding="utf-8")
    tree = ast.parse(text)

    # Inspect the AST, not the text: the module docstring MENTIONS asyncio.gather in order to
    # explain why it is forbidden, and a substring check would trip on that. What matters is
    # whether it is CALLED.
    gathers = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "gather"
    ]
    assert not gathers, (
        "asyncio.gather is CALLED in the canary: two coroutines in one process would be "
        "serialised by the process-local lock and would PASS on the broken implementation"
    )
    assert "subprocess.Popen" in text, "the concurrency assertion must spawn real OS processes"
    assert "adr0042_concurrency_worker.py" in text

    worker = src.parent / "adr0042_concurrency_worker.py"
    assert worker.exists(), "the second-process worker is missing"
    assert os.path.getsize(worker) > 0
