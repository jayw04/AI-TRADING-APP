"""build_symbol_mapping.py: explicit request symbol + provenance for every universe symbol."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import build_symbol_mapping as bsm  # noqa: E402


def _probe(*recs: tuple[str, str, int, int, str | None]) -> dict[str, Any]:
    return {
        "records": [
            {
                "vendor_ticker": v,
                "request_symbol": r,
                "day": "2016-01-04",
                "asof": "-",
                "http_status": st,
                "bars": n,
                "first_bar_utc": None,
                "last_bar_utc": None,
                "symbol_echo": echo,
                "error_kind": None,
            }  # fmt: skip
            for v, r, st, n, echo in recs
        ]
    }


ROWS = {
    "APC1": {
        "relatedtickers": "AEUA APC",
        "firstpricedate": "1997-12-31",
        "lastpricedate": "2019-08-08",
    },
    "DD1": {
        "relatedtickers": "CTA-PA DD",
        "firstpricedate": "1997-12-31",
        "lastpricedate": "2017-08-31",
    },
    "XYZ9": {
        "relatedtickers": "OTHER",
        "firstpricedate": "2000-01-03",
        "lastpricedate": "2020-01-03",
    },
    "ABC2": {
        "relatedtickers": "ABC",
        "firstpricedate": "2000-01-03",
        "lastpricedate": "2020-01-03",
    },
    "BRK.B": {
        "relatedtickers": "BRK.A",
        "firstpricedate": "1997-12-31",
        "lastpricedate": "2026-10-12",
    },
    "AAL": {"relatedtickers": None, "firstpricedate": "1997-12-31", "lastpricedate": "2026-10-12"},
}


def test_every_symbol_gets_an_explicit_request_symbol_and_provenance() -> None:
    probe = _probe(("APC1", "APC", 200, 60, "APC"), ("DD1", "DD", 200, 60, "DD"),
                   ("BRK.B", "BRK.B", 200, 60, "BRK.B"))  # fmt: skip
    got = {e["vendor_ticker"]: e for e in bsm.build_entries(
        ["AAL", "APC1", "DD1", "BRK.B"], ROWS, probe
    )}  # fmt: skip
    assert got["AAL"]["provenance"] == bsm.PROV_ALPHA and got["AAL"]["request_symbol"] == "AAL"
    assert got["APC1"]["provenance"] == bsm.PROV_SUFFIX and got["APC1"]["request_symbol"] == "APC"
    assert got["APC1"]["asof_policy"] == "WINDOW_START_DATE"
    assert got["APC1"]["evidence"]["note"].startswith("supporting evidence")
    assert (
        got["BRK.B"]["provenance"] == bsm.PROV_CLASS and got["BRK.B"]["request_symbol"] == "BRK.B"
    )


def test_class_share_symbol_is_preserved_never_stripped() -> None:
    (e,) = bsm.build_entries(["BRK.B"], ROWS, _probe())
    assert e["request_symbol"] == "BRK.B" and e["provenance"] == bsm.PROV_CLASS


def test_suffix_without_relatedtickers_support_is_unverified_not_stripped() -> None:
    probe = _probe(("XYZ9", "XYZ", 200, 60, "XYZ"))
    (e,) = bsm.build_entries(["XYZ9"], ROWS, probe)
    assert e["provenance"] == bsm.PROV_UNVERIFIED and e["request_symbol"] == "XYZ9"


def test_suffix_without_a_successful_probe_is_unverified() -> None:
    for probe in (
        _probe(),
        _probe(("ABC2", "ABC", 400, 0, None)),
        _probe(("ABC2", "ABC", 200, 0, "ABC")),
    ):
        (e,) = bsm.build_entries(["ABC2"], ROWS, probe)
        assert e["provenance"] == bsm.PROV_UNVERIFIED and e["request_symbol"] == "ABC2"


def test_cli_refuses_to_overwrite_and_reports_unverified_with_exit_3(tmp_path: Path) -> None:
    d = tmp_path / "export"
    d.mkdir()
    con = duckdb.connect(":memory:")
    con.execute(
        'CREATE TABLE tickers("table" VARCHAR, ticker VARCHAR, relatedtickers VARCHAR,'
        " firstpricedate DATE, lastpricedate DATE)"
    )
    con.execute("INSERT INTO tickers VALUES ('SEP','AAL',NULL,'1997-12-31','2026-10-12'),"
                " ('SEP','XYZ9','OTHER','2000-01-03','2020-01-03')")  # fmt: skip
    con.execute(f"COPY tickers TO '{(d / 'tickers.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()
    uni = tmp_path / "u.txt"
    uni.write_text("AAL\nXYZ9\n", encoding="utf-8")
    probe = tmp_path / "p.json"
    probe.write_text(json.dumps(_probe()), encoding="utf-8")
    out = tmp_path / "m.json"
    argv = ["--universe-file", str(uni), "--daily-dir", str(d), "--table-filter", "SEP",
            "--probe-json", str(probe), "--out", str(out)]  # fmt: skip
    assert bsm.main(argv) == bsm.EXIT_UNVERIFIED
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["unverified"] == ["XYZ9"] and doc["symbols"] == 2
    assert bsm.main(argv) == bsm.EXIT_REFUSED  # never overwritten
    pytest.importorskip("duckdb")
