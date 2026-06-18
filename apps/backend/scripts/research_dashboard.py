"""CLI: render the Research Engine dashboard from the registry (§5).

    cd apps/backend
    .venv/Scripts/python.exe scripts/research_dashboard.py --out ../../research/dashboard.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the Research Engine dashboard.")
    ap.add_argument("--out", default="../../research/dashboard.md")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args(argv)

    from app.research.dashboard import write_dashboard
    from app.research.registry import ResearchStore

    store = ResearchStore(read_only=True)
    try:
        path = write_dashboard(store, args.out, limit=args.limit)
    finally:
        store.close()
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
