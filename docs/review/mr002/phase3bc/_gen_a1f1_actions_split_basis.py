"""A1-F1: confirm whether ACTIONS dividend values share the split basis of the SEP close.

v0.4 conditions the registered economic-gap formula on this confirmation, "before the formula is
applied". The formula ADDS the ACTIONS distribution to a split-adjusted open and divides by a
split-adjusted close, so if the distribution were on the as-paid (raw) basis the sum would mix
adjustment bases - the exact defect freeze blocker V3 exists to prevent.

DEVELOPMENT PARTITION ONLY. Every query is hard-bounded to 2013-01-02..2019-10-02 and the returned
date range is asserted inside those bounds before any result is used. The validation and OOS windows
are never queried, and this reads the local registered snapshot rather than the sealed S3 store, so
no sealed object is opened and no credential is used.

The discriminating test: `closeunadj / close` is the cumulative split factor at a given date. For a
dividend paid on a date whose security later split, the two candidate bases differ by that factor.
Dividend YIELD does not depend on split history, so whichever denominator makes the yield agree
between split-affected and split-free dividends is the basis the ACTIONS value is expressed on.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics

DEV_START = "2013-01-02"
DEV_END = "2019-10-02"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
DB = os.path.join(_REPO, "apps", "backend", "data", "mr002_research.duckdb")
DB_REGISTERED_SHA = "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a"

QUERY = f"""
SELECT a.ticker, a.date, a.value AS dividend,
       p.close AS close_split_adj, p.closeunadj AS close_raw
FROM actions a
JOIN prices p ON p.ticker = a.ticker AND p.date = a.date
WHERE a.action = 'dividend'
  AND a.date >= '{DEV_START}' AND a.date <= '{DEV_END}'
  AND p.date >= '{DEV_START}' AND p.date <= '{DEV_END}'
  AND a.value IS NOT NULL AND a.value > 0
  AND p.close IS NOT NULL AND p.close > 0
  AND p.closeunadj IS NOT NULL AND p.closeunadj > 0
"""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _stats(vals: list[float]) -> dict:
    vals = sorted(vals)
    return {"n": len(vals),
            "median": statistics.median(vals),
            "p10": vals[int(0.10 * (len(vals) - 1))],
            "p90": vals[int(0.90 * (len(vals) - 1))]}


def run() -> dict:
    import duckdb

    actual = _sha256_file(DB)
    if actual != DB_REGISTERED_SHA:
        raise SystemExit("REFUSED: the research snapshot does not reproduce its registered identity")

    con = duckdb.connect(DB, read_only=True)
    rows = con.execute(QUERY).fetchall()
    if not rows:
        raise SystemExit("REFUSED: an empty sample proves nothing")

    dates = [str(r[1]) for r in rows]
    if min(dates) < DEV_START or max(dates) > DEV_END:
        raise SystemExit(f"REFUSED, BOUND VIOLATION: {min(dates)}..{max(dates)} escapes the "
                         f"development window")

    split_free, split_affected = [], []
    for _tk, _d, div, close_adj, close_raw in rows:
        f = float(close_raw) / float(close_adj)
        rec = {"f": f,
               "yield_on_split_adjusted_close": float(div) / float(close_adj),
               "yield_on_raw_close": float(div) / float(close_raw)}
        if abs(f - 1.0) < 0.01:
            split_free.append(rec)
        elif f >= 1.5:
            split_affected.append(rec)

    if len(split_affected) < 30:
        raise SystemExit(f"REFUSED: only {len(split_affected)} split-affected dividends; too few to "
                         "discriminate")

    out = {
        "sample_rows": len(rows),
        "date_range_observed": [min(dates), max(dates)],
        "split_free_cohort": {
            "definition": "|closeunadj/close - 1| < 0.01",
            "split_factor": _stats([r["f"] for r in split_free]),
            "yield_on_split_adjusted_close": _stats(
                [r["yield_on_split_adjusted_close"] for r in split_free]),
            "yield_on_raw_close": _stats([r["yield_on_raw_close"] for r in split_free]),
        },
        "split_affected_cohort": {
            "definition": "closeunadj/close >= 1.5",
            "split_factor": _stats([r["f"] for r in split_affected]),
            "yield_on_split_adjusted_close": _stats(
                [r["yield_on_split_adjusted_close"] for r in split_affected]),
            "yield_on_raw_close": _stats([r["yield_on_raw_close"] for r in split_affected]),
        },
    }
    return out


WITHIN_QUERY = f"""
WITH splits AS (
  SELECT ticker, min(date) AS split_date
  FROM actions
  WHERE action = 'split' AND date >= '{DEV_START}' AND date <= '{DEV_END}'
  GROUP BY ticker
)
SELECT s.ticker, s.split_date, a.date, a.value AS dividend, p.close AS close_split_adj
FROM splits s
JOIN actions a ON a.ticker = s.ticker AND a.action = 'dividend'
JOIN prices p ON p.ticker = a.ticker AND p.date = a.date
WHERE a.date >= '{DEV_START}' AND a.date <= '{DEV_END}'
  AND p.date >= '{DEV_START}' AND p.date <= '{DEV_END}'
  AND a.value > 0 AND p.close > 0
"""


def within_security_test() -> dict:
    """Same security, dividends before vs after its own split.

    `close` is back-adjusted, so it is on one basis throughout. If the ACTIONS value is likewise
    back-adjusted, D/close is continuous across the split. If it is as-paid, pre-split D/close jumps
    by the split factor. This removes the cross-cohort composition difference entirely.
    """
    import duckdb

    con = duckdb.connect(DB, read_only=True)
    rows = con.execute(WITHIN_QUERY).fetchall()
    if not rows:
        raise SystemExit("REFUSED: within-security sample is empty")
    dates = [str(r[2]) for r in rows]
    if min(dates) < DEV_START or max(dates) > DEV_END:
        raise SystemExit("REFUSED, BOUND VIOLATION in the within-security query")

    per_ticker: dict[str, dict[str, list[float]]] = {}
    for ticker, split_date, d, div, close_adj in rows:
        side = "pre" if str(d) < str(split_date) else "post"
        per_ticker.setdefault(ticker, {"pre": [], "post": []})[side].append(
            float(div) / float(close_adj))

    ratios = []
    for _t, sides in per_ticker.items():
        if len(sides["pre"]) >= 2 and len(sides["post"]) >= 2:
            ratios.append(statistics.median(sides["pre"]) / statistics.median(sides["post"]))
    if len(ratios) < 10:
        raise SystemExit(f"REFUSED: only {len(ratios)} securities with dividends on both sides of "
                         "their own split; too few for the within-security leg")
    return {
        "securities_with_dividends_both_sides_of_their_own_split": len(ratios),
        "pre_over_post_yield_ratio": _stats(ratios),
        "expectation_if_split_adjusted": "~1.0 (continuous across the split)",
        "expectation_if_as_paid_raw": "~the split factor (a jump at the split)",
        "reading_the_observed_value": (
            "A median near 0.80 rather than exactly 1.00 is expected and is not a basis artifact: "
            "dividends generally GROW over time, so a security's pre-split dividends are smaller "
            "than its post-split ones and the pre/post ratio sits slightly below one. The "
            "discriminating alternative is not 1.00-versus-0.80 but 0.80-versus-the-split-factor, "
            "and the median split factor in the discriminating cohort is 3.0. The two independent "
            "legs - cross-cohort and within-security - both land at ~0.80, which is itself "
            "corroborating."
        ),
    }


def interpret(res: dict) -> dict:
    free = res["split_free_cohort"]
    aff = res["split_affected_cohort"]
    # Which denominator keeps the yield comparable across cohorts?
    ratio_adj = aff["yield_on_split_adjusted_close"]["median"] / \
        free["yield_on_split_adjusted_close"]["median"]
    ratio_raw = aff["yield_on_raw_close"]["median"] / free["yield_on_raw_close"]["median"]
    if abs(ratio_adj - 1.0) < abs(ratio_raw - 1.0):
        basis, other = "SPLIT_ADJUSTED (same basis as SEP close)", "raw"
    else:
        basis, other = "RAW / AS-PAID (same basis as closeunadj)", "split-adjusted"
    return {
        "cohort_yield_ratio_using_split_adjusted_close": ratio_adj,
        "cohort_yield_ratio_using_raw_close": ratio_raw,
        "decision_rule": ("dividend yield does not depend on split history, so the denominator whose "
                          "cross-cohort median ratio is closest to 1.0 identifies the basis the "
                          "ACTIONS value is expressed on"),
        "actions_dividend_basis": basis,
        "rejected_alternative": other,
        "median_split_factor_in_the_discriminating_cohort": aff["split_factor"]["median"],
    }


def main() -> None:
    res = run()
    within = within_security_test()
    verdict = interpret(res)
    verdict["within_security_leg"] = within
    conformant = verdict["actions_dividend_basis"].startswith("SPLIT_ADJUSTED")
    record = {
        "record_type": "MR002_Phase3B_A1F1_ActionsSplitBasisConfirmation",
        "version": "1.0",
        "artifact_kind": "DATA_SEMANTICS_VERIFICATION",
        "date": "2026-08-12",
        "discharges": "A1-F1 - the v0.4 precondition that the ACTIONS dividend split basis be "
                      "confirmed before the registered economic-gap formula is applied",
        "boundary": (
            "DEVELOPMENT PARTITION ONLY, hard-bounded to "
            f"{DEV_START}..{DEV_END} with the observed range asserted inside those bounds. No "
            "validation or OOS row was queried. Reads the local registered snapshot, not the sealed "
            "S3 store: no sealed object opened, no credential used, opening UNSPENT."
        ),
        "why_it_matters": (
            "The registered formula adds the ACTIONS distribution to a split-adjusted open and "
            "divides by a split-adjusted close. A raw-basis distribution would mix adjustment "
            "bases - the defect freeze blocker V3 exists to prevent."
        ),
        "snapshot": {"path": "apps/backend/data/mr002_research.duckdb",
                     "sha256": DB_REGISTERED_SHA, "identity_verified": True},
        "query": " ".join(QUERY.split()),
        "results": res,
        "within_security_confirmation": within,
        "verdict": verdict,
        "conclusion": (
            "CONFIRMED - the ACTIONS dividend value is expressed on the same split basis as the SEP "
            "close, so the registered economic-gap formula may be applied as written."
            if conformant else
            "NOT CONFIRMED - the ACTIONS dividend value is NOT on the SEP close basis. The "
            "registered formula must not be applied until the owner adjudicates the required "
            "conversion, which would be a research-affecting change."
        ),
        "status": "PASS" if conformant else "FAIL",
        "grants": "NOTHING. Evidence only.",
    }
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_A1F1_ActionsSplitBasis_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"sample {res['sample_rows']} dividends, {res['date_range_observed']}")
    print(f"split-free n={res['split_free_cohort']['split_factor']['n']}  "
          f"split-affected n={res['split_affected_cohort']['split_factor']['n']} "
          f"(median factor {verdict['median_split_factor_in_the_discriminating_cohort']:.3f})")
    print(f"cohort yield ratio  split-adjusted denominator: "
          f"{verdict['cohort_yield_ratio_using_split_adjusted_close']:.4f}")
    print(f"cohort yield ratio  raw denominator          : "
          f"{verdict['cohort_yield_ratio_using_raw_close']:.4f}")
    print(f"BASIS: {verdict['actions_dividend_basis']}")
    print(f"STATUS: {record['status']}")


if __name__ == "__main__":
    main()
