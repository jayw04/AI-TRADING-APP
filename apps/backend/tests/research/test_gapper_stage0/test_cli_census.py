"""Census CLI: latch-first exit codes + an end-to-end run over a tiny cache."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from app.research.gapper_stage0 import design_latch
from app.research.gapper_stage0.design_latch import sha256_of_file
from app.research.gapper_stage0.provenance import validate_provenance

BACKEND_DIR = Path(__file__).resolve().parents[3]
CLI_SCRIPT = BACKEND_DIR / "scripts" / "gapper_stage0_census.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("gapper_stage0_census_cli", CLI_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_day_file(root: Path, symbol: str, day: str, pm: int, rth: int) -> None:
    recs = []
    base_pm = pd.Timestamp(f"{day} 04:00", tz="America/New_York")
    for i in range(pm):
        recs.append(
            {
                "t": (base_pm + pd.Timedelta(minutes=i)).tz_convert("UTC"),
                "o": 10.0,
                "h": 10.0,
                "l": 10.0,
                "c": 10.0,
                "v": 100.0,
            }
        )
    base_rth = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
    for i in range(rth):
        recs.append(
            {
                "t": (base_rth + pd.Timedelta(minutes=i)).tz_convert("UTC"),
                "o": 10.0,
                "h": 10.0,
                "l": 10.0,
                "c": 10.0,
                "v": 100.0,
            }
        )
    out = root / symbol / "1Min"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(recs).to_parquet(out / f"{day}.parquet")


def test_missing_docx_exits_2_with_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _load_cli()
    rc = cli.main(
        [
            "--design-docx",
            str(tmp_path / "absent.docx"),
            "--bar-cache-root",
            str(tmp_path / "cache"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert rc == cli.EXIT_DESIGN_MISSING == 2
    assert "design artifact not present" in capsys.readouterr().err


def test_superseded_and_mismatch_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _load_cli()
    docx = tmp_path / "design.docx"
    docx.write_bytes(b"not the approved artifact")
    args = [
        "--design-docx",
        str(docx),
        "--bar-cache-root",
        str(tmp_path / "cache"),
        "--out",
        str(tmp_path / "out"),
    ]
    assert cli.main(args) == cli.EXIT_DESIGN_MISMATCH == 4
    monkeypatch.setattr(design_latch, "SUPERSEDED_SHA256", sha256_of_file(docx))
    assert cli.main(args) == cli.EXIT_DESIGN_SUPERSEDED == 3


def test_end_to_end_census_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _load_cli()
    # Latch mechanism: point the approved constant at this stand-in artifact.
    docx = tmp_path / "design.docx"
    docx.write_bytes(b"stand-in approved design")
    monkeypatch.setattr(design_latch, "APPROVED_DESIGN_SHA256", sha256_of_file(docx))

    cache = tmp_path / "bars_cache"
    _write_day_file(cache, "AAA", "2026-08-13", pm=60, rth=390)  # sufficient
    _write_day_file(cache, "BBB", "2026-08-13", pm=3, rth=100)  # partial
    out_dir = tmp_path / "out"
    rc = cli.main(
        [
            "--design-docx",
            str(docx),
            "--bar-cache-root",
            str(cache),
            "--out",
            str(out_dir),
            "--created-at",
            "2026-08-17T12:00:00+00:00",
        ]
    )
    assert rc == 0
    reports = list(out_dir.glob("gapper_stage0_census_*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    validate_provenance(report)  # stamped, write_class=reconstruction
    assert report["provenance"]["source_sha256"] == sha256_of_file(docx)
    assert report["candidate_dates"] == 2
    assert report["sufficient_candidate_dates"] == 1
    assert report["sufficient_event_days"] == 1
    assert report["meets_target"] is False  # 1 << 250 — the honest shortfall
    assert report["contract_complete"] is False  # source_vendor still owner-unset
    # No verdict anywhere in the census output — measurements only.
    assert "verdict" not in report


def test_events_file_restricts_the_census(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _load_cli()
    docx = tmp_path / "design.docx"
    docx.write_bytes(b"stand-in approved design")
    monkeypatch.setattr(design_latch, "APPROVED_DESIGN_SHA256", sha256_of_file(docx))
    cache = tmp_path / "bars_cache"
    _write_day_file(cache, "AAA", "2026-08-13", pm=60, rth=390)
    _write_day_file(cache, "BBB", "2026-08-13", pm=60, rth=390)
    events = tmp_path / "events.json"
    events.write_text(json.dumps([{"symbol": "AAA", "date": "2026-08-13"}]), encoding="utf-8")
    out_dir = tmp_path / "out"
    rc = cli.main(
        [
            "--design-docx",
            str(docx),
            "--bar-cache-root",
            str(cache),
            "--events",
            str(events),
            "--out",
            str(out_dir),
            "--created-at",
            "2026-08-17T13:00:00+00:00",
        ]
    )
    assert rc == 0
    report = json.loads(next(iter(out_dir.glob("*.json"))).read_text(encoding="utf-8"))
    assert report["candidate_dates"] == 1
    assert report["rows"][0]["symbol"] == "AAA"
