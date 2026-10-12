"""SYNTHETIC fixtures for the screen kernel. No market data, no real spec value, no P0 decision.

A capability is issued by the REAL guard through the only phase that accepts engine validation
(``P2`` + ``REPLAY_RNG001``, range inside the R2 window). Its outputs are never citable.
"""

from __future__ import annotations

import copy
import json
import sys  # noqa: E402
from collections.abc import Iterator
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.spec_adapter import to_guard_view
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.types import Bar, ScreenParams, SessionBars
from app.research.range002.spec.loader import load_frozen, parse_draft
from tests.research.range002.governance.conftest import (  # noqa: F401  (autouse manifest seam)
    LEDGER_SHA,
    SIGNED_LEDGER,
    new_registry,
    open_run,
    synthetic_manifest,
)
from tests.research.range002.spec._fixtures import (
    SYNTH_MANIFEST_PATH,
    complete_payload,
    set_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import freeze_spec  # noqa: E402

REPLAY_RANGE = DateRange(date(2026, 1, 2), date(2026, 6, 12))
DAY = date(2026, 3, 2)
TICK = 0.01
EQUITY = 100_000.0

CANDIDATES = [
    {"id": "TIME", "family": "time", "params": {}},
    {"id": "R2", "family": "fixed_r", "params": {"r_multiple": 2.0}},
]


def synth_payload(**overrides: Any) -> dict[str, Any]:
    payload = complete_payload(signed=True)
    set_path(payload, "exits.candidates", copy.deepcopy(CANDIDATES))
    set_path(payload, "signal.or_completeness_rule", 0)
    set_path(payload, "fill.halt_policy", "UNEXECUTABLE_DURING_UNAVAILABLE")
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    for path, value in overrides.items():
        set_path(payload, path.replace("__", "."), value)
    return payload


def make_capability(tmp: Path, payload: dict[str, Any]) -> tuple[object, ScreenParams | None]:
    draft = tmp / "draft.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")
    frozen = tmp / "frozen.json"
    freeze_spec.freeze(draft, frozen, manifest_path=SYNTH_MANIFEST_PATH)
    view = to_guard_view(load_frozen(frozen))
    registry = new_registry(tmp / "runs.jsonl")
    run_id = open_run(registry, Phase.P2, Partition.REPLAY_RNG001, view.spec_sha256)
    cap = authorize(
        spec=view,
        phase=Phase.P2,
        partition=Partition.REPLAY_RNG001,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ExposureLedger.from_text(SIGNED_LEDGER),
        requested_range=REPLAY_RANGE,
    )
    return cap, None


@pytest.fixture
def cap_params(tmp_path: Path) -> Iterator[tuple[object, ScreenParams]]:
    payload = synth_payload()
    cap, _ = make_capability(tmp_path, payload)
    yield cap, extract_params(cap, parse_draft(payload))


def mk(minute: str, o: float, h: float, low: float, c: float, v: int = 1000) -> Bar:
    hh, mm = (int(p) for p in minute.split(":"))
    return Bar(time(hh, mm), o, h, low, c, v)


def or_bars(high: float = 10.10, low: float = 10.00) -> list[Bar]:
    """30 one-minute OR bars 09:30..09:59 spanning [low, high]."""
    out: list[Bar] = []
    mid = round((high + low) / 2, 4)
    for i in range(30):
        mm = 30 + i
        hh, m = 9 + mm // 60, mm % 60
        bar_hi = high if i == 7 else mid
        bar_lo = low if i == 3 else mid
        out.append(Bar(time(hh, m), mid, bar_hi, bar_lo, mid, 1000))
    return out


def minutes_flat(start: str, end: str, px: float) -> list[Bar]:
    """Flat bars at px every minute from start to end inclusive."""
    sh, sm = (int(p) for p in start.split(":"))
    eh, em = (int(p) for p in end.split(":"))
    out: list[Bar] = []
    t = sh * 60 + sm
    while t <= eh * 60 + em:
        out.append(Bar(time(t // 60, t % 60), px, px, px, px, 500))
        t += 1
    return out


def session(
    bars: list[Bar],
    symbol: str = "AAA",
    day: date = DAY,
    *,
    close: time = time(16, 0),
    gaps: frozenset[time] = frozenset(),
    halts: frozenset[time] = frozenset(),
    feed: str = "sip",
    conv: str = "start",
    permaticker: str | None = None,
) -> SessionBars:
    return SessionBars(
        symbol,
        day,
        feed,
        conv,
        close,
        tuple(sorted(bars, key=lambda b: b.start)),
        gaps,
        halts,
        permaticker if permaticker is not None else f"PERM-{symbol}",
    )
