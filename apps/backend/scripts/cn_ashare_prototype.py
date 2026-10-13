"""CLI: China A-share daily prototype — ingest a bounded sample, cross-check providers, run one
descriptive research run. RESEARCH-ONLY: no broker, no order path, no scheduler.

    cd apps/backend
    .venv/Scripts/python.exe scripts/cn_ashare_prototype.py --mode synthetic
    .venv/Scripts/python.exe scripts/cn_ashare_prototype.py --mode live --symbols 600000.SH,000001.SZ \
        --start 2024-01-01 --end 2024-12-31

``--mode synthetic`` renders a deterministic synthetic world through the real Tushare and Baostock
adapters (fake clients) and labels everything SYNTHETIC. ``--mode live`` needs the optional
``tushare``/``baostock`` packages, network access to both providers and, for Tushare, a token file
at ``settings.cn_ashare_tushare_token_path``. Live output is labelled as a plumbing sample.
The store is ``settings.cn_ashare_db_path`` unless ``--db`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.markets.cn_ashare import context, crosscheck, ingest, research
    from app.markets.cn_ashare.providers.baostock import BaostockProvider
    from app.markets.cn_ashare.providers.base import ProviderError
    from app.markets.cn_ashare.providers.tushare import TushareProvider
    from app.markets.cn_ashare.store import CnAshareStore
    from app.markets.context import PriceBasis

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mode", choices=("synthetic", "live"), default="synthetic")
    ap.add_argument("--symbols", default="", help="comma-separated canonical symbols (live mode)")
    ap.add_argument("--start", default="2024-01-02")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--candidate", default="CN-MOM-20D", choices=sorted(research.CANDIDATES))
    ap.add_argument(
        "--db", default=None, help="store path; the file name must start with cn_ashare"
    )
    ap.add_argument("--cache", default=None)
    args = ap.parse_args(argv)
    s = get_settings()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    providers: list = []
    if args.mode == "synthetic":
        from app.markets.cn_ashare.providers import synthetic

        truth = synthetic.build_truth(start, end)
        symbols = sorted(truth.names)
        providers = [
            TushareProvider(
                synthetic.FakeTusharePro(truth), source_id="cn_synthetic:tushare_shape"
            ),
            BaostockProvider(
                synthetic.FakeBaostock(truth), source_id="cn_synthetic:baostock_shape"
            ),
        ]
        label = ingest.SYNTHETIC_SAMPLE
    else:
        symbols = [x.strip() for x in args.symbols.split(",") if x.strip()]
        if not symbols:
            ap.error("--symbols is required in live mode")
        for make in (lambda: TushareProvider.from_token_file(s.cn_ashare_tushare_token_path),
                     BaostockProvider.from_anonymous_login):  # fmt: skip
            try:
                providers.append(make())
            except (ProviderError, ImportError, OSError) as exc:
                print(f"provider unavailable: {exc}", file=sys.stderr)
        if not providers:
            print("no provider available; nothing ingested", file=sys.stderr)
            return 2
        label = ingest.PLUMBING_SAMPLE

    report: dict = {"mode": args.mode, "sample_label": label, "symbols": symbols}
    with CnAshareStore(
        args.db or s.cn_ashare_db_path, args.cache or s.cn_ashare_cache_dir
    ) as store:
        results = {}
        for p in providers:
            res = ingest.ingest_sample(store, p, symbols, start, end, sample_label=label)
            results[p.source_id] = res
            bad = [i for i in res.ingest_ids if not store.verify_payload(i)]
            for i in bad:
                store.record_issue(
                    severity="BLOCKER", kind="PAYLOAD_HASH_MISMATCH", provider=p.source_id,
                    detail=f"cached raw payload for {i} does not match its recorded SHA-256",
                    source_ref=i,
                )  # fmt: skip
            report.setdefault("ingest", {})[p.source_id] = {
                "ingests": len(res.ingest_ids),
                "missing_symbols": res.missing_symbols,
                "payloads_verified": not bad,
            }
        names = [p.source_id for p in providers]
        if len(names) == 2:
            a, b = names
            report["crosscheck"] = crosscheck.compare(
                a, store.daily(a), store.factors(a), b, store.daily(b), store.factors(b)
            )
            report["crosscheck"]["crosscheck_id"] = store.record_crosscheck(report["crosscheck"])
        else:
            report["crosscheck"] = {
                "skipped": f"only {names} available; a cross-check needs two providers"
            }
        # Run on the provider that carries an ST flag (Baostock shape): Tushare ``daily`` has none,
        # and before 2026-07-06 the main-board limit depends on it.
        run_on = next((n for n in names if "baostock" in n), names[0])
        run = research.run_descriptive(
            args.candidate,
            provider=run_on,
            open_days=store.open_days(run_on),
            daily=store.daily(run_on),
            factors=store.factors(run_on),
            securities=store.securities(run_on),
            sample_label=label,
        )
        run_id = store.record_run(
            candidate_id=args.candidate,
            ctx=context(exchange="SSE+SZSE", provider=run_on, price_basis=PriceBasis.HFQ),
            sample_label=label,
            ingest_ids=results[run_on].ingest_ids,
            report=run,
        )
        report["research_run"] = {
            "run_id": run_id,
            "provider": run_on,
            "labels": run["labels"],
            **run["result"],
        }
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
