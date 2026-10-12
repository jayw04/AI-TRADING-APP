"""One end-to-end SYNTHETIC flow through the real guard (screen profile, P3A):

profile freeze -> registration / capability -> fixture loading -> coverage -> simulation ->
statistics / report -> run closure.

Everything is synthetic. Nothing here is a performance result, a data-coverage finding or a
P0 value; the capability is issued by the real guard against a synthetic spec and manifest.
"""

from __future__ import annotations

import json
import sys
from datetime import date, time
from pathlib import Path

import pytest

from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.results_guard import authorize, require_capability
from app.research.range002.governance.run_registry import RunStatus
from app.research.range002.governance.spec_adapter import to_guard_view
from app.research.range002.screen.coverage import (
    MISSING_NO_DATA,
    coverage_report,
    presence_from_minutes,
)
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.report import summarize, summarize_portfolio
from app.research.range002.screen.scheduler import PortfolioLimits, schedule_portfolio
from app.research.range002.screen.session_calendar import expected_sessions
from app.research.range002.screen.simulate import run_screen
from app.research.range002.screen.stats import (
    BootstrapConfig,
    build_day_matrix,
    max_statistic_test,
    mean_interval,
)
from app.research.range002.screen.types import SessionBars
from app.research.range002.spec.loader import load_frozen, parse_draft
from app.research.range002.spec.schema import SCREEN_V1_EXEMPT, SCREEN_V1_REQUIRED_SHA256
from tests.research.range002.governance.conftest import (  # noqa: F401  (autouse manifest seam)
    SIGNED_LEDGER,
    new_registry,
    open_run,
    synthetic_manifest,
)
from tests.research.range002.screen.conftest import (
    EQUITY,
    TICK,
    minutes_flat,
    mk,
    or_bars,
    session,
    synth_payload,
)
from tests.research.range002.spec._fixtures import SYNTH_MANIFEST_PATH, set_path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

SYMBOLS = ("AAA", "BBB", "CCC")


def _bars(breakout: bool) -> list:  # type: ignore[type-arg]
    if not breakout:
        return or_bars() + minutes_flat("10:00", "15:59", 10.05)
    return (
        or_bars()
        + minutes_flat("10:00", "10:04", 10.05)
        + [mk("10:05", 10.09, 10.20, 10.08, 10.18)]
        + minutes_flat("10:06", "15:59", 10.30)
    )


def test_screen_profile_p3a_flow_end_to_end(tmp_path: Path) -> None:
    # 1. profile freeze: a screen-profile spec, exempt fields null, profile bound into the hash
    payload = synth_payload()
    for path in SCREEN_V1_EXEMPT:
        set_path(payload, path, None)
    payload["profile"] = {
        "name": "screen",
        "version": 1,
        "required_fields_sha256": SCREEN_V1_REQUIRED_SHA256,
    }
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    frozen = tmp_path / "frozen.json"
    freeze_spec.freeze(draft, frozen, manifest_path=SYNTH_MANIFEST_PATH)
    view = to_guard_view(load_frozen(frozen))
    assert view.profile == "screen"

    # 2. registration -> capability (the real guard; only P2 replay and P3A are reachable)
    registry = new_registry(tmp_path / "runs.jsonl")
    run_id = open_run(registry, Phase.P3A, Partition.DEVELOPMENT_SELECTION, view.spec_sha256)
    cap = authorize(
        spec=view,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ExposureLedger.from_text(SIGNED_LEDGER),
    )
    assert cap.profile == "screen" and cap.citable is True  # type: ignore[attr-defined]
    params = extract_params(cap, parse_draft(payload))

    # 3. fixture loading: five regular sessions inside the authorised range, 3 symbols; one
    #    symbol-day has NO bars at all (a completely missing PIT symbol-day)
    rng = cap.date_range  # type: ignore[attr-defined]
    cal = expected_sessions(rng.start, date(rng.start.year, rng.start.month, 28))
    sess_days = [d for d, close in cal.items() if close == time(16, 0)][:5]
    assert len(sess_days) == 5
    missing = ("CCC", sess_days[3])
    sessions: list[SessionBars] = []
    for i, d in enumerate(sess_days):
        for sym in SYMBOLS:
            if (sym, d) == missing:
                continue
            sessions.append(session(_bars(breakout=(i + SYMBOLS.index(sym)) % 2 == 0), sym, d))

    # 4. coverage: denominator = EVERY expected PIT symbol-day, including the missing one
    expected = [(s, d) for d in sess_days for s in SYMBOLS]
    observed = {
        (s.symbol, s.day): presence_from_minutes(
            [b.start for b in s.bars], [], params.or_start, params.or_end
        )
        for s in sessions
    }
    cov = coverage_report(
        expected,
        observed,
        exclusions={},
        missing_causes={missing: MISSING_NO_DATA},
        or_max_gap_minutes=params.or_max_gap_minutes,
        threshold=0.98,
    )
    assert cov.denominator == 15 and cov.observed == 14 and cov.missing_no_data == 1
    assert cov.meets_threshold is False  # 14/15 < 0.98: reported, not repaired or dropped

    # 5. simulation: funnel reconciles, every candidate sees the same entered set
    run = run_screen(cap, params, sessions, TICK, EQUITY)
    assert run.funnel.eligible == 14 and run.citable is True
    entered = run.funnel.states["ENTERED"]
    assert entered > 0
    assert {c: sum(v.values()) for c, v in run.funnel.exits.items()} == {
        "TIME": entered,
        "R2": entered,
    }

    # 6. statistics / report: day-cluster bootstrap, then the portfolio basis with limits
    summary = summarize(cap, run.trades["R2"])
    assert summary["trades"] == entered and summary["basis"] == "signal"
    matrix = build_day_matrix(cap, run.trades, sess_days)
    cfg = BootstrapConfig(mean_block_days=2.0, reps=200, seed=7)
    assert mean_interval(cap, matrix, "R2", 0.9, cfg).config == cfg
    assert max_statistic_test(cap, matrix, 0.10, cfg).config == cfg
    limits = PortfolioLimits(EQUITY, 1, 0.5, 0.5, 3.0)
    port = schedule_portfolio(cap, run.trades["R2"], limits)
    ps = summarize_portfolio(cap, port)
    assert ps["basis"] == "portfolio" and ps["signal_trades"] == entered
    assert ps["accepted_trades"] + sum(ps["rejected_by_reason"].values()) == entered

    # 7. run closure: COMPLETED needs the guard's own capability_issued row; afterwards the
    #    capability is dead and no result entry point accepts it
    require_capability(cap)
    registry.close_run(run_id, RunStatus.COMPLETED, "a" * 64)
    with pytest.raises(InvalidCapabilityError):
        require_capability(cap)
    with pytest.raises(InvalidCapabilityError):
        summarize(cap, run.trades["R2"])
