"""Layer 2 — the countersignable PRICE-BEARING permanent universe (owner ruling 2026-07-29).

The identity crosswalk answers "which permanent identity does each legacy governed key resolve to".
This artifact answers a different and equally material question: "which of those identities does the
authoritative single-vintage source actually supply price history for". Both are bound separately, and
the mapped-identity digest is never redefined to mean the smaller set.

Every one of the 14,145 mapped identities carries BOTH dispositions, so a retracted identity is never
falsely reverted to unresolved:

    identity_disposition      MAPPED_UNIQUE            (the crosswalk resolved it — a durable fact)
    corpus_price_disposition  INCLUDED_PRICE_BEARING
                              | EXCLUDED_AUTHORITATIVE_PRICE_HISTORY_RETRACTED

⚠ `universe_crosswalk_v2.json` is deliberately NOT modified. Its digest `f6d47ac9…` was ratified for
the Layer 2 build, and mutating a ratified artifact to add a second disposition dimension would
invalidate that ratification silently. The price dimension therefore lives here, alongside it.
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
from pathlib import Path

import duckdb

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

# Deterministic console encoding. A cp1252 console raised UnicodeEncodeError on a single arrow
# character AFTER all substantive validation had passed, discarding three otherwise-valid extractions.
# Logging must never decide whether a valid result survives.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from app.validation.governed_corpus import canonical_json  # noqa: E402

MAPPED_IDENTITY_SHA256 = "fd2c843a631f8d9831f221b747937f5e617074c43621c6743cc9b36c718bccc7"
INCLUDED = "INCLUDED_PRICE_BEARING"
#: Non-price-bearing classes. The class per identity is read from the corpus evidence (which reads it
#: from the adjudication file), never assumed here.
NON_PRICE_BEARING = ("EXCLUDED_AUTHORITATIVE_PRICE_HISTORY_RETRACTED",
                     "EXCLUDED_NO_AUTHORITATIVE_SEP_PRICE_COVERAGE")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--crosswalk", required=True)
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    cwp = Path(args.crosswalk) / "universe_crosswalk_v2.json"
    cw = json.loads(cwp.read_text(encoding="utf-8"))
    cw_sha = hashlib.sha256(cwp.read_bytes()).hexdigest()

    cdir = Path(args.corpus_dir)
    ev = json.loads((cdir / "normalized_corpus_evidence.json").read_text(encoding="utf-8"))
    retraction_by_id = {r["permaticker"]: r for r in ev["retractions"]}

    con = duckdb.connect(str(cdir / ev["store"]["path"].rsplit("\\", 1)[-1]), read_only=True)
    present = {r[0]: (int(r[1]), str(r[2]), str(r[3])) for r in con.execute(
        "SELECT permaticker, count(*), min(date), max(date) FROM sep GROUP BY 1").fetchall()}
    con.close()

    rows: list[dict] = []
    for r in cw["rows"]:
        p = r.get("permaticker")
        if not p:
            continue                      # a legacy-key exclusion never had an identity
        rec = {"permaticker": p, "legacy_key": r["old_ticker_key"],
               "identity_disposition": "MAPPED_UNIQUE"}
        if p in present:
            n, lo, hi = present[p]
            rec |= {"corpus_price_disposition": INCLUDED,
                    "price_row_count": n, "price_span": [lo, hi]}
        else:
            ret = retraction_by_id.get(p)
            if ret is None:
                raise SystemExit(
                    f"{p} ({r['old_ticker_key']}) has no price rows and no retraction ruling; every "
                    f"non-price-bearing identity must carry an explicit disposition")
            rec |= {"corpus_price_disposition": ret["corpus_price_disposition"],
                    "price_row_count": 0,
                    "disposition_authority": ret["disposition_authority"],
                    "exclusion_basis": ret["exclusion_basis"],
                    "exclusion_basis_is_not_july27_impact": True,
                    "full_export_sep_row_count": ret["full_export_sep_row_count"],
                    "direct_per_ticker_api_row_count": ret["direct_per_ticker_api_row_count"],
                    "control_query": ret["control_query"],
                    "extraction_methods_agree_on_zero": ret["extraction_methods_agree_on_zero"]}
        rows.append(rec)

    rows.sort(key=lambda r: r["permaticker"])
    included = [r["permaticker"] for r in rows if r["corpus_price_disposition"] == INCLUDED]
    retracted = [r["permaticker"] for r in rows
                 if r["corpus_price_disposition"] in NON_PRICE_BEARING]
    mapped_sha = hashlib.sha256(canonical_json(sorted(r["permaticker"] for r in rows))).hexdigest()
    price_sha = hashlib.sha256(canonical_json(sorted(included))).hexdigest()

    if mapped_sha != MAPPED_IDENTITY_SHA256:
        raise SystemExit(f"the mapped-identity set no longer reproduces {MAPPED_IDENTITY_SHA256}")
    if price_sha != ev["governed_price_universe_sha256"]:
        raise SystemExit(
            f"price digest {price_sha} disagrees with the built corpus "
            f"{ev['governed_price_universe_sha256']}")

    payload = {
        "kind": "governed_price_universe", "version": "v2.0",
        "source_vintage_sha256": ev["source_vintage_sha256"],
        "governed_universe_key_crosswalk_sha256": cw_sha,
        "crosswalk_artifact_unmodified": True,
        "governed_mapped_identity_universe_sha256": mapped_sha,
        "governed_mapped_identity_count": len(rows),
        "governed_mapped_identity_meaning":
            "permanent identities obtained from the terminal disposition of the 14,150 legacy "
            "governed keys",
        "governed_price_universe_sha256": price_sha,
        "governed_price_identity_count": len(included),
        "governed_price_universe_meaning":
            "the countersignable price-bearing permanent universe after authoritative source "
            "retractions; the digest used for SEP restriction, row-coverage validation, ranking, "
            "proxy construction and corpus identity",
        "non_price_bearing_identity_count": len(retracted),
        "identities": rows,
    }
    blob = canonical_json(payload)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)

    print(f"governed_mapped_identity_universe_sha256 : {mapped_sha}  ({len(rows):,})")
    print(f"governed_price_universe_sha256           : {price_sha}  ({len(included):,})")
    print(f"non-price-bearing identities             : {len(retracted)} -> "
          f"{[(r['permaticker'], r['legacy_key']) for r in rows if r['permaticker'] in set(retracted)]}")
    print(f"price_universe_artifact_sha256           : {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
