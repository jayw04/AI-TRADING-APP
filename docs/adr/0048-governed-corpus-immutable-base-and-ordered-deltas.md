# ADR 0048 — Governed data corpora as an immutable base plus ordered, countersigned deltas

| Field | Value |
|---|---|
| Date | 2026-07-27 |
| Status | Proposed |
| Phase | Forward validation (Workstream B) — Account-4 critical path |
| Supersedes | — |
| Related | 0047 (production witness infrastructure), 0046 (AWS SDK dependency and the KMS witness-signer boundary), 0044 (deployment lifecycle and fail-closed operational holds), 0033 (historical data integrity), PREREG_EqualWeight_Production_Validation_v1.0 §0/§5/§7, GITHUB-OPS-001, owner ruling 2026-07-27 |

## Context

The equal-weight forward-validation program runs at least 252 sessions across at least a full forward
year. Every session must evaluate the production strategy against a governed dataset whose coverage
reaches **that session**, and must record, immutably, which dataset it used.

Until now "governed dataset" has meant one countersigned file. The corpus at
`apps/backend/data/factor_data_full.refresh.duckdb` is 1.77 GB; its identity is a whole-file SHA-256
recorded in a countersignature record, and superseding it is a deliberate, documented act. That model
was built for a small number of snapshots taken at long intervals. It was countersigned twice in a
month, the second time to repair a truncated ingest.

The model does not survive contact with a daily program. Three things break at once:

**Coverage must advance daily, but the identity may not drift.** A 2026-07-28 session cannot be
evaluated against a corpus that ends 2026-07-24. But re-ingesting into the file changes its
whole-file hash, so either the countersignature is invalidated on every trading day or it is
re-issued on every trading day. Re-countersigning a 1.77 GB artifact 252 times is not a governance
process; it is a ritual that would be abandoned or automated into meaninglessness within a month, and
a countersignature nobody reads protects nothing.

**There is no automated refresh path for this artifact at all.** The `workbench-factor-refresh` timer
maintains the 44 MB *operational* store — a different file, a ~208-name operational universe, a
different identity. Substituting it would break the countersigned provenance and the
preregistration's universe binding, which is why the 2026-07-27 blocker was a governance question and
not a copy operation.

**Whole-file hashing is the wrong granularity for what a session must prove.** The property a session
needs is not "this file is the file someone approved" but "the rows I read did not move underneath me
while I read them, and the construction they came from was authorized". Those are two different
claims and the existing code already separates them:
`DataFinalityEvidence.store_identity_sha256` is a streaming value-level digest of the rows actually
consumed, re-verified by `verify_store_unchanged` *after* the session's reads. That is a runtime
proof. A whole-file hash — or a manifest hash — is a provenance claim. Neither substitutes for the
other, and an early draft of this decision proposed redefining the runtime field as a manifest
identity, which would have traded a read-coupled proof for a declaration.

The same pressure applies, at a much smaller scale, to the risk-free series. `DGS3MO.csv` is pinned
by a single constant, `forward_window.DGS3MO_SNAPSHOT_SHA256`, whose last observation is
**2026-07-21**. Its own binding document already requires that any extension be *"append-only,
separately hashed, and tied to a documented cutoff"* — a contract a single-file digest cannot
express. Left as-is for a year-plus program, the cash benchmark would accrue on a yield carried
forward from July 2026 for the program's entire duration, which is a benchmark distortion introduced
by a governance mechanism rather than by any research decision.

## Decision

Governed corpora are maintained as an **immutable base plus ordered, append-only, individually
countersigned deltas**, with **two distinct identity fields** — one for authorized construction, one
for runtime consumption — neither substituting for the other.

### 1. Immutable base

The governing SEP/ACTIONS corpus base is fixed:

```yaml
base:
  coverage_through: 2026-07-24
  sha256: 2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87
  universe: governed 14,150 tickers
```

The base file is **never rewritten and never re-countersigned** in the course of normal operation.

### 2. Session deltas

For each session after the base cutoff, a delta is produced that:

- ingests SEP and ACTIONS **only through the latest complete session**;
- is restricted to the **same governed universe and schemas** as the base;
- is **append-only and session-bounded**;
- records row counts, source hashes, coverage, exclusions and validation results;
- is hashed, and its manifest countersigned.

### 3. Fail-closed delta validation

A session **refuses to run** — it does not warn, degrade, or proceed on a partial view — when the
delta sequence is **missing, duplicated, out-of-order, future-dated, or unhashed**. These four
conditions plus future-dating are enforced in code at session start, not by checklist. This mirrors
ADR 0047's ruling that evidence states are structural: a condition that can only be violated silently
is not an invariant.

### 4. Historical corrections are not deltas

A delta may only extend coverage forward. **No prior session is ever silently amended.** A historical
correction requires a **separately documented repair and a new corpus version**, which is the route
the 2026-06-15 truncated-ingest defect took: DELETE + INSERT inside one row-count-guarded
transaction, a superseding whole-file identity, and a countersignature record that qualifies exactly
what changed in both directions.

### 5. Compaction

Periodic compaction into a new full corpus version is authorized, **initially monthly**. The
compacted file receives a new whole-file SHA-256 and its own countersignature. **All prior base and
delta identities remain preserved** — compaction is a new version, never an erasure of the chain that
produced it.

### 6. `corpus_manifest_sha256` — the construction identity (NEW)

A deterministic identity over:

- base corpus identity;
- **every ordered delta** through the observation session;
- governing universe identity;
- ACTIONS provenance.

It binds provenance, cutoff, universe, source artifacts, exclusions and countersignatures. It proves
**which governed corpus construction was authorized**.

### 7. `store_identity_sha256` — the runtime proof (RETAINED, UNCHANGED)

The existing value-level digest of the exact session-consumed rows, computed before or during the
governed read and recomputed by `verify_store_unchanged`. It proves **the consumed dataset did not
change during execution**.

**(6) and (7) are both mandatory in every observation. They are not aliases and neither substitutes
for the other.** The first five manifest fields describe the authorized construction; the last proves
what the session actually consumed.

### 8. Six identities are recorded, across two artifacts — because one of them does not exist yet

```
base_corpus_sha256              ─┐
ordered_delta_manifest_sha256s   │
governed_universe_sha256         ├─ the deployment manifest: the AUTHORIZED CONSTRUCTION
actions_manifest_sha256          │  (plus dgs3mo_manifest_sha256, per (11))
corpus_manifest_sha256          ─┘
store_identity_sha256           ─── every OBSERVATION: what the session actually consumed
```

The first five describe the authorized construction and are fixed when the deployment is assembled.
The sixth is a property of a session's reads and **does not exist until a session performs them**. A
deployment manifest is finalized before observation #1, so requiring it there would force the
generator to invent a value — precisely the "faithful attestation to hand-made evidence" the
deployment-identity module exists to prevent. It is therefore mandatory in **observation evidence**,
where it is real, alongside `corpus_manifest_sha256`. Both are required in every observation and
neither substitutes for the other, which is the property (7) states.

A deployment manifest **may** still declare a store identity — a per-session manifest legitimately
can — and when it does it is verified against the session's actual value rather than trusted.

### 9. Every observation binds to the exact base-plus-delta manifest it used

Not to "the current corpus", not to a mutable pointer, and not to a manifest resolved at read time.
An observation that cannot name its construction is not admissible evidence.

### 10. DGS3MO follows the same model

The frozen artifact is the immutable base:

```yaml
dgs3mo_base:
  sha256: 87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1
  coverage_through: 2026-07-21
```

Extensions are append-only, session/date bounded, separately hashed, carry source and retrieval
timestamp, contain **no future-dated values**, and are ordered in the deployment manifest. The
runtime consumes the frozen base plus ordered extensions through the observation cutoff.

### 11. `DGS3MO_SNAPSHOT_SHA256` is retained and continues to identify the frozen base

It is **not** redefined as the digest of a mutable combined file. A separate composed identity,
**`dgs3mo_manifest_sha256`** (NEW), binds base plus ordered extensions. Delta validation (3) applies
to DGS3MO extensions unchanged.

### 12. The frozen governing inputs are installed, never regenerated

`DGS3MO.csv` (`87d8ba2f…825d1`) and `TrialLedger_v1.0.json` (`b7d9d715…8eb6d`, N=45) already exist,
committed, byte-exact against their preflight pins. They are **installed by exact hash**. A generated
replacement, an empty ledger, a normalized CSV, a reordered JSON or a reserialized copy **is not
equivalent unless its byte hash remains exact**. Synthesizing an empty trial ledger to satisfy
configuration loading is **prohibited** — `EFFECTIVE_DSR_TRIAL_COUNT = 45` is read from that file and
a synthesized ledger would silently change the severity of the DSR gate.

## Rationale

**Why a base plus deltas rather than a rolling countersigned file.** The countersignature is a human
act with a reader. Its value comes from someone examining what changed and attesting to it. A process
that demands that act 252 times destroys the act — either it is skipped, or it is automated, and an
automated countersignature is a timestamp wearing a signature's clothes. Deltas keep the human act
proportionate to the change: a delta is one session of one universe, small enough to actually
examine, and the base — the thing that took real scrutiny — is examined once and then held immutable.

**Why append-only, and why corrections are excluded.** The failure this model must prevent is a
governed result that changed after it was recorded. Append-only makes forward extension cheap and
backward amendment structurally impossible through the routine path. Corrections still happen — the
2026-06-15 defect proves they must — but they are forced onto a loud path that produces a new corpus
version and a countersignature record. The cost asymmetry is the point: extending is easy, amending
is expensive and visible. This is the same polarity CLAUDE.md requires of activation cooldowns.

**Why fail-closed on gaps rather than best-effort.** A missing delta is indistinguishable, from
inside a session, from a session whose data genuinely had no rows. An out-of-order delta silently
changes what a point-in-time read resolves. Neither is detectable after the fact from the observation
alone, so neither may be survivable at run time. The program's entire output is a sequence of
observations that must still be trustworthy in August 2027; a single silently-degraded session
contaminates the gate battery that consumes it.

**Why two identity fields and not one.** They answer different questions and fail differently. A
manifest identity attests what the deployment *declares* it assembled; a value-level digest proves
what the session *read*. A deployment that assembles the authorized construction and then reads
against a store mutating underneath it satisfies the first and violates the second. A deployment that
reads a stable but unauthorized store satisfies the second and violates the first. Collapsing them
leaves one of those two failures undetectable, and the drafting history here is itself the evidence:
the first formulation of this decision proposed exactly that collapse.

**Why DGS3MO is in scope.** It is small enough that freezing it looks harmless, which is precisely
why it would have been frozen. A year of carried-forward yield is a benchmark error introduced by
governance convenience — the cash benchmark is one of four gates in §7, and it would have been
systematically wrong for reasons no reader of the results could see. The binding document already
required append-only extension; only the preflight's single-constant shape prevented it.

**Why the frozen inputs are installed rather than regenerated.** Regeneration is the intuitive
reading of "create the four required artifacts", and it is wrong: a regenerated DGS3MO or ledger
would hash differently and the preflight would refuse every session — correctly. The artifacts are
governing inputs frozen by the preregistration, not deployment-generated records. Only `build_info`
and `deployment_manifest` are genuinely per-deployment.

## Implementation notes

- **Delta validation runs at session start**, before the store is opened for reads, in the same
  fail-closed position as the witness gate. A session that cannot validate its construction must not
  reach the data.
- **`store_identity_sha256` keeps its current computation and its `verify_store_unchanged`
  re-stream.** No change to `data_finality.py`'s semantics is authorized by this ADR. Adding the
  manifest identity must not alter when or how the value-level digest is taken.
- **`DGS3MO_SNAPSHOT_SHA256` keeps its current value and meaning.** The preflight gains
  base-plus-ordered-extension verification; it does not lose the frozen-base check.
- **The four frozen-input pins in `forward_window.py`** (`DGS3MO_SNAPSHOT_SHA256`,
  `DGS3MO_OBSERVATION_CUTOFF`, `TRIAL_LEDGER_SHA256`, `EFFECTIVE_DSR_TRIAL_COUNT`) are governing
  values from the countersigned §0. Changing any of them is a preregistration amendment, not a code
  change.
- **Corpus files, deltas and evidence bundles are never committed.** They live in controlled,
  versioned storage and are referenced by hash, per GITHUB-OPS-001 §6. What is committed: schemas,
  durable configuration references, and non-sensitive hashes.
- **The session host reads the delivery prefixes read-only, under its own role.** It inherits no
  bucket mutation, delete, IAM, Object Lock or witness-signing permission, and the eight-action
  witness role of ADR 0047 is not modified to simplify data delivery.
- ⚠ When verifying that role with `simulate-principal-policy`, pass `ContextEntries` for `s3:prefix`;
  `s3:ListBucket` under a `StringLike` prefix condition returns implicitDeny without it.

## Consequences

**Accepted.** Session start does more work and has more ways to refuse. The manifest becomes a
required, hashed artifact that must be finalized before observation #1, and a missing or malformed
manifest stops the program rather than degrading it. Monthly compaction is a recurring operational
obligation with its own countersignature. Two identity fields must both be produced, recorded and
kept distinct in every observation, and reviewers must understand which answers which question.

**Gained.** Coverage can advance daily without eroding the countersignature. The unit of human
attestation stays small enough to actually attest. A historical amendment cannot reach a recorded
observation through the routine path. Every observation names the exact construction it used, so the
August-2027 gate battery can be re-derived from the record rather than from a claim about what the
corpus was at the time.

**Not addressed.** This ADR does not decide the delta production schedule, who runs it, or how a
delta is countersigned operationally; it fixes the contract the deltas must satisfy. It does not
change the operational `workbench-factor-refresh` store or its timer. It authorizes no observation,
no hold change, and no order.

## Alternatives considered (not chosen)

**Re-countersign the full corpus every session.** Faithful to the existing model and requires no new
concepts. Rejected because it makes the countersignature ceremonial: 252 attestations of a 1.77 GB
file that no one can examine at that cadence, and the first missed day creates a gap with no defined
handling.

**Point the forward program at the operational 44 MB store, which is already refreshed daily.**
Solves coverage immediately and costs nothing. Rejected because it is a different artifact — a
~208-name operational universe against the governing 39M-row corpus, a different file identity — so
it breaks both the countersigned provenance and the preregistration's universe binding. It is a new
construction, which the preregistration forbids.

**Redefine `store_identity_sha256` as the manifest identity.** One field, one concept, less to
explain. Rejected: it replaces a runtime proof coupled to the rows actually read with a declaration
about what was assembled, and the failure it stops detecting — a store mutating during a session — is
exactly the one `verify_store_unchanged` exists to catch.

**Freeze DGS3MO at 2026-07-21 for the whole program.** Simplest, and consistent with the sealed-input
spirit of the preregistration. Rejected because a carried-forward yield for a year-plus is a
benchmark distortion invisible in the results, affecting a §7 gate, introduced by governance
convenience rather than by a research decision.

**Let deltas carry historical corrections.** Would make the 2026-06-15 class of repair routine instead
of exceptional. Rejected because it reintroduces exactly the property append-only exists to remove: a
recorded observation whose inputs can change afterwards, through an ordinary path, without a
superseding version anyone reviews.

## Re-evaluation triggers

- **A delta is ever refused in operation** for a reason other than a genuine integrity stop — a
  source outage, a late Sharadar publication, a scheduling gap. The fail-closed posture is being paid
  for, and the price needs restating rather than quietly loosening.
- **Monthly compaction proves too frequent or too rare** — the delta chain grows unmanageable before
  a month, or a month's compaction is repeatedly deferred because nothing warrants it.
- **A historical correction is needed mid-program.** The new-corpus-version path is deliberately
  expensive; the first real use will show whether it is expensive in the right way.
- **The governing preregistration is superseded or the forward window restarts.** The base identity,
  the cutoffs and the universe binding were all sized to one specific program.
- **A second governed corpus, or a second consumer of this model, appears.** The reasoning here
  assumes one base, one delta chain, and one program reading it.
- **The universe definition changes.** The base is bound to exactly 14,150 tickers; a universe change
  is a new base, not a delta, and this ADR does not describe how the two would be reconciled.
- **`store_identity_sha256` and `corpus_manifest_sha256` ever disagree in a way the runtime cannot
  explain.** That is either a real integrity event or a defect in the separation this ADR rests on,
  and both need a decision rather than a patch.
