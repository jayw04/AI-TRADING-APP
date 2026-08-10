"""Tests for the box-native premarket gapper screener (GAP-NATIVE-001, ADR 0041).

All Alpaca clients are faked — no network. Covers the external-scanner filter
parity, gap recomputation, the stale-IEX-print drop (found live by the
2026-07-10 probe), path A→B discovery degrade, fail-soft, and the atomic write
+ reader round-trip.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.services import native_gapper_screener as ngs
from app.services import premarket_gappers as pg
from app.utils.time import EASTERN

NOW = datetime(2026, 7, 13, 13, 5, tzinfo=UTC)  # Mon 09:05 ET
TODAY_ET = NOW.astimezone(EASTERN).date()


def _mover(symbol: str, pct: float = 10.0, price: float = 20.0) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, percent_change=pct, price=price)


def _snap(
    price: float,
    prev_close: float,
    volume: float = 1_000_000,
    *,
    trade_ts: datetime = NOW,
    bar_ts: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        latest_trade=SimpleNamespace(price=price, timestamp=trade_ts),
        previous_daily_bar=SimpleNamespace(close=prev_close),
        daily_bar=SimpleNamespace(volume=volume, timestamp=bar_ts or trade_ts),
    )


class _FakeScreener:
    """Stand-in for Alpaca's ScreenerClient.

    ``last_updated`` is part of the response and is NOT incidental: it is the only
    field that distinguishes a live premarket tape from the previous session's,
    and the endpoint returns a full gainers list either way. A fake that omitted
    it is what let the stale-tape defect survive review — so it is modelled here,
    defaulting to a fresh (same-day) tape."""

    def __init__(
        self,
        gainers: list[SimpleNamespace] | None = None,
        error: bool = False,
        last_updated: datetime | None = NOW,
    ):
        self._gainers = gainers or []
        self._error = error
        self._last_updated = last_updated

    def get_market_movers(self, _req: Any) -> SimpleNamespace:
        if self._error:
            raise RuntimeError("screener down")
        return SimpleNamespace(
            gainers=self._gainers, losers=[], last_updated=self._last_updated
        )


class _FakeDataClient:
    def __init__(self, snaps: dict[str, SimpleNamespace], error: bool = False):
        self._snaps = snaps
        self._error = error
        self.batches: list[list[str]] = []

    def get_stock_snapshot(self, req: Any) -> dict[str, SimpleNamespace]:
        if self._error:
            raise RuntimeError("snapshots down")
        symbols = req.symbol_or_symbols
        self.batches.append(list(symbols))
        return {s: self._snaps[s] for s in symbols if s in self._snaps}


class _FakeFactorStore:
    """Path-B stand-in: .con.execute for the sep re-anchor + the universe call."""

    def __init__(self, symbols: list[str]):
        self._symbols = symbols
        self.con = SimpleNamespace(
            execute=lambda _sql: SimpleNamespace(fetchone=lambda: (TODAY_ET - timedelta(days=3),))
        )

    def dollar_volume_universe(self, _as_of: Any, _n: int, _lookback: int) -> list[str]:
        return list(self._symbols)


async def test_filter_parity_ranking_and_schema() -> None:
    """External-scanner thresholds (strict >), top-N by gap, rank 1..N, null catalyst."""
    screener = _FakeScreener([_mover(s) for s in ("BIGG", "MIDG", "LOWG", "CHEAP", "THIN")])
    data = _FakeDataClient({
        "BIGG": _snap(24.0, 20.0),                        # +20% → rank 1
        "MIDG": _snap(21.6, 20.0),                        # +8%  → rank 2
        "LOWG": _snap(20.8, 20.0),                        # +4%  → below MIN_GAP_PCT
        "CHEAP": _snap(2.4, 2.0),                         # +20% but price ≤ $3
        "THIN": _snap(24.0, 20.0, volume=10_000),         # +20% but volume ≤ 50k
    })
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert out["ok"] is True
    assert out["discovery_path"] == "movers"
    assert out["count"] == 2
    rows = out["payload"]["gappers"]
    assert [(r["rank"], r["symbol"]) for r in rows] == [(1, "BIGG"), (2, "MIDG")]
    assert rows[0]["gap_pct"] == 20.0
    assert rows[0]["catalyst"] is None and rows[0]["headlines"] == []
    assert out["payload"]["source"] == ngs.SOURCE
    # morning funnel diagnostics (review §5) — per-criterion counts are independent
    funnel = out["funnel"]
    assert funnel["symbols_discovered"] == 5
    assert funnel["symbols_with_snapshot"] == 5
    assert funnel["symbols_with_current_premarket_trade"] == 5
    assert funnel["passing_gap"] == 4          # all but LOWGAP
    assert funnel["passing_price"] == 4        # all but CHEAP
    assert funnel["passing_volume"] == 4       # all but THIN
    assert funnel["final_count"] == 2


async def test_stale_iex_print_is_dropped() -> None:
    """A months-old 'latest' trade (probe: QSEAR) must not fabricate a gap."""
    screener = _FakeScreener([_mover("STALE"), _mover("FRESH")])
    data = _FakeDataClient({
        "STALE": _snap(24.0, 20.0, trade_ts=NOW - timedelta(days=90)),
        "FRESH": _snap(24.0, 20.0),
    })
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert [r["symbol"] for r in out["payload"]["gappers"]] == ["FRESH"]


async def test_prior_day_daily_bar_counts_zero_premarket_volume() -> None:
    """No bar accumulated today → premarket volume 0 → filtered by the volume floor."""
    screener = _FakeScreener([_mover("NOBAR")])
    data = _FakeDataClient(
        {"NOBAR": _snap(24.0, 20.0, bar_ts=NOW - timedelta(days=1))}
    )
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert out["ok"] is True
    assert out["count"] == 0


async def test_suffixed_instruments_dropped_at_discovery() -> None:
    """Warrants/units on the movers tape (EONR.WS) never reach verification."""
    screener = _FakeScreener([_mover("EONR.WS"), _mover("BRK.PR.A"), _mover("GOOD")])
    data = _FakeDataClient({"GOOD": _snap(24.0, 20.0)})
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert data.batches == [["GOOD"]]
    assert [r["symbol"] for r in out["payload"]["gappers"]] == ["GOOD"]


async def test_snapshot_batching() -> None:
    symbols = [
        "".join(chr(65 + (i // 26**k) % 26) for k in (2, 1, 0)) for i in range(450)
    ]  # AAA, AAB, ... — plain 3-letter symbols so discovery keeps all 450
    screener = _FakeScreener([_mover(s) for s in symbols])
    data = _FakeDataClient({})
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert out["ok"] is True
    assert [len(b) for b in data.batches] == [200, 200, 50]


async def test_path_b_store_sweep_when_movers_empty() -> None:
    screener = _FakeScreener([])  # movers returns nothing
    data = _FakeDataClient({"SWEPT": _snap(24.0, 20.0)})
    store = _FakeFactorStore(["SWEPT", "QUIET"])
    out = await ngs.scan_native_gappers(
        now=NOW, screener_client=screener, data_client=data, factor_store=store
    )
    assert out["ok"] is True
    assert out["discovery_path"] == "store_sweep"
    assert [r["symbol"] for r in out["payload"]["gappers"]] == ["SWEPT"]


async def test_stale_movers_tape_is_disqualified_and_falls_through_to_path_b() -> None:
    """★ The ADR 0041 Decision-6 guard, and the reason #407 could not merge as built.

    Premarket, the movers endpoint returns a FULL gainers list carrying the PREVIOUS
    session's ``last_updated`` (3/3 in-window probes: 07-13, 07-17, 07-20). The old
    predicate degraded to path B only on an EMPTY list, so it never fired and the day
    was built from the wrong session's universe — silently, with ``ok: True``."""
    prior_session = datetime(2026, 7, 10, 23, 59, tzinfo=UTC)  # Friday's close
    screener = _FakeScreener(
        [_mover(s) for s in ("STLA", "STLB")], last_updated=prior_session
    )
    data = _FakeDataClient({
        "SWEPT": _snap(24.0, 20.0),
        # Present so a regression that kept path A would visibly produce these:
        "STLA": _snap(24.0, 20.0),
        "STLB": _snap(24.0, 20.0),
    })
    out = await ngs.scan_native_gappers(
        now=NOW, screener_client=screener, data_client=data,
        factor_store=_FakeFactorStore(["SWEPT"]),
    )
    assert out["ok"] is True
    assert out["discovery_path"] == "store_sweep"
    assert out["discovery_reason"] == ngs.DISCOVERY_STALE
    # The stale universe must not leak through: only the swept name survives.
    assert [r["symbol"] for r in out["payload"]["gappers"]] == ["SWEPT"]
    # Write-time provenance, in the artifact itself (GAPPER v2.1.1 §5.5).
    assert out["payload"]["discovery_path"] == "store_sweep"
    assert out["payload"]["discovery_reason"] == ngs.DISCOVERY_STALE
    assert out["payload"]["movers_last_updated"] == prior_session.isoformat()


async def test_fresh_movers_tape_still_uses_path_a() -> None:
    """The guard is scoped to staleness only — a same-day tape keeps path A, so a
    post-open run (or a future fresh premarket endpoint) needs no code change."""
    screener = _FakeScreener([_mover("BIGG")], last_updated=NOW)
    data = _FakeDataClient({"BIGG": _snap(24.0, 20.0)})
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    assert out["ok"] is True
    assert out["discovery_path"] == "movers"
    assert out["discovery_reason"] == ngs.DISCOVERY_MOVERS_FRESH
    assert out["payload"]["discovery_reason"] == ngs.DISCOVERY_MOVERS_FRESH


async def test_unknown_movers_freshness_fails_closed() -> None:
    """No parseable ``last_updated`` ⇒ treat as stale. A current-but-incomplete
    universe beats a complete one from an unknown session."""
    screener = _FakeScreener([_mover("MAYBE")], last_updated=None)
    data = _FakeDataClient({"SWEPT": _snap(24.0, 20.0), "MAYBE": _snap(24.0, 20.0)})
    out = await ngs.scan_native_gappers(
        now=NOW, screener_client=screener, data_client=data,
        factor_store=_FakeFactorStore(["SWEPT"]),
    )
    assert out["discovery_path"] == "store_sweep"
    assert out["discovery_reason"] == ngs.DISCOVERY_STALE
    assert out["payload"]["movers_last_updated"] is None


async def test_write_refuses_a_payload_without_discovery_provenance(tmp_path) -> None:
    """§5.5: provenance is stamped at write time or the write does not happen —
    a record cannot acquire provenance afterwards."""
    import pytest

    with pytest.raises(ValueError, match="discovery_path"):
        ngs.write_gappers_file(
            {"scanned_at": "2026-07-13T13:05:00Z", "source": ngs.SOURCE, "gappers": []},
            str(tmp_path),
            date_str="2026-07-13",
        )


async def test_path_b_also_covers_screener_errors() -> None:
    screener = _FakeScreener(error=True)
    data = _FakeDataClient({"SWEPT": _snap(24.0, 20.0)})
    out = await ngs.scan_native_gappers(
        now=NOW, screener_client=screener, data_client=data,
        factor_store=_FakeFactorStore(["SWEPT"]),
    )
    assert out["ok"] is True and out["discovery_path"] == "store_sweep"


async def test_no_discovery_and_snapshot_errors_fail_soft() -> None:
    out = await ngs.scan_native_gappers(
        now=NOW, screener_client=_FakeScreener([]), data_client=_FakeDataClient({})
    )
    assert out["ok"] is False and out["reason"] == "no_discovery_symbols"

    out2 = await ngs.scan_native_gappers(
        now=NOW,
        screener_client=_FakeScreener([_mover("AAA")]),
        data_client=_FakeDataClient({}, error=True),
    )
    assert out2["ok"] is False and "snapshots down" in out2["reason"]


async def test_write_and_reader_round_trip(tmp_path, monkeypatch) -> None:
    """The written file is the operational payload: native-wins, not stale, source kept."""
    now = datetime.now(UTC)
    # This test runs against the real current date, so the movers tape must be
    # dated to the same day or the Decision-6 guard correctly rejects path A.
    screener = _FakeScreener([_mover("RT")], last_updated=now)
    data = _FakeDataClient({"RT": _snap(24.0, 20.0, trade_ts=now)})
    out = await ngs.scan_native_gappers(now=now, screener_client=screener, data_client=data)
    path = ngs.write_gappers_file(out["payload"], str(tmp_path), date_str=out["date"])
    with open(path, encoding="utf-8") as fh:
        written = json.load(fh)
    assert written["source"] == ngs.SOURCE
    assert written["discovery_path"] == "movers"
    assert written["discovery_reason"] == ngs.DISCOVERY_MOVERS_FRESH

    monkeypatch.setattr(pg, "_native_directory", lambda: str(tmp_path))
    monkeypatch.setattr(pg, "_directory", lambda: str(tmp_path / "no_external"))
    resolved = pg.read_latest_gappers()
    assert resolved["stale"] is False
    assert resolved["source"] == ngs.SOURCE
    assert resolved["gappers"][0]["symbol"] == "RT"


async def test_native_rows_feed_the_premarket_panel() -> None:
    """Schema compatibility with the SCAN-001 adapter (plan §1.7 panel-compat)."""
    from app.factor_data import premarket_adapter as pa

    screener = _FakeScreener([_mover("PANEL")])
    data = _FakeDataClient({"PANEL": _snap(24.0, 20.0)})
    out = await ngs.scan_native_gappers(now=NOW, screener_client=screener, data_client=data)
    store_feat = {"PANEL": {"atr_pct": 4.0, "avg_volume": 1_000_000, "prev_dollar_vol": 5e7}}
    panel = pa.premarket_panel(out["payload"]["gappers"], store_feat)
    assert len(panel) == 1
    assert panel[0]["symbol"] == "PANEL"
    assert panel[0]["gap_pct"] == 20.0
