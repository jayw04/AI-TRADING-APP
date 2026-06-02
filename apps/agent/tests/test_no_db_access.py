"""The agent module must import cleanly WITHOUT pulling in sqlalchemy / app.db.

This is the unit-level companion to the CI invariant
``check_agent_no_db_access.sh`` (which greps the source). Here we prove that
importing every agent module doesn't drag a DB layer into the process — a
developer who accidentally `from sqlalchemy import ...`'d in the agent would
trip this even before CI.
"""
from __future__ import annotations

import sys


def test_imports_clean() -> None:
    import agent  # noqa: F401
    import agent.budget  # noqa: F401
    import agent.config  # noqa: F401
    import agent.llm_call  # noqa: F401

    # No DB-access library should have been imported as a side effect.
    assert "sqlalchemy" not in sys.modules
    assert not any(m == "app.db" or m.startswith("app.db.") for m in sys.modules)
    assert "alembic" not in sys.modules
