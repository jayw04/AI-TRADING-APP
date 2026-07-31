"""Independently verify a sealed Layer 2 vintage. Exit 0 only if EVERY check passes.

A background process exiting zero is not evidence that a governed artifact is sound — the exit code
reports what the process believed, not what is on disk. This re-derives the facts from the files.

Checks the owner's operational cautions and success criteria:
  * no staging directory survives (promotion happened, and only after every guard passed)
  * the final sealed directory exists and its evidence says `sealed: true`
  * every recorded hash RECOMPUTES from the bytes on disk
  * direct-query evidence completed BEFORE the seal
  * the AAPL control returned nonzero data
  * exactly OCCI + HYPG returned zero through both access paths
  * source identities unchanged across the bounded extraction (open == close == seal)
  * a later vendor refresh AFTER promotion is reported as diagnostic only, never as invalidating
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
from datetime import datetime
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.validation.governed_corpus import canonical_json  # noqa: E402

EXPECTED_ZERO_ROW = {"113567": "OCCI", "6399295": "HYPG"}
EXPECTED_INCLUDED = {"6399330": "LTGRU", "120814": "VYNE"}
CONTROL = "AAPL"
_CHUNK = 1 << 20


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(_CHUNK), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vintage", required=True)
    args = ap.parse_args()
    final = Path(args.vintage)
    staging = final.with_name(final.name + "__staging")

    checks: list[tuple[str, bool, str]] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    chk("staging directory does not survive", not staging.exists(), str(staging))
    chk("sealed directory exists", final.exists(), str(final))
    evp = final / "extraction_evidence.json"
    if not evp.exists():
        chk("extraction_evidence.json present", False, "missing")
        _report(checks)
        return 1
    raw = evp.read_bytes()
    ev = json.loads(raw.decode("utf-8"))
    sv = ev["source_vintage"]

    chk("evidence declares sealed: true", sv.get("sealed") is True, repr(sv.get("sealed")))
    chk("extraction_evidence digest recomputes",
        hashlib.sha256(raw).hexdigest() == hashlib.sha256(canonical_json(ev)).hexdigest())
    chk("source_vintage digest recomputes",
        hashlib.sha256(canonical_json(sv)).hexdigest() == ev["source_vintage_sha256"],
        ev["source_vintage_sha256"])

    # every recorded artifact + row-set hash must recompute from the bytes on disk
    for t, src in ev["sources"].items():
        ap_ = Path(src["artifact_path"])
        cp = Path(src["csv_path"])
        chk(f"{t} zip sha256 recomputes", ap_.exists() and _sha(ap_) == src["artifact_sha256"])
        chk(f"{t} row-set identity recomputes",
            cp.exists() and _sha(cp) == src["row_set_identity_sha256"])
        chk(f"{t} identity unchanged open->close",
            {k: src[k] for k in ("data_snapshot_time", "last_refreshed_time", "export_object")}
            == {k: src["vintage_identity_reconfirmed"][k]
                for k in ("data_snapshot_time", "last_refreshed_time", "export_object")})

    sealed = sv["sealed_verification"]
    chk("identities unchanged open->seal", sealed["identities_unchanged_open_through_seal"] is True)
    verified = datetime.fromisoformat(sealed["verified_at_utc"])
    sealed_at = datetime.fromisoformat(sv["sealed_at_utc"])
    chk("direct-query evidence completed BEFORE the seal", verified <= sealed_at,
        f"{verified.isoformat()} <= {sealed_at.isoformat()}")
    chk(f"{CONTROL} control returned nonzero data",
        sealed["control"]["ticker"] == CONTROL and sealed["control"]["api_rows"] > 0,
        str(sealed["control"]))

    zero = {v["permaticker"]: k for k, v in sealed["per_ticker"].items()}
    chk("zero-row set is exactly OCCI + HYPG", zero == EXPECTED_ZERO_ROW, str(zero))
    chk("both access paths agree at zero for all candidates",
        all(v["agree"] and v["api_rows"] == 0 and v["export_rows"] == 0
            for v in sealed["per_ticker"].values()))
    chk("LTGRU and VYNE are NOT zero-row candidates",
        not (set(EXPECTED_INCLUDED) & set(zero)), str(sorted(set(EXPECTED_INCLUDED) & set(zero))))

    ok = all(c[1] for c in checks)
    _report(checks)
    print(f"\nsource_vintage_sha256      : {ev['source_vintage_sha256']}")
    print(f"extraction_evidence_sha256 : {hashlib.sha256(raw).hexdigest()}")
    print(f"sealed_at_utc              : {sv['sealed_at_utc']}")
    print("\nNOTE: a vendor refresh AFTER this seal is post-capture drift and is DIAGNOSTIC ONLY — it "
          "does not invalidate this sealed vintage.")
    print(f"\nVERDICT: {'SEALED VINTAGE VERIFIED' if ok else 'VERIFICATION FAILED'}")
    return 0 if ok else 1


def _report(checks: list[tuple[str, bool, str]]) -> None:
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail and not ok else ""))


if __name__ == "__main__":
    raise SystemExit(main())
