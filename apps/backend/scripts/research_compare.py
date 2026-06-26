"""CLI: compare research experiments side by side (§4).

    cd apps/backend
    .venv/Scripts/python.exe scripts/research_compare.py exp_abc exp_def \
        --metrics sharpe cagr max_drawdown_abs turnover

Prints a direction-aware comparison table (winner per metric) from the research
registry. Use dotted metrics (e.g. mom_12.oos_ls_sharpe) for nested summaries.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare research experiments (Research Engine §4).")
    ap.add_argument("experiment_ids", nargs="+", help="experiment ids to compare")
    ap.add_argument("--metrics", nargs="+", required=True, help="metric keys (dotted ok)")
    args = ap.parse_args(argv)

    from app.research.comparison import compare_experiments
    from app.research.registry import ResearchStore

    store = ResearchStore(read_only=True)
    try:
        res = compare_experiments(store, args.experiment_ids, args.metrics)
    finally:
        store.close()
    print(res.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
