"""Store-path resolution + Settings wiring for the factor-data subsystem."""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings

# apps/backend/ — this file is app/factor_data/config.py, so parents[2] is the
# backend root. Relative store paths resolve against it (matches db_url /
# bars_cache_root, which are also backend-relative).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_store_path(db_path: str | None = None) -> Path:
    """Absolute path to the DuckDB factor-data store.

    ``db_path`` overrides the configured default (``WORKBENCH_FACTOR_DATA_DB_PATH``
    / ``data/factor_data.duckdb``). A relative path resolves against apps/backend/;
    an absolute path is used as-is. The parent directory is created if missing.
    """
    raw = db_path if db_path is not None else get_settings().factor_data_db_path
    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
