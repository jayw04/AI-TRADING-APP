"""Deterministic ordering, append-only progress, and a resume that is genuinely gated."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.state import CrawlState, UnitResult, WorkUnit


def unit(cik: int, ticker: str) -> WorkUnit:
    return WorkUnit(cik=cik, ticker=ticker)


def result(u: WorkUnit) -> UnitResult:
    return UnitResult(
        unit_key=u.key, cik=u.cik, ticker=u.ticker, completed_utc="2026-08-24T12:00:00Z",
        filings_seen=3, observations=3, observations_with_sic=3, missing_sic=0,
        segments=1, conflicts=0, requests_issued=4,
    )


# --- determinism ----------------------------------------------------------------------


def test_order_is_deterministic_and_independent_of_input_order(tmp_path) -> None:
    units = [unit(320193, "AAPL"), unit(789019, "MSFT"), unit(1018724, "AMZN")]
    state = CrawlState.load(tmp_path)
    assert [u.ticker for u in state.pending(units)] == ["AAPL", "MSFT", "AMZN"]
    assert [u.ticker for u in state.pending(list(reversed(units)))] == ["AAPL", "MSFT", "AMZN"]


def test_unit_key_is_zero_padded_and_stable() -> None:
    assert unit(320193, "AAPL").key == "0000320193:AAPL"


# --- resumability ---------------------------------------------------------------------


def test_completed_units_are_not_recrawled(tmp_path) -> None:
    units = [unit(1, "A"), unit(2, "B"), unit(3, "C")]
    state = CrawlState.load(tmp_path)
    state.mark_done(result(units[0]))
    state.mark_done(result(units[2]))
    assert [u.ticker for u in state.pending(units)] == ["B"]


def test_progress_survives_a_restart(tmp_path) -> None:
    units = [unit(1, "A"), unit(2, "B")]
    first = CrawlState.load(tmp_path)
    first.mark_done(result(units[0]))

    reloaded = CrawlState.load(tmp_path)
    assert reloaded.is_done(units[0])
    assert [u.ticker for u in reloaded.pending(units)] == ["B"]
    assert reloaded.done[units[0].key].observations == 3


def test_progress_is_append_only(tmp_path) -> None:
    state = CrawlState.load(tmp_path)
    state.mark_done(result(unit(1, "A")))
    first = state.progress_path.read_bytes()
    state.mark_done(result(unit(2, "B")))
    assert state.progress_path.read_bytes().startswith(first)


def test_torn_final_line_costs_only_the_unit_in_flight(tmp_path) -> None:
    """A hard kill mid-flush must not invalidate the units already earned."""
    state = CrawlState.load(tmp_path)
    state.mark_done(result(unit(1, "A")))
    state.mark_done(result(unit(2, "B")))
    raw = state.progress_path.read_bytes()
    state.progress_path.write_bytes(raw[: -len(raw) // 4])  # truncate the last record

    reloaded = CrawlState.load(tmp_path)
    assert reloaded.is_done(unit(1, "A"))
    assert not reloaded.is_done(unit(2, "B"))


# --- halt and resume ------------------------------------------------------------------


def test_fresh_state_is_not_blocked(tmp_path) -> None:
    assert CrawlState.load(tmp_path).resume_blocked_reason(resume=False) is None


def test_halt_blocks_without_explicit_resume(tmp_path) -> None:
    state = CrawlState.load(tmp_path)
    state.record_halt(status=403, uri="https://www.sec.gov/x", completed=17, total=1167)

    reason = state.resume_blocked_reason(resume=False)
    assert reason is not None and "resume=True" in reason


def test_cooldown_must_elapse_even_with_explicit_resume(tmp_path) -> None:
    state = CrawlState.load(tmp_path)
    state.record_halt(status=403, uri="https://www.sec.gov/x", completed=17, total=1167)

    just_after = datetime.now(UTC) + timedelta(seconds=30)
    reason = state.resume_blocked_reason(resume=True, now=just_after)
    assert reason is not None and "cooldown" in reason

    after = datetime.now(UTC) + timedelta(seconds=policy.HALT_COOLDOWN_SECONDS + 1)
    assert state.resume_blocked_reason(resume=True, now=after) is None


def test_halt_record_preserves_state_and_is_readable(tmp_path) -> None:
    state = CrawlState.load(tmp_path)
    state.mark_done(result(unit(1, "A")))
    state.record_halt(status=403, uri="https://www.sec.gov/x", completed=1, total=1167)

    record = json.loads(state.halt_path.read_text(encoding="utf-8"))
    assert record["http_status"] == 403
    assert record["cooldown_seconds"] >= 600
    assert record["units_completed"] == 1
    assert record["units_total"] == 1167
    assert record["resume_allowed_after_utc"].endswith("Z")

    reloaded = CrawlState.load(tmp_path)
    assert reloaded.is_halted
    assert reloaded.is_done(unit(1, "A"))  # progress preserved across the halt


def test_clearing_a_halt_keeps_the_record_as_evidence(tmp_path) -> None:
    state = CrawlState.load(tmp_path)
    state.record_halt(status=403, uri="https://www.sec.gov/x", completed=0, total=10)
    state.clear_halt()

    assert not state.halt_path.exists()
    assert not state.is_halted
    archived = list(tmp_path.glob("crawl_halt.resumed.*.json"))
    assert len(archived) == 1, "the halt must remain auditable after resumption"


def test_halt_record_carries_no_coverage_quantity(tmp_path) -> None:
    """State goes through the guarded writer like everything else."""
    from app.altdata.sec001_v3.forbidden import FORBIDDEN_COVERAGE_FIELDS

    state = CrawlState.load(tmp_path)
    state.record_halt(status=403, uri="https://www.sec.gov/x", completed=1, total=2)
    record = json.loads(state.halt_path.read_text(encoding="utf-8"))
    assert not (set(record) & FORBIDDEN_COVERAGE_FIELDS)


@pytest.mark.parametrize("status", [403])
def test_only_403_is_a_halt_status(status: int) -> None:
    assert (status,) == policy.HALT_STATUSES
    assert status not in policy.RETRY_STATUSES
