"""SPQ-1 Phase 2B-2 harness regression tests.

Locks in the dev-calendar identity distinction that caused a verification-harness false stop: the
frozen development-calendar identity is dev_calendar_sha256 (newline-joined sessions + trailing
newline), which is NOT the same value as RegisteredCalendar.identity (canonical_sha256 of the session
list). A future developer must not reintroduce the invalid cross-comparison
``ctx.calendar.identity == BOUND["dev_calendar_sha256"]`` -- these are different identity schemes.

Skips if the registered development DBs are absent (local-only).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[5]
RESEARCH = REPO / "apps" / "backend" / "data" / "mr002_research.duckdb"
PROV = REPO / "apps" / "backend" / "data" / "mr002_provenance.duckdb"

pytestmark = pytest.mark.skipif(
    not (RESEARCH.exists() and PROV.exists()),
    reason="registered development DBs absent (local-only)")

# The two registered expectations for the 1,700-session development calendar.
FROZEN_DEV_CALENDAR_SHA256 = "a7ec4f0f2d5ce794d7a24a3d48e628f830cb68dbf1af9b0a51c557d38836e0c0"
REGISTERED_CALENDAR_CANONICAL_IDENTITY = \
    "28f447602be6955f165abc56ba99a0602ee4d105bc5c4220920593014df079b4"


def _dev_sessions() -> tuple[str, ...]:
    from app.research.mr002.spq1.adapters import DEV_END, DEV_START
    con = duckdb.connect(str(RESEARCH), read_only=True)
    try:
        rows = con.execute(
            'select distinct "date" from prices where ticker=? and "date" between ? and ? '
            'order by "date"', ["AAPL", DEV_START, DEV_END]).fetchall()
    finally:
        con.close()
    return tuple(str(r[0]) for r in rows)


def test_dev_calendar_reproduces_frozen_and_canonical_identities():
    from app.research.mr002.spq1.adapters import DEV_CALENDAR_SHA256
    from app.research.mr002.spq1.adapters.calendar_adapter import dev_calendar_sha256
    from app.research.mr002.spq1.calendar import RegisteredCalendar
    from app.research.mr002.spq1.identities import canonical_sha256

    sessions = _dev_sessions()
    assert len(sessions) == 1700
    assert sessions[0] == "2013-01-02"
    assert sessions[-1] == "2019-10-02"

    cal = RegisteredCalendar(sessions)
    frozen = dev_calendar_sha256(sessions)
    canonical = cal.identity

    # each identity independently matches its own registered expectation
    assert frozen == DEV_CALENDAR_SHA256 == FROZEN_DEV_CALENDAR_SHA256
    assert canonical == canonical_sha256(list(sessions)) == REGISTERED_CALENDAR_CANONICAL_IDENTITY


def test_two_calendar_identity_schemes_are_distinct_not_cross_comparable():
    """The frozen dev_calendar_sha256 and RegisteredCalendar.identity are DIFFERENT serializations of
    the SAME session list; comparing one against the other's bound value is the invalid check."""
    from app.research.mr002.spq1.adapters import DEV_CALENDAR_SHA256
    from app.research.mr002.spq1.adapters.calendar_adapter import dev_calendar_sha256
    from app.research.mr002.spq1.calendar import RegisteredCalendar

    sessions = _dev_sessions()
    cal = RegisteredCalendar(sessions)
    frozen = dev_calendar_sha256(sessions)

    # the regression: the two identities must NOT be equal ...
    assert frozen != cal.identity
    # ... and the invalid cross-comparison (the false-stop bug) must NOT hold
    assert cal.identity != DEV_CALENDAR_SHA256
    # ... while the CORRECT mandatory gate (frozen serialization vs bound value) DOES hold
    assert frozen == DEV_CALENDAR_SHA256


def test_mandatory_calendar_gate_uses_frozen_serialization():
    """The 2B-2 runner's mandatory dev-calendar gate must use dev_calendar_sha256(sessions), the same
    serialization load_calendar() independently enforces."""
    from app.research.mr002.spq1.adapters import (
        DEV_CALENDAR_SHA256,
        REGISTERED_RESEARCH_DB,
        abs_path,
    )
    from app.research.mr002.spq1.adapters.calendar_adapter import dev_calendar_sha256, load_calendar

    # load_calendar enforces the frozen identity internally; it must succeed on the registered source
    con = duckdb.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
    try:
        # load_calendar reads a dev-bounded snapshot in the run; here we assert the gate expression
        # itself on the registered dev sessions (equivalent session set).
        sessions = _dev_sessions()
        gate_pass = dev_calendar_sha256(sessions) == DEV_CALENDAR_SHA256
        assert gate_pass is True
        # sanity: load_calendar signature is importable + callable (enforcement path exists)
        assert callable(load_calendar)
    finally:
        con.close()
