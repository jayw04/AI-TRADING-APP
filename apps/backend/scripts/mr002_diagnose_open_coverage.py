"""Does a HELD position lose its execution price because the BAR is missing, or merely
because the symbol fell out of the ENTRY-eligibility funnel?

dataset.py builds open_next only for `members = self._uni_at(d)` and then `continue`s past
any member with a non-finite z or an unresolved sector. Those are ENTRY criteria. If the
price bar exists but open_next is absent, then entry eligibility is being conflated with
the ability to TRADE AN EXISTING POSITION -- a defect.

DIAGNOSTIC ONLY.
"""
from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import scripts.mr002_development_run as devrun  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))

# Ground truth: every (permaticker, session) that HAS a price bar in the frozen store.
# prices are keyed by TICKER; the universe carries permaticker -> ticker.
tick = {int(pt): t for pt, t in ds.con.execute(
    "SELECT DISTINCT permaticker, ticker FROM universe").fetchall()}
rows = ds.con.execute(
    "SELECT ticker, date FROM prices WHERE open IS NOT NULL AND open > 0").fetchall()
BAR = {(t, d if isinstance(d, date) else date.fromisoformat(str(d))) for t, d in rows}
print(f"price bars with a valid open: {len(BAR):,}   permaticker->ticker: {len(tick):,}")

R = {
    "held_position_days": 0,
    "held_with_open_next": 0,
    "held_WITHOUT_open_next": 0,
    "held_WITHOUT_open_next_BUT_BAR_EXISTS": 0,
    "held_WITHOUT_open_next_and_bar_genuinely_absent": 0,
}

orig = devrun.build_joint


def spy(holdings, candidates):
    return orig(holdings, candidates)


# walk the loop ourselves, tracking positions the same way run_config does
import app.research.mr002.joint_portfolio as jp  # noqa: E402

_real_build = jp.build_joint
SESSION = {"inp": None}


def wrapped_build(holdings, candidates):
    inp = SESSION["inp"]
    for h in holdings:
        R["held_position_days"] += 1
        if h.tradable:
            R["held_with_open_next"] += 1
        else:
            R["held_WITHOUT_open_next"] += 1
            if (tick.get(h.permaticker), inp.next_open_session) in BAR:
                R["held_WITHOUT_open_next_BUT_BAR_EXISTS"] += 1
            else:
                R["held_WITHOUT_open_next_and_bar_genuinely_absent"] += 1
    return _real_build(holdings, candidates)


devrun.build_joint = wrapped_build

# patch run_config's loop to publish the current DayInputs
_orig_run = devrun.run_config


def run_with_session(days_, cfg):
    class Tap(list):
        def __iter__(self):
            for x in super().__iter__():
                SESSION["inp"] = x
                yield x

    return _orig_run(Tap(days_), cfg)


print("running config A ...", flush=True)
run_with_session(days, CONFIGS["A"])

R["pct_held_without_open_next"] = (
    100.0 * R["held_WITHOUT_open_next"] / max(1, R["held_position_days"])
)
R["pct_of_those_where_the_BAR_EXISTS"] = (
    100.0 * R["held_WITHOUT_open_next_BUT_BAR_EXISTS"]
    / max(1, R["held_WITHOUT_open_next"])
)
print(json.dumps(R, indent=2))
