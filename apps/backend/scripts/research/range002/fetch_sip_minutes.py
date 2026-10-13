#!/usr/bin/env python3
"""RANGE-002 bounded SIP minute-bar fetch (personal research use).

Single governed command (placeholders; every scope argument is required, none has a default):

    python scripts/research/range002/fetch_sip_minutes.py \\
        --mode store            # dry-plan | counts-only | store
        --spec FROZEN_SPEC.json --registry RUNS.jsonl --exposure-ledger LEDGER.md \\
        --partition DEVELOPMENT_SELECTION --code-sha <40-hex> \\
        --universe-file SYMBOLS.txt --date-from YYYY-MM-DD --date-to YYYY-MM-DD --asof YYYY-MM-DD|- \\
        --key-env NAME_OF_KEY_VAR --secret-env NAME_OF_SECRET_VAR \\
        --requests-per-minute N --max-requests M \\
        --out-store MINUTES.duckdb --journal JOURNAL.jsonl \\
        --authorization-id ID --permitted-use-ref REF --entitlement-ref REF \\
        --permission-basis-claimed "free text" --storage-permitted

What it does: for each symbol and each calendar-month window, GET the Alpaca stock bars endpoint
(timeframe 1Min, feed sip, adjustment raw, explicit asof) page by page, validate every page in
``fetch_adapter.fetch_symbol_window`` (strictly increasing timestamps, inside the window, repeated
page token = defect, feed/adjustment pinned) and write the RAW bars, extended hours included, into
``minute_bars(symbol, ts, open, high, low, close, volume, basis)`` with ``basis = 'raw'`` -- exactly
the table ``run_descriptive_screen`` reads. Regular-session filtering is the loader's job
(``bar_loader.load_session`` filters by America/New_York session), so nothing is dropped here.

Modes. ``dry-plan``: no network, no capability, no store; prints the symbol x window plan and the
request arithmetic. ``counts-only``: fetches, stores NOTHING, prints bar counts per symbol-day and
the timestamp-convention evidence. ``store``: also writes the store, resumably.

Governance. ``counts-only`` and ``store`` need a results-guard capability (the adapter's gates are
intact). It is obtained exactly as the descriptive runner does (frozen spec with an approved
decision covering ``run``, run registry row, exposure ledger, holdout excluded). NOTE: under the
P3A partition issuing the capability consumes one of the pre-registered attempts; that is a
governance property of the guard, not something this tool can avoid.

Resume. The journal is JSONL, one line per COMPLETED symbol-window, appended after the window's
rows are committed. A window's rows are deleted and re-inserted inside one transaction, so a crash
between commit and journal append re-fetches that window without double rows. A journal and store
that disagree about existence, or a journal whose header differs from this invocation, are refused.

Secrets. Credentials are read from the environment variables NAMED on the command line. Values
are never printed, logged, journaled or put into the manifest or any exception text.

Output. Beside the store: ``<store>.fetch_manifest.json`` (per-window request/bar counts, min/max
timestamps, page-token counts, extraction time, tool version and script sha256, store sha256,
license_status UNKNOWN, PU-1 sidecar for ``alpaca_market_data``, ``permission_basis_claimed`` and
``permission_verified: false``) and ``<store>.convention_days.jsonl`` (per symbol-day first bar in
UTC and ET, first/last regular-session bar, volumes of the 09:30/15:59/16:00 ET bars).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb  # noqa: E402

from app.licensing.envelope import write_sidecar  # noqa: E402
from app.research.range002.data.alpaca_transport import (  # noqa: E402
    MAX_LIMIT,
    AlpacaTransportConfig,
    TransportError,
)
from app.research.range002.data.fetch_adapter import (  # noqa: E402
    REQUIRED_ADJUSTMENT,
    REQUIRED_FEED,
    FetchAuthorization,
    PageRequest,
    PageResponse,
    RawBar,
    fetch_symbol_window,
    store_fetched_bars,
    vendor_transport,
)
from app.research.range002.screen.errors import DataDefectError  # noqa: E402
from app.research.range002.spec.hashing import file_sha256  # noqa: E402

TOOL_VERSION = "fetch_sip_minutes/0.1"
MANIFEST_SCHEMA = "range002.sip_minutes_fetch_manifest.v1"
JOURNAL_SCHEMA = "range002.sip_minutes_fetch_journal.v1"
LICENSE_SOURCES: tuple[str, ...] = ("alpaca_market_data",)
BARS_PER_DAY_EXTENDED_MAX = 960  # 04:00-20:00 ET, one bar per minute
MODES = ("dry-plan", "counts-only", "store")

EXIT_OK = 0
EXIT_REFUSED = 2

_ET = ZoneInfo("America/New_York")
_OPEN, _CLOSE = time(9, 30), time(16, 0)
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

# governance partitions this tool may name (same mapping as the descriptive runner)
_PARTITIONS = ("DEVELOPMENT_SELECTION", "REPLAY_RNG001")


class FetchRefusal(RuntimeError):
    """A precondition of this command is not met; nothing was fetched or written."""


# --------------------------------------------------------------------------- plan


def read_universe(path: Path) -> tuple[str, ...]:
    """One symbol per line; blank lines and ``#`` comments ignored; duplicates are refused."""
    out: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if not _SYMBOL.match(s):
            raise FetchRefusal(f"{path.name}:{n}: not a plain upper-case symbol")
        out.append(s)
    if not out:
        raise FetchRefusal("the universe file holds no symbols")
    if len(set(out)) != len(out):
        raise FetchRefusal("the universe file lists a symbol twice")
    return tuple(out)


def _et_midnight_utc(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=_ET).astimezone(UTC).replace(tzinfo=None)


def month_windows(d0: date, d1: date) -> list[tuple[date, date]]:
    """Calendar-month segments covering ``[d0, d1]`` inclusive."""
    if d0 > d1:
        raise FetchRefusal("date-from is after date-to")
    out: list[tuple[date, date]] = []
    cur = d0
    while cur <= d1:
        nxt = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
        out.append((cur, min(nxt - timedelta(days=1), d1)))
        cur = nxt
    return out


def build_chunks(
    symbols: Sequence[str], d0: date, d1: date
) -> list[tuple[str, datetime, datetime]]:
    """``(symbol, start_utc, end_utc)`` per symbol per month; ET-midnight aligned, naive UTC."""
    wins = month_windows(d0, d1)
    return [
        (sym, _et_midnight_utc(a), _et_midnight_utc(b + timedelta(days=1)))
        for sym in symbols
        for a, b in wins
    ]


def _weekdays(a: date, b: date) -> int:
    return sum(1 for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def plan(symbols: Sequence[str], d0: date, d1: date, limit: int) -> dict[str, Any]:
    wins = month_windows(d0, d1)
    min_requests = len(symbols) * len(wins)
    worst = sum(
        math.ceil(_weekdays(a, b) * BARS_PER_DAY_EXTENDED_MAX / limit) for a, b in wins
    ) * len(symbols)
    return {
        "mode": "dry-plan",
        "symbols": len(symbols),
        "windows_per_symbol": len(wins),
        "windows": [[a.isoformat(), b.isoformat()] for a, b in wins],
        "symbol_windows": min_requests,
        "requests_lower_bound": min_requests,
        "requests_worst_case": worst,
        "formula": (
            "requests = sum over symbol-windows of ceil(bars_in_window / limit); lower bound 1 per "
            f"symbol-window; worst case uses weekdays x {BARS_PER_DAY_EXTENDED_MAX} extended-hours "
            "minutes (04:00-20:00 ET) per window"
        ),
        "limit": limit,
        "network": False,
        "store_writes": False,
    }


# --------------------------------------------------------------------------- evidence


def day_evidence(bars: Sequence[RawBar]) -> list[dict[str, Any]]:
    """Per ET calendar day: counts and the timestamp-convention evidence (no prices)."""
    by_day: dict[date, list[RawBar]] = {}
    for b in bars:
        by_day.setdefault(b.t.replace(tzinfo=UTC).astimezone(_ET).date(), []).append(b)
    rows: list[dict[str, Any]] = []
    for day in sorted(by_day):
        bs = by_day[day]
        et = {b.t: b.t.replace(tzinfo=UTC).astimezone(_ET) for b in bs}
        reg = [b for b in bs if _OPEN <= et[b.t].time() < _CLOSE]

        def vol_at(
            h: int, m: int, _bs: list[RawBar] = bs, _et: dict[datetime, datetime] = et
        ) -> Any:
            hit = [b.v for b in _bs if _et[b.t].time() == time(h, m)]
            return hit[0] if hit else None

        first = bs[0]
        row: dict[str, Any] = {
            "day": day.isoformat(),
            "bars": len(bs),
            "regular_bars": len(reg),
            "first_utc": first.t.isoformat() + "Z",
            "first_et": et[first.t].isoformat(),
            "first_regular_utc": None,
            "first_regular_et": None,
            "last_regular_et": None,
            "volume_0930": vol_at(9, 30),
            "volume_1559": vol_at(15, 59),
            "volume_1600": vol_at(16, 0),
        }
        if reg:
            row["first_regular_utc"] = reg[0].t.isoformat() + "Z"
            row["first_regular_et"] = et[reg[0].t].strftime("%H:%M")
            row["last_regular_et"] = et[reg[-1].t].strftime("%H:%M")
        rows.append(row)
    return rows


def convention_summary(days: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate evidence for 'bars are labelled by interval START'. Evidence, not a verdict."""
    firsts = Counter(d["first_regular_et"] for d in days if d["first_regular_et"])
    lasts = Counter(d["last_regular_et"] for d in days if d["last_regular_et"])
    utc_open = Counter(
        d["first_regular_utc"][11:16] for d in days if d["first_regular_et"] == "09:30"
    )
    with_reg = sum(1 for d in days if d["first_regular_et"])
    return {
        "symbol_days": len(days),
        "symbol_days_with_regular_bars": with_reg,
        "first_regular_minute_et_histogram": dict(sorted(firsts.items())),
        "last_regular_minute_et_histogram": dict(sorted(lasts.items())),
        "days_with_0930_bar": sum(1 for d in days if d["first_regular_et"] == "09:30"),
        "days_with_1559_last_regular_bar": lasts.get("15:59", 0),
        "days_with_1600_bar_volume": sum(1 for d in days if d["volume_1600"] is not None),
        "utc_hhmm_of_0930_et_bar_histogram": dict(sorted(utc_open.items())),
        "expected_if_interval_start": (
            "first regular bar 09:30 ET (13:30 UTC in EST / 14:30 UTC in EDT); last regular bar "
            "15:59 ET (12:59 on early-close days). If labelled by interval END the first regular "
            "bar would read 09:31 and the last 16:00."
        ),
        "caveat": (
            "A bar labelled 16:00 ET also exists after the close (extended hours); the 09:30 / "
            "15:59 histograms and the 09:30 and 16:00 volumes are the discriminating evidence."
        ),
    }


# --------------------------------------------------------------------------- run


@dataclass(frozen=True)
class RunConfig:
    mode: str  # "counts-only" | "store"
    symbols: tuple[str, ...]
    date_from: date
    date_to: date
    asof: str
    limit: int
    max_pages: int
    universe_sha256: str
    requests_per_minute: int
    max_requests: int
    authorization: FetchAuthorization
    permission_basis_claimed: str
    store_path: Path | None
    journal_path: Path | None
    script_sha256: str
    #: optional run binding (spec, baseline, universe, dates, sources, request cap) written
    #: into the journal header: a resume under a different binding is refused
    binding: dict[str, Any] | None = None


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _header(cfg: RunConfig) -> dict[str, Any]:
    return {
        "type": "header",
        "schema": JOURNAL_SCHEMA,
        "universe_sha256": cfg.universe_sha256,
        "symbols": len(cfg.symbols),
        "date_from": cfg.date_from.isoformat(),
        "date_to": cfg.date_to.isoformat(),
        "asof": cfg.asof,
        "feed": REQUIRED_FEED,
        "adjustment": REQUIRED_ADJUSTMENT,
        "limit": cfg.limit,
        **({"binding": cfg.binding} if cfg.binding is not None else {}),
    }


def _load_journal(path: Path, header: dict[str, Any]) -> list[dict[str, Any]]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise FetchRefusal("the journal exists but is empty")
    recs = [json.loads(ln) for ln in lines]
    if recs[0] != header:
        raise FetchRefusal("the journal header differs from this invocation; resume refused")
    chunks = [r for r in recs[1:] if r.get("type") == "chunk"]
    seen = {(c["symbol"], c["chunk_key"]) for c in chunks}
    if len(seen) != len(chunks):
        raise FetchRefusal("the journal lists a window twice")
    return chunks


def _append(path: Path, rec: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True, allow_nan=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _chunk_stats(
    symbol: str,
    key: str,
    bars: Sequence[RawBar],
    pages: int,
    requests_before: int,
    requests_now: int,
) -> dict[str, Any]:
    return {
        "type": "chunk",
        "symbol": symbol,
        "chunk_key": key,
        "pages": pages,
        "http_requests": requests_now - requests_before,
        "page_tokens_followed": max(pages - 1, 0),
        "bars": len(bars),
        "min_ts_utc": bars[0].t.isoformat() + "Z" if bars else None,
        "max_ts_utc": bars[-1].t.isoformat() + "Z" if bars else None,
        "extracted_at_utc": _now_utc(),
    }


def run_fetch(
    capability: object,
    transport: Callable[[PageRequest], PageResponse],
    cfg: RunConfig,
    *,
    http_attempts: Callable[[], int] = lambda: 0,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    """Fetch every window not yet journaled. Returns the manifest (store mode) or the counts
    document (counts-only). Never writes the store in counts-only mode."""
    if cfg.mode not in ("counts-only", "store"):
        raise FetchRefusal(f"run_fetch handles counts-only and store, not {cfg.mode!r}")
    chunks = build_chunks(cfg.symbols, cfg.date_from, cfg.date_to)
    store_mode = cfg.mode == "store"
    started = _now_utc()
    con: Any = None
    done: dict[tuple[str, str], dict[str, Any]] = {}
    journal_keys: set[tuple[str, str]] = set()
    if store_mode:
        if cfg.store_path is None or cfg.journal_path is None:
            raise FetchRefusal("store mode needs --out-store and --journal")
        if not cfg.authorization.storage_permitted:
            raise FetchRefusal("store mode needs --storage-permitted (recorded, not verified)")
        have_s, have_j = cfg.store_path.exists(), cfg.journal_path.exists()
        if have_s != have_j:
            raise FetchRefusal("store and journal must both exist (resume) or both be absent")
        header = _header(cfg)
        if have_j:
            for c in _load_journal(cfg.journal_path, header):
                done[(c["symbol"], c["chunk_key"])] = c
            journal_keys = set(done)
        else:
            _append(cfg.journal_path, header)
        con = duckdb.connect(str(cfg.store_path))
    counts: list[dict[str, Any]] = []
    all_days: list[dict[str, Any]] = []
    try:
        for symbol, start, end in chunks:
            key = f"{start.isoformat()}|{end.isoformat()}"
            if (symbol, key) in done:
                continue
            before = http_attempts()
            res = fetch_symbol_window(
                capability, transport, symbol=symbol, start_utc=start, end_utc=end,
                feed=REQUIRED_FEED, adjustment=REQUIRED_ADJUSTMENT, asof=cfg.asof,
                limit=cfg.limit, max_pages=cfg.max_pages,
            )  # fmt: skip
            stats = _chunk_stats(symbol, key, res.bars, res.pages, before, http_attempts())
            days = day_evidence(res.bars)
            stats["days"] = days
            if store_mode:
                _store_window(capability, con, res, cfg, journal_keys, key, start, end)
                _append(cfg.journal_path, stats)  # type: ignore[arg-type]
                done[(symbol, key)] = stats
            else:
                counts.append(stats)
                all_days.extend({"symbol": symbol, **d} for d in days)
            progress(f"{symbol} {start:%Y-%m-%d}: {len(res.bars)} bars, {res.pages} page(s)")
        if not store_mode:
            return {
                "mode": "counts-only",
                "store_writes": False,
                "started_at_utc": started,
                "symbol_days": [
                    {"symbol": d["symbol"], "day": d["day"], "bars": d["bars"],
                     "regular_bars": d["regular_bars"]}
                    for d in all_days
                ],
                "windows": [{k: v for k, v in c.items() if k != "days"} for c in counts],
                "convention_check": convention_summary(all_days),
            }  # fmt: skip
        assert con is not None and cfg.store_path is not None
        total_rows = con.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
        journal_rows = sum(c["bars"] for c in done.values())
        con.close()
        con = None
        if total_rows != journal_rows:
            raise DataDefectError(
                f"store holds {total_rows} rows but the journal accounts for {journal_rows}"
            )
        return _write_manifest(cfg, done, started, total_rows)
    finally:
        if con is not None:
            con.close()


def _store_window(
    capability: object,
    con: Any,
    res: Any,
    cfg: RunConfig,
    journal_keys: set[tuple[str, str]],
    key: str,
    start: datetime,
    end: datetime,
) -> None:
    """One window, one transaction: delete any partial prior rows, then insert (via the adapter's
    gated writer). The caller appends the journal line after this commits."""
    con.begin()
    try:
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'minute_bars'"
        ).fetchone()[0]
        if exists:
            con.execute(
                "DELETE FROM minute_bars WHERE symbol = ? AND ts >= ? AND ts < ?",
                [res.symbol, start, end],
            )
        store_fetched_bars(
            capability, con, res, authorization=cfg.authorization, journal=journal_keys,
            chunk_key=key,
        )  # fmt: skip
        con.commit()
    except BaseException:
        con.rollback()
        journal_keys.discard((res.symbol, key))
        raise


def _write_manifest(
    cfg: RunConfig, done: dict[tuple[str, str], dict[str, Any]], started: str, total_rows: int
) -> dict[str, Any]:
    assert cfg.store_path is not None
    store = cfg.store_path
    chunks = sorted(done.values(), key=lambda c: (c["symbol"], c["chunk_key"]))
    expected = len(build_chunks(cfg.symbols, cfg.date_from, cfg.date_to))
    complete = len(chunks) == expected
    days_path = store.with_name(store.name + ".convention_days.jsonl")
    day_rows = [{"symbol": c["symbol"], **d} for c in chunks for d in c.get("days", [])]
    with open(days_path, "w", encoding="utf-8", newline="\n") as fh:
        for r in day_rows:
            fh.write(json.dumps(r, sort_keys=True, allow_nan=False) + "\n")
    write_sidecar(days_path, LICENSE_SOURCES)
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "tool": {"version": TOOL_VERSION, "script_sha256": cfg.script_sha256},
        "started_at_utc": started,
        "finished_at_utc": _now_utc(),
        "source": {
            "vendor": "alpaca",
            "host": "data.alpaca.markets",
            "endpoint": "/v2/stocks/{symbol}/bars",
            "timeframe": "1Min",
            "feed": REQUIRED_FEED,
            "adjustment": REQUIRED_ADJUSTMENT,
            "asof": cfg.asof,
            "limit": cfg.limit,
            "requests_per_minute_cap": cfg.requests_per_minute,
            "max_requests_cap": cfg.max_requests,
            "regular_session_filtered": False,
            "timestamp_semantics": "bar START, UTC (vendor documentation claim; see convention_check)",
        },
        "scope": {
            "universe_sha256": cfg.universe_sha256,
            "symbols": len(cfg.symbols),
            "date_from": cfg.date_from.isoformat(),
            "date_to": cfg.date_to.isoformat(),
            "windows_expected": expected,
            "windows_done": len(chunks),
        },
        "authorization": {
            "authorization_id": cfg.authorization.authorization_id,
            "permitted_use_ref": cfg.authorization.permitted_use_ref,
            "entitlement_ref": cfg.authorization.entitlement_ref,
            "storage_permitted_flag": cfg.authorization.storage_permitted,
        },
        "license_status": "UNKNOWN",
        "license_note": "personal-use PU-1 scope; not presentable, not shareable",
        "license_sources": list(LICENSE_SOURCES),
        "permission_basis_claimed": cfg.permission_basis_claimed,
        "permission_verified": False,
        "totals": {
            "http_requests": sum(c["http_requests"] for c in chunks),
            "pages": sum(c["pages"] for c in chunks),
            "page_tokens_followed": sum(c["page_tokens_followed"] for c in chunks),
            "bars": sum(c["bars"] for c in chunks),
            "store_rows": total_rows,
        },
        "windows": [{k: v for k, v in c.items() if k != "days"} for c in chunks],
        "convention_check": convention_summary(day_rows),
        "convention_days": {"path": days_path.name, "sha256": file_sha256(days_path)},
        "store": {
            "path": str(store),
            "table": "minute_bars",
            "basis": REQUIRED_ADJUSTMENT,
            "sha256": file_sha256(store) if complete else None,
        },
    }
    mpath = store.with_name(store.name + ".fetch_manifest.json")
    with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    write_sidecar(mpath, LICENSE_SOURCES)
    if complete:
        write_sidecar(store, LICENSE_SOURCES)
    manifest["manifest_path"] = str(mpath)
    manifest["manifest_sha256"] = file_sha256(mpath)
    return manifest


# --------------------------------------------------------------------------- governance


def _open_capability(
    a: argparse.Namespace, universe_sha: str
) -> tuple[object, Callable[[str], None], Callable[[str], None]]:
    """Same authorization path as the descriptive runner. Returns (capability, complete, abort)."""
    from app.research.range002.governance.exposure_ledger import ExposureLedger
    from app.research.range002.governance.model import DateRange, Partition, Phase
    from app.research.range002.governance.results_guard import authorize
    from app.research.range002.governance.run_registry import RunRegistry, RunStatus
    from app.research.range002.governance.spec_adapter import to_guard_view
    from app.research.range002.spec.loader import load_draft, load_frozen

    table = {
        "DEVELOPMENT_SELECTION": (Phase.P3A, Partition.DEVELOPMENT_SELECTION),
        "REPLAY_RNG001": (Phase.P2, Partition.REPLAY_RNG001),
    }
    phase, part = table[a.partition]
    view = to_guard_view(load_frozen(a.spec))
    draft = load_draft(a.spec)
    ledger = ExposureLedger.from_text(Path(a.exposure_ledger).read_text(encoding="utf-8"))
    registry = RunRegistry(Path(a.registry))
    requested = DateRange(date.fromisoformat(a.date_from), date.fromisoformat(a.date_to))
    if requested.overlaps(view.partitions.holdout):
        raise FetchRefusal("the requested range overlaps the holdout partition")
    run_id = registry.open_run(
        phase=phase,
        spec_sha256=view.spec_sha256,
        code_sha=a.code_sha,
        data_manifest_sha256=universe_sha,
        partition=part,
        seeds={"fetch_no_rng": 0},
        exit_candidates=[c.id for c in draft.exits.candidates or []],
        protected_range=view.partitions.selection if phase is Phase.P3A else None,
    )
    try:
        cap = authorize(
            spec=view, phase=phase, partition=part, run_id=run_id, registry=registry,
            exposure_ledger=ledger, requested_range=requested,
        )  # fmt: skip
    except BaseException:
        registry.close_run(run_id, RunStatus.ABORTED, None)
        raise

    def complete(digest: str) -> None:
        registry.close_run(run_id, RunStatus.COMPLETED, digest)

    def abort(_why: str) -> None:
        state = registry.get_run(run_id)
        if state is not None and state.status is RunStatus.OPEN:
            registry.close_run(run_id, RunStatus.ABORTED, None)

    return cap, complete, abort


# --------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    req = p.add_argument
    req("--mode", required=True, choices=MODES)
    req("--universe-file", required=True, type=Path)
    req("--date-from", required=True)
    req("--date-to", required=True)
    req("--asof", required=True, help="YYYY-MM-DD, or '-' to skip symbol mapping (explicit)")
    req("--limit", type=int, default=MAX_LIMIT, help=f"page size, max {MAX_LIMIT}")
    req("--max-pages", type=int, default=100, help="page cap per symbol-window (fails closed)")
    # network / governance (not needed for dry-plan)
    req("--key-env")
    req("--secret-env")
    req("--requests-per-minute", type=int)
    req("--max-requests", type=int)
    req("--max-retries", type=int, default=5)
    req("--spec", type=Path)
    req("--registry", type=Path)
    req("--exposure-ledger", type=Path)
    req("--partition", choices=_PARTITIONS)
    req("--code-sha")
    req("--authorization-id")
    req("--permitted-use-ref")
    req("--entitlement-ref")
    req("--permission-basis-claimed")
    req("--storage-permitted", action="store_true")
    req("--out-store", type=Path)
    req("--journal", type=Path)
    return p


def _need(a: argparse.Namespace, names: Sequence[str]) -> None:
    missing = [n for n in names if getattr(a, n) in (None, "")]
    if missing:
        raise FetchRefusal(
            "missing required argument(s): "
            + ", ".join("--" + n.replace("_", "-") for n in missing)
        )


def main(argv: list[str] | None = None) -> int:
    a = _build_parser().parse_args(argv)
    try:
        d0, d1 = date.fromisoformat(a.date_from), date.fromisoformat(a.date_to)
        if not 0 < a.limit <= MAX_LIMIT or a.max_pages <= 0:
            raise FetchRefusal(f"limit must be 1..{MAX_LIMIT} and max-pages > 0")
        symbols = read_universe(a.universe_file)
        if a.mode == "dry-plan":
            print(json.dumps(plan(symbols, d0, d1, a.limit), indent=2, sort_keys=True))
            return EXIT_OK
        _need(a, ["key_env", "secret_env", "requests_per_minute", "max_requests", "spec",
                  "registry", "exposure_ledger", "partition", "code_sha", "authorization_id",
                  "permitted_use_ref", "entitlement_ref", "permission_basis_claimed"])  # fmt: skip
        if a.mode == "store":
            _need(a, ["out_store", "journal"])
        if not _HEX40.match(a.code_sha):
            raise FetchRefusal("code-sha must be 40 lowercase hex")
        if a.requests_per_minute <= 0 or a.max_requests <= 0 or a.max_retries < 0:
            raise FetchRefusal("requests-per-minute and max-requests must be positive")
        universe_sha = file_sha256(a.universe_file)
        auth = FetchAuthorization(
            a.authorization_id, a.permitted_use_ref, a.entitlement_ref, bool(a.storage_permitted)
        )
        if a.mode == "store" and not a.storage_permitted:
            raise FetchRefusal("store mode needs --storage-permitted")
        cap, complete, abort = _open_capability(a, universe_sha)
        try:
            transport = vendor_transport(
                cap, auth,
                config=AlpacaTransportConfig(
                    key_env=a.key_env, secret_env=a.secret_env,
                    requests_per_minute=a.requests_per_minute, max_retries=a.max_retries,
                    max_requests=a.max_requests,
                ),
            )  # fmt: skip
            cfg = RunConfig(
                mode=a.mode, symbols=symbols, date_from=d0, date_to=d1, asof=a.asof,
                limit=a.limit, max_pages=a.max_pages, universe_sha256=universe_sha,
                requests_per_minute=a.requests_per_minute, max_requests=a.max_requests,
                authorization=auth, permission_basis_claimed=a.permission_basis_claimed,
                store_path=a.out_store, journal_path=a.journal,
                script_sha256=file_sha256(Path(__file__)),
            )  # fmt: skip
            out = run_fetch(
                cap, transport, cfg,
                http_attempts=transport.__dict__["http_attempts"],
                progress=lambda m: print(m, file=sys.stderr),
            )  # fmt: skip
            digest = (
                out.get("manifest_sha256")
                or hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()
            )
            complete(digest)
        except BaseException as exc:
            abort(type(exc).__name__)
            raise
    except Exception as exc:  # every refusal is reported; values of credentials never appear
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps({k: v for k, v in out.items() if k != "windows"}, indent=2, sort_keys=True))
    return EXIT_OK


# Referenced for type checkers: names re-exported for tests.
__all__ = [
    "FetchRefusal",
    "RunConfig",
    "TransportError",
    "build_chunks",
    "convention_summary",
    "day_evidence",
    "main",
    "month_windows",
    "plan",
    "read_universe",
    "run_fetch",
]

if __name__ == "__main__":
    sys.exit(main())
