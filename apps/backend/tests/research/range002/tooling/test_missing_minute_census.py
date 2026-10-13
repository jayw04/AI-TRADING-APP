"""Missing-minute census: documented bar rule, planner, checkpointed cap, classification.

SYNTHETIC: fake HTTP, tiny duckdb store; no network, no market data.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import build_census_manifest as bcm  # noqa: E402
import classify_census as cc  # noqa: E402
import sip_trades_probe as sp  # noqa: E402

DAY = "2017-03-01"  # EST, 09:30 ET == 14:30 UTC
_ET, _UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")


def _utc(hh: int, mm: int, ss: int = 5) -> str:
    local = datetime(2017, 3, 1, hh, mm, ss, tzinfo=_ET)
    return local.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def test_documented_condition_rule() -> None:
    assert sp.bar_eligible((" ",), "A") and sp.bar_eligible(("@", "F"), "C")
    assert not sp.bar_eligible(("@", "I"), "C")  # strictest rule: odd lot wins
    assert not sp.bar_eligible(("Q",), "C") and not sp.bar_eligible(("Z",), "A")
    assert sp.bar_eligible(("B",), "C") and not sp.bar_eligible(("B",), "A")
    assert sp.bar_eligible(("T",), "A") and sp.bar_eligible((), None)  # unknown: conservative


def _store(tmp: Path, missing: set[tuple[str, int]]) -> Path:
    path = tmp / "s.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    for sym in ("AAA", "BBB", "CCC", "DDD", *[f"X{i:02d}" for i in range(20)]):
        for m in range(569, 640):
            if (sym, m) in missing:
                continue
            local = datetime(2017, 3, 1, m // 60, m % 60, tzinfo=_ET)
            ts = local.astimezone(_UTC).replace(tzinfo=None)
            con.execute("INSERT INTO minute_bars VALUES (?,?,1,1,1,1,1,'raw')", [sym, ts])
    con.close()
    return path


def test_planner_clusters_missing_minutes_controls_and_outage(tmp_path: Path) -> None:
    missing = {("AAA", 575), ("AAA", 576), ("AAA", 590), ("BBB", 580), ("CCC", 580), ("DDD", 580)}
    store = _store(tmp_path, missing)
    report = {"months": [{"month_start": "2017-03-01", "members_ranked": ["AAA", "BBB"]}]}
    mapping = {
        "entries": [
            {
                "vendor_ticker": "AAA",
                "schedule": [{"from": "2017-01-01", "request_symbol": "AAA"}],
                "asof_policy": "-",
            },
            {
                "vendor_ticker": "BBB",
                "schedule": [{"from": "2017-01-01", "request_symbol": "BBX"}],
                "asof_policy": "SEGMENT_START_DATE",
            },
        ]
    }
    doc = bcm.build(store, report, mapping)
    assert doc["summary"]["incomplete_member_days"] == 2 and doc["summary"]["samples"] == 3
    by = {(s["symbol"], s["interval_start_et"]): s for s in doc["samples"]}
    a1 = by[("AAA", "09:35:00")]
    assert a1["missing_minutes"] == ["09:35:00", "09:36:00"] and a1["interval_end_et"] == "09:37:00"
    assert a1["window_start_et"] == "09:34:00" and a1["window_end_et"] == "09:38:00"
    assert a1["control_minutes"] == ["09:34:00", "09:37:00"] and a1["request_symbol"] == "AAA"
    b = by[("BBB", "09:40:00")]
    assert b["request_symbol"] == "BBX" and b["asof"] == "2017-01-01"
    # 3 of 4 symbols lack 09:40 (>= 10%): suspected provider gap, never accounted for
    assert b["suspected_provider_gap_minutes"] == ["09:40:00"]
    assert by[("AAA", "09:50:00")]["suspected_provider_gap_minutes"] == []
    assert [s["id"] for s in doc["samples"]] == ["C0001", "C0002", "C0003"]


def _sample(**over: Any) -> dict[str, Any]:
    s = {
        "id": "C1",
        "symbol": "AAA",
        "day": DAY,
        "missing_minutes": ["09:35:00"],
        "control_minutes": ["09:34:00", "09:36:00"],
        "suspected_provider_gap_minutes": [],
    }
    s.update(over)
    return s


def _rec(minutes: dict[str, dict[str, Any]], **over: Any) -> dict[str, Any]:
    r = {
        "id": "C1",
        "symbol": "AAA",
        "day": DAY,
        "complete": True,
        "http_status": 200,
        "timestamps_within_window": True,
        "minutes": minutes,
    }
    r.update(over)
    return r


CTRL = {
    "09:34": {"trades": 3, "eligible": 3, "codes": {"@": 3}},
    "09:36": {"trades": 2, "eligible": 2, "codes": {"@": 2}},
}


def test_classification_matrix() -> None:
    c = cc.classify_sample
    assert c(_sample(), _rec(CTRL)) == {"09:35": cc.ACCOUNTED_EMPTY}
    odd = dict(CTRL, **{"09:35": {"trades": 2, "eligible": 0, "codes": {"I": 2}}})
    assert c(_sample(), _rec(odd)) == {"09:35": cc.ACCOUNTED_POSITIVE}
    elig = dict(CTRL, **{"09:35": {"trades": 2, "eligible": 1, "codes": {"@": 1, "I": 1}}})
    assert c(_sample(), _rec(elig)) == {"09:35": cc.BAR_ABSENT}
    assert c(_sample(), None) == {"09:35": cc.UNRESOLVED_INCOMPLETE}
    assert c(_sample(), _rec(CTRL, complete=False)) == {"09:35": cc.UNRESOLVED_INCOMPLETE}
    bad = {"09:34": {"trades": 0, "eligible": 0, "codes": {}}, "09:36": CTRL["09:36"]}
    assert c(_sample(), _rec(bad)) == {"09:35": cc.UNRESOLVED_CONTROL_FAILED}
    assert c(_sample(control_minutes=[]), _rec({})) == {"09:35": cc.UNRESOLVED_NO_CONTROL}
    out_of_window = _rec(CTRL, timestamps_within_window=False)
    assert c(_sample(), out_of_window) == {"09:35": cc.UNRESOLVED_CONTROL_FAILED}
    gap = _sample(suspected_provider_gap_minutes=["09:35:00"])
    assert c(gap, _rec(CTRL)) == {"09:35": cc.UNRESOLVED_GAP}


def test_day_level_counts_separate_the_two_evidence_tiers() -> None:
    manifest = {
        "samples": [
            _sample(id="C1"),
            _sample(id="C2", symbol="BBB"),
            _sample(id="C3", symbol="CCC"),
        ]
    }
    odd = dict(CTRL, **{"09:35": {"trades": 1, "eligible": 0, "codes": {"I": 1}}})
    recs = {
        "C1": _rec(CTRL, id="C1"),
        "C2": _rec(odd, id="C2", symbol="BBB"),
        "C3": {**_rec(CTRL, id="C3", symbol="CCC"), "complete": False},
    }
    res = cc.classify(manifest, recs)
    assert res["incomplete_member_days"] == 3
    assert res["days_all_minutes_accounted_positive_only"] == 1
    assert res["days_all_minutes_accounted_both_tiers"] == 2
    assert res["days_with_any_unresolved_minute"] == 1


def _manifest(tmp: Path, n: int) -> tuple[Path, str]:
    samples = [
        {
            "id": f"C{i:04d}",
            "stratum": "t",
            "symbol": "AAA",
            "request_symbol": "AAA",
            "asof": "-",
            "day": DAY,
            "interval_start_et": "09:35:00",
            "interval_end_et": "09:36:00",
            "window_start_et": "09:34:00",
            "window_end_et": "09:37:00",
        }
        for i in range(n)
    ]
    p = tmp / "m.json"
    p.write_text(json.dumps({"schema": sp.MANIFEST_SCHEMA, "samples": samples}), "utf-8")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def _tr(hh: int, mm: int, c: list[str], z: str = "C") -> dict[str, Any]:
    return {"t": _utc(hh, mm), "c": c, "z": z, "p": 1.23, "s": 9}


def test_cap_checkpoint_and_resume_never_classify_unattempted_as_no_trade(tmp_path: Path) -> None:
    path, sha = _manifest(tmp_path, 5)
    samples, _ = sp.load_manifest(path, sha)
    body = {"trades": [_tr(9, 34, ["@"]), _tr(9, 36, ["@"])], "next_page_token": None}
    ck = tmp_path / "ck.jsonl"
    out = sp.run_probe(
        samples,
        max_requests=3,
        key="k",
        secret="s",
        checkpoint=ck,
        partial_ok=True,
        http_get=lambda *_a: (200, body),
    )
    assert out["requests_made"] == 3 and len(out["records"]) == 3
    assert out["samples_not_attempted"] == ["C0003", "C0004"]
    assert len(ck.read_text().splitlines()) == 3

    def forbidden(*_a: Any) -> tuple[int, Any]:
        raise AssertionError("no request allowed")

    out2 = sp.run_probe(
        samples,
        max_requests=3,
        key="k",
        secret="s",
        checkpoint=ck,
        partial_ok=True,
        http_get=forbidden,
    )
    assert out2["requests_made"] == 3 and out2["samples_not_attempted"] == ["C0003", "C0004"]
    r = out["records"][0]
    assert r["minutes"]["09:34"]["eligible"] == 1 and r["timestamps_within_window"] is True
    assert "1.23" not in json.dumps(out)
    out3 = sp.run_probe(
        samples,
        max_requests=5,
        key="k",
        secret="s",
        checkpoint=ck,
        partial_ok=True,
        http_get=lambda *_a: (200, body),
    )
    assert out3["requests_made"] == 5
    assert [x["id"] for x in out3["records"]] == [f"C000{i}" for i in range(5)]


def test_returned_timestamp_outside_window_is_flagged(tmp_path: Path) -> None:
    path, sha = _manifest(tmp_path, 1)
    samples, _ = sp.load_manifest(path, sha)
    body = {"trades": [_tr(9, 40, ["@"])], "next_page_token": None}  # outside 09:34-09:37
    out = sp.run_probe(
        samples, max_requests=2, key="k", secret="s", http_get=lambda *_a: (200, body)
    )
    assert out["records"][0]["timestamps_within_window"] is False


def test_throttle_spaces_requests(tmp_path: Path) -> None:
    path, sha = _manifest(tmp_path, 2)
    samples, _ = sp.load_manifest(path, sha)
    slept: list[float] = []
    body = {"trades": [_tr(9, 34, ["@"])], "next_page_token": None}
    sp.run_probe(
        samples,
        max_requests=5,
        key="k",
        secret="s",
        http_get=lambda *_a: (200, body),
        sleep=slept.append,
        requests_per_minute=120,
    )
    assert slept and all(abs(x - 0.5) < 1e-9 for x in slept)


def test_record_for_another_symbol_day_is_never_applied() -> None:
    wrong = _rec(CTRL, symbol="ZZZ")
    assert cc.classify_sample(_sample(), wrong) == {"09:35": cc.UNRESOLVED_INCOMPLETE}
    other_day = _rec(CTRL, day="2017-03-02")
    assert cc.classify_sample(_sample(), other_day) == {"09:35": cc.UNRESOLVED_INCOMPLETE}


def test_unknown_condition_code_never_accounts_for_a_minute() -> None:
    assert sp.bar_eligible(("S",), "A") is True  # undocumented: stays eligible (conservative)
    assert sp.bar_eligible(("I", "S"), "A") is False  # a documented non-updating code still wins
