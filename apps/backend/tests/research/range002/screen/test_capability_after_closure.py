"""Every supported result-producing path refuses a missing capability and a CLOSED run's capability.

Discovery is by introspection over the screen and data packages, so a new decorated entry point is
swept automatically, and a named floor stops the sweep from passing vacuously.

Stated limit (unchanged): this is in-process, Level-1 protection. Private helpers such as
``simulate._simulate`` are importable and Python privacy plus the import lint are developer
safeguards, not an access boundary. The boundary that matters is that supported paths need a live
capability; arbitrary same-process code is out of scope until the Level-2 design lands.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.results_guard import authorize, require_capability
from app.research.range002.governance.run_registry import RunStatus
from tests.research.range002.governance.conftest import (  # noqa: F401  (autouse manifest seam)
    SIGNED_LEDGER,
    new_registry,
    open_run,
    synthetic_manifest,
)
from tests.research.range002.screen.conftest import REPLAY_RANGE, synth_payload
from tests.research.range002.spec._fixtures import SYNTH_MANIFEST_PATH

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

from app.research.range002.governance.spec_adapter import to_guard_view  # noqa: E402
from app.research.range002.spec.loader import load_frozen  # noqa: E402

MODULES = (
    "app.research.range002.screen.simulate",
    "app.research.range002.screen.causal",
    "app.research.range002.screen.params",
    "app.research.range002.screen.report",
    "app.research.range002.screen.stats",
    "app.research.range002.screen.scheduler",
    "app.research.range002.screen.criteria",
    "app.research.range002.screen.selection",
    "app.research.range002.data.bar_loader",
    "app.research.range002.data.store_adapter",
)
FLOOR = {
    "simulate_session", "run_screen", "reconcile_funnel", "check_causal", "extract_params",
    "summarize", "summarize_portfolio", "build_day_matrix", "mean_interval", "max_statistic_test",
    "schedule_portfolio", "limits_from_draft", "classify_family", "select_candidate",
    "load_session", "load_sessions", "volume_reconciles", "load_observations",
    "build_month_from_store",
}  # fmt: skip


def _entry_points() -> dict[str, object]:
    found: dict[str, object] = {}
    for name in MODULES:
        mod = importlib.import_module(name)
        for attr, fn in vars(mod).items():
            if (
                inspect.isfunction(fn)
                and fn.__module__ == name
                and not attr.startswith("_")
                and hasattr(fn, "__wrapped__")
                and "capability" in inspect.signature(fn).parameters
            ):
                found[attr] = fn
    return found


def test_the_sweep_is_not_vacuous() -> None:
    assert set(_entry_points()) >= FLOOR


@pytest.fixture
def closed_and_open(tmp_path: Path):  # type: ignore[no-untyped-def]
    draft = tmp_path / "d.json"
    draft.write_text(json.dumps(synth_payload()), encoding="utf-8")
    frozen = tmp_path / "f.json"
    freeze_spec.freeze(draft, frozen, manifest_path=SYNTH_MANIFEST_PATH)
    view = to_guard_view(load_frozen(frozen))
    registry = new_registry(tmp_path / "runs.jsonl")
    run_id = open_run(registry, Phase.P2, Partition.REPLAY_RNG001, view.spec_sha256)
    cap = authorize(
        spec=view, phase=Phase.P2, partition=Partition.REPLAY_RNG001, run_id=run_id,
        registry=registry, exposure_ledger=ExposureLedger.from_text(SIGNED_LEDGER),
        requested_range=REPLAY_RANGE,
    )  # fmt: skip
    require_capability(cap)  # live before closure
    registry.close_run(run_id, RunStatus.ABORTED, None)
    return cap


def test_no_entry_point_accepts_a_missing_or_closed_capability(closed_and_open) -> None:  # type: ignore[no-untyped-def]
    points = _entry_points()
    assert points
    for name, fn in points.items():
        for bad in (None, closed_and_open):
            with pytest.raises(InvalidCapabilityError):
                fn(bad)  # type: ignore[operator]
            assert name  # the failing name is in the pytest traceback
