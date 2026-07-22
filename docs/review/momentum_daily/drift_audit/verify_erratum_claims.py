#!/usr/bin/env python3
"""Re-verify EVERY numeric claim in weighting_defect_erratum_v1.0.md against the source artifacts.

Read-only. Exists because a hand-transcription defect was found in this package: the impact
study's reproduction gate carried reference constants typed at full precision from a console
echo that had printed them rounded to six decimals, with the trailing digits invented. That
gate then failed a run which had in fact reproduced exactly. Every number a reviewer is asked
to rely on should be re-derivable from an artifact by machine, not trusted because it appears
in prose.

Sources: MR_MomentumDaily_Stage3_full.json (the regime-free N=5 comparison) and
replica_seams.json (the census's validated-side seam capture).

    python docs/review/momentum_daily/drift_audit/verify_erratum_claims.py
    # exit 0 = every claim reproduced; exit 1 = at least one mismatch (listed)
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EV = ROOT / "docs/implementation/evidence/momentum_daily_stage2_4"
SEAMS = Path(__file__).resolve().parent / "replica_seams.json"


def main() -> int:
    s3 = {c["label"]: c for c in json.loads(
        (EV / "MR_MomentumDaily_Stage3_full.json").read_text(encoding="utf-8"))["configs"]}
    h, e = s3["N5/hyb/nocap"], s3["N5/ew/nocap"]
    cw_h, cw_e = h["crash_windows"], e["crash_windows"]

    claims: list[tuple[str, bool]] = [
        ("S1.4 CAGR hybrid 14.783%", round(h["cagr"] * 100, 3) == 14.783),
        ("S1.4 CAGR equal 14.523%", round(e["cagr"] * 100, 3) == 14.523),
        ("S1.4 dCAGR +26.1 bps", round((h["cagr"] - e["cagr"]) * 1e4, 1) == 26.1),
        ("S1.4 Sharpe hybrid 0.5282", round(h["sharpe"], 4) == 0.5282),
        ("S1.4 Sharpe equal 0.5233", round(e["sharpe"], 4) == 0.5233),
        ("S1.4 dSharpe +0.0049", round(h["sharpe"] - e["sharpe"], 4) == 0.0049),
        ("S1.4 Calmar hybrid 0.1994", round(h["calmar"], 4) == 0.1994),
        ("S1.4 Calmar equal 0.1958", round(e["calmar"], 4) == 0.1958),
        ("S1.4 maxDD hybrid -74.143%", round(h["max_drawdown"] * 100, 3) == -74.143),
        ("S1.4 maxDD equal -74.186%", round(e["max_drawdown"] * 100, 3) == -74.186),
        ("S1.4 turnover hybrid 12.817x", round(h["annualized_turnover"], 3) == 12.817),
        ("S1.4 turnover equal 12.805x", round(e["annualized_turnover"], 3) == 12.805),
        ("S1.4 trades 1378 / 1384", (h["trades"], e["trades"]) == (1378, 1384)),
        ("S1.4 avg holding 31.194d both",
         round(h["avg_holding_days"], 3) == round(e["avg_holding_days"], 3) == 31.194),
        ("S1.4 worst single-name gap -70.260% both",
         round(h["worst_single_name_gap"] * 100, 3)
         == round(e["worst_single_name_gap"] * 100, 3) == -70.260),
        ("S1.4 final equity 1,921,486", round(h["final_equity"]) == 1_921_486),
        ("S1.4 final equity 1,830,097", round(e["final_equity"]) == 1_830_097),
        ("S1.4 d final equity +91,390",
         round(h["final_equity"] - e["final_equity"]) == 91_390),
        ("S1.4 2008 hybrid -57.03%", round(cw_h["2008_gfc"] * 100, 2) == -57.03),
        ("S1.4 2008 equal -56.65%", round(cw_e["2008_gfc"] * 100, 2) == -56.65),
        ("S1.4 2008 delta -38 bps (EQUAL was better)",
         round((cw_h["2008_gfc"] - cw_e["2008_gfc"]) * 1e4) == -38),
        ("S1.4 2020 hybrid +39.59%", round(cw_h["2020_covid"] * 100, 2) == 39.59),
        ("S1.4 2020 equal +39.47%", round(cw_e["2020_covid"] * 100, 2) == 39.47),
        ("S1.4 2022 hybrid -24.76%", round(cw_h["2022_drawdown"] * 100, 2) == -24.76),
        ("S1.4 2022 equal -24.84%", round(cw_e["2022_drawdown"] * 100, 2) == -24.84),
    ]

    if SEAMS.exists():
        five = [r for r in json.loads(SEAMS.read_text(encoding="utf-8"))
                if len(r["weights"]) == 5]
        dev, over, mx = [], 0, []
        for r in five:
            g = r["regime_gross"] or 1.0
            v = [x / g for x in r["weights"].values()]
            if max(v) > 0.20 + 1e-9:
                over += 1
            dev.append(max(abs(x - 0.2) for x in v))
            mx.append(max(v))
        claims += [
            ("S1.3 five-name sessions = 5,393", len(five) == 5393),
            ("S1.3 cap breached on 100% of them", over == len(five)),
            ("S1.3 largest weight 20.594%", round(max(mx) * 100, 3) == 20.594),
            ("S1.3 median |w-0.20| 42.6 bps",
             round(statistics.median(dev) * 1e4, 1) == 42.6),
            ("S1.3 p95 |w-0.20| 155.1 bps",
             round(sorted(dev)[int(0.95 * len(dev))] * 1e4, 1) == 155.1),
            ("S1.3 max |w-0.20| 237.6 bps", round(max(dev) * 1e4, 1) == 237.6),
        ]
    else:
        print(f"  SKIP S1.3 seam claims — {SEAMS.name} not present (gitignored; SHA-bound "
              f"in the findings doc)")

    for name, ok in claims:
        print(f"  {'OK   ' if ok else 'WRONG'} {name}")
    bad = [n for n, ok in claims if not ok]
    print(f"\n{len(claims) - len(bad)}/{len(claims)} claims reproduced from artifacts")
    if bad:
        print("MISMATCHES:")
        for n in bad:
            print(f"  - {n}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
