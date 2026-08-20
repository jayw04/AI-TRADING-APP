"""DISC-MDQ-001 Phase A — the constrained reader.

The load-bearing tests here are the ones that put holdout rows *into* a
partition and prove the reader will not hand them back.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.research.capture.store import CaptureStore, PartitionRef
from app.research.disc_mdq.policy import (
    MdqExplorationPolicy,
    ReviewWindow,
    UnauthorizedReadError,
)
from app.research.disc_mdq.reader import (
    MdqFeatureReader,
    PartitionIntegrityError,
    PartitionNotFrozenError,
)
from app.research.disc_mdq.spec import READER_VERSION, ReadPurpose

HOLDOUT = ["AMZN", "EFA", "KMLM", "MSTR", "NBIS", "NOW", "TSLA", "XLK", "XLV", "XOM"]
UNIVERSE = [*HOLDOUT, "AAPL", "GOOGL", "MSFT", "NVDA"]

SESSION = date(2026, 8, 20)
HOLDOUT_SESSION = date(2026, 10, 7)
FEED = "sip"

PROVENANCE = {
    "feed_literal": "sip",
    "account": "PA3BGKRLH2AP",
    "key_fingerprint": "b56421a28128",
    "universe": UNIVERSE,
    "universe_sha256": "0" * 64,
    "capture_modes": ["rest_quote_sampler_v1"],
}


def quote_row(symbol: str, minute: int, *, bid: float = 100.0, ask: float = 100.1) -> dict:
    cycle = datetime(2026, 8, 20, 13, 25 + minute, 0, tzinfo=UTC)
    return {
        "cycle_ts": cycle.isoformat(),
        "symbol": symbol,
        "quote_ts": datetime(2026, 8, 20, 13, 25 + minute, 0, 500000, tzinfo=UTC).isoformat(),
        "bid": bid,
        "ask": ask,
        "bid_size": 5.0,
        "ask_size": 7.0,
        "bid_exchange": "V",
        "ask_exchange": "V",
        "conditions": ["R"],
    }


@pytest.fixture
def frozen_partition(tmp_path: Path) -> CaptureStore:
    """A frozen partition containing BOTH allowed and holdout symbols."""
    store = CaptureStore(tmp_path / "capture")
    ref = PartitionRef(feed=FEED, session=SESSION)
    rows = []
    for minute in range(3):
        for sym in ("AAPL", "NVDA", "TSLA", "XOM", "AMZN"):
            rows.append(quote_row(sym, minute))
    rows.append({"cycle_ts": rows[0]["cycle_ts"], "symbol": "MSFT", "missing": True})
    rows.append({"cycle_ts": rows[0]["cycle_ts"], "feed_error": "Timeout: boom"})
    store.append_jsonl(ref, "quotes", rows)
    store.freeze(ref, provenance=PROVENANCE)
    return store


def make_scope(symbols: list[str], dates: list[date]):
    policy = MdqExplorationPolicy(
        universe_symbols=UNIVERSE,
        holdout_symbols=HOLDOUT,
        window=ReviewWindow.governed(),
    )
    return policy.authorize(symbols, dates, ReadPurpose.EXPLORATION)


# --- the quarantine ---------------------------------------------------------


def test_holdout_symbols_in_the_partition_are_never_returned(
    frozen_partition: CaptureStore,
) -> None:
    """The partition physically contains TSLA/XOM/AMZN rows. The reader must
    not surface them even though the caller asked for them."""
    scope = make_scope(["AAPL", "NVDA", "TSLA", "XOM", "AMZN"], [SESSION])
    reader = MdqFeatureReader(frozen_partition, scope)

    result = reader.read_quotes(FEED, SESSION)

    returned = {o.symbol for o in result.observations}
    assert returned == {"AAPL", "NVDA"}
    for held in ("TSLA", "XOM", "AMZN"):
        assert held not in returned
    # 3 minutes x 2 allowed symbols
    assert len(result.observations) == 6
    # 9 holdout rows + 1 missing + 1 feed_error withheld
    assert result.rows_withheld == 11
    assert result.rows_scanned == 17


def test_a_holdout_date_is_refused_before_the_partition_is_opened(tmp_path: Path) -> None:
    """No file is touched: the store points at a directory that does not even
    exist, and the call still raises the authorization error."""
    store = CaptureStore(tmp_path / "does-not-exist")
    scope = make_scope(["AAPL"], [HOLDOUT_SESSION])
    assert scope.is_empty

    reader = MdqFeatureReader(store, scope)
    with pytest.raises(UnauthorizedReadError, match="authorizes no symbol"):
        reader.read_quotes(FEED, HOLDOUT_SESSION)


def test_reading_a_date_outside_the_scope_is_refused(frozen_partition: CaptureStore) -> None:
    scope = make_scope(["AAPL"], [SESSION])
    reader = MdqFeatureReader(frozen_partition, scope)
    with pytest.raises(UnauthorizedReadError):
        reader.read_quotes(FEED, date(2026, 8, 21))


def test_reader_cannot_be_constructed_without_a_scope(frozen_partition: CaptureStore) -> None:
    with pytest.raises(TypeError, match="AuthorizedScope"):
        MdqFeatureReader(frozen_partition, None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="AuthorizedScope"):
        MdqFeatureReader(frozen_partition, {("TSLA", SESSION)})  # type: ignore[arg-type]


def test_scope_is_not_widenable_at_read_time(frozen_partition: CaptureStore) -> None:
    """AuthorizedScope is frozen and its pairs are a frozenset — there is no
    supported way to add a holdout name after authorization."""
    scope = make_scope(["AAPL"], [SESSION])
    with pytest.raises((AttributeError, TypeError)):
        scope.pairs = frozenset({("TSLA", SESSION)})  # type: ignore[misc]
    with pytest.raises(AttributeError):
        scope.pairs.add(("TSLA", SESSION))  # type: ignore[attr-defined]


# --- frozen-only + integrity ------------------------------------------------


def test_unfrozen_partition_is_refused(tmp_path: Path) -> None:
    store = CaptureStore(tmp_path / "capture")
    ref = PartitionRef(feed=FEED, session=SESSION)
    store.append_jsonl(ref, "quotes", [quote_row("AAPL", 0)])
    # deliberately not frozen

    reader = MdqFeatureReader(store, make_scope(["AAPL"], [SESSION]))
    with pytest.raises(PartitionNotFrozenError, match="frozen partitions only"):
        reader.read_quotes(FEED, SESSION)


def test_a_mutated_partition_fails_closed(frozen_partition: CaptureStore) -> None:
    ref = PartitionRef(feed=FEED, session=SESSION)
    path = frozen_partition.partition_dir(ref) / "quotes" / "samples.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(quote_row("AAPL", 9)) + "\n")

    reader = MdqFeatureReader(frozen_partition, make_scope(["AAPL"], [SESSION]))
    with pytest.raises(PartitionIntegrityError, match="failed verification"):
        reader.read_quotes(FEED, SESSION)


# --- provenance -------------------------------------------------------------


def test_read_result_carries_full_provenance(frozen_partition: CaptureStore) -> None:
    scope = make_scope(["AAPL", "NVDA"], [SESSION])
    result = MdqFeatureReader(frozen_partition, scope).read_quotes(FEED, SESSION)

    prov = result.as_provenance_dict()
    assert prov["reader_version"] == READER_VERSION
    assert prov["policy_version"] == scope.policy_version
    assert prov["purpose"] == "exploration"
    assert prov["scope_fingerprint"] == scope.fingerprint()

    partition = prov["partition"]
    assert isinstance(partition, dict)
    assert partition["feed"] == FEED
    assert partition["session_date"] == "2026-08-20"
    assert partition["collector_version"] == "mdq-collector/0.1.0"
    assert partition["integrity_verified"] is True
    assert len(str(partition["manifest_sha256"])) == 64
    assert partition["files"]
    assert all(len(f["sha256"]) == 64 for f in partition["files"])  # type: ignore[index]


# --- observation arithmetic (§0.4 definitions) ------------------------------


def test_spread_and_freshness_follow_the_frozen_definitions(
    frozen_partition: CaptureStore,
) -> None:
    result = MdqFeatureReader(frozen_partition, make_scope(["AAPL"], [SESSION])).read_quotes(
        FEED, SESSION
    )
    obs = result.observations[0]
    assert obs.mid == pytest.approx(100.05)
    assert obs.spread_bps == pytest.approx(10_000 * 0.1 / 100.05)
    # quote_ts is 0.5s AFTER cycle_ts in the fixture, so age is negative here;
    # what matters is the arithmetic, not the sign.
    assert obs.quote_age_s == pytest.approx(-0.5)


def test_crossed_or_zero_quotes_yield_no_midpoint(tmp_path: Path) -> None:
    store = CaptureStore(tmp_path / "capture")
    ref = PartitionRef(feed=FEED, session=SESSION)
    store.append_jsonl(
        ref,
        "quotes",
        [
            quote_row("AAPL", 0, bid=101.0, ask=100.0),  # crossed
            quote_row("NVDA", 0, bid=0.0, ask=0.0),  # stub
        ],
    )
    store.freeze(ref, provenance=PROVENANCE)

    result = MdqFeatureReader(store, make_scope(["AAPL", "NVDA"], [SESSION])).read_quotes(
        FEED, SESSION
    )
    assert len(result.observations) == 2
    for obs in result.observations:
        assert obs.mid is None
        assert obs.spread_bps is None


def test_torn_final_line_is_tolerated(tmp_path: Path) -> None:
    """store.append_jsonl documents that a torn tail is possible."""
    store = CaptureStore(tmp_path / "capture")
    ref = PartitionRef(feed=FEED, session=SESSION)
    store.append_jsonl(ref, "quotes", [quote_row("AAPL", 0)])
    path = store.partition_dir(ref) / "quotes" / "samples.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write('{"cycle_ts": "2026-08-20T13:2')
    store.freeze(ref, provenance=PROVENANCE)

    result = MdqFeatureReader(store, make_scope(["AAPL"], [SESSION])).read_quotes(FEED, SESSION)
    assert len(result.observations) == 1
