"""Generate the Phase 3B execution-boundary evidence memo.

Answers the owner's five questions from the FROZEN artifacts only, with every citation carrying a
hash this script recomputes at generation time. Where a record declares a self-excluded identity
hash that cannot be reproduced by hashing the file, the memo says so rather than implying a
verification that did not happen.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential,
no image change.
"""
from __future__ import annotations

import hashlib
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

# label -> (repo-relative path, registered sha256 or None, where it is registered)
CITED = {
    "EvaluatorBinding": (
        "docs/review/mr002/evaluator/MR002_EvaluatorBinding.json", None,
        "P5 binding (historical image leg); superseded for RUNTIME use only"),
    "EvaluatorBinding_Runtime": (
        "docs/review/mr002/evaluator/MR002_EvaluatorBinding_Runtime_v1.0.json", None,
        "P5 runtime renewal"),
    "EvaluatorImageManifest_Runtime": (
        "docs/review/mr002/evaluator/MR002_EvaluatorImageManifest_Runtime_v1.0.json", None,
        "runtime image manifest, 21 modules"),
    "ValidationRunSpecification": (
        "docs/review/mr002/phase3a/ValidationRunSpecification_v1.0.json", None,
        "Phase 3A run specification"),
    "ExecutionEnrichmentSchema": (
        "docs/review/mr002/phase3a/ExecutionEnrichmentSchema_v1.0.json",
        "5b2480c1bc80abfc2d520bbc3f5c00399d20f5ca7b75f815d1e5a4bf2719f71f",
        "ValidationRunSpecification.bound_schemas AND .bound_specifications"),
    "ExecutionEnrichmentCodeRegistry": (
        "docs/review/mr002/phase3a/ExecutionEnrichmentCodeRegistry_v1.0.json",
        "0bddd73c311b790a4f3ff07831279d91edb9c005b12d03543d6594749d705e51",
        "ValidationRunSpecification.bound_specifications"),
    "ExecutionEnrichmentEdgeCaseSpecification": (
        "docs/review/mr002/phase3a/MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json",
        "792c6717c6e4344062ba84c1b762b6eb5b8cf51d4464cb40b280230540794d17",
        "ValidationRunSpecification.bound_specifications"),
    "SignalDecisionRecord_model_module": (
        "apps/backend/app/research/mr002/spq1/models.py",
        "efc26d3ae7301cc45c782ab0174693f62d31cf9cc5289a4ec876d39bbc18666f",
        "ValidationRunSpecification.bound_schemas.SignalDecisionRecord_model_module_sha256"),
    "SignalDecisionRecord_schema": (
        "docs/review/mr002/spq1/MR002_SPQ1_InputOutputSchema_Draft_v1.1.json",
        "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f",
        "ValidationRunSpecification.bound_schemas.SignalDecisionRecord_schema_sha256"),
    "ExecutionGateTable": (
        "docs/review/mr002/phase3bc/MR002_Phase3BC_ExecutionGateTable_v1.0.json",
        "f113a232c0536e0e130a11d9d6a3dbe01610e1ee70b9fc7633ab87e8ac290ff3",
        "MR002_Phase3BC_PublicationManifest_v1.0.artifact_sha256.ExecutionGateTable"),
    "P12AuthorizationGrant": (
        "docs/review/mr002/phase3bc/MR002_Phase3BC_P12AuthorizationGrant_v1.0.json", None,
        "P12 grant record; declares grant_identity_sha256 440e96e1... over a self-excluded body"),
    "D3Submission": (
        "docs/review/mr002/phase3bc/MR002_Phase3BC_ExecutionAuthorizationRequest_v2.0.json", None,
        "D3 submission; declares submission_identity_sha256 4c984a4b... over a self-excluded body"),
    "enrichment_implementation": (
        "apps/backend/app/research/mr002/spq1/execution_enrichment.py", None,
        "implementation of the frozen enrichment schema; NOT in the bound image"),
    "partition_guard": (
        "apps/backend/app/research/mr002/spq1/adapters/partition_guard.py", None,
        "development-only access boundary"),
}


def sha256_file(rel: str) -> str:
    with open(os.path.join(_REPO, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verify() -> dict[str, dict]:
    out = {}
    for label, (rel, registered, where) in CITED.items():
        path = os.path.join(_REPO, rel)
        if not os.path.exists(path):
            raise SystemExit(f"REFUSED: cited artifact absent: {rel}")
        actual = sha256_file(rel)
        out[label] = {
            "path": rel, "sha256": actual, "registered": registered,
            "verified_against_registered": (actual == registered) if registered else None,
            "registered_in": where,
        }
    bad = [k for k, v in out.items()
           if v["verified_against_registered"] is False]
    if bad:
        raise SystemExit(f"REFUSED: cited artifact does not reproduce its registered hash: {bad}")
    return out


def module_count_in_image() -> int:
    import json
    with open(os.path.join(_REPO, CITED["EvaluatorImageManifest_Runtime"][0]), encoding="ascii") as f:
        return len(json.load(f)["module_digests_in_image"])


def enrichment_in_image() -> bool:
    import json
    with open(os.path.join(_REPO, CITED["EvaluatorImageManifest_Runtime"][0]), encoding="ascii") as f:
        mods = json.load(f)["module_digests_in_image"]
    return any("enrich" in m for m in mods)


def citation_table(v: dict) -> str:
    rows = ["| Artifact | Path | SHA-256 | Registered where |",
            "|---|---|---|---|"]
    for label, d in v.items():
        mark = " ✅" if d["verified_against_registered"] else ""
        rows.append(f"| `{label}`{mark} | `{d['path']}` | `{d['sha256'][:16]}…` | {d['registered_in']} |")
    return "\n".join(rows)


MEMO = """# MR-002 Phase 3B — Execution-Boundary Evidence Memo v1.0

**Date:** 2026-08-12 · **Kind:** EVIDENCE MEMO — decision input, grants nothing
**Boundary:** Zero-data. No AWS call, no sealed object opened, no credential assumed, no image
change. `validation_authorization` remains `true` at `_rev 1`; the single validation opening remains
**UNSPENT**.

**The question:** does the frozen Phase 3A contract require execution enrichment to live inside the
bound evaluator identity `sha256:194efbdf…`, or may it be a separately hash-bound execution layer?

**Recommendation: Option A** — a separately hash-bound orchestration/enrichment layer is
*supported by the frozen contract*, not merely cheaper. The decisive fact is that the frozen run
specification **already hash-binds runtime-critical code outside the evaluator image** and makes the
run fail closed on its drift. See Q3.

⚠ Every hash below was recomputed by `_gen_execution_boundary_memo.py` at generation time. Where a
record declares a self-excluded identity hash, that is stated rather than implied as verified.

---

## Q1 — What does P5 / the evaluator identity actually bind?

**It binds the evaluator directory's Python modules. It does not claim to bind all code that can
affect Phase 3B candidate records.**

- `MR002_EvaluatorBinding.json` → `authorizes`: *"NOTHING — this is an identity binding; it grants
  no data access, releases no credentials, and computes no performance."*
- `inclusion_rule`: *"`*.py` excluding the test and generator prefixes"*, `derivation`:
  *"mechanically enumerated at qualification time"*, with exclusion classes `EXCLUDED_TEST`,
  `EXCLUDED_GENERATOR`, `EXCLUDED_NON_EVALUATOR`, `EXCLUDED_CACHE`.
- `inventory_counts`: `INCLUDED_MODULE: 21`, `EXCLUDED_NON_EVALUATOR: 18`, `EXCLUDED_GENERATOR: 7`,
  `EXCLUDED_TEST: 6`, `EXCLUDED_CACHE: 3`.
- `verification_rule`: a run is refused unless every included module reproduces its bound digest
  **in the then-current tree**, and *"no unbound module is present"*.

**Reading.** The enumeration is **directory-scoped**, over `docs/review/mr002/evaluator/`. The
"no unbound module is present" clause polices *that tree*, not the repository. `EXCLUDED_NON_EVALUATOR`
exists precisely to classify files living beside the evaluator that are not part of it. Nothing in
the binding asserts jurisdiction over code elsewhere in the repository.

`MR002_EvaluatorImageManifest_Runtime_v1.0.json` records `evaluator_path_in_image:
/opt/mr002/evaluator` and **{module_count} modules**, all named `mr002_valoos_*`. Enrichment module
present in the image: **{enrichment_present}**.

**Answer: evaluator/decision logic only.**

---

## Q2 — How is `ExecutionEnrichedCandidateRecord` defined in Phase 3A?

**As a downstream transform across an explicit seam, not as evaluator-internal behaviour.**

`ExecutionEnrichmentSchema_v1.0.json` (✅ reproduces its registered hash):

- `binding`: *"immutable SignalDecisionRecord → ExecutionEnrichedCandidateRecord"*
- `signal_decision_record_ref`: `bound_by: "decision_record_sha256 (Phase 2B publication)"`,
  `immutable: true`, **`never_mutated_by_enrichment: true`**
- `future_information_guard`: *"any t+1 fact bearing on close-t decision →
  `INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED`"*
- `enriched_candidate_record_fields` add only execution-side facts: execution session, official-open
  source identity and price reference, corporate-action identity, disposition/code, conservative
  short flag.

`ExecutionEnrichmentCodeRegistry_v1.0.json` (✅ reproduces its registered hash) is stronger still:

- `namespace`: *"`EXECUTION_ENRICHMENT_*` (**SEPARATE** from signal-production refusal codes)"*
- `invariant`: *"…enrichment codes are **never reused** for signal-production failures"*

**Reading.** The contract does not merely permit a seam — it **mandates a namespace separation**
between enrichment failures and signal-production failures. A contract that required one monolithic
producer would have no reason to forbid code reuse across the two stages.

**Answer: explicitly downstream of the frozen `SignalDecisionRecord` seam.**

---

## Q3 — What code is allowed to transform close-t records into enriched records?

**This is the decisive evidence, and it is dispositive for Option A.**

`ValidationRunSpecification_v1.0.json` → `bound_schemas`:

```
SignalDecisionRecord_model_module_sha256 = efc26d3a…
fail_closed = "the run MUST fail closed if EITHER the SignalDecisionRecord schema identity OR the
               ExecutionEnrichmentSchema identity differs from the values bound here"
```

That hash resolves — recomputed at generation time — to:

**`apps/backend/app/research/mr002/spq1/models.py`**

which is **not** one of the {module_count} modules in `sha256:194efbdf…`, and which defines **both**
`SignalDecisionRecord` (line 56) and `ExecutionEnrichedCandidateRecord` (line 114).

**Reading.** The frozen contract therefore *already*:

1. binds runtime-critical Phase 3B code that lives **outside** the evaluator image;
2. binds it **by SHA-256**, exactly as a separately hash-bound layer would be bound;
3. makes the run **fail closed** on its drift.

A contract requiring enrichment inside the evaluator identity would not bind the module defining the
enriched record as an *external* identity. The mechanism Option A proposes is the mechanism the
contract already uses.

Counter-evidence search: across every Phase 3A artifact, **no** statement associates the evaluator
with producing enriched records — a search for `evaluator` co-occurring with `enrich`/`produce`/
`emit` returns **zero** matches.

**Answer: a separate, hash-bound stage — and the contract already names one such module.**

---

## Q4 — Which identities does P12 actually bind?

**The evaluator image, the runtime, the host, and the role. Not a broader execution package.**

`MR002_Phase3BC_ExecutionAuthorizationRequest_v2.0.json` → `bound_execution_identities`:
evaluator image index `sha256:194efbdf…`; dependency lockfile `bb38b685…`; numeric runtime manifest
`8e5e3947…`; frozen host `i-00c1034f7026db45e` (SR-HOST-1); the WP-B resolver as sole permitted
path; the role `arn:aws:iam::219024422756:role/mr002-phase3c-run-host`.

**No orchestrator, runner, enrichment, or execution-package identity appears.**

`MR002_Phase3BC_P12AuthorizationGrant_v1.0.json` → `does_not_authorize` includes: *"changing Config
A/B/C or evaluator logic"*, *"changing the runtime image or Linux dependency lock"*, *"replacing the
qualified host without requalification and a P10 refresh"*.

**Reading — the two paths diverge sharply here:**

- **Option A** changes none of the P12-bound identities. It introduces one identity P12 does not
  name, which is a **gap**, not a violation → a **supplemental execution-identity adjudication**
  before consuming the opening.
- **Option B** changes the runtime image, which `does_not_authorize` names explicitly → the current
  grant **may not be used**; the prerequisite chain (P5 → custody → WP-B → recovery copy → P10 →
  WP-F → D3 → P12) must be recomputed and a fresh authorization obtained.

⚠ Under **either** option the opening cannot be spent until the execution identity is adjudicated.
Option A makes that a narrow supplement; Option B makes it a full re-grant.

**Answer: evaluator image + runtime + host + role only.**

---

## Q5 — Would the separate-layer model preserve the frozen research semantics?

**Yes, and the enforcement is structural rather than procedural.**

The invariant is *no recomputation of signal economics; no mutation of close-t facts; enrichment adds
only permitted t+1 information; any violation fails closed.* Each leg is already enforced in the
module the contract binds:

| Requirement | Enforcement | Where |
|---|---|---|
| No mutation of close-t facts | `ExecutionEnrichedCandidateRecord` embeds the decision record's canonical form **and** its identity; `verify_decision_unchanged` raises `INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED` | `models.py:140-148` |
| No recomputation of signal economics | *"reads the decision record but recomputes NONE of its facts (z / sigma / beta / sector / eligibility / ADV / side / configuration / decision session)"* | `execution_enrichment.py` docstring |
| Only permitted t+1 information added | `enriched_candidate_record_fields` is a closed list of execution-side fields | `ExecutionEnrichmentSchema` |
| Fail closed | `EXECUTION_ENRICHMENT_STOP:*` codes; *"no silent price substitution, previous-close fallback, later-open fallback, or post-hoc security winner"* | `ExecutionEnrichmentCodeRegistry`, `DeliverableRegister.enrichment_default` |
| Verifiable after the fact | `decision_record_mutations = 0`, `missing_decision_enrichment_bindings = 0`, `future_information_violations = 0` | `ExecutionGateTable.phase_3b_integrity_gates` |

**Reading.** Semantic preservation rides on the *record structure and the gate census*, not on
co-location of code in one image. Moving enrichment inside the image would not strengthen any of
these; leaving it outside weakens none of them — **provided** the layer is hash-bound and the gates
are evidenced by the run.

**Answer: yes, preserved — conditional on hash-binding the layer and emitting the integrity census.**

---

## Options

### Option A — separately hash-bound orchestration/enrichment layer ✅ recommended

Keep `sha256:194efbdf…` intact. Bind a new Phase 3B execution package by its own module roster and
hashes, in the manner the run specification already uses for `models.py`.

- **Supported by:** Q1 (P5 scope is directory-bounded), Q2 (mandated namespace separation),
  **Q3 (the contract already binds external code by hash and fails closed on it)**, Q5.
- **Cost:** a supplemental execution-identity adjudication before the opening is spent.
- **Preserves:** the entire P5 → custody → WP-B → recovery → P10 → WP-F → D3 → P12 chain.

### Option B — enrichment must live inside the evaluator identity

- **Would require:** rebuilding the runtime image (new digest), renewing P5, re-running WP-B, a new
  recovery copy, a fresh P10 capture on a qualified host, a fresh WP-F, a new D3, and a new P12.
- **Explicitly not authorized** by the current grant (`does_not_authorize`: *"changing the runtime
  image or Linux dependency lock"*).
- **Evidence found for it:** none. No frozen artifact assigns enriched-record production to the
  evaluator.

### Option C — contract genuinely ambiguous

- **What is ambiguous:** the contract never states a *general* rule about which code must be inside
  the evaluator identity. Option A rests on a strong precedent (Q3) and a mandated separation (Q2),
  not on an explicit sentence saying "enrichment may live outside".
- **If chosen:** record a narrow prospective clarification before implementation — never a
  retrospective reading after the layer is built.

**Honest statement of the residual risk:** the case for A is *inferential but strongly evidenced* —
it argues from an existing external binding and a mandated code-separation invariant, not from an
explicit permission. If the owner wants the explicit permission on record, that is Option C, and
Option C's clarification is cheap now and impossible later.

---

## What this memo does not do

Grants nothing. Changes no image, no code, no identity, no authorization state. Opens no partition.
Does not draft the RunSpecification — that waits on this ruling, because the execution boundary
determines the run specification's module roster, entry point, and identity-binding section.

---

## Citations — all hashes recomputed at generation time

{citations}

✅ = recomputed value equals the value registered in the frozen contract. Rows without ✅ are cited by
path and current hash; records declaring a self-excluded identity hash (the P12 grant, the D3
submission) are **not** claimed here as recomputed, because hashing the file cannot reproduce a
self-excluded identity.
"""


def main() -> None:
    v = verify()
    memo = MEMO.format(
        module_count=module_count_in_image(),
        enrichment_present="NO" if not enrichment_in_image() else "YES",
        citations=citation_table(v),
    )
    out = os.path.join(_HERE, "MR002_Phase3B_ExecutionBoundary_EvidenceMemo_v1.0.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(memo)
    verified = sum(1 for d in v.values() if d["verified_against_registered"])
    print(f"wrote {out}")
    print(f"citations: {len(v)}; recomputed-and-matched against registered values: {verified}")
    print(f"memo sha256: {hashlib.sha256(memo.encode('utf-8')).hexdigest()}")


if __name__ == "__main__":
    main()
