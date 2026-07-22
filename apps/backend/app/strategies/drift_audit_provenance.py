"""§8 drift audit — fail-closed provenance manifest.

An equivalence audit is only meaningful against the EXACT input the validation used. This
module builds a full, verifiable manifest of every input and refuses (``ProvenanceError``)
unless the databases match their operator-asserted digests. The CLI must not silently run
against whichever database happens to exist.

The manifest records, for adjudication: absolute db paths + SHA-256; schema/table inventory;
per-table row counts + date bounds + issuer/symbol counts; the universe / validation-artifact
identifier; code commit + working-tree status; strategy/version/config parameters; the replica
implementation reference; and the session count + exclusions.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import subprocess
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIGEST_CANON_VERSION = "drift_audit_content_digest/v1"


class ProvenanceError(Exception):
    """A required provenance check failed — a digest mismatch, a missing db, or a missing
    required identifier. The audit MUST NOT run: the input is not the validated input."""


def sha256_file(path: str | Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def db_manifest(path: str | Path) -> dict[str, Any]:
    """Full manifest of a duckdb database: abs path, sha256, size, and per-table inventory
    (rows, date bounds where a ``date`` column exists, issuer/symbol count where a ``ticker``
    column exists). Raises ``ProvenanceError`` if the file is absent."""
    p = Path(path).resolve()
    if not p.is_file():
        raise ProvenanceError(f"database not found: {p}")
    import duckdb

    con = duckdb.connect(str(p), read_only=True)

    def _one(sql: str) -> tuple:
        row = con.execute(sql).fetchone()
        assert row is not None  # aggregate queries always return a row
        return row

    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY table_name").fetchall()]
        inv: dict[str, Any] = {}
        for t in tables:
            cols = [r[0] for r in con.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}'"
            ).fetchall()]
            entry: dict[str, Any] = {"columns": cols, "rows": _one(f"SELECT COUNT(*) FROM {t}")[0]}
            if "date" in cols:
                mn, mx = _one(f"SELECT MIN(date), MAX(date) FROM {t}")
                entry["date_min"], entry["date_max"] = str(mn), str(mx)
            if "ticker" in cols:
                entry["distinct_tickers"] = _one(f"SELECT COUNT(DISTINCT ticker) FROM {t}")[0]
            inv[t] = entry
    finally:
        con.close()
    return {"abs_path": str(p), "sha256": sha256_file(p), "size_bytes": p.stat().st_size,
            "tables": tables, "inventory": inv}


def verify_db(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    """Build the db manifest and FAIL-CLOSED if its sha256 != the operator assertion."""
    man = db_manifest(path)
    if man["sha256"].lower() != expected_sha256.lower():
        raise ProvenanceError(
            f"digest mismatch for {man['abs_path']}: actual {man['sha256']} != "
            f"expected {expected_sha256}. This is NOT the validated input — refusing to run.")
    man["digest_verified"] = True
    return man


def _canon_value(v: Any) -> str:
    """Canonicalize one cell (drift_audit_content_digest/v1): null -> \\N; bool ->
    true/false; date -> ISO; float -> round-trip-exact repr(); int -> str; else escaped str.
    MUST stay byte-identical to the content-digest tool that produced the countersigned pins."""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, int):
        return str(v)
    return str(v).replace("\\", "\\\\").replace("|", "\\|")


def _stream_digest(con: Any, sql: str, dup_sql: str) -> tuple[str, int]:
    dup = con.execute(dup_sql).fetchone()
    if dup is not None:
        raise ProvenanceError(f"duplicate logical key {dup} — nondeterministic; refusing")
    h = hashlib.sha256()
    rows = 0
    cur = con.execute(sql)
    while batch := cur.fetchmany(200_000):
        for r in batch:
            h.update(("|".join(_canon_value(v) for v in r) + "\n").encode("utf-8"))
        rows += len(batch)
    return h.hexdigest(), rows


def sep_content_digest(db_path: str | Path, start: str, end: str) -> dict[str, Any]:
    """Deterministic logical-content digest of the audit-consumed ``sep`` columns over the
    window (sorted date,ticker; dup (date,ticker) fail-closed)."""
    import duckdb

    cols = ["ticker", "date", "open", "high", "low", "closeadj", "volume"]
    win = f"date BETWEEN DATE '{start}' AND DATE '{end}'"
    sql = f"SELECT {', '.join(cols)} FROM sep WHERE {win} ORDER BY date, ticker"
    dup = f"SELECT date, ticker, COUNT(*) FROM sep WHERE {win} GROUP BY date, ticker HAVING COUNT(*) > 1 LIMIT 1"
    con = duckdb.connect(str(Path(db_path).resolve()), read_only=True)
    try:
        sha, rows = _stream_digest(con, sql, dup)
        st = con.execute(f"SELECT COUNT(DISTINCT date), COUNT(DISTINCT ticker), MIN(date), "
                         f"MAX(date) FROM sep WHERE {win}").fetchone()
        assert st is not None  # aggregate always returns a row
    finally:
        con.close()
    return {"sha256": sha, "rows": rows, "columns": cols, "algorithm": "sha256",
            "canonicalization": CONTENT_DIGEST_CANON_VERSION, "query": " ".join(sql.split()),
            "distinct_sessions": st[0], "distinct_tickers": st[1],
            "date_min": str(st[2]), "date_max": str(st[3])}


def tickers_content_digest(db_path: str | Path, start: str, end: str) -> dict[str, Any]:
    """Deterministic logical-content digest of the audit-relevant ``tickers`` classification
    columns for the in-window universe (sorted ticker; dup ticker fail-closed)."""
    import duckdb

    cols = ["ticker", "sector", "industry", "category", "isdelisted",
            "firstpricedate", "lastpricedate"]
    inwin = (f"ticker IN (SELECT DISTINCT ticker FROM sep WHERE date BETWEEN DATE '{start}' "
             f"AND DATE '{end}')")
    sql = f"SELECT {', '.join(cols)} FROM tickers WHERE {inwin} ORDER BY ticker"
    dup = f"SELECT ticker, COUNT(*) FROM tickers WHERE {inwin} GROUP BY ticker HAVING COUNT(*) > 1 LIMIT 1"
    con = duckdb.connect(str(Path(db_path).resolve()), read_only=True)
    try:
        sha, rows = _stream_digest(con, sql, dup)
    finally:
        con.close()
    return {"sha256": sha, "rows": rows, "columns": cols, "algorithm": "sha256",
            "canonicalization": CONTENT_DIGEST_CANON_VERSION, "query": " ".join(sql.split()),
            "distinct_tickers": rows}


def verify_content_digests(db_path: str | Path, start: str, end: str, *,
                           expected_sep_sha256: str,
                           expected_tickers_sha256: str) -> dict[str, Any]:
    """Recompute both logical-content digests and FAIL-CLOSED if either differs from the
    countersigned pin — the audit must run only against the exact consumed rows."""
    sep = sep_content_digest(db_path, start, end)
    tkr = tickers_content_digest(db_path, start, end)
    if sep["sha256"].lower() != expected_sep_sha256.lower():
        raise ProvenanceError(
            f"sep content digest mismatch: actual {sep['sha256']} != pinned {expected_sep_sha256} "
            "— the audit-consumed sep rows are NOT the countersigned input. Refusing.")
    if tkr["sha256"].lower() != expected_tickers_sha256.lower():
        raise ProvenanceError(
            f"tickers content digest mismatch: actual {tkr['sha256']} != pinned "
            f"{expected_tickers_sha256}. Refusing.")
    return {"sep": {**sep, "digest_verified": True}, "tickers": {**tkr, "digest_verified": True}}


def code_provenance() -> dict[str, Any]:
    def _git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=_BACKEND_ROOT, capture_output=True,
                              text=True, check=False).stdout.strip()

    porcelain = _git("status", "--porcelain")
    return {"commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "working_tree_clean": porcelain == "",
            "dirty_paths": [ln[3:] for ln in porcelain.splitlines()] if porcelain else []}


def build_manifest(
    *, factor_db: str | Path, price_db: str | Path, expected_factor_db_sha256: str,
    expected_universe_id: str, start_date: str, end_date: str,
    strategy_name: str, strategy_version: str, strategy_params: dict[str, Any],
    replica_reference: str, session_count: int | None = None,
    exclusions: list[str] | None = None, expected_price_db_sha256: str | None = None,
    expected_sep_content_sha256: str | None = None,
    expected_tickers_content_sha256: str | None = None,
    content_digest_artifact_sha256: str | None = None,
) -> dict[str, Any]:
    """Assemble + FAIL-CLOSED-verify the full audit manifest. Raises ``ProvenanceError`` on
    any digest mismatch or a missing required identifier. ``expected_universe_id`` is
    mandatory. When the sep/tickers content pins are supplied (the countersigned binding),
    they are RE-COMPUTED and verified fail-closed, and a top-level ``provenance_binding``
    block is emitted; supplying one content pin requires the other."""
    if not expected_universe_id:
        raise ProvenanceError("expected_universe_id is required (the validation artifact id)")
    if not expected_factor_db_sha256:
        raise ProvenanceError("expected_factor_db_sha256 is required (fail-closed)")
    if bool(expected_sep_content_sha256) != bool(expected_tickers_content_sha256):
        raise ProvenanceError("supply BOTH sep and tickers content pins, or neither")

    factor = verify_db(factor_db, expected_factor_db_sha256)
    price = (verify_db(price_db, expected_price_db_sha256) if expected_price_db_sha256
             else db_manifest(price_db))
    price["digest_verified"] = bool(expected_price_db_sha256)

    content: dict[str, Any] | None = None
    binding: dict[str, Any] | None = None
    if expected_sep_content_sha256 and expected_tickers_content_sha256:
        content = verify_content_digests(
            factor_db, start_date, end_date,
            expected_sep_sha256=expected_sep_content_sha256,
            expected_tickers_sha256=expected_tickers_content_sha256)
        binding = {
            "whole_file_sha256": factor["sha256"],
            "sep_content_sha256": content["sep"]["sha256"],
            "tickers_content_sha256": content["tickers"]["sha256"],
            "content_digest_artifact_sha256": content_digest_artifact_sha256,
            "canonicalization_version": CONTENT_DIGEST_CANON_VERSION,
            "universe_id": expected_universe_id,
            "audit_window": {"start_date": start_date, "end_date": end_date},
            "measurement_code_commit": code_provenance()["commit"],
            "working_tree_clean": code_provenance()["working_tree_clean"],
            "replica_reference": replica_reference,
            "strategy_configuration": {"name": strategy_name, "version": strategy_version,
                                       "params": strategy_params},
        }

    manifest: dict[str, Any] = {
        "schema": "drift_audit_manifest/v2" if binding else "drift_audit_manifest/v1",
        "expected_universe_id": expected_universe_id,
        "window": {"start_date": start_date, "end_date": end_date,
                   "session_count": session_count, "exclusions": exclusions or []},
        "factor_db": factor,
        "price_db": price,
        "code": code_provenance(),
        "strategy": {"name": strategy_name, "version": strategy_version,
                     "params": strategy_params},
        "replica_reference": replica_reference,
        "all_digests_verified": bool(factor.get("digest_verified") and (
            price.get("digest_verified") or expected_price_db_sha256 is None)),
    }
    if content is not None:
        manifest["content_digests"] = content
        manifest["provenance_binding"] = binding
    return manifest


__all__ = [
    "CONTENT_DIGEST_CANON_VERSION",
    "ProvenanceError",
    "build_manifest",
    "code_provenance",
    "db_manifest",
    "sep_content_digest",
    "sha256_file",
    "tickers_content_digest",
    "verify_content_digests",
    "verify_db",
]
