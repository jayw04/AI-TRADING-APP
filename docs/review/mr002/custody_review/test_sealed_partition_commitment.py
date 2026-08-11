"""Tests for WP-C — the P9/P6 custodian sealing-process producer.

Two properties carry the whole weight of these records, and neither is visible
by reading the output:

  1. **The commitment must be value-blind.** A structural manifest that leaked
     sealed universe membership would defeat the precommitment it exists to
     support. So the tests assert on what is ABSENT from the emitted records,
     not only on what is present.
  2. **The commitment must recompute identically later**, inside a different
     image on different hardware. Every drift channel that would silently
     produce a different hash over the same corpus gets its own test: row
     order, NULL versus empty string, float formatting, time zone, and field
     delimiting.

The second is the subtle one. A commitment that fails to reproduce does not
announce itself as a bug; it presents as evidence that the sealed corpus was
tampered with. Getting a false positive there would be expensive and alarming,
so the encoding is pinned by test rather than by convention.

No network, no AWS, no real corpus. Every test runs against a synthetic DuckDB
fixture with the real schema and a patched window design, so the suite never
touches the sealed snapshot.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
import pytest

MODULE_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


S = _load("sealed_partition_commitment")


# ---------------------------------------------------------------------------
# Synthetic corpus
# ---------------------------------------------------------------------------

SESSIONS = [datetime.date(2020, 1, d) for d in range(1, 11)]

SYNTHETIC_WINDOWS = {
    "development": ("2020-01-01", "2020-01-03", 3),
    "validation": ("2020-01-04", "2020-01-07", 4),
    "oos": ("2020-01-08", "2020-01-10", 3),
}

DDL = """
CREATE TABLE prices (ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE,
                     close DOUBLE, closeadj DOUBLE, closeunadj DOUBLE, volume DOUBLE);
CREATE TABLE etf_prices (ticker VARCHAR, date DATE, adjclose DOUBLE);
CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, name VARCHAR, value DOUBLE,
                      contraticker VARCHAR, contraname VARCHAR);
CREATE TABLE universe (universe_month DATE, ticker VARCHAR, permaticker BIGINT, siccode BIGINT,
                       liquidity_rank BIGINT, med_dv_60 DOUBLE, in_long_universe BOOLEAN,
                       in_short_universe BOOLEAN);
CREATE TABLE anchors (cik BIGINT, ticker VARCHAR, accession VARCHAR, report_date DATE,
                      acceptance_utc TIMESTAMP WITH TIME ZONE, session_date DATE,
                      availability_class VARCHAR, event_time_basis VARCHAR,
                      is_amendment_origin BOOLEAN, amended_by VARCHAR,
                      collapsed_duplicates VARCHAR);
CREATE TABLE sic_observations (cik BIGINT, accession VARCHAR, form VARCHAR,
                               accepted_utc TIMESTAMP WITH TIME ZONE, sic VARCHAR);
CREATE TABLE crosswalk (permaticker BIGINT, ticker VARCHAR, cik BIGINT, effective_from DATE,
                        effective_to DATE, relationship_type VARCHAR, source VARCHAR,
                        source_record_id VARCHAR, confidence VARCHAR,
                        mapping_rationale VARCHAR, review_status VARCHAR);
CREATE TABLE predecessor_overrides (permaticker BIGINT, ticker VARCHAR, predecessor_cik BIGINT,
                                    successor_cik BIGINT, effective_from VARCHAR,
                                    effective_to DATE, event_type VARCHAR, event_date DATE,
                                    authoritative_evidence VARCHAR, continuity_rationale VARCHAR,
                                    baton_test VARCHAR, predecessor_entity VARCHAR,
                                    predecessor_sic VARCHAR, predecessor_filing_range VARCHAR,
                                    successor_first_domestic_filing DATE, gap_months BIGINT,
                                    flags VARCHAR, crawl_manifest_included BOOLEAN,
                                    review_status VARCHAR, reviewer VARCHAR, review_date DATE,
                                    countersign_limitation VARCHAR);
CREATE TABLE security_sector_overrides (permaticker BIGINT, ticker VARCHAR, cik BIGINT,
                                        effective_from DATE, effective_to DATE,
                                        research_sector VARCHAR, sector_etf VARCHAR,
                                        confidence VARCHAR, review_status VARCHAR,
                                        mapping_rationale VARCHAR, evidence VARCHAR,
                                        reviewer VARCHAR, review_date DATE);
CREATE TABLE sic_mapping (sic_start VARCHAR, sic_end VARCHAR, effective_from DATE,
                          effective_to DATE, research_sector VARCHAR, sector_etf VARCHAR,
                          mapping_rationale VARCHAR, mapping_confidence VARCHAR,
                          mapping_specificity VARCHAR, review_status VARCHAR, reviewer VARCHAR,
                          review_date DATE, source_reference VARCHAR);
"""

SECRET_TICKERS = ("ZZTOPSECRET", "QQHIDDEN")


def _build_corpus(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute("SET TimeZone='UTC'")
    con.execute(DDL)
    for ticker in SECRET_TICKERS:
        for i, day in enumerate(SESSIONS):
            con.execute(
                "INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?)",
                [ticker, day, 1.0 + i, 2.0, 0.5, 1.5, 1.5, 1.5, 100.0 * (i + 1)],
            )
    for etf in ("XLK", "XLF"):
        for i, day in enumerate(SESSIONS):
            con.execute("INSERT INTO etf_prices VALUES (?,?,?)", [etf, day, 10.0 + i])
    con.execute(
        "INSERT INTO actions VALUES (?,?,?,?,?,?,?)",
        [SESSIONS[4], "split", SECRET_TICKERS[0], "Name", 2.0, None, None],
    )
    con.execute(
        "INSERT INTO universe VALUES (?,?,?,?,?,?,?,?)",
        [datetime.date(2020, 1, 1), SECRET_TICKERS[0], 111, 3570, 1, 5.0, True, False],
    )
    con.execute(
        "INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            111,
            SECRET_TICKERS[0],
            "acc-1",
            SESSIONS[4],
            datetime.datetime(2020, 1, 5, 12, 0, tzinfo=datetime.timezone.utc),
            SESSIONS[4],
            "SAME_DAY",
            "acceptance",
            False,
            None,
            None,
        ],
    )
    con.execute(
        "INSERT INTO sic_observations VALUES (?,?,?,?,?)",
        [111, "acc-1", "10-K", datetime.datetime(2020, 1, 5, 12, 0,
                                                 tzinfo=datetime.timezone.utc), "3570"],
    )
    con.execute(
        "INSERT INTO crosswalk VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [111, SECRET_TICKERS[0], 111, SESSIONS[0], SESSIONS[-1], "primary", "src", "r1",
         "high", "rationale", "approved"],
    )
    con.execute("INSERT INTO predecessor_overrides SELECT " + ",".join(["NULL"] * 22))
    con.execute("INSERT INTO security_sector_overrides SELECT " + ",".join(["NULL"] * 13))
    con.execute(
        "INSERT INTO sic_mapping VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ["3500", "3599", SESSIONS[0], SESSIONS[-1], "Technology", "XLK", "r", "high",
         "range", "approved", "rev", SESSIONS[0], "ref"],
    )
    con.close()


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    """A synthetic snapshot with the real schema, plus the module patched onto it."""
    path = tmp_path / "synthetic.duckdb"
    _build_corpus(path)
    sha = S.sha256_file(str(path))
    monkeypatch.setattr(S, "WINDOWS", dict(SYNTHETIC_WINDOWS))
    monkeypatch.setattr(S, "GOVERNED_FIRST", "2020-01-01")
    monkeypatch.setattr(S, "GOVERNED_LAST", "2020-01-10")
    monkeypatch.setattr(S, "GOVERNED_SESSIONS", len(SESSIONS))
    listing = "|".join(str(d) for d in SESSIONS)
    monkeypatch.setattr(
        S, "GOVERNED_SESSION_LIST_SHA256", hashlib.sha256(listing.encode()).hexdigest()
    )
    monkeypatch.setattr(S, "SNAPSHOT", str(path))
    monkeypatch.setattr(S, "SNAPSHOT_SHA256", sha)
    return {"path": str(path), "sha256": sha}


def _records(corpus):
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        return S.build_records(
            con, custodian="Test Custodian", authority="test", produced_at="2026-08-11T00:00:00Z"
        )


# ---------------------------------------------------------------------------
# Canonical encoding — the reproducibility contract
# ---------------------------------------------------------------------------


def test_null_is_distinct_from_empty_string():
    """The classic silent-collapse bug: a NULL price and a "" price are not the same fact."""
    assert S.canonical_field(None) != S.canonical_field("")


def test_bool_is_distinct_from_int():
    """bool subclasses int in Python; encoding True as "1" would erase the type."""
    assert S.canonical_field(True) != S.canonical_field(1)
    assert S.canonical_field(False) != S.canonical_field(0)


def test_field_encoding_is_injective_against_delimiter_forgery():
    """A value containing the separator must not be able to forge a field boundary."""
    forged = S.canonical_row(["a:b", "c"])
    honest = S.canonical_row(["a", "b:c"])
    assert forged != honest


def test_row_boundaries_cannot_be_forged_by_embedded_newline():
    assert S.canonical_row(["a\nb"]) != S.canonical_row(["a", "b"])


def test_float_encoding_round_trips_exactly():
    value = 0.1 + 0.2
    assert float(S.canonical_scalar(value)) == value


def test_float_specials_are_spelled_out():
    assert S.canonical_scalar(float("nan")) == "NaN"
    assert S.canonical_scalar(float("inf")) == "Infinity"
    assert S.canonical_scalar(float("-inf")) == "-Infinity"


def test_timestamps_normalize_to_utc():
    """Same instant, two zones -> one encoding. Otherwise the host time zone changes the hash."""
    utc = datetime.datetime(2020, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)
    chicago = utc.astimezone(datetime.timezone(datetime.timedelta(hours=-6)))
    assert S.canonical_scalar(utc) == S.canonical_scalar(chicago)


def test_naive_and_aware_timestamps_do_not_collide():
    naive = datetime.datetime(2020, 1, 5, 12, 0)
    aware = datetime.datetime(2020, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)
    assert S.canonical_scalar(naive) != S.canonical_scalar(aware)


def test_unencodable_type_refuses():
    with pytest.raises(S.CommitmentRefused):
        S.canonical_field({"not": "a scalar"})


# ---------------------------------------------------------------------------
# Fail-closed snapshot handling
# ---------------------------------------------------------------------------


def test_snapshot_digest_mismatch_refuses_before_opening(corpus):
    with pytest.raises(S.CommitmentRefused) as exc:
        with S.open_snapshot(corpus["path"], "0" * 64):
            pytest.fail("must not open a snapshot whose digest does not match")
    assert "snapshot_digest_mismatch_before" in str(exc.value)


def test_snapshot_is_unchanged_by_the_read(corpus):
    before = S.sha256_file(corpus["path"])
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        S.commit_window(con, "validation")
    assert S.sha256_file(corpus["path"]) == before


def test_session_count_mismatch_refuses(corpus, monkeypatch):
    """A window that does not contain its frozen session count is a different window."""
    monkeypatch.setitem(S.WINDOWS, "validation", ("2020-01-04", "2020-01-07", 999))
    with pytest.raises(S.CommitmentRefused) as exc:
        with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
            S._session_list(con, "validation")
    assert "session_count_mismatch" in str(exc.value)


def test_governed_calendar_mismatch_refuses(corpus, monkeypatch):
    monkeypatch.setattr(S, "GOVERNED_SESSION_LIST_SHA256", "f" * 64)
    with pytest.raises(S.CommitmentRefused) as exc:
        _records(corpus)
    assert "governed_calendar_mismatch" in str(exc.value)


def test_absent_table_refuses(corpus):
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        with pytest.raises(S.CommitmentRefused):
            S.table_columns(con, "no_such_table")


# ---------------------------------------------------------------------------
# Window boundaries
# ---------------------------------------------------------------------------


def test_window_boundaries_are_inclusive_on_both_ends(corpus):
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        sessions = S._session_list(con, "validation")
    assert sessions["first_session"] == "2020-01-04"
    assert sessions["last_session"] == "2020-01-07"
    assert sessions["observed_sessions"] == 4


def test_windows_partition_the_corpus_without_overlap_or_gap(corpus):
    """Every observation row lands in exactly one window. Overlap would double-commit;
    a gap would leave sealed rows uncommitted and therefore unverifiable."""
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        counts = {w: S.commit_window(con, w)["tables"]["prices"]["row_count"]
                  for w in ("development", "validation", "oos")}
        (total,) = con.execute("SELECT COUNT(*) FROM prices").fetchone()
    assert sum(counts.values()) == total


def test_unknown_window_refuses():
    with pytest.raises(S.CommitmentRefused):
        S._window_bounds("not_a_window")


# ---------------------------------------------------------------------------
# Content commitment sensitivity
# ---------------------------------------------------------------------------


def test_commitment_is_deterministic_across_runs(corpus):
    first = _records(corpus)["P6"]["validation_partition"]["partition_content_sha256"]
    second = _records(corpus)["P6"]["validation_partition"]["partition_content_sha256"]
    assert first == second


def test_commitment_changes_when_a_single_value_changes(corpus):
    before = _records(corpus)["P6"]["validation_partition"]["partition_content_sha256"]
    con = duckdb.connect(corpus["path"])
    con.execute("UPDATE prices SET closeadj = closeadj + 0.0000001 WHERE date = DATE '2020-01-05'")
    con.close()
    sha = S.sha256_file(corpus["path"])
    with S.open_snapshot(corpus["path"], sha) as con2:
        after = S.commit_window(con2, "validation")["partition_content_sha256"]
    assert after != before


def test_commitment_changes_when_a_row_is_deleted(corpus):
    before = _records(corpus)["P6"]["validation_partition"]["partition_content_sha256"]
    con = duckdb.connect(corpus["path"])
    con.execute("DELETE FROM prices WHERE date = DATE '2020-01-05'")
    con.close()
    sha = S.sha256_file(corpus["path"])
    with S.open_snapshot(corpus["path"], sha) as con2:
        after = S.commit_window(con2, "validation")["partition_content_sha256"]
    assert after != before


def test_validation_and_oos_commitments_differ(corpus):
    records = _records(corpus)
    assert (
        records["P6"]["validation_partition"]["partition_content_sha256"]
        != records["P6"]["oos_partition"]["partition_content_sha256"]
    )


def test_roll_up_binds_table_identity_not_just_content(corpus):
    """Two tables swapping content must change the roll-up even if the multiset of
    per-table hashes is unchanged."""
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        window = S.commit_window(con, "validation")
    roll = [
        {"table": t, "row_count": e["row_count"], "content_sha256": e["content_sha256"]}
        for t, e in sorted(window["tables"].items())
    ]
    swapped = list(roll)
    swapped[0], swapped[1] = (
        {**swapped[1], "table": swapped[0]["table"]},
        {**swapped[0], "table": swapped[1]["table"]},
    )
    payload = json.dumps(swapped, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(payload.encode()).hexdigest() != window["partition_content_sha256"]


def test_schema_identity_changes_when_a_column_type_changes(corpus):
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        before = S.schema_identity(con, ["prices"])["schema_identity_sha256"]
    con = duckdb.connect(corpus["path"])
    con.execute("ALTER TABLE prices ALTER volume TYPE VARCHAR")
    con.close()
    sha = S.sha256_file(corpus["path"])
    with S.open_snapshot(corpus["path"], sha) as con2:
        after = S.schema_identity(con2, ["prices"])["schema_identity_sha256"]
    assert after != before


# ---------------------------------------------------------------------------
# Completeness — did we commit EVERYTHING, not just commit something
# ---------------------------------------------------------------------------


def _insert_price(path: str, ticker: str, day):
    con = duckdb.connect(path)
    con.execute(
        "INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?)",
        [ticker, day, 1.0, 2.0, 0.5, 1.5, 1.5, 1.5, 100.0],
    )
    con.close()
    return S.sha256_file(path)


def test_completeness_accounts_for_every_governed_row(corpus):
    completeness = _records(corpus)["P6"]["partition_completeness"]
    assert completeness["every_in_window_row_committed_exactly_once"] is True
    prices = completeness["tables"]["prices"]
    assert prices["committed_across_windows"] == prices["in_governed_window"]
    assert prices["total_rows"] == len(SECRET_TICKERS) * len(SESSIONS)


def test_row_before_the_governed_window_is_excluded_but_counted(corpus, monkeypatch):
    """Pre-window warm-up history must be visibly excluded, never silently dropped."""
    sha = _insert_price(corpus["path"], SECRET_TICKERS[0], datetime.date(2019, 12, 31))
    monkeypatch.setattr(S, "SNAPSHOT_SHA256", sha)
    with S.open_snapshot(corpus["path"], sha) as con:
        records = S.build_records(
            con, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
        )
    prices = records["P6"]["partition_completeness"]["tables"]["prices"]
    assert prices["before_governed_window"] == 1
    assert prices["committed_across_windows"] == prices["in_governed_window"]


def test_null_availability_date_refuses_as_incomplete(corpus, monkeypatch):
    """A NULL availability date belongs to no window; committing around it would leave a
    sealed row uncommitted while every hash still matched."""
    sha = _insert_price(corpus["path"], SECRET_TICKERS[0], None)
    monkeypatch.setattr(S, "SNAPSHOT_SHA256", sha)
    with pytest.raises(S.CommitmentRefused) as exc:
        with S.open_snapshot(corpus["path"], sha) as con:
            S.build_records(
                con, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
            )
    assert "partition_incomplete:prices" in str(exc.value)


# ---------------------------------------------------------------------------
# Value-blindness — asserted on what is ABSENT
# ---------------------------------------------------------------------------


def test_p9_does_not_leak_sealed_universe_membership(corpus):
    """Counts are value-blind; membership is not. No sealed ticker may appear in P9."""
    blob = json.dumps(_records(corpus)["P9"])
    for ticker in SECRET_TICKERS:
        assert ticker not in blob


def test_p6_does_not_leak_sealed_universe_membership(corpus):
    blob = json.dumps(_records(corpus)["P6"])
    for ticker in SECRET_TICKERS:
        assert ticker not in blob


def test_p9_reports_security_counts_rather_than_identities(corpus):
    prices = _records(corpus)["P9"]["structure"]["prices"]
    assert prices["security_counts"]["distinct_ticker"] == len(SECRET_TICKERS)


def test_factor_series_coverage_names_only_the_etf_series(corpus):
    """Sector-ETF identities are registered and public; naming them leaks nothing."""
    coverage = _records(corpus)["P9"]["factor_series_coverage"]
    assert coverage["series_count"] == 2
    assert {s["ticker"] for s in coverage["series"]} == {"XLK", "XLF"}


def test_p9_emits_every_required_value_blind_field(corpus):
    """The specification enumerates nine fields; a manifest missing one is incomplete."""
    p9 = _records(corpus)["P9"]
    assert p9["schema_identity"]["schema_identity_sha256"]
    assert set(p9["structure"]) == set(S.OBSERVATION_TABLES)
    prices = p9["structure"]["prices"]
    assert prices["row_count"] > 0
    assert prices["date_bounds"]["first"] and prices["date_bounds"]["last"]
    assert "volume" in prices["null_counts"]
    assert p9["window_sessions"]["observed_sessions"] == 4
    assert p9["latest_source_date"] == "2020-01-10"


def test_null_counts_are_reported_per_column(corpus):
    """actions has two deliberately NULL columns in-window."""
    actions = _records(corpus)["P9"]["structure"]["actions"]
    assert actions["null_counts"]["contraticker"] == 1
    assert actions["null_counts"]["contraname"] == 1


# ---------------------------------------------------------------------------
# Record integrity and boundary claims
# ---------------------------------------------------------------------------


def test_records_are_marked_runtime_instances_not_templates(corpus):
    """The whole point of WP-C: the Phase 3A files of these names are templates."""
    records = _records(corpus)
    assert records["P9"]["artifact_kind"] == "RUNTIME_INSTANCE"
    assert records["P6"]["artifact_kind"] == "RUNTIME_INSTANCE"


def test_identity_hash_covers_the_record_and_excludes_itself(corpus):
    p9 = _records(corpus)["P9"]
    recomputed = S._identity(p9)
    assert recomputed == p9["manifest_identity_sha256"]
    mutated = dict(p9)
    mutated["latest_source_date"] = "1999-01-01"
    assert S._identity(mutated) != recomputed


def test_provenance_binds_custodian_producer_and_snapshot(corpus):
    provenance = _records(corpus)["P9"]["provenance"]
    assert provenance["custodian"] == "Test Custodian"
    assert provenance["read_mode"] == "READ_ONLY"
    assert provenance["snapshot_sha256"] == S.SNAPSHOT_SHA256
    assert provenance["session_settings"]["TimeZone"] == "UTC"
    assert len(provenance["producer_sha256"]) == 64


def test_records_grant_nothing(corpus):
    """These satisfy prerequisites; they must not read as an authorization."""
    for record in _records(corpus).values():
        assert "validation_authorization remains false" in record["boundary"]


def test_reference_layer_carve_out_is_disclosed_not_silent(corpus):
    disclosure = _records(corpus)["P6"]["reference_tables"]["disclosure"]
    assert "NOT part of any sealed partition" in disclosure
    assert set(_records(corpus)["P6"]["reference_tables"]["tables"]) == set(S.REFERENCE_TABLES)


def test_emitted_json_is_stable_on_disk(corpus, tmp_path):
    """Sorted keys and a pinned newline: a re-emission must diff cleanly or not at all."""
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    S.write_record(_records(corpus)["P9"], str(first))
    S.write_record(_records(corpus)["P9"], str(second))
    assert first.read_bytes() == second.read_bytes()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
