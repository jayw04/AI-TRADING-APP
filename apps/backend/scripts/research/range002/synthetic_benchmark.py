#!/usr/bin/env python3
"""Print the RANGE-002 synthetic engineering benchmark: expected vs actual, per scenario and
candidate, with funnel counts and per-stage wall-clock runtime.

    python scripts/research/range002/synthetic_benchmark.py            (run from apps/backend)

NON-INFERENTIAL: every input is a deterministic synthetic fixture; the output proves arithmetic
and behaviour of the screen kernel only and says nothing about any market or strategy. It reuses
``tests/research/range002/screen/test_synthetic_benchmark.py::run_benchmark`` (the same pipeline
the test asserts on) and only prints; it writes no file and reads no market data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    from app.research.range002.screen.types import TERMINAL_STATES
    from tests.research.range002.screen import _benchmark_expected as x
    from tests.research.range002.screen import test_synthetic_benchmark as b

    with tempfile.TemporaryDirectory(prefix="range002-bench-") as tmp:
        res = b.run_benchmark(Path(tmp))

    print(f"== {b.LABEL} ==")
    print(
        "Results prove arithmetic/behaviour on planted synthetic fixtures; not evidence of profit."
    )
    worst = 0.0
    for sc in x.EXPECTED:
        r = res.scenarios[sc]
        print(f"\n--- {sc} ---")
        print(
            f"{'cand':<12}{'n_exp':>6}{'n_act':>6}{'base_exp':>12}{'base_act':>12}"
            f"{'stress_exp':>12}{'stress_act':>12}{'max|d|':>10}"
        )
        for c in x.CANDS:
            exp = x.expected_trades(sc, c)
            act = {(t.symbol, t.day): t for t in r.run.trades[c]}
            be, se = x.total_net(sc, c), x.total_net(sc, c, stress=True)
            ba = sum(t.net_r_base for t in act.values())
            sa = sum(t.net_r_stress for t in act.values())
            dev = max(
                [abs(be - ba), abs(se - sa)]
                + [
                    abs(xt.net_base - act[(s.symbol, s.day)].net_r_base)
                    for s, xt in exp
                    if (s.symbol, s.day) in act
                ]
                + [
                    abs(xt.net_stress - act[(s.symbol, s.day)].net_r_stress)
                    for s, xt in exp
                    if (s.symbol, s.day) in act
                ]
            )
            worst = max(worst, dev)
            print(
                f"{c:<12}{len(exp):>6}{len(act):>6}{be:>12.6f}{ba:>12.6f}"
                f"{se:>12.6f}{sa:>12.6f}{dev:>10.2e}"
            )
        n, states, exits = x.expected_funnel(sc)
        f = r.run.funnel
        act_states = {k: v for k, v in f.states.items() if v}
        ok = (
            f.eligible == n
            and act_states == states
            and all(f.exits[c] == exits[c] for c in x.CANDS)
        )
        print(f"funnel expected: eligible {n} states {states}")
        print(
            f"funnel actual  : eligible {f.eligible} states {act_states} "
            f"(sum {sum(f.states.values())}, terminal states {len(TERMINAL_STATES)})  "
            f"{'MATCH' if ok else 'MISMATCH'}"
        )
        print(f"exits TIME actual: {f.exits['TIME']}   causal problems: {len(r.causal_problems)}")

    print("\n--- S6 portfolio (all candidates identical; shown for TIME) ---")
    d, rl = res.portfolio_default["TIME"], res.portfolio_relaxed["TIME"]
    print(f"signal trades {d.signal_trades}")
    print(
        f"default  accepted {[(t.symbol, t.day.isoformat()) for t in d.accepted]} "
        f"rejected {d.rejected} net_base {sum(t.net_r_base for t in d.accepted):.6f}"
    )
    print(
        f"expected accepted {x.S6_DEFAULT_ACCEPTED} rejected {x.S6_DEFAULT_REJECTED} "
        "net_base -1.939625"
    )
    print(
        f"relaxed  accepted {[(t.symbol, t.day.isoformat()) for t in rl.accepted]} "
        f"rejected {rl.rejected} net_base {sum(t.net_r_base for t in rl.accepted):.6f}"
    )
    print(
        f"expected accepted {x.S6_RELAXED_ACCEPTED} rejected {x.S6_RELAXED_REJECTED} "
        "net_base -1.380500"
    )

    print("\n--- pooled bootstrap / selection (synthetic payload values) ---")
    for c in x.CANDS:
        v = x.pooled(c)
        print(
            f"{c:<12} pooled mean expected {sum(v) / len(v):>10.6f} "
            f"actual {res.matrix_observed[c]:>10.6f}"
        )
    mt = res.max_test_runs[0]
    print(
        f"max-stat: argmax {mt.observed_argmax} observed_max {mt.observed_max:.6f} "
        f"p {mt.p_value:.4f} rejects {mt.rejects} (deterministic: "
        f"{res.max_test_runs[0] == res.max_test_runs[1]})"
    )
    print(
        f"selection: winner {res.selection.winner} reason {res.selection.reason} "
        f"ineligible {res.selection.ineligible}"
    )

    print("\n--- runtime (seconds) ---")
    for k, secs in sorted(res.timings.items()):
        print(f"{k:<38}{secs:>10.3f}")
    print(f"\nmax |expected - actual| over every trade total and per-trade net R: {worst:.3e}")
    print(f"{b.LABEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
