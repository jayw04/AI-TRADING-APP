"""MDQ-001 collector unit tests — store immutability, provenance, identity
latch, and paired sampling. No network; the Alpaca client and the account
getter are faked."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.research.capture.collector import (
    PHASE_A_UNIVERSE,
    fetch_session_bars,
    sample_quotes_cycle,
)
from app.research.capture.identity import (
    AcquisitionPins,
    IdentityError,
    key_fingerprint,
    verify_identity,
)
from app.research.capture.store import (
    CaptureStore,
    FrozenPartitionError,
    PartitionRef,
)

SESSION = date(2026, 8, 17)


# --- identity -----------------------------------------------------------------


def test_key_fingerprint_is_stable_12_hex() -> None:
    fp = key_fingerprint("PKTESTKEY123")
    assert len(fp) == 12
    assert fp == key_fingerprint("PKTESTKEY123")
    int(fp, 16)  # valid hex


def test_verify_identity_rejects_wrong_fingerprint() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("EXPECTED"))
    with pytest.raises(IdentityError, match="fingerprint"):
        verify_identity("OTHER", "s", pins, account_getter=lambda *_: "PA3BGKRLH2AP")


def test_verify_identity_rejects_wrong_account() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("K"))
    with pytest.raises(IdentityError, match="account"):
        verify_identity("K", "s", pins, account_getter=lambda *_: "PAWRONGACCT")


def test_verify_identity_passes_and_returns_account() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("K"))
    assert (
        verify_identity("K", "s", pins, account_getter=lambda *_: pins.account_number)
        == pins.account_number
    )


def test_default_pins_are_the_account7_latch() -> None:
    pins = AcquisitionPins()
    assert pins.account_number == "PA3BGKRLH2AP"
    assert pins.key_fingerprint == "5b6f39e5198d"


# --- store --------------------------------------------------------------------


def test_partition_ref_rejects_unknown_feed() -> None:
    with pytest.raises(ValueError):
        PartitionRef(feed="best_available", session=SESSION)


def test_append_write_freeze_verify_roundtrip(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    store.append_jsonl(ref, "quotes", [{"symbol": "SPY", "bid": 1.0}])
    store.write_parquet(ref, "bars", "bars_1min", pd.DataFrame({"symbol": ["SPY"], "close": [1.0]}))

    mpath = store.freeze(ref, provenance={"credential_fingerprint": "abc"})
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    assert manifest["feed"] == "sip"
    assert manifest["credential_fingerprint"] == "abc"
    assert {f["path"] for f in manifest["files"]} == {
        "quotes/samples.jsonl",
        "bars/bars_1min.parquet",
    }
    assert store.verify(ref) == []


def test_frozen_partition_refuses_all_writes(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="iex", session=SESSION)
    store.append_jsonl(ref, "quotes", [{"symbol": "SPY"}])
    store.freeze(ref, provenance={})
    with pytest.raises(FrozenPartitionError):
        store.append_jsonl(ref, "quotes", [{"symbol": "QQQ"}])
    with pytest.raises(FrozenPartitionError):
        store.write_parquet(ref, "bars", "x", pd.DataFrame({"a": [1]}))
    with pytest.raises(FrozenPartitionError):
        store.freeze(ref, provenance={})


def test_verify_detects_tamper_and_unmanifested_files(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    path = store.append_jsonl(ref, "quotes", [{"symbol": "SPY"}])
    store.freeze(ref, provenance={})

    path.write_text("tampered\n", encoding="utf-8")
    problems = store.verify(ref)
    assert any("hash mismatch" in p for p in problems)

    (store.partition_dir(ref) / "rogue.txt").write_text("x", encoding="utf-8")
    assert any("unmanifested" in p for p in store.verify(ref))


def test_freeze_refuses_empty_partition(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    store.partition_dir(ref).mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        store.freeze(ref, provenance={})


# --- collector primitives -----------------------------------------------------


class _FakeQuote(SimpleNamespace):
    pass


class _FakeClient:
    """Records every request so tests can assert explicit feed binding."""

    def __init__(self) -> None:
        self.requests: list = []

    def get_stock_latest_quote(self, req):
        self.requests.append(req)
        ts = datetime(2026, 8, 17, 14, 30, tzinfo=UTC)
        return {
            sym: _FakeQuote(
                timestamp=ts,
                bid_price=99.0,
                ask_price=101.0,
                bid_size=1.0,
                ask_size=2.0,
                bid_exchange="V",
                ask_exchange="V",
                conditions=["R"],
            )
            for sym in req.symbol_or_symbols
            if sym != "MISSING"
        }

    def get_stock_bars(self, req):
        self.requests.append(req)
        bar = SimpleNamespace(
            timestamp=datetime(2026, 8, 17, 13, 30, tzinfo=UTC),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=100.0,
            trade_count=7,
            vwap=1.4,
        )
        return SimpleNamespace(data={s: [bar] for s in req.symbol_or_symbols})


def test_sample_cycle_pairs_feeds_and_binds_explicit_feed() -> None:
    client = _FakeClient()
    out = sample_quotes_cycle(client, ("SPY", "MISSING"))
    assert set(out) == {"iex", "sip"}
    assert [str(r.feed.value) for r in client.requests] == ["iex", "sip"]
    iex = {r["symbol"]: r for r in out["iex"]}
    assert iex["SPY"]["bid"] == 99.0 and iex["SPY"]["ask"] == 101.0
    assert iex["MISSING"]["missing"] is True
    # paired: both feeds share one cycle_ts
    assert out["iex"][0]["cycle_ts"] == out["sip"][0]["cycle_ts"]


def test_fetch_session_bars_tidy_frame_with_explicit_feed() -> None:
    client = _FakeClient()
    df = fetch_session_bars(client, ("SPY", "QQQ"), SESSION, "sip")
    assert str(client.requests[0].feed.value) == "sip"
    assert sorted(df["symbol"]) == ["QQQ", "SPY"]
    assert set(df.columns) >= {"symbol", "ts", "open", "close", "volume", "trade_count", "vwap"}


def test_phase_a_universe_is_the_proposed_default() -> None:
    assert "SPY" in PHASE_A_UNIVERSE and "XLK" in PHASE_A_UNIVERSE
    assert len(PHASE_A_UNIVERSE) == 14


# --- structural invariants (ADR 0051 / registration §7 control 1) --------------


def test_capture_package_http_boundary_is_structural() -> None:
    """app/research/capture performs raw HTTP for exactly one purpose — the
    read-only GET /v2/account identity latch. Raw HTTP must never grow into
    trading capability: no mutating verbs, no other /v2/ endpoints, no
    alpaca.trading import (MDQ-001 registration §7 control 1)."""
    import re

    import app.research.capture as pkg

    pkg_dir = Path(pkg.__file__).parent
    forbidden_verbs = re.compile(
        r"(httpx|requests)\.(post|put|delete|patch)\(|\.request\(\s*[\"'](POST|PUT|DELETE|PATCH)"
    )
    v2_endpoint = re.compile(r"/v2/[a-zA-Z_/]+")
    for path in sorted(pkg_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not forbidden_verbs.search(text), f"mutating HTTP verb in {path.name}"
        for hit in v2_endpoint.findall(text):
            assert hit.startswith("/v2/account"), f"non-identity /v2/ endpoint {hit} in {path.name}"
        trading_import = re.compile(r"^\s*(from|import)\s+alpaca\.trading", re.MULTILINE)
        assert not trading_import.search(text), f"trading SDK import in {path.name}"
        # No order-path or broker-module imports: the package imports nothing
        # from app.* outside itself (plan v0.3 §4.5 — structural, not reviewed).
        app_import = re.compile(r"^\s*(?:from|import)\s+(app\.[\w.]+)", re.MULTILINE)
        for mod in app_import.findall(text):
            assert mod.startswith("app.research.capture"), (
                f"foreign app import {mod} in {path.name}"
            )


def test_sample_cycle_isolates_per_feed_failures() -> None:
    """A transient failure on one feed must not lose the other feed's cycle;
    the failed feed gets a single auditable error record (frozen retry policy)."""

    class _FlakyClient(_FakeClient):
        def get_stock_latest_quote(self, req):
            if str(req.feed.value) == "sip":
                raise ConnectionError("transient")
            return super().get_stock_latest_quote(req)

    out = sample_quotes_cycle(_FlakyClient(), ("SPY",))
    assert out["iex"][0]["bid"] == 99.0
    assert len(out["sip"]) == 1 and "feed_error" in out["sip"][0]
    assert "ConnectionError" in out["sip"][0]["feed_error"]
