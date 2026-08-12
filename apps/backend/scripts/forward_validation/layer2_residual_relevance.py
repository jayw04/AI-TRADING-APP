"""Layer 2 Step 3 — DECISION-RELEVANCE assessment for the 21 residual blockers (owner ruling
2026-07-30).

## What this is, and what it is emphatically NOT

⛔ This is NOT an acceptance rule and NOT a general acquisition valuation engine. It does not convert
unsupported M&A semantics into proven reflection, and it relaxes no gate.

It answers a NARROWER question than "has every corporate action been economically reconciled?" — namely
**"is the adjusted price series actually consumed by the July 27 decision internally valid?"** Those are
different claims, and conflating them is precisely the error this file exists to avoid.

## The two residual classes get DIFFERENT governance outcomes

**18 `acquisitionby | delisted` groups.** The vendor schema cannot prove the acquired security's final
economic treatment: there is no per-share consideration, exchange-ratio or successor-conversion field,
and `value` is AGGREGATE TRANSACTION VALUE IN MILLIONS, which cannot supply that proof. They stay
`NOT_PROVEN_UNSUPPORTED_SEMANTICS` unless every one of them is shown to be economically terminal AND
decision-irrelevant, in which case they may be DISCLOSED as `UNRESOLVED_NONDECISION_MA_SEMANTICS`.

⚠ That disclosure is a limitation bound into the countersignature, NOT a proof. If even ONE affects the
July 27 decision path or leaves an unexplained factor movement, the corpus stays blocked.

**3 `listed | spunofffrom | tickerchange` groups.** These are lineage-construction events for the
CHILD security, not one-security price adjustments. They may clear only on positive permanent-identity
evidence, and only when the PARENT's spinoff distribution has already been reconciled — otherwise the
child's listing would be standing in for a parent adjustment nobody verified.

## Every question below is measured, never asserted

The owner's seven questions for the acquisition class and five for the lineage class are each computed
from the store and recorded with their inputs, so the verdict can be re-derived rather than trusted.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402
from app.validation.data_finality import ConstructionSpec  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date
#: The registered selection for the session, re-derived by `layer2_shop_tln_quarantine.py`.
TOP_FIVE = ["AXTI", "SNDK", "BE", "WDC", "MU"]


def _load_residual(path: Path) -> tuple[list[dict], list[dict], dict[str, int]]:
    d = json.loads(path.read_bytes())
    blockers = d["blockers"]
    acq = [b for b in blockers if "acquisitionby" in "|".join(b["action_types"])]
    lin = [b for b in blockers if "spunofffrom" in "|".join(b["action_types"])]
    moves: dict[str, int] = {}
    for u in d.get("unexplained_examples", []):
        moves[u["ticker"]] = moves.get(u["ticker"], 0) + 1
    return acq, lin, moves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--reconciliation", required=True)
    ap.add_argument("--out", required=True)
    add_session_argument(ap)
    args = ap.parse_args()
    global SESSION
    SESSION = args.session

    acq, lin, moves = _load_residual(Path(args.reconciliation))
    spec = ConstructionSpec()
    store = FactorDataStore(args.store, read_only=True)
    con = store.con

    window_desc = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [SESSION, spec.required_history_sessions]).fetchall()]
    window_start = window_desc[-1]
    ma_dates = sorted(window_desc[:spec.regime_ma_sessions])
    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates)
                  or (ma_dates[i + 1].year, ma_dates[i + 1].month) != (d.year, d.month)]

    top200 = set(universe_asof(store, SESSION, n=spec.scoring_universe_n))
    draws = {d: set(universe_asof(store, d, n=spec.proxy_universe_n)) for d in month_ends}
    basket: set[str] = set()
    for s in draws.values():
        basket |= s
    ph = ",".join("?" * len(basket))
    contributors = {r[0] for r in con.execute(
        f"SELECT ticker FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? "
        f"AND closeadj IS NOT NULL GROUP BY ticker HAVING count(DISTINCT date) >= ?",
        [*sorted(basket), ma_dates[0], SESSION, len(ma_dates)]).fetchall()}

    print(f"window {window_start}..{SESSION} ({len(window_desc)} sessions) · "
          f"MA {len(ma_dates)} · month-ends {len(month_ends)}")
    print(f"top-200 scoring universe · proxy basket {len(basket)} · "
          f"final contributors {len(contributors)}\n")

    # ── the 18 acquired-side groups ────────────────────────────────────────────────────────────────
    print("== 18 ACQUIRED-SIDE GROUPS — the owner's seven questions, measured ==")
    hdr = (f"{'ticker':<7}{'effective':<12}{'rows_after':>11}{'last_price':>12}{'in_win':>8}"
           f"{'draws':>7}{'top200':>8}{'contrib':>9}{'top5':>6}{'unexpl':>8}")
    print(hdr)
    print("-" * len(hdr))
    acq_rows: list[dict] = []
    for b in sorted(acq, key=lambda x: x["action_date"]):
        t, eff = b["ticker"], date.fromisoformat(b["action_date"])
        after, last = con.execute(
            "SELECT count(*), max(date) FROM sep WHERE ticker = ? AND date > ?", [t, eff]).fetchone()
        in_win = con.execute(
            "SELECT count(*) FROM sep WHERE ticker = ? AND date BETWEEN ? AND ?",
            [t, window_start, SESSION]).fetchone()[0]
        hit_draws = sorted(d.isoformat() for d, s in draws.items() if t in s)
        rec = {
            "ticker": t, "permaticker": b["permaticker"], "effective_date": eff.isoformat(),
            "action_types": b["action_types"],
            "price_rows_after_effective_date": int(after or 0),
            "last_price_date": last.isoformat() if last else None,
            "price_rows_in_273_session_window": int(in_win),
            "month_end_proxy_draws_entered": hit_draws,
            "in_top_200_scoring_universe": t in top200,
            "contributes_to_final_proxy": t in contributors,
            "in_top_five": t in TOP_FIVE,
            "unexplained_factor_movements": moves.get(t, 0),
        }
        # Economically terminal = the series STOPS at the event. A row after the effective date would
        # mean the history continues past a delisting and therefore needs successor linkage nobody
        # has proven.
        rec["economically_terminal"] = rec["price_rows_after_effective_date"] == 0
        rec["decision_relevant"] = bool(rec["contributes_to_final_proxy"] or rec["in_top_five"]
                                        or rec["unexplained_factor_movements"])
        acq_rows.append(rec)
        print(f"{t:<7}{rec['effective_date']:<12}{rec['price_rows_after_effective_date']:>11}"
              f"{str(rec['last_price_date']):>12}{in_win:>8}{len(hit_draws):>7}"
              f"{str(rec['in_top_200_scoring_universe']):>8}"
              f"{str(rec['contributes_to_final_proxy']):>9}{str(rec['in_top_five']):>6}"
              f"{rec['unexplained_factor_movements']:>8}")

    all_terminal = all(r["economically_terminal"] for r in acq_rows)
    none_relevant = not any(r["decision_relevant"] for r in acq_rows)
    acq_disclosable = all_terminal and none_relevant
    print(f"\n  all economically terminal (no rows after the event) : {all_terminal}")
    print(f"  none decision-relevant                              : {none_relevant}")
    print(f"  => may be DISCLOSED as UNRESOLVED_NONDECISION_MA_SEMANTICS : {acq_disclosable}")
    print("     (a DISCLOSED LIMITATION bound into the countersignature — NOT proven reflection)")

    # ── the 3 lineage-construction groups ──────────────────────────────────────────────────────────
    print("\n== 3 LINEAGE-EVENT GROUPS — positive permanent-identity evidence required ==")
    # The parent whose spinoff distribution was already reconciled, per the Step-3 artifact.
    recon = json.loads(Path(args.reconciliation).read_bytes())
    proven_spinoffs = {(c["ticker"], c["action_date"]) for c in recon["checks"]
                       if c["status"] == "PROVEN_REFLECTED"
                       and "spinoff" in "|".join(c["action_types"])}
    lin_rows: list[dict] = []
    for b in sorted(lin, key=lambda x: x["action_date"]):
        t, eff = b["ticker"], date.fromisoformat(b["action_date"])
        first, last, n = con.execute(
            "SELECT min(date), max(date), count(*) FROM sep WHERE ticker = ?", [t]).fetchone()
        before = con.execute(
            "SELECT count(*) FROM sep WHERE ticker = ? AND date < ?", [t, eff]).fetchone()[0]
        permas = [r[0] for r in con.execute(
            "SELECT DISTINCT permaticker FROM sep WHERE ticker = ?", [t]).fetchall()]
        # The declaring parent: the security whose `spinoff` row names this ticker as contraticker.
        parent = con.execute(
            "SELECT DISTINCT ticker FROM actions WHERE action = 'spinoff' AND contraticker = ? "
            "AND date = ?", [t, eff]).fetchall()
        parents = [p[0] for p in parent]
        parent_proven = all((p, eff.isoformat()) in proven_spinoffs for p in parents) and bool(parents)
        rec = {
            "ticker": t, "permaticker": b["permaticker"], "effective_date": eff.isoformat(),
            "action_types": b["action_types"],
            "first_price_date": first.isoformat() if first else None,
            "last_price_date": last.isoformat() if last else None,
            "total_price_rows": int(n or 0),
            "price_rows_before_effective_date": int(before),
            "distinct_permatickers_in_sep": permas,
            "declaring_parent": parents,
            "parent_spinoff_distribution_already_proven": parent_proven,
            "unexplained_factor_movements": moves.get(t, 0),
        }
        rec["single_permanent_identity"] = len(permas) == 1
        rec["no_predecessor_history_inherited"] = rec["price_rows_before_effective_date"] == 0
        rec["series_begins_at_effective_boundary"] = (first == eff) if first else False
        rec["all_conditions_pass"] = bool(
            rec["single_permanent_identity"] and rec["no_predecessor_history_inherited"]
            and rec["series_begins_at_effective_boundary"]
            and rec["unexplained_factor_movements"] == 0 and parent_proven)
        lin_rows.append(rec)
        print(f"  {t:<6}({rec['permaticker']}) eff {rec['effective_date']}  "
              f"first_price {rec['first_price_date']}  rows_before {before}  "
              f"permatickers {permas}")
        print(f"        parent {parents} spinoff already PROVEN: {parent_proven} · "
              f"unexplained {rec['unexplained_factor_movements']} · "
              f"ALL CONDITIONS PASS: {rec['all_conditions_pass']}")

    lineage_clear = all(r["all_conditions_pass"] for r in lin_rows)
    print(f"\n  => all 3 provable as PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT : "
          f"{lineage_clear}")

    step3_narrow = acq_disclosable and lineage_clear
    print("\n" + "=" * 78)
    print(f"ACQUIRED-SIDE DISCLOSABLE : {acq_disclosable}")
    print(f"LINEAGE EVENTS PROVABLE   : {lineage_clear}")
    print(f"NARROW STEP-3 CLAIM SUPPORTED BY THIS EVIDENCE : {step3_narrow}")
    print("  claim = 'the corpus is valid for the governed July 27 decision, while certain")
    print("           economically terminal acquisition events remain unverifiable from the")
    print("           available vendor schema'")
    print("  ⛔ NOT a claim that all corporate actions are economically reconciled.")

    payload = {
        "kind": "layer2_residual_relevance", "version": "v1.0",
        "session": SESSION.isoformat(), "store": args.store,
        "reconciliation_artifact": args.reconciliation,
        "window": [window_start.isoformat(), SESSION.isoformat(), len(window_desc)],
        "construction": {"scoring_universe_n": spec.scoring_universe_n,
                         "proxy_universe_n": spec.proxy_universe_n,
                         "regime_ma_sessions": spec.regime_ma_sessions,
                         "month_end_draws": len(month_ends),
                         "proxy_basket": len(basket), "final_contributors": len(contributors),
                         "top_five": TOP_FIVE},
        "acquired_side": {
            "count": len(acq_rows), "groups": acq_rows,
            "all_economically_terminal": all_terminal,
            "none_decision_relevant": none_relevant,
            "disclosable_as_unresolved_nondecision_ma_semantics": acq_disclosable,
            "disposition": ("UNRESOLVED_NONDECISION_MA_SEMANTICS" if acq_disclosable
                            else "NOT_PROVEN_UNSUPPORTED_SEMANTICS"),
            "basis": "the vendor schema supplies no per-share consideration, exchange ratio or "
                     "successor conversion term; ACTIONS.value is AGGREGATE TRANSACTION VALUE IN "
                     "MILLIONS and cannot supply that proof",
            "not_a_proof": "this is a DISCLOSED LIMITATION bound into the countersignature, not "
                           "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE and not proven reflection",
        },
        "lineage_events": {
            "count": len(lin_rows), "groups": lin_rows,
            "all_conditions_pass": lineage_clear,
            "disposition": ("PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT" if lineage_clear
                            else "NOT_PROVEN_UNSUPPORTED_SEMANTICS"),
        },
        "narrow_step3_claim_supported": step3_narrow,
        "gates_relaxed": False,
        "general_ma_valuation_engine": "NOT AUTHORIZED AND NOT IMPLEMENTED",
    }
    blob = canonical_json(payload)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)
    print(f"\nresidual_relevance_sha256 : {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {outp}  ({len(blob):,} bytes)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
