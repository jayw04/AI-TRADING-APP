"""census_tier_e_gap_share: shares of symbols lacking a bar at tier-E minutes (synthetic)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import census_tier_e_gap_share as g  # noqa: E402

_ET, _UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")


def test_shares_and_summary(tmp_path: Path) -> None:
    store = tmp_path / "s.duckdb"
    con = duckdb.connect(str(store))
    con.execute("CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, volume BIGINT)")
    for sym in [f"S{i}" for i in range(10)]:
        for m in range(570, 600):
            if sym in ("S0", "S1") and m == 575:  # 2 of 10 symbols lack 09:35
                continue
            ts = (
                datetime(2017, 3, 1, m // 60, m % 60, tzinfo=_ET)
                .astimezone(_UTC)
                .replace(tzinfo=None)
            )
            con.execute("INSERT INTO minute_bars VALUES (?,?,1)", [sym, ts])
        ts = datetime(2017, 3, 1, 15, 59, tzinfo=_ET).astimezone(_UTC).replace(tzinfo=None)
        con.execute("INSERT INTO minute_bars VALUES (?,?,1)", [sym, ts])
    con.close()
    manifest = {"samples": [{"id": "C1", "day": "2017-03-01"}]}
    cls = {
        "per_sample": [
            {"id": "C1", "classes": {"09:35": g.TIER_E, "09:36": "ACCOUNTED_FOR_POSITIVE"}}
        ]
    }
    vals = g.shares(store, manifest, cls)
    assert vals == [0.2]
    s = g.summary(vals, 0.05)
    assert s["tier_e_minutes"] == 1 and s["minutes_at_or_above_warn_share"] == 1
