"""Structural census of the two frozen earnings controls over the DEVELOPMENT window.

Value- and performance-blind by construction: it reads anchors, the registered session list and the
universe. It never reads a price, a return, a residual or a z-score, and it computes no performance.
Its only question is how much of the development window the two frozen controls would have
excluded, had either ever been implemented.

DEVELOPMENT PARTITION ONLY, hard-bounded, with the observed range asserted inside the bounds before
any result is used. Validation and OOS are never queried; the sealed store is never touched.

This is deliberately cheaper than a corrected producer replay. The controls only REMOVE eligibility,
so their structural footprint answers most of what a replay would, without recomputing economics.
Records that Phase 2B emitted and these controls would have blocked are reported as exactly that -
"historically emitted candidates that would have been eligibility-blocked" - not as corrected
producer output, which is not knowable without the replay.
"""

from __future__ import annotations

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


class CensusRefused(Exception):
    """A census that cannot be produced truthfully."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run() -> dict:
    import duckdb

    if _sha_file(DB) != DB_SHA:
        raise CensusRefused("the research snapshot does not reproduce its registered identity")
    con = duckdb.connect(DB, read_only=True)

    sessions = [
        str(r[0])
        for r in con.execute(
            f"SELECT DISTINCT date FROM prices WHERE date >= '{DEV_START}' "
            f"AND date <= '{DEV_END}' ORDER BY date"
        ).fetchall()
    ]
    if not sessions or sessions[0] < DEV_START or sessions[-1] > DEV_END:
        raise CensusRefused(f"session bounds escape the development window: {sessions[:1]}")
    calendar = Calendar(tuple(sessions))

    rows = con.execute(
        "SELECT ticker, cik, accession, session_date, availability_class, "
        "is_amendment_origin, amended_by, collapsed_duplicates FROM anchors "
        f"WHERE session_date >= '{DEV_START}' AND session_date <= '{DEV_END}'"
    ).fetchall()
    if not rows:
        raise CensusRefused("no development-window anchors; an empty census proves nothing")
    dates = [str(r[3]) for r in rows]
    if min(dates) < DEV_START or max(dates) > DEV_END:
        raise CensusRefused("BOUND VIOLATION in the anchor query")

    by_ticker: dict[str, list[Anchor]] = {}
    classes, amendment_origin = Counter(), 0
    amended, collapsed = 0, 0
    for ticker, cik, accession, session_date, cls, is_amd, amended_by, dups in rows:
        by_ticker.setdefault(str(ticker), []).append(
            Anchor(int(cik), str(ticker), str(accession), str(session_date), str(cls), bool(is_amd))
        )
        classes[str(cls)] += 1
        amendment_origin += 1 if is_amd else 0
        amended += 1 if amended_by not in (None, "", "[]", "null") else 0
        collapsed += 1 if dups not in (None, "", "[]", "null") else 0

    universe = {
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT ticker FROM universe WHERE universe_month >= '2013-01-01' "
            "AND universe_month <= '2019-10-01'"
        ).fetchall()
    }

    cooling_units = blackout_units = both_units = 0
    securities_with_exclusions = 0
    per_ticker: dict[str, dict[str, int]] = {}
    for ticker, anchors in sorted(by_ticker.items()):
        reasons = exclusions_for_security(anchors, calendar)
        c = sum(1 for r in reasons.values() if COOLING in r)
        b = sum(1 for r in reasons.values() if BLACKOUT in r)
        both = sum(1 for r in reasons.values() if COOLING in r and BLACKOUT in r)
        cooling_units += c
        blackout_units += b
        both_units += both
        if c or b:
            securities_with_exclusions += 1
        per_ticker[ticker] = {"cooling": c, "blackout": b}

    universe_without_anchor = sorted(universe - set(by_ticker))
    total_units = len(by_ticker) * len(sessions)

    return {
        "window": {"start": DEV_START, "end": DEV_END, "sessions": len(sessions),
                   "observed_first": sessions[0], "observed_last": sessions[-1]},
        "anchors": {
            "total": len(rows),
            "securities_with_anchors": len(by_ticker),
            "by_availability_class": dict(sorted(classes.items())),
            "amendment_without_original": amendment_origin,
            "rows_carrying_matching_amendments": amended,
            "rows_carrying_collapsed_duplicates": collapsed,
        },
        "universe": {
            "distinct_tickers": len(universe),
            "in_universe_without_any_anchor": len(universe_without_anchor),
            "sample_without_anchor": universe_without_anchor[:10],
        },
        "exclusion_units": {
            "denominator_security_sessions": total_units,
            "post_release_cooling": cooling_units,
            "stale_anchor_blackout": blackout_units,
            "both_controls_same_unit": both_units,
            "union": cooling_units + blackout_units - both_units,
            "union_share_of_denominator": round(
                (cooling_units + blackout_units - both_units) / total_units, 6
            )
            if total_units
            else None,
            "securities_with_at_least_one_exclusion": securities_with_exclusions,
        },
        "per_security_hash": hashlib.sha256(
            json.dumps(per_ticker, sort_keys=True).encode()
        ).hexdigest(),
    }


def main() -> None:
    result = run()
    record = {
        "record_type": "MR002_Phase3B_EarningsControlStructuralCensus",
        "version": "1.0",
        "artifact_kind": "STRUCTURAL_CENSUS",
        "date": "2026-08-12",
        "purpose": (
            "Measure the structural footprint of the two frozen earnings controls on the "
            "DEVELOPMENT window, neither of which Phase 2B implemented."
        ),
        "boundary": (
            f"DEVELOPMENT ONLY, hard-bounded {DEV_START}..{DEV_END} with the observed range "
            "asserted inside the bounds. Value- and performance-blind: no price, return, residual "
            "or z-score is read and no performance is computed. No sealed object, no credential; "
            "the validation opening remains UNSPENT."
        ),
        "controls": {
            "post_release_cooling": "v0.4 frozen wording; session mapping corrected by v0.5 §1",
            "stale_anchor_blackout": "v0.4 V1; 70 calendar days, adjudicated inclusive 2026-08-12",
            "kept_separate": "the deciding reason is preserved per (security, session); the two "
                             "controls are never collapsed into one boolean",
        },
        "phase2b_state": (
            "Neither control fired. cooling_start_session/cooling_end_session are declared and "
            "never assigned - 0 of 399 populated in the provenance table - so both consumers "
            "computed excludes=False, and the 2B-2 refusal census contains no event_blackout "
            "outcome at all."
        ),
        "interpretation_limit": (
            "These are historically emitted candidates that WOULD have been eligibility-blocked "
            "under the frozen controls. They are NOT corrected producer output: the corrected "
            "record set is not knowable without a replay."
        ),
        "snapshot": {"path": "apps/backend/data/mr002_research.duckdb", "sha256": DB_SHA},
        "results": result,
        "grants": "NOTHING. Evidence only.",
    }
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_EarningsControlStructuralCensus_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    r = result
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"sessions {r['window']['sessions']}  anchors {r['anchors']['total']}  "
          f"securities {r['anchors']['securities_with_anchors']}")
    print(f"classes {r['anchors']['by_availability_class']}")
    print(f"amendment_without_original {r['anchors']['amendment_without_original']}  "
          f"matching-amended {r['anchors']['rows_carrying_matching_amendments']}  "
          f"collapsed-dups {r['anchors']['rows_carrying_collapsed_duplicates']}")
    e = r["exclusion_units"]
    print(f"cooling {e['post_release_cooling']:,}  blackout {e['stale_anchor_blackout']:,}  "
          f"overlap {e['both_controls_same_unit']:,}  union {e['union']:,} "
          f"({e['union_share_of_denominator']:.1%} of {e['denominator_security_sessions']:,})")


if __name__ == "__main__":
    main()
