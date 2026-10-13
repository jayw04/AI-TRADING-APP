"""SIP trades probe: classification, request cap, truncation, return-blindness, manifest freeze.

SYNTHETIC: a fake HTTP layer; no network, no credentials, no market data.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import sip_trades_probe as sp  # noqa: E402

DAY = "2016-02-02"


def _manifest(tmp_path: Path, n: int = 1) -> tuple[Path, str]:
    samples = [
        {
            "id": f"S{i:02d}",
            "stratum": "t",
            "symbol": f"AAA{i}",
            "day": DAY,
            "interval_start_et": "09:30:00",
            "interval_end_et": "09:31:00",
            "window_start_et": "09:25:00",
            "window_end_et": "09:36:00",
        }
        for i in range(n)
    ]
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"schema": sp.MANIFEST_SCHEMA, "samples": samples}), "utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _tr(hhmmss: str, c: list[str] | None = None) -> dict[str, Any]:
    # 09:30 ET on 2016-02-02 is 14:30 UTC (EST)
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return {
        "t": f"{DAY}T{h + 5:02d}:{m:02d}:{s:02d}.123456789Z",
        "p": 123.45,
        "s": 7,
        "c": c or ["@"],
    }


def _fake(pages: list[tuple[int, Any]], seen: list[dict[str, str]] | None = None) -> sp.HttpGet:
    it = iter(pages)

    def get(url: str, params: Any, headers: Any) -> tuple[int, Any]:
        if seen is not None:
            seen.append(dict(params))
        return next(it)

    return get


def _run(tmp_path: Path, pages: list[tuple[int, Any]], *, n: int = 1, cap: int = 40, **kw: Any):
    path, sha = _manifest(tmp_path, n)
    samples, _ = sp.load_manifest(path, sha)
    return sp.run_probe(
        samples,
        max_requests=cap,
        key="k",
        secret="s",
        http_get=_fake(pages, kw.get("seen")),
        sleep=lambda _s: None,
    )


def test_no_trades_returned_when_window_has_neighbours(tmp_path: Path) -> None:
    body = {"trades": [_tr("09:29:10"), _tr("09:32:05")], "next_page_token": None}
    out = _run(tmp_path, [(200, body)])
    r = out["records"][0]
    assert r["classification"] == sp.CLASS_NO_TRADES and r["complete"] is True
    assert r["trades_before_interval"] == 1 and r["trades_after_interval"] == 1


def test_unresolved_when_the_whole_window_is_empty(tmp_path: Path) -> None:
    out = _run(tmp_path, [(200, {"trades": [], "next_page_token": None})])
    assert out["records"][0]["classification"] == sp.CLASS_UNRESOLVED


def test_potentially_excluded_vs_eligible(tmp_path: Path) -> None:
    only_odd = {"trades": [_tr("09:30:01", ["I"]), _tr("09:30:30", ["Q"])], "next_page_token": None}
    mixed = {
        "trades": [_tr("09:30:01", ["I"]), _tr("09:30:30", ["@", "F"])],
        "next_page_token": None,
    }
    sub = tmp_path / "a"
    sub.mkdir()
    a = _run(sub, [(200, only_odd)])
    assert a["records"][0]["classification"] == sp.CLASS_EXCLUDED
    assert a["records"][0]["condition_histogram_interval"] == {"I": 1, "Q": 1}
    b = _run(tmp_path, [(200, mixed)])
    assert b["records"][0]["classification"] == sp.CLASS_ELIGIBLE
    assert b["records"][0]["interval_trades_with_only_regular_codes"] == 1


def test_truncated_before_interval_end_is_incomplete_not_no_trades(tmp_path: Path) -> None:
    page = {"trades": [_tr("09:25:01")], "next_page_token": "tok"}
    # the cap of 2 total requests stops the pagination: INCOMPLETE, never NO_TRADES
    out = _run(tmp_path, [(200, page), (200, page)], cap=2)
    r = out["records"][0]
    assert r["classification"] == sp.CLASS_INCOMPLETE and r["complete"] is False


def test_pagination_stops_once_the_interval_is_covered(tmp_path: Path) -> None:
    page = {"trades": [_tr("09:30:10"), _tr("09:31:30")], "next_page_token": "tok"}
    out = _run(tmp_path, [(200, page)])
    r = out["records"][0]
    assert r["complete"] is True and r["requests_used"] == 1
    assert r["classification"] == sp.CLASS_ELIGIBLE


def test_http_error_and_429_retries_count_against_the_cap(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        [(429, None), (429, None), (200, {"trades": [_tr("09:29:00")], "next_page_token": None})],
    )
    assert out["requests_made"] == 3 and out["records"][0]["classification"] == sp.CLASS_NO_TRADES
    err = _run(tmp_path, [(500, None)])
    assert err["records"][0]["classification"] == sp.CLASS_INCOMPLETE


def test_samples_over_the_cap_are_refused_before_any_request(tmp_path: Path) -> None:
    path, sha = _manifest(tmp_path, 5)
    samples, _ = sp.load_manifest(path, sha)
    with pytest.raises(sp.ProbeRefusal):
        sp.run_probe(samples, max_requests=4, key="k", secret="s", http_get=_fake([]))


def test_manifest_hash_mismatch_refuses(tmp_path: Path) -> None:
    path, _ = _manifest(tmp_path)
    with pytest.raises(sp.ProbeRefusal):
        sp.load_manifest(path, "0" * 64)


def test_request_uses_the_dated_request_symbol_and_asof(tmp_path: Path) -> None:
    doc = {
        "schema": sp.MANIFEST_SCHEMA,
        "samples": [
            {
                "id": "R1",
                "stratum": "t",
                "symbol": "BKNG",
                "request_symbol": "PCLN",
                "asof": "-",
                "day": DAY,
                "interval_start_et": "09:30:00",
                "interval_end_et": "09:31:00",
                "window_start_et": "09:25:00",
                "window_end_et": "09:36:00",
            }
        ],
    }
    path = tmp_path / "r.json"
    path.write_text(json.dumps(doc), "utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    samples, _ = sp.load_manifest(path, sha)
    urls: list[str] = []
    seen: list[dict[str, str]] = []

    def get(url: str, params: Any, headers: Any) -> tuple[int, Any]:
        urls.append(url)
        seen.append(dict(params))
        return 200, {"trades": [_tr("09:29:10")], "next_page_token": None}

    out = sp.run_probe(samples, max_requests=5, key="k", secret="s", http_get=get)
    assert urls[0].endswith("/PCLN/trades") and seen[0]["asof"] == "-"
    assert out["records"][0]["symbol"] == "BKNG" and out["records"][0]["request_symbol"] == "PCLN"


def test_output_is_return_blind(tmp_path: Path) -> None:
    out = _run(tmp_path, [(200, {"trades": [_tr("09:30:01")], "next_page_token": None})])
    text = json.dumps(out)
    assert "123.45" not in text
    for rec in out["records"]:
        assert set(rec) == set(sp.RECORD_FIELDS)
        assert "p" not in rec and "s" not in rec and "price" not in rec


def test_cli_writes_output_and_chained_access_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, sha = _manifest(tmp_path)
    monkeypatch.setenv("K_ENV", "x")
    monkeypatch.setenv("S_ENV", "y")
    out, log = tmp_path / "out.json", tmp_path / "log.jsonl"
    body = {"trades": [_tr("09:29:10")], "next_page_token": None}
    rc = sp.main(
        [
            "--manifest",
            str(path),
            "--manifest-sha256",
            sha,
            "--max-requests",
            "5",
            "--key-env",
            "K_ENV",
            "--secret-env",
            "S_ENV",
            "--out",
            str(out),
            "--access-log",
            str(log),
        ],
        http_get=_fake([(200, body)]),
    )
    assert rc == sp.EXIT_OK and out.exists()
    lines = log.read_text().splitlines()
    assert [json.loads(x)["event"] for x in lines] == ["trades_probe_start", "trades_probe_done"]
    assert json.loads(lines[1])["prev_line_sha256"] == hashlib.sha256(lines[0].encode()).hexdigest()
    # never overwritten
    assert (
        sp.main(
            [
                "--manifest",
                str(path),
                "--manifest-sha256",
                sha,
                "--max-requests",
                "5",
                "--key-env",
                "K_ENV",
                "--secret-env",
                "S_ENV",
                "--out",
                str(out),
                "--access-log",
                str(log),
            ],
            http_get=_fake([]),
        )
        == sp.EXIT_REFUSED
    )


def test_bars_endpoint_reads_only_timestamps(tmp_path: Path) -> None:
    doc = {
        "schema": sp.MANIFEST_SCHEMA,
        "samples": [
            {
                "id": "BARS1",
                "stratum": "t",
                "symbol": "AMGN",
                "endpoint": "bars",
                "day": DAY,
                "interval_start_et": "10:26:00",
                "interval_end_et": "10:30:00",
                "window_start_et": "10:20:00",
                "window_end_et": "10:40:00",
            }
        ],
    }
    path = tmp_path / "b.json"
    path.write_text(json.dumps(doc), "utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    samples, _ = sp.load_manifest(path, sha)
    seen: list[tuple[str, dict[str, str]]] = []
    bar = {"t": f"{DAY}T15:27:00Z", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 9}

    def get(url: str, params: Any, headers: Any) -> tuple[int, Any]:
        seen.append((url, dict(params)))
        return 200, {"bars": [bar], "symbol": "AMGN", "next_page_token": None}

    out = sp.run_probe(samples, max_requests=3, key="k", secret="s", http_get=get)
    assert seen[0][0].endswith("/AMGN/bars") and seen[0][1]["timeframe"] == "1Min"
    rec = out["records"][0]
    assert rec["classification"] == sp.CLASS_BARS_RETURNED and rec["endpoint"] == "bars"
    assert "1.5" not in json.dumps(out) and set(rec) == set(sp.RECORD_FIELDS)
    empty = sp.run_probe(
        samples,
        max_requests=3,
        key="k",
        secret="s",
        http_get=lambda *_a: (200, {"bars": [], "next_page_token": None}),
    )
    assert empty["records"][0]["classification"] == sp.CLASS_UNRESOLVED
    with pytest.raises(sp.ProbeRefusal):
        bad = dict(doc["samples"][0], endpoint="quotes")
        path.write_text(json.dumps({"schema": sp.MANIFEST_SCHEMA, "samples": [bad]}), "utf-8")
        sp.load_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest())
