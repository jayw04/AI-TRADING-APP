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

import hashlib
import subprocess
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


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
) -> dict[str, Any]:
    """Assemble + FAIL-CLOSED-verify the full audit manifest. Raises ``ProvenanceError`` on
    any digest mismatch or a missing required identifier. ``expected_universe_id`` is
    mandatory — the audit is bound to a specific validation universe/artifact."""
    if not expected_universe_id:
        raise ProvenanceError("expected_universe_id is required (the validation artifact id)")
    if not expected_factor_db_sha256:
        raise ProvenanceError("expected_factor_db_sha256 is required (fail-closed)")

    factor = verify_db(factor_db, expected_factor_db_sha256)
    price = (verify_db(price_db, expected_price_db_sha256) if expected_price_db_sha256
             else db_manifest(price_db))
    price["digest_verified"] = bool(expected_price_db_sha256)

    return {
        "schema": "drift_audit_manifest/v1",
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


__all__ = [
    "ProvenanceError",
    "build_manifest",
    "code_provenance",
    "db_manifest",
    "sha256_file",
    "verify_db",
]
