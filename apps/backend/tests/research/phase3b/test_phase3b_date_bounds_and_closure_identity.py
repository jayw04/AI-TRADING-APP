"""v3.3: the two execution-guard corrections, each pinned by the incident that motivated it.

Both defects were observed, not hypothesised. On 2026-08-14 a governed replacement opening was
spent and the run refused at S9 with

    ParquetRefused: sic_observations: date bounds
    2019-10-03 10:03:29+00:00..2023-02-16 22:32:22+00:00 != committed 2019-10-03..2023-02-16

while the data and the P9 commitment were both correct; and the same run executed v3.2 bytes under
a stale v1.0 configuration declaring a superseded ``code_identity``, which no gate caught.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.research.mr002.phase3b import parquet as PQ
from app.research.mr002.phase3b import roster as R
from app.research.mr002.phase3b import runner as RUN

COMMITTED_FIRST = "2019-10-03"
COMMITTED_LAST = "2023-02-16"

# The two endpoints the sealed partition actually carries, verbatim from the refusal.
REAL_FIRST_TS = datetime(2019, 10, 3, 10, 3, 29, tzinfo=UTC)
REAL_LAST_TS = datetime(2023, 2, 16, 22, 32, 22, tzinfo=UTC)


class _Column:
    def __init__(self, values):
        self._values = list(values)

    def to_pylist(self):
        return list(self._values)


class _Table:
    """The narrow surface `_verify_date_bounds` uses: column_names and column()."""

    def __init__(self, name, values):
        self.column_names = [name]
        self._values = values

    def column(self, name):
        assert name == self.column_names[0]
        return _Column(self._values)


def _commitment(availability_column="accepted_utc", first=COMMITTED_FIRST, last=COMMITTED_LAST):
    return PQ.TableCommitment(
        name="sic_observations",
        column_order=(availability_column,),
        row_count=8470,
        first_date=first,
        last_date=last,
        availability_column=availability_column,
    )


# ---------------------------------------------------------------------------------------------
# 1-3: the date-bound guard
# ---------------------------------------------------------------------------------------------

def test_a_date_column_still_passes_unchanged():
    """The pre-existing DATE behaviour is preserved; the fix must not trade one type for another."""
    table = _Table("d", [date(2019, 10, 3), date(2021, 5, 4), date(2023, 2, 16)])
    PQ._verify_date_bounds(table, _commitment("d"))


def test_the_exact_incident_timestamps_now_normalise_to_the_committed_dates():
    """2019-10-03 10:03:29+00:00 .. 2023-02-16 22:32:22+00:00 -> 2019-10-03 .. 2023-02-16."""
    table = _Table("accepted_utc", [REAL_FIRST_TS, datetime(2021, 5, 4, 1, 2, 3, tzinfo=UTC),
                                    REAL_LAST_TS])
    PQ._verify_date_bounds(table, _commitment())


@pytest.mark.parametrize(
    "value,expected",
    [
        (REAL_FIRST_TS, "2019-10-03"),
        (REAL_LAST_TS, "2023-02-16"),
        (date(2020, 1, 1), "2020-01-01"),
        # A non-UTC zone must be normalised to UTC before the date is taken, not truncated in place.
        (datetime(2019, 10, 3, 20, 0, tzinfo=timezone(timedelta(hours=-8))), "2019-10-04"),
    ],
)
def test_availability_values_reduce_to_the_utc_date(value, expected):
    assert PQ._availability_date(value, "t") == expected


# ---------------------------------------------------------------------------------------------
# 4-6: it must still REFUSE what it is there to refuse
# ---------------------------------------------------------------------------------------------

def test_a_timestamp_whose_utc_date_falls_outside_the_commitment_refuses():
    table = _Table("accepted_utc", [REAL_FIRST_TS, datetime(2023, 2, 17, 0, 5, tzinfo=UTC)])
    with pytest.raises(PQ.ParquetRefused) as exc:
        PQ._verify_date_bounds(table, _commitment())
    assert "2023-02-17" in str(exc.value)


def test_a_naive_timestamp_refuses_rather_than_being_assumed_utc():
    """Assuming a zone is the silent coercion this module exists to prevent."""
    table = _Table("accepted_utc", [datetime(2019, 10, 3, 10, 3, 29), REAL_LAST_TS])
    with pytest.raises(PQ.ParquetRefused) as exc:
        PQ._verify_date_bounds(table, _commitment())
    assert "naive" in str(exc.value).lower()


def test_a_rendered_timestamp_string_refuses_rather_than_being_parsed():
    """The incident's own shape, as a STRING, must not be quietly accepted.

    A bare ``YYYY-MM-DD`` literal is allowed for fixture compatibility, but anything carrying a
    time component has to arrive as a real datetime so its zone is explicit rather than parsed out
    of a rendering.
    """
    table = _Table("accepted_utc", ["2019-10-03 10:03:29+00:00"])
    with pytest.raises(PQ.ParquetRefused) as exc:
        PQ._verify_date_bounds(table, _commitment())
    assert "not a bare YYYY-MM-DD date literal" in str(exc.value)


def test_a_non_date_type_refuses():
    table = _Table("accepted_utc", [17510101])
    with pytest.raises(PQ.ParquetRefused) as exc:
        PQ._verify_date_bounds(table, _commitment())
    assert "unexpected type" in str(exc.value)


@pytest.mark.parametrize("first,last", [("2019-10-04", COMMITTED_LAST),
                                        (COMMITTED_FIRST, "2023-02-15")])
def test_mutating_either_committed_endpoint_refuses(first, last):
    table = _Table("accepted_utc", [REAL_FIRST_TS, REAL_LAST_TS])
    with pytest.raises(PQ.ParquetRefused):
        PQ._verify_date_bounds(table, _commitment(first=first, last=last))


def test_an_empty_availability_column_still_refuses():
    with pytest.raises(PQ.ParquetRefused):
        PQ._verify_date_bounds(_Table("accepted_utc", [None, None]), _commitment())


# ---------------------------------------------------------------------------------------------
# The real sic_observations SHAPE, exercised through the whole decode path on a non-sealed fixture.
#
# This is the test the fixture suite never had. Every existing fixture writes DATE columns as ISO
# STRINGS, so no fixture run -- including the 429x850 capacity qualification -- could reach the
# timestamp branch at all. Here the column is a genuine pyarrow timestamp('us', tz='UTC'), which is
# what the sealed partition actually carries.
# ---------------------------------------------------------------------------------------------

def _sic_observations_parquet(first_ts, last_ts):
    import io as _io

    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [first_ts, datetime(2021, 5, 4, 12, 0, 0, tzinfo=UTC), last_ts]
    table = pa.table(
        {
            "cik": pa.array([320193, 789019, 1045810], type=pa.int64()),
            "accession": pa.array(["a-1", "a-2", "a-3"], type=pa.string()),
            "form": pa.array(["10-K", "10-Q", "8-K"], type=pa.string()),
            "accepted_utc": pa.array(rows, type=pa.timestamp("us", tz="UTC")),
            "sic": pa.array(["3571", "7372", "3674"], type=pa.string()),
        }
    )
    buf = _io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _sic_commitment(first=COMMITTED_FIRST, last=COMMITTED_LAST, rows=3):
    return PQ.TableCommitment(
        name="sic_observations",
        column_order=("cik", "accession", "form", "accepted_utc", "sic"),
        row_count=rows,
        first_date=first,
        last_date=last,
        availability_column="accepted_utc",
    )


def test_real_timestamp_shape_decodes_past_the_date_bound_guard():
    """A true TIMESTAMP WITH TIME ZONE column at the incident's own endpoints now decodes."""
    payload = _sic_observations_parquet(REAL_FIRST_TS, REAL_LAST_TS)
    table = PQ.decode(payload, _sic_commitment())
    assert table.num_rows == 3
    assert table.column_names == ["cik", "accession", "form", "accepted_utc", "sic"]
    # and the values really did arrive as aware datetimes, not strings
    assert all(v.tzinfo is not None for v in table.column("accepted_utc").to_pylist())


def test_real_timestamp_shape_still_refuses_an_out_of_window_endpoint():
    payload = _sic_observations_parquet(REAL_FIRST_TS, datetime(2023, 2, 17, 0, 1, tzinfo=UTC))
    with pytest.raises(PQ.ParquetRefused) as exc:
        PQ.decode(payload, _sic_commitment())
    assert "2023-02-17" in str(exc.value)


# ---------------------------------------------------------------------------------------------
# 7-: live closure identity vs the identity the configuration declares
# ---------------------------------------------------------------------------------------------

def test_closure_identity_uses_the_encoding_the_execution_manifest_binds():
    """Reproduce the scheme independently; a private encoding would bind nothing comparable."""
    closure = {"b.py": "2" * 64, "a.py": "1" * 64}
    expected = json.dumps(dict(sorted(closure.items())), sort_keys=True, indent=1,
                          ensure_ascii=True) + "\n"
    import hashlib
    assert R.closure_identity(closure) == hashlib.sha256(expected.encode("ascii")).hexdigest()


def test_closure_identity_of_the_live_mount_is_stable():
    assert R.closure_identity() == R.closure_identity(R.current_roster()["closure"])


def _runner(identities, observed_identities):
    """A runner carrying only what the closure check reads."""
    return RUN.Phase3BRunner(
        reader=object(), candidate_source=object(), output_root="/nonexistent",
        registered_objects={}, inputs=[], bound_roster=R.current_roster(),
        contract_identities={}, expected_contract_identities={},
        config_mapping={}, expected_config_mapping={},
        runtime_facts={}, expected_runtime_facts={},
        identities=identities, observed_identities=observed_identities,
    )


def test_the_live_mount_passes_against_its_own_declared_identity():
    live = R.closure_identity()
    _runner({"code_identity": live}, {"execution_closure_sha256": live})._verify_declared_closure_identity()


STALE = "f35e8209bcaac16a23b58ec2c0d75aae338721ab895a5b5d91e6c168506426b2"


def test_THE_INCIDENT_stale_config_refuses_before_any_credential_or_sealed_access():
    """2026-08-14, reproduced: v3.2/v3.3 live bytes under the stale v1.0 configuration.

    This is the load-bearing test. Under the old code this combination reached S8_READER_ASSUMED
    and S9_OPENING_CONSUMED and spent a governed opening. It must now refuse at S1, before reader
    construction, before STS, and before any object is opened.
    """
    r = _runner({"code_identity": STALE}, {"execution_closure_sha256": STALE})
    with pytest.raises(RUN.RunRefused) as exc:
        r._verify_code_identity()
    msg = str(exc.value)
    assert "execution closure identity mismatch" in msg
    assert STALE in msg and R.closure_identity() in msg
    # and it never advanced out of the pre-access states
    assert r.sequence.state not in (
        RUN.S.S8_READER_ASSUMED, RUN.S.S9_OPENING_CONSUMED, RUN.S.S1_CODE_IDENTITY_VERIFIED
    )


def test_a_configuration_that_disagrees_with_itself_refuses():
    live = R.closure_identity()
    r = _runner({"code_identity": live}, {"execution_closure_sha256": STALE})
    with pytest.raises(RUN.RunRefused) as exc:
        r._verify_declared_closure_identity()
    assert "disagrees with itself" in str(exc.value)


@pytest.mark.parametrize("identities,observed", [
    ({}, {"execution_closure_sha256": "x"}),
    ({"code_identity": "x"}, {}),
    ({}, {}),
])
def test_a_missing_declaration_refuses_rather_than_skipping_the_check(identities, observed):
    """Absent is not 'nothing to compare'; it is a package that binds no identity."""
    with pytest.raises(RUN.RunRefused):
        _runner(identities, observed)._verify_declared_closure_identity()
