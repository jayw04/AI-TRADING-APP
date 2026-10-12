"""The PIT diagnostic on a SYNTHETIC DuckDB built in tmp_path. Fixture data only; the numbers
asserted here describe the fixture, never a vendor store."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import pit_coverage_ro  # noqa: E402


@pytest.fixture
def store(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        'CREATE TABLE tickers("table" VARCHAR, ticker VARCHAR, permaticker BIGINT, isdelisted VARCHAR,'
        " firstpricedate DATE, lastpricedate DATE)"
    )
    con.execute(
        """INSERT INTO tickers VALUES
        ('SEP','AAA',1,'N','2010-01-04','2026-06-12'),('SF1','AAA',1,'N','2010-01-04','2026-06-12'),
        ('SEP','DEAD',2,'Y','2010-01-04','2015-03-02'),('SF1','DEAD',2,'Y','2010-01-04','2015-03-02'),
        ('SEP','REUS',3,'Y','2010-01-04','2012-01-03'),('SEP','REUS',4,'N','2018-01-02','2026-06-12'),
        ('SEP','OLDN',5,'Y','2010-01-04','2017-06-30'),('SEP','NEWN',5,'N','2017-07-01','2026-06-12'),
        ('SEP','CLSH',6,'N','2010-01-04','2026-06-12'),('SEP','CLSH',7,'N','2016-01-04','2026-06-12')"""
    )
    con.execute("CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute(
        "INSERT INTO sep SELECT 'AAA', d, 1, 1 FROM range(DATE '2024-01-01', DATE '2024-01-11', INTERVAL 1 DAY) t(d)"
    )
    con.execute(
        "INSERT INTO sep SELECT 'DEAD', d, 1, 1 FROM range(DATE '2015-01-01', DATE '2015-01-06', INTERVAL 1 DAY) t(d)"
    )
    con.close()
    return path


def _section(text: str, title: str) -> list[str]:
    block = text.split(f"## {title}\n", 1)[1].split("\n\n", 1)[0]
    return block.splitlines()[1:]  # drop the header row


def test_sep_counts_are_not_inflated_by_duplicate_metadata_rows(store: Path) -> None:
    out = pit_coverage_ro.report(str(store))
    rows = _section(out, "SEP coverage delisted vs active (SEP aggregated per ticker first)")
    by_flag = {r.split(" | ")[0]: r.split(" | ") for r in rows}
    # DEAD has two metadata rows (SEP + SF1) but only 5 SEP rows: the count must stay 5
    assert by_flag["True"][4] == "5"
    assert by_flag["False"][4] == "10"


def test_repeated_ids_are_split_by_temporal_overlap_not_declared_legitimate(store: Path) -> None:
    out = pit_coverage_ro.report(str(store))
    ticker_side = _section(
        out, "ticker -> several issuers: reuse candidates (no overlap) vs CONFLICTS (overlap)"
    )[0].split(" | ")
    # REUS: sequential issuers 3 then 4; CLSH: issuers 6 and 7 simultaneously active
    assert ticker_side == ["2", "1", "1"]
    issuer_side = _section(
        out, "issuer -> several tickers: rename candidates (no overlap) vs CONFLICTS (overlap)"
    )[0].split(" | ")
    assert issuer_side == ["1", "0", "1"]  # permaticker 5: OLDN then NEWN, no overlap


def test_report_is_read_only_and_records_a_checksum(store: Path) -> None:
    before = store.read_bytes()
    out = pit_coverage_ro.report(str(store))
    assert "sha256:" in out and "NOT provenance or freshness" in out
    assert store.read_bytes() == before
    with pytest.raises(duckdb.Error):
        duckdb.connect(str(store), read_only=True).execute("DELETE FROM sep")


def test_parquet_export_directory_gives_the_same_answers(store: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "export"
    out_dir.mkdir()
    con = duckdb.connect(str(store), read_only=True)
    for t in ("tickers", "sep"):
        con.execute(f"COPY {t} TO '{(out_dir / (t + '.parquet')).as_posix()}' (FORMAT PARQUET)")
    con.close()
    out = pit_coverage_ro.report(str(out_dir))
    rows = _section(out, "SEP coverage delisted vs active (SEP aggregated per ticker first)")
    assert {r.split(" | ")[0]: r.split(" | ")[4] for r in rows} == {"False": "10", "True": "5"}
    assert "sha256:" in out and "PIT-required columns actions: MISSING" in out


def test_required_column_list_mirrors_the_application_manifest() -> None:
    from app.research.range002.data.manifest import REQUIRED_COLUMNS

    assert pit_coverage_ro.PIT_REQUIRED_COLUMNS == REQUIRED_COLUMNS


def _split_store(tmp_path: Path, *, volume_adjusted: bool) -> Path:
    """One forward 10:1 split on 2020-03-02. Traded: 1M shares/day at 100 before, 10M at 10 after.
    The vendor's split-adjusted series: close 10 throughout; closeunadj 100 then 10;
    volume 10M throughout if split-adjusted, else (hazard) as traded: 1M then 10M."""
    path = tmp_path / ("adj.duckdb" if volume_adjusted else "traded.duckdb")
    c = duckdb.connect(str(path))
    c.execute(
        "CREATE TABLE tickers(permaticker VARCHAR, ticker VARCHAR, isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE)"
    )
    c.execute("INSERT INTO tickers VALUES ('P1','SPL','N','2010-01-04','2026-06-12')")
    c.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    c.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, value DOUBLE, contraticker VARCHAR)"
    )
    c.execute("INSERT INTO actions VALUES ('2020-03-02','split','SPL',10.0,NULL)")
    pre = ["2020-02-24", "2020-02-25", "2020-02-26", "2020-02-27", "2020-02-28"]
    post = ["2020-03-02", "2020-03-03", "2020-03-04", "2020-03-05", "2020-03-06"]
    for d in pre:
        c.execute(
            "INSERT INTO sep VALUES ('SPL', ?, 10.0, 100.0, ?)",
            [d, 10_000_000.0 if volume_adjusted else 1_000_000.0],
        )
    for d in post:
        c.execute("INSERT INTO sep VALUES ('SPL', ?, 10.0, 10.0, 10_000_000.0)", [d])
    c.close()
    return path


def test_volume_semantics_check_recognises_split_adjusted_volume(tmp_path: Path) -> None:
    out = pit_coverage_ro.report(str(_split_store(tmp_path, volume_adjusted=True)))
    assert (
        "CONSISTENT_WITH_SPLIT_ADJUSTED_VOLUME" in out
        and "CONSISTENT_WITH_AS_TRADED_VOLUME" not in out
    )


def test_volume_semantics_check_flags_as_traded_volume(tmp_path: Path) -> None:
    out = pit_coverage_ro.report(str(_split_store(tmp_path, volume_adjusted=False)))
    assert (
        "CONSISTENT_WITH_AS_TRADED_VOLUME" in out
        and "CONSISTENT_WITH_SPLIT_ADJUSTED_VOLUME" not in out
    )


def test_volume_semantics_check_is_skipped_without_the_columns(store: Path) -> None:
    assert "VOLUME SEMANTICS: SKIPPED" in pit_coverage_ro.report(str(store))


def test_volume_semantics_check_does_not_force_an_ambiguous_observation(tmp_path: Path) -> None:
    """Volume steps by ~sqrt(10) around a 10:1 split: equidistant from both hypotheses."""
    path = tmp_path / "ambiguous.duckdb"
    c = duckdb.connect(str(path))
    c.execute(
        "CREATE TABLE tickers(permaticker VARCHAR, ticker VARCHAR, isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE)"
    )
    c.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    c.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, value DOUBLE, contraticker VARCHAR)"
    )
    c.execute("INSERT INTO actions VALUES ('2020-03-02','split','AMB',10.0,NULL)")
    for d in ["2020-02-24", "2020-02-25", "2020-02-26", "2020-02-27", "2020-02-28"]:
        c.execute("INSERT INTO sep VALUES ('AMB', ?, 10.0, 100.0, 1000000.0)", [d])
    for d in ["2020-03-02", "2020-03-03", "2020-03-04", "2020-03-05", "2020-03-06"]:
        c.execute("INSERT INTO sep VALUES ('AMB', ?, 10.0, 10.0, 3162278.0)", [d])
    c.close()
    out = pit_coverage_ro.report(str(path))
    assert "AMBIGUOUS_VOLUME_EVIDENCE" in out
    assert (
        "CONSISTENT_WITH_SPLIT_ADJUSTED_VOLUME" not in out
        and "CONSISTENT_WITH_AS_TRADED_VOLUME" not in out
    )
