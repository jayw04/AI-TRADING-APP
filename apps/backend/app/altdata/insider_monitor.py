"""Insider Reference Monitor — reference-only context surface (NOT a signal).

Product status: Reference-only / Context Surface. Research status: INSIDER-001 rejected
(beta-not-alpha); INSIDER-002 reserved. Order-path status: prohibited — ``insider_buy`` is a
``rejected_reference_only`` event type (see ``app.altdata.reference_only``); this module is
display-side only and must never be imported by ranking, sizing, or order-path code.

Plan: ``docs/implementation/TradingWorkbench_InsiderReferenceMonitor_ImplementationPlan_v0.1.md``
(v1.0 frozen 2026-07-09). Enrichment is computed at READ time and never persisted — there is
deliberately no place a "conviction score" could accrete. Rows sort by ``filed_at`` DESC only
(freshness); value/cluster/role/%-mktcap/%-ADV are display context, never ordering keys.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.altdata.events.store import EventStore

logger = structlog.get_logger(__name__)

MONITOR_EVENT_TYPE = "insider_buy"  # already in REFERENCE_ONLY_PROGRAMS (INSIDER-001, rejected)
INSIDER_MONITOR_USER_ID = 3  # owning identity ONLY (plan OQ1) — account 3 never orders here

EVIDENCE_NOTE = (
    "Reference Only — INSIDER-001 found no standalone residual alpha. "
    "Not a validated trading signal. Not used for ranking, sizing, or orders."
)
EVIDENCE_DOC = "docs/implementation/evidence/insider_001_s4_reproduction/"

# The sibling app's 134 survivorship-checked small/mid-caps — the DEGRADED-mode universe when the
# factor store is unreadable (the monitor degrades, never breaks). Kept sorted for a stable hash.
FALLBACK_UNIVERSE: tuple[str, ...] = (
    "ABCB", "ACAD", "ADC", "AIT", "AMPH", "AMPY", "ANIP", "AR", "ARWR", "ATKR", "AUB", "BANR",
    "BCC", "BJ", "BLDR", "BOKF", "BOOT", "BRY", "CADE", "CAKE", "CATY", "CBRL", "CBSH", "CDNA",
    "CFG", "CFR", "CHRD", "CIVI", "CMA", "CMC", "CMP", "COLB", "COLL", "CPRX", "CRC", "CRL",
    "CROX", "DIN", "DMLP", "EBC", "EGP", "ESTE", "FELE", "FFBC", "FFIN", "FHB", "FIBK", "FITB",
    "FIVE", "FNB", "FND", "FOLD", "FORM", "FRME", "FULT", "GBCI", "GES", "GGG", "GPOR", "GTLS",
    "HALO", "HAYN", "HBAN", "HOPE", "HRMY", "HWC", "INDB", "IRTC", "KBR", "KEY", "KOS", "LKFN",
    "LNTH", "LSCC", "MEDP", "MKSI", "MLI", "MTB", "MTDR", "MTRN", "MUR", "NBTB", "NEOG", "NOG",
    "NOVT", "NPO", "NSA", "ONB", "ONTO", "OSK", "OZK", "PB", "PCRX", "PLNT", "PNFP", "POWI",
    "PPBI", "PR", "REPX", "REXR", "RF", "RNST", "ROAD", "ROCK", "RRC", "SASR", "SFBS", "SHAK",
    "SHOO", "SKX", "SLAB", "SM", "SNV", "STAG", "STBA", "SUPN", "SXI", "TALO", "TOWN", "TRMK",
    "TWST", "TXRH", "UCBI", "VLY", "VTLE", "WAFD", "WAL", "WBS", "WCC", "WING", "WSFS", "WTFC",
    "YETI", "ZION",
)

_UNIVERSE_CAP = 1500          # plan OQ2 (option B)
_DV_LOOKBACK_DAYS = 30        # trailing dollar-volume ranking window
_LARGE_CAP_FLOOR = 50e9       # exclude mega-caps: the monitor is a small/mid-cap surface
_CLUSTER_WINDOW_DAYS = 14
_MANIFEST_DIRNAME = "insider_monitor"


# ---------------------------------------------------------------- universe + weekly manifest


def _manifest_dir(data_dir: str | Path = "data") -> Path:
    return Path(data_dir) / _MANIFEST_DIRNAME


def resolve_monitor_universe(factor_store: Any, *, as_of: date, cap: int = _UNIVERSE_CAP,
                             ) -> tuple[list[str], str]:
    """(tickers, inclusion_reason) — the small/mid-cap monitor universe from the PIT factor
    store, or the vendored 134-name fallback when the store is unreadable (logged loudly)."""
    try:
        dv = factor_store.dollar_volume_universe(as_of, cap * 2, _DV_LOOKBACK_DAYS)
        # small/mid filter: drop names with a known marketcap above the mega-cap floor; a name
        # with NO marketcap row stays (small-caps are exactly where metrics are sparse).
        rows = factor_store.con.execute(
            "SELECT ticker, max(marketcap) FROM metrics WHERE ticker IN "
            f"({','.join('?' * len(dv))}) GROUP BY ticker", dv,
        ).fetchall()
        too_big = {t for t, mc in rows if mc is not None and mc > _LARGE_CAP_FLOOR}
        tickers = [t for t in dv if t not in too_big][:cap]
        if tickers:
            return tickers, f"smallmid-dv-rank<={cap}"
    except Exception:  # noqa: BLE001 — degrade to the fallback, never break the monitor
        logger.warning("insider_monitor_universe_fallback", reason="factor store unreadable")
    return list(FALLBACK_UNIVERSE), "fallback-134"


def write_universe_manifest(tickers: list[str], *, inclusion_reason: str, as_of: date,
                            cik_by_ticker: dict[str, int] | None = None,
                            company_by_ticker: dict[str, str] | None = None,
                            data_dir: str | Path = "data") -> Path:
    """Persist the weekly monitor-universe manifest (plan §4.2a, owner-required control):
    coverage must be auditable and reproducible. The fallback path writes a manifest too."""
    d = _manifest_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": as_of.isoformat(),
        "source_universe": (
            f"factor_store.dollar_volume_universe(smallmid, cap={_UNIVERSE_CAP})"
            if inclusion_reason != "fallback-134" else "vendored sibling 134-name survivors"
        ),
        "count": len(tickers),
        "hash": hashlib.sha256(",".join(sorted(tickers)).encode()).hexdigest(),
        "rows": [
            {
                "ticker": t,
                "cik": (cik_by_ticker or {}).get(t),
                "company": (company_by_ticker or {}).get(t),
                "inclusion_reason": inclusion_reason,
            }
            for t in tickers
        ],
    }
    path = d / f"universe_manifest_{as_of.isoformat()}.json"
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    logger.info("insider_monitor_manifest_written", path=str(path), count=len(tickers),
                inclusion_reason=inclusion_reason)
    return path


def load_latest_manifest(data_dir: str | Path = "data") -> dict[str, Any] | None:
    d = _manifest_dir(data_dir)
    if not d.exists():
        return None
    files = sorted(d.glob("universe_manifest_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt manifest reads as absent
        logger.warning("insider_monitor_manifest_unreadable", path=str(files[-1]))
        return None


def manifest_is_fresh(manifest: dict[str, Any] | None, *, today: date, max_age_days: int = 7,
                      ) -> bool:
    if not manifest:
        return False
    try:
        return (today - date.fromisoformat(manifest["date"])).days < max_age_days
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- read-time reference rows


@dataclass(frozen=True)
class InsiderReferenceRow:
    """One display row. ``reference_only`` is ALWAYS True — test-pinned. Context fields
    (value / cluster / role / pct_*) are never ordering keys; sorting is filed_at DESC only."""

    ticker: str
    company: str | None
    insider_name: str | None
    insider_role: str  # "officer: <title>" | "director" | "10% owner" | "insider"
    transaction_type: str  # "P" (open-market purchase) only in v1
    transaction_date: str | None  # ISO date
    filing_date: str | None
    filed_at: str  # ISO datetime — the PIT anchor and the ONLY sort key
    transaction_value: float | None
    open_market: bool
    cluster_count: int
    pct_of_marketcap: float | None
    pct_of_adv: float | None
    sector: str | None
    size_bucket: str | None  # "micro" | "small" | "mid" | "large" | None
    freshness_hours: float
    reference_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _role_label(payload: dict[str, Any]) -> str:
    """Role CONTEXT label (plan wording rule: role context, never a weighting/score input)."""
    if payload.get("is_officer"):
        title = (payload.get("officer_title") or "").strip()
        return f"officer: {title}" if title else "officer"
    if payload.get("is_director"):
        return "director"
    if payload.get("is_ten_percent_owner"):
        return "10% owner"
    return "insider"


def _size_bucket(marketcap: float | None) -> str | None:
    if marketcap is None:
        return None
    if marketcap < 300e6:
        return "micro"
    if marketcap < 2e9:
        return "small"
    if marketcap < 10e9:
        return "mid"
    return "large"


def _context_maps(factor_store: Any, tickers: list[str]) -> tuple[dict, dict, dict]:
    """(marketcap, adv_20d_dollar, sector) per ticker — best-effort; empty maps on any failure
    (an event on a name outside the factor store still displays, just without the context)."""
    if not tickers:
        return {}, {}, {}
    ph = ",".join("?" * len(tickers))
    mcap: dict[str, float] = {}
    adv: dict[str, float] = {}
    sector: dict[str, str] = {}
    try:
        for t, mc in factor_store.con.execute(
            f"SELECT ticker, max(marketcap) FROM metrics WHERE ticker IN ({ph}) GROUP BY ticker",
            tickers,
        ).fetchall():
            if mc is not None:
                mcap[t] = float(mc)
        for t, a in factor_store.con.execute(
            f"""SELECT ticker, avg(close * volume) FROM (
                    SELECT ticker, close, volume,
                           row_number() OVER (PARTITION BY ticker ORDER BY date DESC) rn
                    FROM sep WHERE ticker IN ({ph})
                ) WHERE rn <= 20 GROUP BY ticker""",
            tickers,
        ).fetchall():
            if a is not None:
                adv[t] = float(a)
        for t, s in factor_store.con.execute(
            f"SELECT ticker, sector FROM tickers WHERE ticker IN ({ph})", tickers
        ).fetchall():
            if s:
                sector[t] = str(s)
    except Exception:  # noqa: BLE001 — context is optional, never fatal
        logger.warning("insider_monitor_context_unavailable")
    return mcap, adv, sector


def recent_reference_rows(
    events_store: EventStore, factor_store: Any, *,
    window_days: int = 14, min_value: float = 10_000.0, open_market_only: bool = True,
    now: datetime | None = None,
) -> list[InsiderReferenceRow]:
    """The display rows: recent ``insider_buy`` events, enriched at read time, sorted by
    ``filed_at`` DESC ONLY. ``min_value`` / ``open_market_only`` are display hygiene (plan
    wording rule), not selection."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=window_days)
    events = [e for e in events_store.events_filed_since(cutoff, event_type=MONITOR_EVENT_TYPE)
              if e.ticker]

    # cluster context: distinct insiders per ticker over the trailing cluster window
    cluster_events = events_store.events_filed_since(
        now - timedelta(days=_CLUSTER_WINDOW_DAYS), event_type=MONITOR_EVENT_TYPE
    )
    cluster: dict[str, set[str]] = {}
    for ev in cluster_events:
        if ev.ticker:
            cluster.setdefault(ev.ticker, set()).add(
                str(ev.payload.get("owner_name") or ev.accession)
            )

    mcap, adv, sector = _context_maps(
        factor_store, sorted({e.ticker for e in events if e.ticker})
    )

    rows: list[InsiderReferenceRow] = []
    for ev in events:
        ticker = ev.ticker
        if ticker is None:  # filtered above; re-narrowed here for the type checker
            continue
        p = ev.payload
        value = p.get("buy_value")
        value_f = float(value) if value is not None else None
        if value_f is not None and value_f < min_value:
            continue  # display hygiene only
        if open_market_only and p.get("form_type") not in ("4", "4/A"):
            continue
        filed = ev.filed_at if ev.filed_at.tzinfo else ev.filed_at.replace(tzinfo=UTC)
        mc = mcap.get(ticker)
        a = adv.get(ticker)
        rows.append(InsiderReferenceRow(
            ticker=ticker,
            company=p.get("issuer_name"),
            insider_name=p.get("owner_name"),
            insider_role=_role_label(p),
            transaction_type="P",
            transaction_date=ev.event_date.isoformat() if ev.event_date else None,
            filing_date=filed.date().isoformat(),
            filed_at=filed.isoformat(),
            transaction_value=value_f,
            open_market=True,
            cluster_count=len(cluster.get(ticker, set())) or 1,
            pct_of_marketcap=(value_f / mc * 100.0) if (value_f and mc) else None,
            pct_of_adv=(value_f / a * 100.0) if (value_f and a) else None,
            sector=sector.get(ticker),
            size_bucket=_size_bucket(mc),
            freshness_hours=max(0.0, (now - filed).total_seconds() / 3600.0),
        ))
    rows.sort(key=lambda r: r.filed_at, reverse=True)  # freshness ONLY — never value/cluster/role
    return rows
