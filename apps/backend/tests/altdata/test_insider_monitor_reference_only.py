"""Insider Reference Monitor — the owner-required reference-only guarantees (plan §4.4).

Covers: every row + envelope flagged ``reference_only``; import isolation from order-path /
ranking modules; the ``insider_buy`` → rejected INSIDER-001 mapping (drift guard); ingest
idempotency by accession; factor-store-unavailable fallback (manifest included); sort by
``filed_at`` DESC only. The account-3 order-count assertion runs in the box smoke (plan §5) —
here its structural equivalent is the import-isolation test (the modules *cannot* order).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.insider_monitor import (
    FALLBACK_UNIVERSE,
    InsiderReferenceRow,
    load_latest_manifest,
    manifest_is_fresh,
    recent_reference_rows,
    resolve_monitor_universe,
    write_universe_manifest,
)
from app.altdata.reference_only import REFERENCE_ONLY_PROGRAMS
from app.research.programs import RESEARCH_PROGRAMS

_NOW = datetime(2026, 7, 9, 18, 30, tzinfo=UTC)


def _event(accession: str, ticker: str, *, hours_ago: float, value: float = 50_000.0,
           owner: str = "Jane Exec") -> CorporateEvent:
    filed = _NOW - timedelta(hours=hours_ago)
    return CorporateEvent(
        cik=1, ticker=ticker, event_type="insider_buy", source="sec_edgar_form4",
        accession=accession, filed_at=filed.replace(tzinfo=None),
        event_date=filed.date(),
        payload={"owner_name": owner, "is_officer": True, "officer_title": "CEO",
                 "buy_value": value, "form_type": "4", "issuer_name": f"{ticker} Corp"},
    )


def _store(tmp_path: Path, events: list[CorporateEvent]) -> EventStore:
    store = EventStore(str(tmp_path / "events.duckdb"))
    store.upsert_events(events)
    return store


class _BrokenFactorStore:
    @property
    def con(self):  # noqa: ANN202
        raise RuntimeError("store unavailable")

    def dollar_volume_universe(self, *a, **k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("store unavailable")


# ---- 1+2. every row (and, shape-wise, the envelope) is reference_only ----------------------


def test_rows_always_reference_only(tmp_path: Path) -> None:
    store = _store(tmp_path, [_event("a-1", "FULT", hours_ago=2)])
    rows = recent_reference_rows(store, _BrokenFactorStore(), now=_NOW)
    store.close()
    assert rows and all(r.reference_only is True for r in rows)
    assert all(r.to_dict()["reference_only"] is True for r in rows)


def test_reference_only_not_constructible_false() -> None:
    # the dataclass defaults True; the read path never passes it — pin the default
    assert InsiderReferenceRow.__dataclass_fields__["reference_only"].default is True


# ---- 3. import isolation: display modules must not reach order-path / ranking code ---------


def test_monitor_modules_import_isolation() -> None:
    forbidden = ("app.orders", "app.risk", "app.services.order_router", "app.strategies",
                 "app.brokers")
    base = Path(__file__).resolve().parents[2] / "app"
    for rel in ("altdata/insider_monitor.py", "jobs/insider_reference_monitor.py",
                "api/v1/insider_reference.py"):
        src = (base / rel).read_text(encoding="utf-8")
        for mod in forbidden:
            assert f"from {mod}" not in src and f"import {mod}" not in src, (
                f"{rel} references {mod} — the reference-only surface must stay display-side"
            )


# ---- 4+5. invariant wiring: insider_buy stays a rejected reference-only label --------------


def test_insider_buy_maps_to_rejected_program() -> None:
    assert REFERENCE_ONLY_PROGRAMS["insider_buy"] == "INSIDER-001"
    prog = next(p for p in RESEARCH_PROGRAMS if p.id == "INSIDER-001")
    assert prog.status == "rejected"


# ---- 6 (structural) + 7. ingest idempotency by accession -----------------------------------


def test_upsert_idempotent_by_accession(tmp_path: Path) -> None:
    ev = _event("a-dup", "FULT", hours_ago=1)
    store = _store(tmp_path, [ev])
    assert store.upsert_events([ev]) == 0  # second pass: no new rows
    rows = store.events_filed_since(_NOW.replace(tzinfo=None) - timedelta(days=1),
                                    event_type="insider_buy")
    store.close()
    assert len(rows) == 1


class _Sf1OnlyCon:
    """A store connection with NO metrics table but an sf1_fundamentals marketcap (the live
    box store shape, found at first deploy 2026-07-09)."""

    def execute(self, sql: str, params: list):  # noqa: ANN001, ANN202
        if "FROM metrics" in sql:
            raise RuntimeError("Table 'metrics' does not exist")
        if "FROM sf1_fundamentals" in sql:
            self._rows = [(t, 1e9) for t in params]  # everything $1B — none mega-cap
            return self
        raise RuntimeError("unexpected query")

    def fetchall(self):  # noqa: ANN202
        return self._rows


class _Sf1OnlyFactorStore:
    con = _Sf1OnlyCon()

    def dollar_volume_universe(self, as_of, n, lookback):  # noqa: ANN001, ARG002, ANN202
        return ["FULT", "INDB", "UCBI"]


class _NoMcapCon(_Sf1OnlyCon):
    def execute(self, sql: str, params: list):  # noqa: ANN001, ANN202
        raise RuntimeError("no marketcap source at all")


class _NoMcapFactorStore(_Sf1OnlyFactorStore):
    con = _NoMcapCon()


class _StaleAsofCon(_Sf1OnlyCon):
    def execute(self, sql: str, params: list | None = None):  # noqa: ANN001, ANN202
        if "max(date) FROM sep" in sql:
            self._rows = [(date(2026, 7, 8),)]
            return self
        return super().execute(sql, params or [])

    def fetchone(self):  # noqa: ANN202
        return self._rows[0]


class _StaleAsofFactorStore(_Sf1OnlyFactorStore):
    """dollar_volume_universe is EMPTY for today's as_of (lastpricedate = prior close) but
    resolves for the store's own latest sep date - the live 2026-07-09 shape."""

    def __init__(self) -> None:
        self.calls: list[date] = []
        self.con = _StaleAsofCon()

    def dollar_volume_universe(self, as_of, n, lookback):  # noqa: ANN001, ARG002, ANN202
        self.calls.append(as_of)
        return ["FULT", "INDB", "UCBI"] if as_of <= date(2026, 7, 8) else []


def test_universe_reanchors_asof_to_store_latest_when_empty() -> None:
    store = _StaleAsofFactorStore()
    tickers, reason = resolve_monitor_universe(store, as_of=date(2026, 7, 9))
    assert tickers == ["FULT", "INDB", "UCBI"]  # NOT the 134 fallback
    assert store.calls == [date(2026, 7, 9), date(2026, 7, 8)]  # retried at the store's date
    assert reason.startswith("smallmid-dv-rank")


def test_universe_uses_sf1_marketcap_when_metrics_missing() -> None:
    tickers, reason = resolve_monitor_universe(_Sf1OnlyFactorStore(), as_of=date(2026, 7, 9))
    assert tickers == ["FULT", "INDB", "UCBI"]
    assert reason.startswith("smallmid-dv-rank")


def test_universe_ships_unfiltered_when_no_marketcap_source() -> None:
    # the mega-cap FILTER degrades; the dv universe must NOT collapse to the 134 fallback
    tickers, reason = resolve_monitor_universe(_NoMcapFactorStore(), as_of=date(2026, 7, 9))
    assert tickers == ["FULT", "INDB", "UCBI"]
    assert reason.endswith("-unfiltered")


# ---- 8. factor store unavailable -> fallback universe + auditable manifest -----------------


def test_fallback_universe_and_manifest(tmp_path: Path) -> None:
    tickers, reason = resolve_monitor_universe(_BrokenFactorStore(), as_of=date(2026, 7, 9))
    assert reason == "fallback-134" and len(tickers) == 134
    path = write_universe_manifest(tickers, inclusion_reason=reason, as_of=date(2026, 7, 9),
                                   data_dir=tmp_path)
    assert path.exists()
    manifest = load_latest_manifest(tmp_path)
    assert manifest is not None
    assert manifest["count"] == len(FALLBACK_UNIVERSE)
    assert manifest["rows"][0]["inclusion_reason"] == "fallback-134"
    assert manifest_is_fresh(manifest, today=date(2026, 7, 9))
    assert not manifest_is_fresh(manifest, today=date(2026, 7, 20))


# ---- sorting + display-hygiene filters ------------------------------------------------------


def test_sorted_by_filed_at_desc_only(tmp_path: Path) -> None:
    # a fresher, much SMALLER trade must sort first — value must not influence order
    store = _store(tmp_path, [
        _event("a-old-big", "FULT", hours_ago=48, value=5_000_000.0, owner="A"),
        _event("a-new-small", "INDB", hours_ago=1, value=15_000.0, owner="B"),
    ])
    rows = recent_reference_rows(store, _BrokenFactorStore(), now=_NOW)
    store.close()
    assert [r.ticker for r in rows] == ["INDB", "FULT"]


def test_min_value_filter_is_display_hygiene(tmp_path: Path) -> None:
    store = _store(tmp_path, [_event("a-tiny", "FULT", hours_ago=2, value=500.0)])
    rows = recent_reference_rows(store, _BrokenFactorStore(), now=_NOW)
    assert rows == []  # default $10k floor hides it
    rows = recent_reference_rows(store, _BrokenFactorStore(), min_value=0.0, now=_NOW)
    store.close()
    assert len(rows) == 1 and rows[0].insider_role == "officer: CEO"
