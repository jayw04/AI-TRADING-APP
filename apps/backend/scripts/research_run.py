"""CLI: run a research experiment through the Research Engine orchestrator (§2).

Builds an ``ExperimentConfig``, derives the ``DatasetRecord`` from the factor
store's current snapshot, and runs it — recording the experiment + artifacts in
the research registry (content-addressed, so reruns of an unchanged config + code
+ data are instant cache hits).

    cd apps/backend
    WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data.duckdb \
      .venv/Scripts/python.exe scripts/research_run.py factor_ic --n 200 --start 2016-01-01 --split 2023-01-01

Outputs the experiment_id + its registry row. (Dashboard is built later — §5.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _dataset_from_store():
    from app.factor_data.store import FactorDataStore
    from app.research.registry import DatasetRecord
    store = FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        ntk = store.con.execute("SELECT COUNT(DISTINCT ticker) FROM sep").fetchone()[0]
    finally:
        store.close()
    return DatasetRecord(
        dataset_id=f"sep_{latest}", provider="sharadar", version=str(latest),
        coverage=f"{floor}..{latest}", row_count=int(ntk),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a research experiment (Research Engine §2).")
    ap.add_argument("kind", choices=["factor_ic"], help="experiment kind")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--split", default="2023-01-01")
    ap.add_argument("--report-dir", default="../../research")
    ap.add_argument("--force", action="store_true", help="re-run even if cached")
    args = ap.parse_args(argv)

    from app.research.engine import ExperimentConfig, run_experiment
    from app.research.engine.runners import factor_ic_runner
    from app.research.registry import ResearchStore

    config = ExperimentConfig(
        kind=args.kind, name=f"{args.kind} n={args.n} {args.start}..(split {args.split})",
        params={"n": args.n, "start": args.start, "split": args.split},
        is_window=f"{args.start}..{args.split}", oos_window=f"{args.split}..",
        pit_mode="n/a", survivorship_mode="sep_universe",
    )
    dataset = _dataset_from_store()
    store = ResearchStore()
    try:
        eid = run_experiment(config, factor_ic_runner, store=store, dataset=dataset,
                             report_dir=args.report_dir, force=args.force)
        exp = store.get_experiment(eid)
        print(f"experiment_id: {eid}")
        print(f"  kind={exp.kind} dataset={exp.dataset_id} commit={exp.git_commit} "
              f"duration_ms={exp.duration_ms}")
        print(f"  metrics_summary: {exp.metrics_summary}")
        print(f"  dependencies: {store.dependencies(eid)}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
