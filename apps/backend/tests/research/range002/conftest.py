"""Suite-wide seam: every RANGE-002 test resolves a decision's minutes file against the synthetic
minutes directory (written once under a temp directory), never against the repository. Production
code never sets the seam. A test that wants the real repository root (or another one) sets
``decision._MINUTES_ROOT`` itself."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.research.range002.spec._fixtures import synthetic_minutes_root


@pytest.fixture(autouse=True)
def _synthetic_minutes_root() -> Iterator[None]:
    with synthetic_minutes_root():
        yield
