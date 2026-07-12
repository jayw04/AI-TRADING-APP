"""MR-002 DEVELOPMENT RUN — frozen §8a development window ONLY.

    development: 2013-01-02 .. 2019-10-02  (1,700 sessions)

Validation (2019-10-03..2023-02-16) and sealed OOS (2023-02-17..2026-07-10) are
NOT READ by this script — the dataset is hard-bounded and the bound is asserted.

Purpose (frozen §7): IMPLEMENTATION VERIFICATION ONLY. A/B/C are run to exercise
the code paths. **No winner selection. No gate is read.** Economic outputs appear
only where required to prove arithmetic, and are labelled:

    DEVELOPMENT-ONLY HARNESS OUTPUT — no gate interpretation and no configuration
    comparison permitted.

Emits: dev_run_<cfg>.json (ledger summary + diagnostics), dev_ledger_<cfg>.csv
(immutable fills), dev_daily_<cfg>.csv (daily records) and the reconciliation.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_dev_run.py [--slice N]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "backend"))
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
OUT = EV / "development"
STORE = str(ROOT / "apps" / "backend" / "data" / "mr002_research.duckdb")

DEV_START = date(2013, 1, 2)
DEV_END = date(2019, 10, 2)          # frozen §8a — NEVER beyond this
VALIDATION_START = date(2019, 10, 3)

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.execution import (  # noqa: E402
    cagr,
    calmar,
    max_drawdown,
    reconcile,
    sharpe,
)
from app.research.mr002.runner import CONFIGS, run  # noqa: E402

LABEL = ("DEVELOPMENT-ONLY HARNESS OUTPUT — no gate interpretation and no "
         "configuration comparison permitted.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", type=int, default=0,
                    help="run only the first N development sessions (pipeline check)")
    ap.add_argument("--configs", default="A,B,C")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    ds = FrozenDataset(STORE)
    end = DEV_END
    days = ds.day_inputs(DEV_START, end)
    # HARD ASSERTION: the validation and sealed windows must remain unread
    assert all(d.session <= DEV_END for d in days), "window bound violated"
    assert all(d.next_open_session is None or d.next_open_session <= DEV_END
               for d in days), "execution beyond the development window"
    if args.slice:
        days = days[:args.slice]
    print(f"development sessions: {len(days)} "
          f"({days[0].session} .. {days[-1].session})", flush=True)

    summary = {}
    for name in args.configs.split(","):
        cfg = CONFIGS[name.strip()]
        led = run(days, cfg)
        rec = reconcile(led, 10_000_000.0)
        nav = led.equity_curve()
        rets = led.returns()
        # fills ledger (immutable)
        with (OUT / f"dev_ledger_{cfg.name}.csv").open("w", newline="",
                                                       encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["session", "permaticker", "ticker", "side", "shares",
                        "price", "notional", "cost", "reason", "z", "clipped_by_adv"])
            for x in led.fills:
                w.writerow([x.session, x.permaticker, x.ticker, x.side,
                            f"{x.shares:.6f}", f"{x.price:.6f}", f"{x.notional:.2f}",
                            f"{x.cost:.4f}", x.reason, f"{x.z:.4f}", x.clipped_by_adv])
        with (OUT / f"dev_daily_{cfg.name}.csv").open("w", newline="",
                                                      encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(led.daily[0]).keys()))
            w.writeheader()
            for d in led.daily:
                w.writerow(asdict(d))
        summary[cfg.name] = {
            "label": LABEL,
            "z_entry": cfg.z_entry,
            "sessions": len(led.daily),
            "fills": len(led.fills),
            "entries": sum(d.n_entries for d in led.daily),
            "exits": sum(d.n_exits for d in led.daily),
            "exit_reasons": {r: sum(1 for f in led.fills if f.reason == r)
                             for r in sorted({f.reason for f in led.fills})},
            "adv_clipped_orders": sum(1 for f in led.fills if f.clipped_by_adv),
            "exceptions": len(led.exceptions),
            "reconciliation": rec,
            "arithmetic_check_only": {
                "final_nav": float(nav[-1]) if len(nav) else None,
                "sharpe": sharpe(rets), "cagr": cagr(nav),
                "max_drawdown": max_drawdown(nav), "calmar": calmar(nav),
            },
            "ledger_sha256": hashlib.sha256(
                (OUT / f"dev_ledger_{cfg.name}.csv").read_bytes()).hexdigest(),
            "daily_sha256": hashlib.sha256(
                (OUT / f"dev_daily_{cfg.name}.csv").read_bytes()).hexdigest(),
        }
        print(f"  {cfg.name}: fills={len(led.fills)} entries="
              f"{summary[cfg.name]['entries']} exits={summary[cfg.name]['exits']} "
              f"reconciled={rec['ok']}", flush=True)

    (OUT / "dev_run_summary.json").write_text(json.dumps(
        {"label": LABEL, "window": {"start": str(DEV_START), "end": str(DEV_END),
                                    "sessions_run": len(days)},
         "validation_and_sealed_windows_read": False,
         "configs": summary}, indent=2, default=str))
    print(json.dumps({k: {"fills": v["fills"], "entries": v["entries"],
                          "exits": v["exits"],
                          "reconciled": v["reconciliation"]["ok"]}
                      for k, v in summary.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
