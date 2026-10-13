"""The return-blind mapping probe and the non-blocking ``return_blind_probe`` ledger kind.

Synthetic only: no network. The fake vendor answers with bars carrying price and volume fields so
the tests can prove none of them reaches the output."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance.errors import ExposureLedgerError
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.model import DateRange, Partition, Phase

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import mapping_probe as mp  # noqa: E402

SECRET = "SECRET-VALUE-XYZ"
KEY = "KEY-VALUE-ABC"
DECISION = {
    "decision_date": "2026-10-13",
    "record_kind": "owner_instruction",
    "minutes_path": "docs/x.md",
    "minutes_sha256": "a" * 64,
}


def _bars(n: int) -> list[dict[str, Any]]:
    return [
        {"t": f"2016-01-04T14:{30 + i:02d}:00Z", "o": 1.11, "h": 2.22, "l": 0.99, "c": 1.5,
         "v": 98765, "n": 7, "vw": 1.4}
        for i in range(n)
    ]  # fmt: skip


def _vendor(calls: list[dict[str, Any]], statuses: dict[str, int] | None = None) -> Any:
    def get(url: str, params: Any, headers: Any) -> tuple[int, Any]:
        sym = url.rsplit("/", 2)[-2]
        calls.append({"sym": sym, "params": dict(params), "headers": dict(headers)})
        st = (statuses or {}).get(sym, 200)
        if st != 200:
            return st, {"message": "invalid symbol"}
        return 200, {"bars": _bars(3), "symbol": sym, "next_page_token": None}

    return get


def _items() -> list[Any]:
    return [
        mp.parse_probe("DD1,DD,2016-01-04,2016-01-04"),
        mp.parse_probe("DD1,DD,2016-01-04,-"),
        mp.parse_probe("BRK.B,BRK.B,2016-03-31,-"),
    ]


def test_output_has_status_counts_and_timestamps_only() -> None:
    calls: list[dict[str, Any]] = []
    out = mp.run_probe(
        _items(),
        max_requests=10,
        window_minutes=60,
        key=KEY,
        secret=SECRET,
        http_get=_vendor(calls),
    )
    text = json.dumps(out)
    for needle in ("1.11", "2.22", "0.99", "98765", "vw", '"o"', '"h"', '"c"', '"v"'):
        assert needle not in text
    assert KEY not in text and SECRET not in text
    rec = out["records"][0]
    assert tuple(rec) == mp.RECORD_FIELDS
    assert rec["bars"] == 3 and rec["first_bar_utc"] == "2016-01-04T14:30:00Z"
    assert rec["last_bar_utc"] == "2016-01-04T14:32:00Z" and rec["symbol_echo"] == "DD"
    assert out["return_blind"] is True and out["requests_made"] == 3


def test_request_shape_dst_aware_end_exclusive_and_credentials_in_headers_only() -> None:
    calls: list[dict[str, Any]] = []
    mp.run_probe(
        _items(),
        max_requests=10,
        window_minutes=60,
        key=KEY,
        secret=SECRET,
        http_get=_vendor(calls),
    )
    p0, p2 = calls[0]["params"], calls[2]["params"]
    assert p0["start"] == "2016-01-04T14:30:00Z" and p0["end"] == "2016-01-04T15:29:59Z"
    assert p2["start"] == "2016-03-31T13:30:00Z"  # EDT
    assert p0["feed"] == "sip" and p0["adjustment"] == "raw" and p0["asof"] == "2016-01-04"
    assert calls[1]["params"]["asof"] == "-"
    assert calls[0]["headers"]["APCA-API-KEY-ID"] == KEY
    assert KEY not in json.dumps([c["params"] for c in calls])


def test_hard_cap_is_enforced_before_any_request() -> None:
    calls: list[dict[str, Any]] = []
    with pytest.raises(mp.ProbeRefusal, match="hard cap"):
        mp.run_probe(
            _items(),
            max_requests=2,
            window_minutes=60,
            key=KEY,
            secret=SECRET,
            http_get=_vendor(calls),
        )
    assert calls == []


def test_a_400_is_recorded_not_retried_and_never_silently_dropped() -> None:
    calls: list[dict[str, Any]] = []
    out = mp.run_probe(
        [mp.parse_probe("APC1,APC1,2016-01-04,-")],
        max_requests=5, window_minutes=60, key=KEY, secret=SECRET,
        http_get=_vendor(calls, {"APC1": 400}),
    )  # fmt: skip
    assert len(calls) == 1
    rec = out["records"][0]
    assert rec["http_status"] == 400 and rec["bars"] is None and rec["error_kind"] == "HTTP_400"


def test_429_is_retried_at_most_twice_within_the_cap() -> None:
    seq = iter([429, 429, 200])
    calls: list[int] = []

    def get(url: str, params: Any, headers: Any) -> tuple[int, Any]:
        calls.append(1)
        st = next(seq)
        return (200, {"bars": _bars(1), "symbol": "DD"}) if st == 200 else (429, None)

    out = mp.run_probe(
        [mp.parse_probe("DD1,DD,2016-01-04,2016-01-04")],
        max_requests=3, window_minutes=60, key=KEY, secret=SECRET, http_get=get,
        sleep=lambda _s: None,
    )  # fmt: skip
    assert len(calls) == 3 and out["records"][0]["http_status"] == 200


def test_cli_never_overwrites_and_needs_both_credentials(tmp_path: Path, monkeypatch: Any) -> None:
    out = tmp_path / "probe.json"
    argv = ["--out", str(out), "--max-requests", "5", "--window-minutes", "60",
            "--key-env", "PK", "--secret-env", "PS", "--probe", "DD1,DD,2016-01-04,-"]  # fmt: skip
    monkeypatch.delenv("PK", raising=False)
    monkeypatch.delenv("PS", raising=False)
    assert mp.main(argv, http_get=_vendor([])) == mp.EXIT_REFUSED
    monkeypatch.setenv("PK", KEY)
    monkeypatch.setenv("PS", SECRET)
    assert mp.main(argv, http_get=_vendor([])) == mp.EXIT_OK
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert KEY not in out.read_text() and SECRET not in out.read_text()
    assert doc["schema"] == "range002.mapping_probe.v1"
    assert mp.main(argv, http_get=_vendor([])) == mp.EXIT_REFUSED  # exists: never overwritten


# ---- the ledger kind -------------------------------------------------------------------------


def _ledger(entries: list[dict[str, Any]]) -> ExposureLedger:
    return ExposureLedger.from_text(
        json.dumps({"schema_version": 1, "decision": DECISION, "entries": entries})
    )


def _probe_entry(**over: Any) -> dict[str, Any]:
    base = {
        "id": "probe-1", "start": "2016-01-04", "end": "2016-03-31",
        "description": "mapping probe", "source": "mapping_probe.py", "observed_by": "claude",
        "kind": "return_blind_probe",
        "probe_scope": "status codes, bar counts and bar timestamps only; no price or volume",
    }  # fmt: skip
    base.update(over)
    return base


def test_probe_entry_is_listed_but_never_blocks_a_request() -> None:
    led = _ledger([_probe_entry()])
    win = DateRange(date(2016, 1, 1), date(2016, 3, 31))
    assert [e.id for e in led.overlaps(win)] == ["probe-1"]  # visible
    assert (
        led.blocking_overlaps(win, phase=Phase.P3A, partition=Partition.DEVELOPMENT_SELECTION) == ()
    )


def test_a_prior_exposure_alongside_a_probe_still_blocks() -> None:
    prior = {
        "id": "seen-1", "start": "2016-02-01", "end": "2016-02-05", "description": "d",
        "source": "s", "observed_by": "o",
    }  # fmt: skip
    led = _ledger([_probe_entry(), prior])
    win = DateRange(date(2016, 1, 1), date(2016, 3, 31))
    hits = led.blocking_overlaps(win, phase=Phase.P3A, partition=Partition.DEVELOPMENT_SELECTION)
    assert [h.id for h in hits] == ["seen-1"]


@pytest.mark.parametrize(
    "bad",
    [
        {"probe_scope": "   "},
        {"phase": "P3A"},
        {"partition": "DEVELOPMENT_SELECTION"},
        {"planned_label": "x"},
    ],
)
def test_malformed_probe_entries_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ExposureLedgerError):
        _ledger([_probe_entry(**bad)])


def test_probe_scope_is_refused_on_other_kinds() -> None:
    with pytest.raises(ExposureLedgerError):
        _ledger([_probe_entry(kind="prior_exposure")])
