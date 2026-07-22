#!/usr/bin/env python3
"""§8 live-class drift audit — CLI (ADR 0044 validation-production equivalence).

Drives the ACTUAL live ``MomentumDaily`` and the Stage 4 replica (variant C) over the
same historical sessions on the SAME verified input, and emits a DIAGNOSTIC drift census
(first-cause + downstream, per §8). FAIL-CLOSED: it refuses to run unless every input db
matches its operator-asserted SHA-256 and a universe/validation-artifact id is supplied —
it will not silently pick whichever database exists.

Two seam divergences are EXPECTED and are the point of the census (adjudicate, don't gate):
  * trigger gate: replica ``changed`` vs the live six named §5.1 triggers;
  * weights: replica ``hybrid_50_50`` inverse-vol vs the live equal-weight.

Usage:
    # provenance/manifest only — all db + config checks, NO 21-year comparison:
    python scripts/drift_audit_momentum_daily.py --provenance-only \
        --factor-db data/factor_data_full.duckdb --price-db data/factor_data_full.duckdb \
        --expected-factor-db-sha256 <sha> --expected-universe-id momentum_daily_stage2_4_full \
        --start-date 2005-01-03 --end-date 2026-07-01 --output out/drift_manifest.json

    # full diagnostic run (only after the digest is pinned + the manifest reviewed):
    python scripts/drift_audit_momentum_daily.py  <same args, without --provenance-only>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling stage scripts

from app.strategies.drift_audit_provenance import (  # noqa: E402
    ProvenanceError,
    build_manifest,
)

REPLICA_REF = "scripts/backtest_momentum_stage4.py::simulate (variant C, graduated)"
STRATEGY_NAME = "momentum-daily"
STRATEGY_VERSION = "0.2.0"


def _strategy_params() -> dict:
    from strategies_user.templates.momentum_daily import MomentumDaily
    return {**MomentumDaily.default_params, "regime_mode": "graduated",
            "use_market_regime_filter": True, "initial_seed_investable_gross": 0.60,
            "order_pacing_seconds": 0.0}


def _run_comparison(args, manifest: dict) -> dict:
    """Wire the production FactorAccessor + duckdb prices into the live drive, and the
    validated Stage functions into the replica extractor; return the §8 drift report.

    Only reached AFTER the fail-closed manifest verification (so the input is the exact
    validated database). Deterministic plumbing; its first REAL exercise is the run itself
    — the pipeline logic (drive_live + capture_replica_seams + build_report) is covered by
    the fixture test, and this glue's output is the DIAGNOSTIC census to be adjudicated,
    not trusted blindly. Fidelity choices (recorded for adjudication):
      * universe = the replica's scored set (both sides eligible over the same names);
      * live scores = production FactorAccessor.momentum_scores(as_of=day, 252/21);
      * market symbol ("SPY") = the same broad proxy index the replica's regime uses.
    """
    import os
    from datetime import datetime as _dt
    from decimal import Decimal

    import pandas as pd

    os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"] = str(Path(args.factor_db).resolve())
    import asyncio

    import backtest_momentum_stage2 as s2  # noqa: N813
    import backtest_momentum_stage3 as s3  # noqa: N813
    import backtest_momentum_stage4 as s4  # noqa: N813

    from app.factor_data.accessor import FactorAccessor
    from app.factor_data.backtest import _CachedPriceStore
    from app.factor_data.store import FactorDataStore
    from app.strategies.deployment_state import initial_blob
    from app.strategies.drift_audit import build_report
    from app.strategies.drift_audit_driver import (
        DriftCtxAdapter,
        capture_replica_seams,
        drive_live,
    )
    from strategies_user.templates.momentum_daily import _K_DEPLOYMENT, MomentumDaily

    start = _dt.strptime(args.start_date, "%Y-%m-%d").date()
    end = _dt.strptime(args.end_date, "%Y-%m-%d").date()
    store = FactorDataStore(read_only=True)
    trading_days = store.trading_days(start, end)
    cached = _CachedPriceStore(store)
    db_path = os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"]

    proxy = s4.build_market_proxy(store, trading_days, db_path)          # SPY substitution
    gross = s4.gross_series(proxy, "C")                                   # variant C (graduated)
    proxy_close = {d: float(v) for d, v in proxy["idx"].items() if pd.notna(v)}

    day_scores: dict = {}
    for d in trading_days:
        ds = s2.compute_day(cached, d)
        if ds is not None:
            day_scores[d] = ds
    universe = sorted({t for ds in day_scores.values() for t in ds.ranked})
    sectors = store.get_sectors(universe)

    price_cache: dict[str, dict] = {}

    def _price(t: str, d) -> float | None:
        if t not in price_cache:
            df = store.get_prices(t, trading_days[0], trading_days[-1], adjusted=True)
            price_cache[t] = {row.date(): float(c) for row, c in
                              zip(df["date"], df["close"], strict=False) if c and float(c) > 0}
        return price_cache[t].get(d if not hasattr(d, "date") else d)

    replica_records = capture_replica_seams(
        trading_days, day_scores, gross,
        select_fn=lambda ds, held, prev: s3.select_n(ds, held, prev, s4.N, sectors, s4.CAP_ON),
        weigh_fn=lambda chosen, d: s3.weigh(store, chosen, d, sizing=s4.SIZING, n=s4.N,
                                            cap_on=s4.CAP_ON, sectors=sectors),
        price_fn=_price, backstop_days=s4.BACKSTOP_DAYS, weight_drift_pct=s4.WEIGHT_DRIFT_PCT,
        turnover_cost_bps=s4.TURNOVER_COST_BPS, initial_equity=float(s4.INITIAL_EQUITY))

    # live side — universe = the replica's scored set + the proxy market symbol.
    market_sym = "SPY"
    accessor = FactorAccessor(store)

    def scores_provider(day):
        return accessor.momentum_scores(as_of=day, n=len(universe),
                                        lookback_days=252, skip_days=21)

    def bars_provider(sym: str, as_of, n: int) -> pd.DataFrame:
        if sym.upper() == market_sym:                                   # regime = proxy index
            ser = [(d, c) for d, c in proxy_close.items() if d <= as_of][-n:]
        else:
            ser = [(d, _price(sym, d)) for d in trading_days if d <= as_of][-n:]
            ser = [(d, c) for d, c in ser if c is not None]
        idx = pd.to_datetime([d for d, _ in ser])
        c = [c for _, c in ser]
        df = pd.DataFrame({"o": c, "h": c, "l": c, "c": c, "v": [1] * len(c)}, index=idx)
        df.index.name = "t"
        return df

    adapter = DriftCtxAdapter(symbols=[market_sym, *universe], strategy_id=11,
                              scores_provider=scores_provider, bars_provider=bars_provider,
                              equity=Decimal(str(s4.INITIAL_EQUITY)), sim_day=trading_days[0])
    adapter._state[_K_DEPLOYMENT] = initial_blob().to_dict()
    strat = MomentumDaily(ctx=adapter, params=_strategy_params())
    live_records = asyncio.run(drive_live(strat, adapter, trading_days,
                                          fill_price_fn=lambda s, d: _price(s, d)))

    return build_report(live_records, replica_records).to_dict()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--factor-db", required=True)
    ap.add_argument("--price-db", required=True)
    ap.add_argument("--expected-factor-db-sha256", required=True)
    ap.add_argument("--expected-price-db-sha256", default=None)
    ap.add_argument("--expected-universe-id", required=True,
                    help="the validation universe / artifact identifier the audit is bound to")
    ap.add_argument("--expected-sep-content-sha256", default=None,
                    help="countersigned logical-content digest of the audit-consumed sep rows")
    ap.add_argument("--expected-tickers-content-sha256", default=None,
                    help="countersigned logical-content digest of the audit-relevant tickers rows")
    ap.add_argument("--content-digest-artifact-sha256", default=None,
                    help="SHA-256 of the countersigned content-digest artifact (recorded in the binding)")
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--provenance-only", action="store_true",
                    help="run all db + config checks and write the manifest; NO comparison")
    ap.add_argument("--dry-run", action="store_true", help="alias for --provenance-only")
    args = ap.parse_args()

    # FAIL-CLOSED: verify every input before anything else.
    try:
        manifest = build_manifest(
            factor_db=args.factor_db, price_db=args.price_db,
            expected_factor_db_sha256=args.expected_factor_db_sha256,
            expected_price_db_sha256=args.expected_price_db_sha256,
            expected_universe_id=args.expected_universe_id,
            start_date=args.start_date, end_date=args.end_date,
            strategy_name=STRATEGY_NAME, strategy_version=STRATEGY_VERSION,
            strategy_params=_strategy_params(), replica_reference=REPLICA_REF,
            expected_sep_content_sha256=args.expected_sep_content_sha256,
            expected_tickers_content_sha256=args.expected_tickers_content_sha256,
            content_digest_artifact_sha256=args.content_digest_artifact_sha256)
    except ProvenanceError as exc:
        print(f"✖ PROVENANCE REFUSED (fail-closed): {exc}", file=sys.stderr)
        return 5

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.provenance_only or args.dry_run:
        out.write_text(json.dumps({"mode": "provenance-only", "manifest": manifest}, indent=2,
                                  default=str), encoding="utf-8")
        print("✔ provenance verified. Manifest written to", out)
        print("  factor_db sha256:", manifest["factor_db"]["sha256"])
        print("  universe id     :", manifest["expected_universe_id"])
        print("  code commit     :", manifest["code"]["commit"],
              "(clean)" if manifest["code"]["working_tree_clean"] else "(DIRTY)")
        print("  → review the manifest, then re-run WITHOUT --provenance-only for the census.")
        return 0

    report = _run_comparison(args, manifest)
    out.write_text(json.dumps({"mode": "full", "manifest": manifest, "report": report},
                              indent=2, default=str), encoding="utf-8")
    print("✔ drift census written to", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
