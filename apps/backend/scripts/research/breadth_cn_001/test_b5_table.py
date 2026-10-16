"""Parser and consistency test for the B5 cost/rule table (offline).  Run: python3 test_b5_table.py"""

import csv
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import b5_build_table as B  # noqa: E402

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL = re.compile(r"^https?://[A-Za-z0-9.-]+(/[^\s;]*)?$")


def load() -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "b5.csv"
        B.write(p)
        with p.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))


def is_iso(s: str) -> bool:
    if not ISO.match(s):
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


def test_schema_and_dates() -> None:
    rows = load()
    assert rows and list(rows[0]) == B.COLUMNS
    for r in rows:
        assert is_iso(r["effective_from"]), r
        assert is_iso(r["notice_date"]), r
        assert r["status"] in B.STATUSES, r
        assert r["event_type"] in B.EVENT_TYPES, r
        assert r["side"] in B.SIDES and r["hedge_class"] in B.HEDGE, r
        assert r["binding_for_ic"] in {"yes", "N/A"}, r
        assert r["parameter"] and r["products"] and r["unit"], r
    print(
        f"ok {len(rows)} rows: strict ISO dates, allowed statuses/event types/sides/hedge classes"
    )


def test_one_row_per_event_and_order() -> None:
    rows = load()
    keys = [
        (r["parameter"], r["products"], r["side"], r["hedge_class"], r["effective_from"])
        for r in rows
    ]
    assert len(keys) == len(set(keys)), "two rows describe the same change event"
    for r in rows:
        assert ";" not in r["url"] and ".." not in r["url"], r["url"]
        assert r["url"] == "N/A" or URL.match(r["url"]), r["url"]
        assert (r["url"] == "N/A") == (r["status"] == "ASSUMPTION") or r["status"] != "ASSUMPTION"
        if r["status"] == "PRESS_REPORTED":
            assert r["url"].startswith("https://"), r
    print("ok one row per change event; every URL absolute and single")


def test_values() -> None:
    rows = load()
    for r in rows:
        if r["binding_for_ic"] == "N/A" and "IC" not in r["products"].split("|"):
            assert r["value"] == "N/A" and r["value_kind"] == "N/A", r
        if r["value_kind"] == "number":
            float(r["value"])
        if r["status"] == "NOT_EXTRACTED":
            assert r["value"] == "N/A", r

    def get(p: str, eff: str, **kw: str) -> dict:
        return next(
            x
            for x in rows
            if x["parameter"] == p
            and x["effective_from"] == eff
            and all(x[k] == v for k, v in kw.items())
        )

    assert get("close_today_fee_bp", "2015-09-07")["value"] == "23"  # the 2015 peak
    assert get("close_today_fee_bp", "2023-03-20")["value"] == "2.3"
    assert (
        get("open_limit_lots", "2019-04-22")["value"] == "500"
        and get("open_limit_lots", "2019-04-22")["status"] == "PRESS_REPORTED"
    )
    assert get("open_limit_lots", "2022-07-22")["status"] == "VERIFIED_PRIMARY"
    assert get("margin_pct", "2019-04-22", products="IC")["value"] == "12"
    assert get("margin_pct", "2017-09-18")["binding_for_ic"] == "N/A"  # IF/IH-only change
    assert get("tick_points", "2026-10-16")["value"] == "0.2"
    assert get("broker_addon_bp", "2016-10-17")["status"] == "ASSUMPTION"
    assert (
        get("broker_addon_bp", "2016-10-17")["value"] == "1"
        and get("stress_run_cost_multiplier", "2016-10-17")["value"] == "2"
    )
    fees = [
        x for x in rows if x["parameter"] == "close_today_fee_bp" and x["event_type"] == "change"
    ]
    assert [x["value"] for x in sorted(fees, key=lambda x: x["effective_from"])] == [
        "1.15",
        "23",
        "9.2",
        "6.9",
        "4.6",
        "3.45",
        "2.3",
    ]
    print(
        "ok spot checks: 2015-09 close-today peak, 500-lot limit dated 2019-04-22 (press) and 2022 (primary), IC margin path, tick, assumption flagged"
    )


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ALL TESTS PASSED")
