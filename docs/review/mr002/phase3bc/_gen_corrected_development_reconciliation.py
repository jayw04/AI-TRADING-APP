"""Corrected-development conformity reconciliation, derived exactly rather than replayed.

The owner authorised a full corrected replay on my report that selection is cross-sectional. That
report was wrong as applied to Phase 2B, and checking it before spending the run is why this file
exists.

`produce_decision` consumes ONE security's data. Its own comment at step 9 reads "no z/percentile/
gap", and the decile selection - bottom/top 10% of the side-eligible pool - lives in
`mr002_valoos_construction._select_side`, which is EVALUATOR/Phase-3C portfolio construction and is
not performed by the Phase 2B stage at all. Phase 2B production is therefore entirely per-unit, and
the corrected development record set is mechanically derivable from the historical outcomes plus the
earnings verdict for each unit.

The cross-sectional concern is real - it just applies one stage later, at 3C, where the eligible
pool determines the deciles.

Because the two controls sit at frozen precedence rank 4, they can only:
  * turn an ELIGIBLE unit INELIGIBLE, or
  * take over as the deciding rule from a rank-5 (liquidity/price) refusal,
and can never reverse a rank<=3 refusal or an integrity stop.

DEVELOPMENT ONLY. Reads historical Phase 2B shard outcomes, the anchors table and the registered
session list. No price, return, residual, z-score or performance. No sealed access.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "apps", "backend"))

from app.research.mr002.phase3b.earnings_blackout import (  # noqa: E402
    BLACKOUT,
    COOLING,
    NO_ANCHOR,
    Anchor,
    Calendar,
    exclusions_for_security,
)

DEV_START, DEV_END = "2013-01-02", "2019-10-02"
DB = os.path.join(_REPO, "apps", "backend", "data", "mr002_research.duckdb")
DB_SHA = "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a"
SHARDS = os.path.join(_REPO, "docs", "review", "mr002", "spq1", "phase2b", "2b2", "shards_*", "*.json")

EMITTED = "SIGNAL_DECISION_RECORD_EMITTED"  # the shard rows' literal disposition value
ELIGIBLE = "ELIGIBLE"


class ReconciliationRefused(Exception):
    """A reconciliation that cannot be produced truthfully."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_historical() -> list[dict]:
    files = sorted(glob.glob(SHARDS))
    if not files:
        raise ReconciliationRefused("no Phase 2B shard outputs found")
    rows: list[dict] = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            rows.extend(json.load(fh)["rows"])
    if not rows:
        raise ReconciliationRefused("shards contain no rows")
    return rows


def load_intervals() -> tuple[dict[str, dict[int, set[str]]], int]:
    import duckdb

    if _sha_file(DB) != DB_SHA:
        raise ReconciliationRefused("research snapshot identity mismatch")
    con = duckdb.connect(DB, read_only=True)
    sessions = [
        str(r[0])
        for r in con.execute(
            f"SELECT DISTINCT date FROM prices WHERE date >= '{DEV_START}' "
            f"AND date <= '{DEV_END}' ORDER BY date"
        ).fetchall()
    ]
    if not sessions or sessions[0] < DEV_START or sessions[-1] > DEV_END:
        raise ReconciliationRefused("session bounds escape the development window")
    calendar = Calendar(tuple(sessions))

    anchors: dict[str, list[Anchor]] = {}
    for ticker, cik, accession, session_date, cls, is_amd in con.execute(
        "SELECT ticker, cik, accession, session_date, availability_class, is_amendment_origin "
        f"FROM anchors WHERE session_date >= '{DEV_START}' AND session_date <= '{DEV_END}'"
    ).fetchall():
        anchors.setdefault(str(ticker), []).append(
            Anchor(int(cik), str(ticker), str(accession), str(session_date), str(cls), bool(is_amd))
        )
    if not anchors:
        raise ReconciliationRefused("no development anchors")

    intervals = {t: exclusions_for_security(a, calendar) for t, a in anchors.items()}
    return intervals, len(sessions)


def reconcile() -> dict:
    rows = load_historical()
    intervals, n_sessions = load_intervals()

    historical = Counter()
    corrected = Counter()
    changed_to_ineligible = 0
    deciding_rule_taken_over = 0
    unchanged = 0
    by_reason = Counter()
    changed_units: list[tuple[str, int, str]] = []
    emitted_eligible_historical = 0
    no_anchor_units = 0

    for row in rows:
        symbol = row["symbol"]
        t = int(row["decision_session"])
        disposition = row["disposition"]
        status = row.get("decision_eligibility_status")
        historical[f"{disposition}|{status}"] += 1

        # The controls are evaluated on the EXECUTION open, t+1.
        reasons = intervals.get(symbol, {}).get(t + 1, set())
        earnings_excludes = bool(reasons & {COOLING, BLACKOUT})
        if NO_ANCHOR in reasons:
            no_anchor_units += 1

        if disposition == EMITTED and status == ELIGIBLE:
            emitted_eligible_historical += 1
            if earnings_excludes:
                changed_to_ineligible += 1
                reason = COOLING if COOLING in reasons else BLACKOUT
                by_reason[reason] += 1
                corrected[f"{EMITTED}|INELIGIBLE"] += 1
                if len(changed_units) < 20:
                    changed_units.append((symbol, t, reason))
                continue
        elif disposition == EMITTED and status and status != ELIGIBLE and earnings_excludes:
            # rank 4 takes over from a rank-5 refusal; disposition unchanged
            deciding_rule_taken_over += 1

        unchanged += 1
        corrected[f"{disposition}|{status}"] += 1

    if not emitted_eligible_historical:
        raise ReconciliationRefused(
            "no historically ELIGIBLE units; the comparison would be vacuous"
        )

    return {
        "units_examined": len(rows),
        "sessions": n_sessions,
        "historical_outcome_counts": dict(sorted(historical.items())),
        "corrected_outcome_counts": dict(sorted(corrected.items())),
        "historically_emitted_eligible": emitted_eligible_historical,
        "now_ineligible_under_the_frozen_controls": changed_to_ineligible,
        "share_of_historically_eligible_removed": round(
            changed_to_ineligible / emitted_eligible_historical, 6
        ),
        "attribution": {
            "post_release_cooling": by_reason[COOLING],
            "stale_anchor_blackout": by_reason[BLACKOUT],
        },
        "deciding_rule_taken_over_from_rank5": deciding_rule_taken_over,
        "units_unchanged": unchanged,
        "units_flagged_no_prior_anchor": no_anchor_units,
        "sample_changed_units": [
            {"symbol": s, "decision_session": t, "reason": r} for s, t, r in changed_units
        ],
    }


def main() -> None:
    result = reconcile()
    record = {
        "record_type": "MR002_Phase3B_CorrectedDevelopmentReconciliation",
        "version": "1.0",
        "artifact_kind": "CONFORMITY_RECONCILIATION",
        "date": "2026-08-12",
        "method": "EXACT DERIVATION, not a producer replay",
        "why_derivation_is_exact": (
            "Phase 2B production is per-unit: produce_decision consumes one security's data and its "
            "own step-9 comment reads 'no z/percentile/gap'. The decile selection lives in "
            "mr002_valoos_construction._select_side, which is Phase-3C portfolio construction and is "
            "not performed by the Phase 2B stage. The two controls sit at frozen precedence rank 4, "
            "so they can only turn an ELIGIBLE unit INELIGIBLE or take over as the deciding rule "
            "from a rank-5 refusal; they can never reverse a rank<=3 refusal or an integrity stop."
        ),
        "corrects_my_earlier_report": (
            "I previously concluded a full corrected replay was REQUIRED because selection is "
            "cross-sectional. That is true of Phase 3C, not of the Phase 2B stage this "
            "reconciliation covers. Checking it before spending the run is why this is a derivation."
        ),
        "boundary": (
            f"DEVELOPMENT ONLY, {DEV_START}..{DEV_END}. Historical Phase 2B shard outcomes, the "
            "anchors table and the registered session list. No price, return, residual, z-score or "
            "performance. No sealed object, no credential; the validation opening remains UNSPENT."
        ),
        "controls_evaluated_on": "the EXECUTION open t+1, matching the frozen cooling wording",
        "results": result,
        "record_identity_note": (
            "Record identities necessarily change for EVERY unit under the correction, because the "
            "eligibility evidence trail gains two rules and eligibility_evidence_identity hashes "
            "that trail. Structural reconciliation therefore compares DISPOSITIONS and CODES, never "
            "record identities."
        ),
        "grants": "NOTHING. Evidence only.",
    }
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_CorrectedDevelopmentReconciliation_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    r = result
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"units examined            {r['units_examined']:,}")
    print(f"historically EMITTED+ELIGIBLE {r['historically_emitted_eligible']:,}")
    print(f"now INELIGIBLE                {r['now_ineligible_under_the_frozen_controls']:,} "
          f"({r['share_of_historically_eligible_removed']:.1%} of historically eligible)")
    print(f"  cooling {r['attribution']['post_release_cooling']:,}   "
          f"blackout {r['attribution']['stale_anchor_blackout']:,}")
    print(f"deciding rule taken over from rank5 {r['deciding_rule_taken_over_from_rank5']:,}")
    print(f"historical outcomes {r['historical_outcome_counts']}")


if __name__ == "__main__":
    main()
