"""Validate the relationship between the Layer 2 artifacts. Exit 0 only if every check passes.

Two artifacts answer two different questions and are hashed independently:

    universe_crosswalk_v2.json   identity resolution of all 14,150 legacy keys      (f6d47ac9…, ratified)
    price_universe_v2.json       corpus-inclusion disposition of the 14,145 mapped identities

Neither implies the other, so the relationship between them is proved here rather than assumed:

  * every price-universe row references exactly one mapped crosswalk identity
  * the non-price-bearing set is exactly the owner-adjudicated set
  * the price-bearing count matches the adjudicated expectation
  * no price-bearing identity is absent from the mapped set
  * no excluded legacy key and no non-price-bearing identity appears in the store's SEP
  * both digests recompute over their own membership
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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.validation.governed_corpus import canonical_json  # noqa: E402

MAPPED_SHA = "fd2c843a631f8d9831f221b747937f5e617074c43621c6743cc9b36c718bccc7"
CROSSWALK_SHA = "f6d47ac962749ee2284f03bec4ee4a0030da2d6615483065124714afc77ca3cc"
INCLUDED = "INCLUDED_PRICE_BEARING"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--crosswalk", required=True)
    ap.add_argument("--corpus-dir", required=True)
    ap.add_argument("--adjudication", default="layer2_price_adjudication.json")
    args = ap.parse_args()

    cwp = Path(args.crosswalk) / "universe_crosswalk_v2.json"
    cw = json.loads(cwp.read_text(encoding="utf-8"))
    cdir = Path(args.corpus_dir)
    pu = json.loads((cdir / "price_universe_v2.json").read_text(encoding="utf-8"))
    ev = json.loads((cdir / "normalized_corpus_evidence.json").read_text(encoding="utf-8"))
    adj = json.loads(Path(args.adjudication).read_text(encoding="utf-8"))

    checks: list[tuple[str, bool, str]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    chk("crosswalk artifact is byte-unchanged (ratified)",
        hashlib.sha256(cwp.read_bytes()).hexdigest() == CROSSWALK_SHA)

    mapped = {r["permaticker"] for r in cw["rows"] if r.get("permaticker")}
    excluded_keys = {r["old_ticker_key"] for r in cw["rows"]
                     if str(r["disposition"]).startswith("EXCLUDED")}
    rows = pu["identities"]
    pu_ids = {r["permaticker"] for r in rows}
    included = {r["permaticker"] for r in rows if r["corpus_price_disposition"] == INCLUDED}
    non_pb = {r["permaticker"] for r in rows if r["corpus_price_disposition"] != INCLUDED}
    adjudicated = set(adj["expected_non_price_bearing"])

    chk("every price-universe row references a mapped crosswalk identity",
        pu_ids <= mapped, str(sorted(pu_ids - mapped)[:5]))
    chk("price universe covers every mapped identity exactly once",
        pu_ids == mapped and len(rows) == len(pu_ids) == len(mapped),
        f"{len(rows)} rows / {len(pu_ids)} ids / {len(mapped)} mapped")
    chk("all identity_disposition are MAPPED_UNIQUE",
        all(r["identity_disposition"] == "MAPPED_UNIQUE" for r in rows))
    chk("non-price-bearing set == owner adjudication",
        non_pb == adjudicated, f"{sorted(non_pb)} vs {sorted(adjudicated)}")
    chk("non-price-bearing count is exactly 2", len(non_pb) == 2, str(len(non_pb)))
    chk("price-bearing count == adjudicated expectation",
        len(included) == int(adj["expected_price_identity_count"]),
        f"{len(included)} vs {adj['expected_price_identity_count']}")
    chk("no price-bearing identity absent from the mapped set", included <= mapped)
    chk("mapped digest recomputes",
        hashlib.sha256(canonical_json(sorted(mapped))).hexdigest() == MAPPED_SHA)
    chk("price digest recomputes over its own membership",
        hashlib.sha256(canonical_json(sorted(included))).hexdigest()
        == pu["governed_price_universe_sha256"])
    chk("price digest agrees with the built corpus",
        pu["governed_price_universe_sha256"] == ev["governed_price_universe_sha256"])

    store = cdir / Path(ev["store"]["path"]).name
    con = duckdb.connect(str(store), read_only=True)
    in_sep = {r[0] for r in con.execute(
        "SELECT DISTINCT permaticker FROM sep WHERE permaticker IN (SELECT unnest(?))",
        [sorted(non_pb)]).fetchall()}
    keys_in_sep = int(con.execute(
        "SELECT count(*) FROM sep WHERE ticker IN (SELECT unnest(?))",
        [sorted(excluded_keys)]).fetchone()[0])
    sep_ids = int(con.execute("SELECT count(DISTINCT permaticker) FROM sep").fetchone()[0])
    out_of_universe = int(con.execute(
        "SELECT count(*) FROM sep WHERE permaticker NOT IN (SELECT unnest(?))",
        [sorted(included)]).fetchone()[0])
    con.close()

    chk("no non-price-bearing identity appears in SEP", not in_sep, str(sorted(in_sep)))
    chk("no excluded legacy key appears in SEP", keys_in_sep == 0, str(keys_in_sep))
    chk("store SEP holds exactly the price-bearing identities",
        sep_ids == len(included), f"{sep_ids} vs {len(included)}")
    chk("no out-of-universe rows in SEP", out_of_universe == 0, str(out_of_universe))

    ok = all(c[1] for c in checks)
    for name, good, detail in checks:
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f"  {detail}" if detail and not good else ""))
    print(f"\n  mapped permanent identities : {len(mapped):,}")
    print(f"  price-bearing identities    : {len(included):,}")
    print(f"  no SEP price coverage       : {len(non_pb):,} -> "
          f"{sorted((r['permaticker'], r['legacy_key']) for r in rows if r['permaticker'] in non_pb)}")
    print(f"\nVERDICT: {'LAYER 2 ARTIFACTS RECONCILE' if ok else 'RECONCILIATION FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
