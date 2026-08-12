"""Layer 2 Step 3 — the COMPLETE, uncapped adjustment reconciliation.

Proves that the rebuilt adjusted series reflects every declared corporate action over the session's
relevance window, and that no adjustment in the series is unexplained.

## The two caps are different things, and only one is lifted

`MAX_EVIDENCE_ACTIONS` / `MAX_EVIDENCE_SERIALIZED_BYTES` bound what gets EMBEDDED IN AN IMMUTABLE
OBSERVATION. That is a legitimate production control: an observation is written once and forever, and
an unbounded payload is a size no one chose. This diagnostic needs every relevant action represented in
machine-readable evidence, which is a different requirement from the observation payload.

So the caps are raised **for this process only**, by rebinding the module constants in this runner. The
product defaults are NOT edited, and the original values are recorded in the artifact alongside the
raised ones so a reader can see exactly what was relaxed and that it was a diagnostic, not a change to
production observation-size controls.

## The relevance set

Copied from what `data_finality` actually assembles, because a reconciliation over a narrower set would
prove less than the session requires: the top-200 scoring candidates over the 273-session history
window, UNION the WHOLE month-end proxy basket over the 200-session MA window — including names that
left the universe mid-window, since they still priced into the consumed history.

## Verdict handling

`PROVEN` and `NO_RELEVANT_ACTIONS` are terminal successes. `INTEGRITY_STOP_CONFLICT`,
`NOT_PROVEN_INSUFFICIENT_DATA` and `NOT_PROVEN_UNSUPPORTED_ACTION` are BLOCKERS and every instance is
listed in full — never sampled, never summarised away.
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
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402
from app.validation import adjustment_verifier as av  # noqa: E402
from app.validation.data_finality import ConstructionSpec  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402
from app.validation.security_lineage import SessionLineageFilter  # noqa: E402
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date

#: Diagnostic-only ceilings. Large enough that no relevant action can be dropped, and asserted below to
#: have actually bound nothing.
DIAG_MAX_ACTIONS = 1_000_000
DIAG_MAX_BYTES = 512 * 1024 * 1024

TERMINAL_OK = {"PROVEN", "NO_RELEVANT_ACTIONS"}


def _check_json(c) -> dict:
    """One check, with every enum rendered as its string value so the artifact is plain JSON."""
    return asdict(c) | {
        "action_class": str(c.action_class), "verdict": str(c.verdict), "status": str(c.status),
        "applicability": str(c.applicability),
        "duplicate_disposition": str(c.duplicate_disposition),
        "action_types": list(c.action_types),
        "source_csv_line_numbers": list(c.source_csv_line_numbers),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--residual-relevance",
                    help="layer2_residual_relevance.json. Supplies the EXTERNAL decision-irrelevance "
                         "finding for economically terminal acquired-side events. ⚠ A DISCLOSURE, NOT "
                         "A PROOF: the verifier still cross-checks that each subject is terminal and "
                         "movement-free, and the resulting status does NOT satisfy readiness.")
    add_session_argument(ap)
    args = ap.parse_args()
    global SESSION
    SESSION = args.session

    disclosure = None
    if args.residual_relevance:
        rr_bytes = Path(args.residual_relevance).read_bytes()
        rr = json.loads(rr_bytes)
        acq = rr["acquired_side"]
        if not acq["disclosable_as_unresolved_nondecision_ma_semantics"]:
            print("residual-relevance assessment does NOT support disclosure — supplying none")
        else:
            disclosure = av.NonDecisionMADisclosure(
                assessment_artifact_sha256=hashlib.sha256(rr_bytes).hexdigest(),
                entries=frozenset((g["permaticker"], date.fromisoformat(g["effective_date"]))
                                  for g in acq["groups"]))
            print(f"non-decision M&A disclosure: {len(disclosure.entries)} acquired-side event(s), "
                  f"assessment {disclosure.assessment_artifact_sha256[:16]}…")

    prod_caps = {"MAX_EVIDENCE_ACTIONS": av.MAX_EVIDENCE_ACTIONS,
                 "MAX_EVIDENCE_SERIALIZED_BYTES": av.MAX_EVIDENCE_SERIALIZED_BYTES}
    print(f"production observation-payload caps (UNCHANGED in the product): {prod_caps}")

    spec = ConstructionSpec()
    store = FactorDataStore(args.store, read_only=True)
    con = store.con

    window_desc = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [SESSION, spec.required_history_sessions]).fetchall()]
    history_start = window_desc[-1]
    ma_dates = sorted(window_desc[:spec.regime_ma_sessions])

    # ---- relevance set, exactly as data_finality assembles it ----
    lineage = SessionLineageFilter(store, session_date=SESSION, lookback_start=history_start)
    scoring = lineage.filter(list(universe_asof(store, SESSION, n=spec.scoring_universe_n)))
    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates)
                  or (ma_dates[i + 1].year, ma_dates[i + 1].month) != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        basket |= set(universe_asof(store, d, n=spec.proxy_universe_n))
    relevant = sorted(set(scoring) | basket)
    print(f"relevance set: {len(scoring)} scoring + {len(basket)} proxy basket -> "
          f"{len(relevant)} distinct tickers")

    # ---- the declared, authoritative action source ----
    cov = con.execute("SELECT min(date), max(date), count(*) FROM actions").fetchone()
    src = av.ActionSourceDeclaration(
        identity=("SHARADAR/ACTIONS|layer2 single-vintage reconstruction|"
                  "HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE"),
        authoritative=True, coverage_start=cov[0], coverage_end=cov[1])
    print(f"action source: authoritative, coverage {cov[0]}..{cov[1]} ({int(cov[2]):,} rows)")

    # ---- raise the caps for THIS PROCESS ONLY ----
    av.MAX_EVIDENCE_ACTIONS = DIAG_MAX_ACTIONS
    av.MAX_EVIDENCE_SERIALIZED_BYTES = DIAG_MAX_BYTES

    ev = av.verify_adjustments(
        store, window_start=history_start, session_date=SESSION,
        relevant_tickers=relevant, source=src,
        store_identity_sha256="layer2-step3-diagnostic", max_examples=10_000,
        ma_disclosure=disclosure)

    # Restore immediately, so nothing later in this process can observe a relaxed control.
    av.MAX_EVIDENCE_ACTIONS = prod_caps["MAX_EVIDENCE_ACTIONS"]
    av.MAX_EVIDENCE_SERIALIZED_BYTES = prod_caps["MAX_EVIDENCE_SERIALIZED_BYTES"]
    store.con.close()

    be = ev.action_evidence
    truncated = bool(getattr(be, "truncated", False))
    included = len(ev.checks)

    # ---- reconciliation table: action class x TERMINAL STATUS ----
    #
    # Keyed on the six terminal per-action statuses, not on the window verdict: the window verdict is a
    # roll-up and cannot show that (say) a group cleared via a NAMED no-adjustment rule rather than by
    # reconciling an arithmetic action.
    table: dict[str, dict[str, int]] = {}
    for c in ev.checks:
        table.setdefault(str(c.action_class), {})
        k = str(c.status)
        table[str(c.action_class)][k] = table[str(c.action_class)].get(k, 0) + 1

    statuses = sorted({str(c.status) for c in ev.checks})
    print(f"\nverdict          : {ev.verdict}  (proven={ev.proven})")
    print(f"actions in window: {ev.total_actions_in_window:,} total | "
          f"{ev.relevant_actions_in_window:,} relevant | "
          f"{ev.irrelevant_actions_in_window:,} irrelevant")
    print(f"(ticker,date) checks: {included:,}   truncated={truncated}")

    cen = ev.factor_census
    print("\n-- direction (b): undeclared FACTOR MOVEMENTS, per factor --")
    print(f"  dividend-factor only   : {cen.undeclared_dividend_factor_changes:,}")
    print(f"  split-factor only      : {cen.undeclared_split_factor_changes:,}")
    print(f"  combined / ambiguous   : {cen.combined_or_ambiguous_changes:,}")
    print(f"  explained (dividend)   : {cen.explained_dividend_factor_sessions:,}")
    print(f"  explained (split)      : {cen.explained_split_factor_sessions:,}")
    print(f"  session pairs examined : {cen.session_pairs_examined:,} over "
          f"{cen.identities_examined:,} permanent identities")
    print(f"  unresolved identities  : {cen.unresolved_identity_count:,}")

    w = max((len(v) for v in statuses), default=10)
    print(f"\n{'action class':<22}" + "".join(f"{v:>{w + 2}}" for v in statuses) + f"{'TOTAL':>9}")
    for klass in sorted(table):
        row = table[klass]
        print(f"{klass:<22}" + "".join(f"{row.get(v, 0):>{w + 2},}" for v in statuses)
              + f"{sum(row.values()):>9,}")
    print(f"{'TOTAL':<22}"
          + "".join(f"{sum(t.get(v, 0) for t in table.values()):>{w + 2},}" for v in statuses)
          + f"{included:>9,}")

    print("\n-- how each cleared group left the default-deny status --")
    for code, n in sorted(ev.checks_by_reason_code.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>6,}  {code}")

    dupes = [c for c in ev.checks
             if str(c.duplicate_disposition) != "SINGLE_SOURCE_ROW"]
    print(f"\n-- duplicate canonicalization: {len(dupes):,} group(s) --")
    dd: dict[str, int] = {}
    for c in dupes:
        dd[str(c.duplicate_disposition)] = dd.get(str(c.duplicate_disposition), 0) + 1
    for k, n in sorted(dd.items()):
        print(f"  {n:>6,}  {k}")

    blockers = [c for c in ev.checks if c.status not in av.SATISFIES_READINESS]
    print(f"\nBLOCKERS (every relevant action not in a readiness-satisfying status): {len(blockers):,}")
    for c in blockers:
        print(f"  ! {c.ticker:<8} ({c.permaticker}) {c.action_date} {str(c.action_class):<22} "
              f"{c.status}")
        print(f"      types={c.action_types} expected={c.expected_ratio} observed={c.observed_ratio} "
              f"rel_resid={c.relative_residual}")
        print(f"      {c.detail[:150]}")
    if ev.unexplained_examples:
        print(f"\nUNEXPLAINED FACTOR MOVEMENTS ({len(ev.unexplained_examples)}):")
        for u in ev.unexplained_examples[:50]:
            print(f"  ! {u.ticker:<8} ({u.permaticker}) {u.session_date} {str(u.factor):<22} "
                  f"D={u.dividend_factor_ratio} S={u.split_factor_ratio} "
                  f"resid={u.absolute_residual:.3e} tol={u.relative_tolerance:.3e}")

    # ---- completeness proof: every relevant action must be represented ----
    complete = (not truncated) and included > 0
    payload = {
        "kind": "layer2_adjustment_reconciliation", "version": "v1.0",
        "generated_utc": datetime.now(UTC).isoformat(),
        "store": args.store,
        "session_date": SESSION.isoformat(),
        "window": [history_start.isoformat(), SESSION.isoformat(), len(window_desc)],
        "relevance": {"scoring": len(scoring), "proxy_basket": len(basket),
                      "distinct_tickers": len(relevant), "month_ends": len(month_ends)},
        "caps": {
            "production_observation_payload_caps_unchanged": prod_caps,
            "diagnostic_caps_applied_to_this_process_only":
                {"MAX_EVIDENCE_ACTIONS": DIAG_MAX_ACTIONS,
                 "MAX_EVIDENCE_SERIALIZED_BYTES": DIAG_MAX_BYTES},
            "selection_truncated": truncated,
            "note": ("the observation-payload cap is a production control on an immutable record and "
                     "was NOT modified; it was rebound in this diagnostic process only, and restored "
                     "immediately after the verification call"),
        },
        "verdict": str(ev.verdict),
        "proven": ev.proven,
        "adjustment_series_consistent_with_declared_actions":
            ev.adjustment_series_consistent_with_declared_actions,
        "declared_action_source_authoritative": ev.declared_action_source_authoritative,
        "source_identity": ev.source_identity,
        "source_coverage": [ev.source_coverage_start, ev.source_coverage_end],
        "total_actions_in_window": ev.total_actions_in_window,
        "relevant_actions_in_window": ev.relevant_actions_in_window,
        "irrelevant_actions_in_window": ev.irrelevant_actions_in_window,
        "relevant_ticker_count": ev.relevant_ticker_count,
        "relevance_set_sha256": ev.relevance_set_sha256,
        "checks_by_verdict": ev.checks_by_verdict,
        "checks_by_status": ev.checks_by_status,
        "checks_by_applicability": ev.checks_by_applicability,
        "checks_by_reason_code": ev.checks_by_reason_code,
        "factor_census": asdict(cen),
        "checks_included": included,
        "every_relevant_action_represented": complete,
        "unexplained_adjustment_count": ev.unexplained_adjustment_count,
        "tolerance": ev.tolerance,
        "reconciliation_table": table,
        "blockers": [_check_json(c) for c in blockers],
        "checks": [_check_json(c) for c in ev.checks],
        "unexplained_examples": [asdict(u) | {"factor": str(u.factor)}
                                 for u in ev.unexplained_examples],
        "detail": ev.detail,
    }
    blob = canonical_json(payload)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()

    print(f"\nevery relevant action represented (selection not truncated): {complete}")
    print(f"adjustment_reconciliation_sha256 : {digest}")
    print(f"wrote {outp}  ({len(blob):,} bytes)")

    ok = (ev.proven and not blockers and complete and ev.unexplained_adjustment_count == 0)
    print(f"\nVERDICT: {'RECONCILED' if ok else 'BLOCKED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
