"""Store-backed PIT adapter: DuckDB file or Parquet export -> identity map -> monthly universe.

BUILD scope, synthetic-tested. It reads whatever snapshot it is handed, read-only; whether a
real snapshot may be used is decided by the governance capability on the value-reading entry
points, not by this module.

Grain. The live factor store keys ``tickers`` on ``ticker`` (``INSERT OR REPLACE``), so a ticker
reused by two issuers collapses to one row there and reuse becomes unobservable. The adapter
therefore reports ``one_row_per_ticker``: when true the table cannot show reuse, and "no reuse
found" must not be read as "no reuse exists". An export of the raw vendor TICKERS rows is the
input that makes the identity audit meaningful.

Identity. SEP rows are attributed to an issuer by ``(ticker, date)`` through the identity map's
effective intervals, never by ticker string alone. Rows that cannot be attributed, or that land
in an overlap, are counted and left out of selection; they are reported, never silently kept.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from app.research.range002.data.identity_map import (
    RESOLVED,
    IdentityMap,
    IdentityRecord,
    build_identity_map,
    permaticker_on,
)
from app.research.range002.data.manifest import REQUIRED_COLUMNS
from app.research.range002.data.pit_universe import (
    BASIS_SPLIT_ADJUSTED,
    DailyObs,
    Listing,
    UniverseMonth,
    UniverseParams,
    build_universe_month,
)
from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import (
    DataDefectError,
    ParamsUnsetError,
    SpecBindingError,
)
from app.research.range002.spec.loader import spec_sha256
from app.research.range002.spec.schema import DraftSpec

PURE_FUNCTIONS = ("open_snapshot", "load_identity_records", "load_listings")

_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


class SnapshotError(ValueError):
    """The snapshot cannot support the PIT logic (missing table/column, ambiguous grain)."""


@dataclass(frozen=True)
class IdentityLoad:
    records: tuple[IdentityRecord, ...]
    refused: tuple[tuple[str, str, str], ...]  # (ticker, permaticker, reason)
    source_rows: int
    duplicate_rows_collapsed: int
    one_row_per_ticker: bool


@dataclass(frozen=True)
class ObsLoad:
    observations: tuple[DailyObs, ...]
    unattributed_rows: int
    ambiguous_rows: int
    duplicate_after_attribution: int


@dataclass(frozen=True)
class MonthBuild:
    universe: UniverseMonth
    identity: IdentityLoad
    observations: ObsLoad
    #: "PIT_FULL" is the registered N-name point-in-time universe. Anything else names the scope
    #: amendment under which a RESTRICTED exploratory universe was built; such a build is not the
    #: original PIT strategy test and must be reported as exploratory.
    scope: str


def _q(name: str) -> str:
    if not _NAME.match(name):
        raise SnapshotError(f"refusing unsafe identifier {name!r}")
    return f'"{name}"'


def open_snapshot(root: Path) -> duckdb.DuckDBPyConnection:
    """Open a ``.duckdb`` file read-only, or a directory of Parquet exports as views.

    A directory holds ``<table>.parquet`` or ``<table>/*.parquet`` for every required table.
    Declared columns are checked; a missing table or column refuses the snapshot.
    """
    if root.suffix == ".duckdb":
        con = duckdb.connect(str(root), read_only=True)
    else:
        con = duckdb.connect(":memory:")
        for table, _ in REQUIRED_COLUMNS:
            single, many = root / f"{table}.parquet", root / table
            pattern = (
                str(single) if single.suffix and _has(con, single) else str(many / "*.parquet")
            )
            safe = pattern.replace("'", "''")
            try:
                con.execute(f"CREATE VIEW {_q(table)} AS SELECT * FROM read_parquet('{safe}')")
                con.execute(f"SELECT * FROM {_q(table)} LIMIT 0")
            except duckdb.Error as exc:
                raise SnapshotError(f"required table {table!r} not readable: {exc}") from exc
    for table, required in REQUIRED_COLUMNS:
        try:
            have = {
                r[0].lower()
                for r in con.execute(f"SELECT column_name FROM (DESCRIBE {_q(table)})").fetchall()
            }
        except duckdb.Error as exc:
            raise SnapshotError(f"required table {table!r} not readable: {exc}") from exc
        missing = [c for c in required if c not in have]
        if missing:
            raise SnapshotError(f"table {table!r} lacks required column(s) {missing}")
    return con


def _has(con: duckdb.DuckDBPyConnection, path: Path) -> bool:
    try:
        con.execute("SELECT 1 FROM read_parquet(?) LIMIT 0", [str(path)])
        return True
    except duckdb.Error:
        return False


def _table_filter_sql(con: Any, table_filter: str | None) -> tuple[str, list[Any]]:
    cols = {
        r[0].lower() for r in con.execute('SELECT column_name FROM (DESCRIBE "tickers")').fetchall()
    }
    if "table" in cols:
        if not table_filter:
            raise SnapshotError(
                "tickers carries a vendor `table` column: pass table_filter explicitly "
                "(rows of different vendor tables have different intervals)"
            )
        return ' WHERE "table" = ?', [table_filter]
    return "", []


def _is_delisted(v: Any) -> bool | None:
    if v is None:
        return None
    return str(v).strip().upper() in ("Y", "TRUE", "T", "1")


def load_identity_records(con: Any, *, table_filter: str | None) -> IdentityLoad:
    where, args = _table_filter_sql(con, table_filter)
    rows = con.execute(
        "SELECT CAST(permaticker AS VARCHAR), ticker, firstpricedate, lastpricedate, isdelisted "
        f'FROM "tickers"{where}',
        args,
    ).fetchall()
    seen: set[tuple[str, str, date, date | None]] = set()
    records: list[IdentityRecord] = []
    refused: list[tuple[str, str, str]] = []
    dupes = 0
    for perma, ticker, first, last, delisted in rows:
        p, t = (perma or "").strip(), (ticker or "").strip()
        if not p or not t:
            refused.append((t, p, "BLANK_IDENTIFIER"))
            continue
        if first is None:
            refused.append((t, p, "NO_FIRST_PRICE_DATE"))
            continue
        gone = _is_delisted(delisted)
        end = last if gone else None  # a live name's interval is open, not frozen at ingest day
        if gone and end is None:
            refused.append((t, p, "DELISTED_WITHOUT_LAST_PRICE_DATE"))
            continue
        if end is not None and first > end:
            refused.append((t, p, "INVERTED_INTERVAL"))
            continue
        key = (p, t, first, end)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        records.append(IdentityRecord(p, t, first, end))
    distinct = len({r[1] for r in rows if r[1]})
    return IdentityLoad(tuple(records), tuple(refused), len(rows), dupes, len(rows) == distinct)


def load_listings(
    con: Any, *, table_filter: str | None, common_stock_categories: Collection[str]
) -> tuple[Listing, ...]:
    where, args = _table_filter_sql(con, table_filter)
    rows = con.execute(
        "SELECT CAST(permaticker AS VARCHAR), category, firstpricedate, lastpricedate, isdelisted "
        f'FROM "tickers"{where}',
        args,
    ).fetchall()
    latest: dict[str, tuple[date, str | None, date | None, bool | None]] = {}
    for perma, category, first, last, delisted in rows:
        p = (perma or "").strip()
        if not p or first is None:
            continue
        if p not in latest or first >= latest[p][0]:
            latest[p] = (first, category, last, _is_delisted(delisted))
    return tuple(
        Listing(p, (cat or "") in common_stock_categories, last if gone else None)
        for p, (_, cat, last, gone) in sorted(latest.items())
    )


@requires_capability
def load_observations(
    capability: object,
    con: Any,
    idmap: IdentityMap,
    *,
    window_start: date,
    decision_day: date,
    basis: str,
) -> ObsLoad:
    if basis != BASIS_SPLIT_ADJUSTED:
        raise SnapshotError(f"basis must be {BASIS_SPLIT_ADJUSTED!r}")
    rows = con.execute(
        'SELECT ticker, date, close, closeunadj, volume FROM "sep" WHERE date BETWEEN ? AND ?',
        [window_start, decision_day],
    ).fetchall()
    out: dict[tuple[str, date], DailyObs] = {}
    clash: set[tuple[str, date]] = set()
    unattributed = ambiguous = 0
    for ticker, day, close, close_unadj, volume in rows:
        res = permaticker_on(idmap, ticker, day)
        if res.status != RESOLVED or res.value is None:
            if res.status == "NO_MAPPING":
                unattributed += 1
            else:
                ambiguous += 1
            continue
        key = (res.value, day)
        if key in out:
            clash.add(key)
            continue
        out[key] = DailyObs(res.value, day, close, close_unadj, volume, basis)
    for key in clash:
        del out[key]
    ordered = tuple(out[k] for k in sorted(out))
    return ObsLoad(ordered, unattributed, ambiguous, len(clash))


def _prior_trading_day(con: Any, month_start: date) -> date:
    row = con.execute('SELECT MAX(date) FROM "sep" WHERE date < ?', [month_start]).fetchone()
    if row is None or row[0] is None:
        raise SnapshotError(f"no SEP session before {month_start}")
    return row[0]


@requires_capability
def build_month_from_store(
    capability: object,
    con: Any,
    month_start: date,
    params: UniverseParams,
    *,
    table_filter: str | None,
    common_stock_categories: Iterable[str],
    lookback_calendar_days: int,
    raw_vendor_rows_attested: bool,
    exploratory_scope_amendment_id: str | None,
) -> MonthBuild:
    rng = getattr(capability, "date_range", None)
    if rng is None or not (rng.start <= month_start <= rng.end):
        raise DataDefectError(f"month {month_start} is outside the authorised date range")
    if lookback_calendar_days < params.adv_window:
        raise SnapshotError("lookback_calendar_days is shorter than adv_window")
    ident = load_identity_records(con, table_filter=table_filter)
    has_table_col = any(
        r[0].lower() == "table"
        for r in con.execute('SELECT column_name FROM (DESCRIBE "tickers")').fetchall()
    )
    grain_ok = has_table_col or raw_vendor_rows_attested or not ident.one_row_per_ticker
    scope = "PIT_FULL"
    if not grain_ok:
        # One row per ticker and no vendor `table` column: the shape of the live store, where
        # PRIMARY KEY(ticker) + INSERT OR REPLACE collapses a reused ticker to one issuer.
        # Historical membership cannot be shown survivorship-safe from it.
        if not exploratory_scope_amendment_id:
            raise SnapshotError(
                "DATA-INTEGRITY BLOCKER: tickers has one row per ticker and no vendor `table` "
                "column, so ticker reuse is unobservable and PIT membership cannot be shown "
                "survivorship-safe. Supply retained raw vendor TICKERS rows, or build a "
                "restricted exploratory universe under an explicit scope amendment id."
            )
        scope = f"EXPLORATORY_RESTRICTED:{exploratory_scope_amendment_id}"
    idmap = build_identity_map(ident.records)
    decision_day = _prior_trading_day(con, month_start)
    obs = load_observations(
        capability,
        con,
        idmap,
        window_start=decision_day - timedelta(days=lookback_calendar_days),
        decision_day=decision_day,
        basis=params.basis,
    )
    listings = load_listings(
        con, table_filter=table_filter, common_stock_categories=frozenset(common_stock_categories)
    )
    universe = build_universe_month(
        month_start, decision_day, listings, obs.observations, idmap, params
    )
    return MonthBuild(universe, ident, obs, scope)


@requires_capability
def universe_params_from_draft(
    capability: object, draft: DraftSpec, *, basis: str
) -> UniverseParams:
    """Universe parameters from the frozen spec (Plan v0.5 section 2.1): ``universe.n`` (P0, may
    be null), ``universe.min_price`` and ``universe.adv_window_days`` (schema-pinned to 10.0 and
    20). Nothing is a literal here, and a null ``n`` fails closed."""
    if spec_sha256(draft) != getattr(capability, "spec_sha256", None):
        raise SpecBindingError("draft spec hash differs from the capability's spec hash")
    u = draft.universe
    if u.n is None:
        raise ParamsUnsetError("universe.n is null (P0 decision D03)")
    return UniverseParams(
        n=int(u.n), adv_window=int(u.adv_window_days), min_price=float(u.min_price), basis=basis
    )
