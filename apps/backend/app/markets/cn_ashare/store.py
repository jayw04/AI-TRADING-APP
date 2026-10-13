"""The A-share research store: its own DuckDB file, never a US store.

Tables hold provider rows in canonical units, each tagged with its provider and the ingest that
produced it. ``ingest_runs`` carries the full market context (market, exchange, currency, timezone,
provider, price basis), the request parameters, the unit conversion, the source classification and
the SHA-256 of the raw payload, which is cached byte-for-byte under the A-share cache directory.

The store refuses a file name that does not start with ``cn_ashare`` and any context whose market
is not CN_ASHARE, so it cannot be pointed at, or fed from, the US subsystem by mistake.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from app.markets.cn_ashare import MARKET
from app.markets.cn_ashare.providers.base import COLUMNS, Fetched
from app.markets.context import MarketContext, require_market
from app.markets.source_classification import get_source

_BACKEND_ROOT = Path(__file__).resolve().parents[3]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_runs (
  ingest_id VARCHAR PRIMARY KEY, dataset VARCHAR NOT NULL, provider VARCHAR NOT NULL,
  market VARCHAR NOT NULL, exchange VARCHAR NOT NULL, currency VARCHAR NOT NULL,
  timezone VARCHAR NOT NULL, price_basis VARCHAR NOT NULL, params_json VARCHAR NOT NULL,
  units_json VARCHAR NOT NULL, source_class_json VARCHAR NOT NULL, fetched_at_utc VARCHAR NOT NULL,
  raw_row_count INTEGER NOT NULL, row_count INTEGER NOT NULL, payload_sha256 VARCHAR NOT NULL,
  payload_path VARCHAR NOT NULL, sample_label VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS securities (
  provider VARCHAR, symbol VARCHAR, name VARCHAR, exchange VARCHAR, board VARCHAR,
  list_date DATE, delist_date DATE, status VARCHAR, ingest_id VARCHAR
);
CREATE TABLE IF NOT EXISTS trade_calendar (
  provider VARCHAR, exchange VARCHAR, cal_date DATE, is_open BOOLEAN, ingest_id VARCHAR
);
CREATE TABLE IF NOT EXISTS daily_bars (
  provider VARCHAR, symbol VARCHAR, trade_date DATE, open DOUBLE, high DOUBLE, low DOUBLE,
  close DOUBLE, pre_close DOUBLE, volume_shares DOUBLE, amount_cny DOUBLE, trade_status INTEGER,
  is_st BOOLEAN, market VARCHAR, currency VARCHAR, price_basis VARCHAR, ingest_id VARCHAR
);
CREATE TABLE IF NOT EXISTS adj_factors (
  provider VARCHAR, symbol VARCHAR, trade_date DATE, factor DOUBLE, factor_kind VARCHAR,
  ingest_id VARCHAR
);
CREATE TABLE IF NOT EXISTS research_runs (
  run_id VARCHAR PRIMARY KEY, created_at_utc VARCHAR NOT NULL, candidate_id VARCHAR NOT NULL,
  market_context_json VARCHAR NOT NULL, sample_label VARCHAR NOT NULL,
  ingest_ids_json VARCHAR NOT NULL, report_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS crosscheck_runs (
  crosscheck_id VARCHAR PRIMARY KEY, created_at_utc VARCHAR NOT NULL, providers_json VARCHAR NOT NULL,
  all_explained BOOLEAN NOT NULL, report_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS data_issues (
  issue_id VARCHAR PRIMARY KEY, created_at_utc VARCHAR NOT NULL, severity VARCHAR NOT NULL,
  kind VARCHAR NOT NULL, provider VARCHAR, dataset VARCHAR, detail VARCHAR NOT NULL,
  source_ref VARCHAR, resolved BOOLEAN NOT NULL DEFAULT FALSE
);
"""

#: Issue severities. A BLOCKER means the affected data must not be used until it is resolved.
SEVERITIES = ("BLOCKER", "WARNING")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_TABLE = {"securities": "securities", "trade_calendar": "trade_calendar", "daily": "daily_bars",
          "adj_factor": "adj_factors"}  # fmt: skip


class StoreRefusal(ValueError):
    pass


def resolve(raw: str | Path) -> Path:
    p = Path(raw).expanduser()
    return p if p.is_absolute() else _BACKEND_ROOT / p


def _canonical_json(obj: Any) -> bytes:
    def default(o: Any) -> Any:
        if isinstance(o, date | datetime):
            return o.isoformat()
        if hasattr(o, "item"):  # numpy scalars
            return o.item()
        return str(o)

    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), default=default, ensure_ascii=False
    ).encode("utf-8")


class CnAshareStore:
    def __init__(
        self, db_path: str | Path, cache_dir: str | Path, *, read_only: bool = False
    ) -> None:
        path = resolve(db_path)
        if not path.name.startswith("cn_ashare"):
            raise StoreRefusal(
                f"refusing {path.name}: the A-share store file must start with 'cn_ashare'"
            )
        self.path = path
        self.cache_dir = resolve(cache_dir)
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path), read_only=read_only)
        if not read_only:
            self.con.execute(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> CnAshareStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes --------------------------------------------------------------------------------

    def record(self, fetched: Fetched, ctx: MarketContext, *, sample_label: str) -> str:
        """Cache the raw payload, then insert the normalized rows under one ingest id."""
        require_market(ctx, MARKET)
        if ctx.provider != fetched.provider:
            raise StoreRefusal(
                f"context provider {ctx.provider!r} != fetched provider {fetched.provider!r}"
            )
        ingest_id = f"{fetched.provider}-{fetched.dataset}-{uuid.uuid4().hex[:12]}"
        payload = _canonical_json({"params": fetched.params, "rows": fetched.raw_rows})
        sha = hashlib.sha256(payload).hexdigest()
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in fetched.provider)
        ingest_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in ingest_id)
        cache = self.cache_dir / safe / fetched.dataset / f"{ingest_id}.json.gz"
        cache.parent.mkdir(parents=True, exist_ok=True)
        with gzip.GzipFile(filename=str(cache), mode="wb", mtime=0) as fh:
            fh.write(payload)
        self.con.execute(
            "INSERT INTO ingest_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ingest_id, fetched.dataset, fetched.provider, ctx.market.value, ctx.exchange,
                ctx.currency, ctx.timezone, ctx.price_basis.value,
                _canonical_json(fetched.params).decode(), _canonical_json(fetched.units.as_dict()).decode(),
                _canonical_json(asdict(get_source(fetched.provider))).decode(), fetched.fetched_at_utc,
                len(fetched.raw_rows), len(fetched.rows), sha, str(cache), sample_label,
            ],
        )  # fmt: skip
        cols = list(COLUMNS[fetched.dataset])
        extra: list[str] = []
        if fetched.dataset == "daily":
            extra = ["market", "currency", "price_basis"]
        table = _TABLE[fetched.dataset]
        names = ["provider", *cols, *extra, "ingest_id"]
        marks = ",".join("?" for _ in names)
        values = []
        for r in fetched.rows:
            row = [fetched.provider, *(r[c] for c in cols)]
            if extra:
                row += [ctx.market.value, ctx.currency, ctx.price_basis.value]
            values.append([*row, ingest_id])
        if values:
            self.con.executemany(
                f"INSERT INTO {table} ({','.join(names)}) VALUES ({marks})", values
            )
        return ingest_id

    def record_run(
        self, *, candidate_id: str, ctx: MarketContext, sample_label: str, ingest_ids: list[str],
        report: dict[str, Any],
    ) -> str:  # fmt: skip
        require_market(ctx, MARKET)
        run_id = f"cnrun-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO research_runs VALUES (?,?,?,?,?,?,?)",
            [
                run_id, _now(), candidate_id,
                _canonical_json(ctx.as_dict()).decode(), sample_label,
                _canonical_json(sorted(ingest_ids)).decode(), _canonical_json(report).decode(),
            ],
        )  # fmt: skip
        return run_id

    def record_issue(
        self, *, severity: str, kind: str, detail: str, provider: str | None = None,
        dataset: str | None = None, source_ref: str | None = None,
    ) -> str:  # fmt: skip
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")
        issue_id = f"cnissue-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO data_issues VALUES (?,?,?,?,?,?,?,?,FALSE)",
            [issue_id, _now(), severity, kind, provider, dataset, detail, source_ref],
        )
        return issue_id

    def record_crosscheck(self, report: dict[str, Any]) -> str:
        """Keep the comparison and open one BLOCKER issue per unexplained difference class."""
        crosscheck_id = f"cncross-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO crosscheck_runs VALUES (?,?,?,?,?)",
            [
                crosscheck_id, _now(), _canonical_json(report["providers"]).decode(),
                bool(report["all_explained"]), _canonical_json(report).decode(),
            ],
        )  # fmt: skip
        for cls, count in report["unexplained"].items():
            self.record_issue(
                severity="BLOCKER",
                kind=f"CROSSCHECK_{cls}",
                detail=f"{count} unexplained {cls} between {' and '.join(report['providers'])}",
                dataset="daily",
                source_ref=crosscheck_id,
            )
        return crosscheck_id

    # -- reads ---------------------------------------------------------------------------------

    def issues(self, *, include_resolved: bool = False) -> list[dict[str, Any]]:
        where = "" if include_resolved else "WHERE NOT resolved"
        return self._dicts(
            "SELECT issue_id, created_at_utc, severity, kind, provider, dataset, detail, source_ref, "
            f"resolved FROM data_issues {where} ORDER BY created_at_utc DESC, issue_id",
            [],
        )

    def latest_crosscheck(self) -> dict[str, Any] | None:
        row = self.con.execute(
            "SELECT crosscheck_id, created_at_utc, report_json FROM crosscheck_runs "
            "ORDER BY created_at_utc DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        rep = json.loads(row[2])
        return {
            "crosscheck_id": row[0], "created_at_utc": row[1], "providers": rep["providers"],
            "all_explained": rep["all_explained"], "counts": rep["counts"],
            "unexplained": rep["unexplained"], "days_compared": rep["days_compared"],
        }  # fmt: skip

    def calendar_summary(self) -> list[dict[str, Any]]:
        return self._dicts(
            "SELECT provider, exchange, count(*) FILTER (WHERE is_open) AS open_days, "
            "min(cal_date) AS first_day, max(cal_date) AS last_day, "
            "max(cal_date) FILTER (WHERE is_open) AS last_open_day "
            "FROM trade_calendar GROUP BY 1, 2 ORDER BY 1, 2",
            [],
        )

    def verify_payload(self, ingest_id: str) -> bool:
        """Re-hash the cached raw payload against the digest recorded at ingest."""
        row = self.con.execute(
            "SELECT payload_sha256, payload_path FROM ingest_runs WHERE ingest_id = ?", [ingest_id]
        ).fetchone()
        if row is None:
            raise StoreRefusal(f"no ingest {ingest_id}")
        with gzip.open(row[1], "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest() == row[0]

    def _dicts(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        cur = self.con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def daily(self, provider: str) -> list[dict[str, Any]]:
        cols = ",".join(COLUMNS["daily"])
        return self._dicts(
            f"SELECT {cols} FROM daily_bars WHERE provider = ? ORDER BY symbol, trade_date",
            [provider],
        )

    def factors(self, provider: str) -> list[dict[str, Any]]:
        cols = ",".join(COLUMNS["adj_factor"])
        return self._dicts(
            f"SELECT {cols} FROM adj_factors WHERE provider = ? ORDER BY symbol, trade_date",
            [provider],
        )

    def open_days(self, provider: str) -> list[date]:
        rows = self.con.execute(
            "SELECT DISTINCT cal_date FROM trade_calendar WHERE provider = ? AND is_open ORDER BY 1",
            [provider],
        ).fetchall()
        return [r[0] for r in rows]

    def securities(self, provider: str) -> list[dict[str, Any]]:
        cols = ",".join(COLUMNS["securities"])
        return self._dicts(
            f"SELECT DISTINCT {cols} FROM securities WHERE provider = ? ORDER BY symbol", [provider]
        )

    def ingest_ids(self, provider: str) -> list[str]:
        rows = self.con.execute(
            "SELECT ingest_id FROM ingest_runs WHERE provider = ? ORDER BY 1", [provider]
        )
        return [r[0] for r in rows.fetchall()]

    def availability(self) -> list[dict[str, Any]]:
        rows = self.con.execute(
            """
            SELECT i.provider, i.dataset, i.sample_label, count(*) AS ingests, sum(i.row_count) AS rows,
                   max(i.fetched_at_utc) AS last_fetch
            FROM ingest_runs i GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
            """
        ).fetchall()
        out = []
        for provider, dataset, label, ingests, nrows, last in rows:
            item: dict[str, Any] = {
                "provider": provider, "dataset": dataset, "sample_label": label, "ingests": ingests,
                "rows": int(nrows or 0), "last_fetch_utc": last,
            }  # fmt: skip
            if dataset == "daily":
                s = self.con.execute(
                    "SELECT count(DISTINCT symbol), min(trade_date), max(trade_date) FROM daily_bars "
                    "WHERE provider = ?",
                    [provider],
                ).fetchone()
                assert s is not None
                item.update(symbols=s[0], first_date=str(s[1]), last_date=str(s[2]))
            out.append(item)
        return out

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.con.execute(
            "SELECT run_id, created_at_utc, candidate_id, market_context_json, sample_label, report_json "
            "FROM research_runs ORDER BY created_at_utc DESC, rowid DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            {
                "run_id": r[0], "created_at_utc": r[1], "candidate_id": r[2],
                "market_context": json.loads(r[3]), "sample_label": r[4], "report": json.loads(r[5]),
            }
            for r in rows
        ]  # fmt: skip
