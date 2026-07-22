# MR-002 Custody — Review Set

Consolidated review copies of every custody artifact produced 2026-07-22, gathered here so the
whole custody chain can be reviewed in one place.

⚠ **These are COPIES for review. The authoritative source is `scripts/mr002_custody/`.**
Copies were verified byte-identical at creation. Do not edit them — edit the source and
re-copy, or the two will drift silently.

⚠ These files are **outside** `docs/review/mr002/evaluator/` on purpose. That directory is the
§4 module inventory of the RESOLVED evaluator binding, and any `.py` added there would enter
the inventory and invalidate the binding. The inventory is scoped to `evaluator/` only
(its excluded paths are bare filenames relative to that directory), so copies at this level are
safe. The same reasoning governs the `_gen_*.py` generators in the parent folder.

---

## Review order

Read the governance records first; they explain why the code exists.

### 1. Governance records (parent folder, `docs/review/mr002/`)

| Artifact | What it settles |
|---|---|
| `MR002_ResearchSidePrerequisiteCloseout_v1.0.json` | P3/P4/P5 SATISFIED; the seven custody requirements |
| `MR002_EvaluatorImageCustody_v1.0.json` | Custody reqs 1–6 SATISFIED, req 7 not implemented |
| `MR002_EvaluatorImageManifest_DigestKindCorrigendum_v1.0.json` | The bound digest is an OCI **index**, not a config digest |
| `MR002_CustodyDetection_Submission_v1.0.md` | Trail, alerting, integrity monitor |
| `MR002_ExternalRecoveryCopy_Submission_v1.0.md` | Recovery archive; **§7 awaits the human custodian** |
| `MR002_ExternalRecoveryCopy_v1.0.json` | Machine-readable archive inventory + classification |

### 2. Detection code (this folder)

| File | Role |
|---|---|
| `custody_monitor.py` | Daily integrity monitor (deployed as Lambda `mr002-custody-monitor`) |
| `test_custody_monitor.py` | 12 tests — stub-driven; never probes the custody repository |

### 3. Recovery code (this folder)

| File | Role |
|---|---|
| `export_recovery_copy.py` | Builds + offline-verifies the OCI recovery archive |
| `test_recovery_verifier.py` | 15 tests, incl. regressions for both disclosed verifier defects |

### 4. Applied AWS configuration (`aws/`)

`cloudtrail-bucket-policy.json`, `ecr-mutation-pattern.json`, `control-plane-pattern.json`,
`monitor-role-policy.json`, `monitor-role-trust.json`, `sns-topic-policy.json` — all **applied**.

`PROPOSED-custody-role.json` — **NOT APPLIED.** Changes administrative access paths; awaits
adjudication.

---

## Reviewer's checklist of claims

Each is verifiable independently:

- The monitor **never** satisfies Requirement 7 — every receipt carries
  `satisfies_requirement_7: false` and forbids `require_binding()` consuming it.
- The monitor role is **read-only**, resource-scoped to one repository ARN.
- Drift testing uses **stubs only** — no AWS resource is mutated by any test.
- The recovery verifier fails on: misnamed blobs, unreferenced objects, missing objects, wrong
  image, wrapper-hash mismatch, missing `index.json`, empty archives, malformed reachable
  descriptors, size disagreement, and media-type disagreement.
- The build gate and the custodian's offline check are the **same** function
  (`verify_archive`); no weaker build-time variant exists.
- **No prevention claim** appears anywhere; prevention is impossible in a management account.

## Deliberately NOT here

- `mr002-evaluator-p5-recovery.tar` (44,410,880 bytes) — kept out of git. It lives in the
  staging directory outside the repository. Wrapper `sha256:c3cf3b9e…`, inner
  `sha256:60b15568…`.
- Any key, passphrase, serial number, or physical storage location.
- Any resolver for custody Requirement 7 — **not authorized, not built.**

## Standing state

Custody requirements 1–6 SATISFIED · Requirement 7 SPECIFIED_NOT_IMPLEMENTED · independent
offline custody UNSATISFIED · recovery from account-level loss UNSATISFIED ·
`validation_authorization = false` · validation partition closed · single opening unconsumed ·
OOS under DENY.
