"""P10 §5 (ADR 0022) — ingest the ^VIX daily series from FMP into the factor store.

Host-venv entrypoint (no Docker, no stack) — same posture as ingest_sharadar.py.
Idempotent: re-running converges (index_prices keyed by (symbol, date)). Sources the
already-accepted FMP vendor (ADR 0018) via its ``/stable`` ``historical-price-eod/light``
endpoint — NO new vendor (ADR 0022). VIX is consumed downstream as a percentile, never
raw (``regime.vix_percentile``).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/ingest_vix.py            # ^VIX, full available history

Key hygiene (ADR 0018 §5): the API key is read from FMP_API_KEY and never logged.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# ADR 0017 — OS trust store before any HTTPS (a standalone script must do this itself).
import truststore

truststore.inject_into_ssl()

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[3]
    for _env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)
except Exception:
    pass

from app.factor_data.providers.fmp import FMPError, FMPProvider  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest the ^VIX daily series from FMP.")
    ap.add_argument("--symbol", default="^VIX", help="FMP index symbol (default ^VIX)")
    ap.add_argument("--db", help="override store path (default: WORKBENCH_FACTOR_DATA_DB_PATH)")
    args = ap.parse_args(argv)

    try:
        provider = FMPProvider()
    except Exception as e:  # noqa: BLE001 — surface a missing/invalid key clearly
        print(f"FMP not configured: {e}", file=sys.stderr)
        return 1

    store = FactorDataStore(db_path=args.db)
    started = datetime.now()
    try:
        # FMP /stable light EOD → columns [symbol, date, price, volume]; map price→close.
        df = provider.fetch("historical-price-eod/light", symbol=args.symbol)
        if df.empty or "date" not in df.columns or "price" not in df.columns:
            print(f"no usable rows for {args.symbol!r} (cols={list(df.columns)})", file=sys.stderr)
            store.record_ingest_run(f"index:{args.symbol}", started, datetime.now(), 0, "failed")
            return 1
        df = df.rename(columns={"price": "close"})
        df["symbol"] = args.symbol
        df["lastupdated"] = datetime.now().isoformat()
        rows = store.ingest_index_prices(df)
        store.record_ingest_run(f"index:{args.symbol}", started, datetime.now(), rows, "ok")
        print(f"  index:{args.symbol}: {rows} rows  (total index_prices: {store.row_count('index_prices')})")
    except FMPError as e:
        store.record_ingest_run(f"index:{args.symbol}", started, datetime.now(), 0, "failed")
        print(f"FMP error: {e}", file=sys.stderr)
        return 1
    finally:
        store.close()
        provider.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
