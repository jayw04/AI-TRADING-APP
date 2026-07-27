# Owner ruling — governing-corpus refresh model and forward-validation deployment inputs

| Field | Value |
|---|---|
| Date | 2026-07-27 |
| Ruled by | Jay Wang (owner) |
| Status | **Issued — binding** |
| Governs | Workstream B forward-validation sessions for momentum-daily (strategy 11, Account 4) |
| Related | Governing corpus countersignature v2.0, PREREG_EqualWeight_Production_Validation_v1.0 §0/§5/§7, ADR 0046, ADR 0047, GITHUB-OPS-001 |
| Supersedes | nothing |

This record closes the two governance questions that blocked construction of the forward-validation
session host. It authorizes a maintenance model and a set of artifacts. It authorizes **no**
observation, **no** hold change, and **no** order.

---

## 0. The questions that were put

1. **Corpus refresh.** No automated refresh path exists for the *governing* corpus. The
   `workbench-factor-refresh` timer maintains the 44 MB operational store, a different artifact.
   Every observation requires coverage through its own session, but re-countersigning a 1.63 GB file
   252 times is not viable, and the per-session binding recorded in an observation is a value-level
   digest rather than a whole-file hash. The governance model needed an explicit owner ruling.
2. **Four deployment inputs.** `dgs3mo_path`, `trial_ledger_path`, `build_info_path` and
   `deployment_manifest_path` are all in `forward_deployment_config._REQUIRED_KEYS`;
   `load_forward_deployment_config` refuses a configuration that omits any of them.

---

## 1. Ruling — corpus refresh: immutable base plus countersigned session deltas

**Adopted.**

The v2.0 corpus is the **immutable base**:

```yaml
base:
  coverage_through: 2026-07-24
  sha256: 2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87
  universe: governed 14,150 tickers
```

For each later session:

- ingest SEP and ACTIONS **only through the latest complete session**;
- restrict to the same governed universe and schemas;
- produce an **append-only session delta**;
- record row counts, source hashes, coverage, exclusions and validation results;
- hash and countersign the delta manifest.

The base file is **not rewritten and not re-countersigned per session.**

**Periodic compaction is authorized**, initially monthly, into a new full corpus version. The
compacted file receives a new whole-file SHA-256 and its own countersignature. All prior base and
delta identities remain preserved.

### 1.1 Conditions the model is authorized under

The authorization is conditional on all six of these holding:

1. deltas are append-only and session-bounded;
2. no prior session is silently amended;
3. a historical correction requires a **separately documented repair and a new corpus version** —
   the route the 2026-06-15 truncated-ingest defect already took;
4. missing, duplicated, out-of-order or unhashed deltas **fail closed**;
5. each observation binds to the **exact base-plus-delta manifest it used**;
6. the manifest identity is deterministic over: base corpus identity · every ordered delta through
   the observation session · governing universe identity · ACTIONS provenance.

Conditions 1–4 are to be made **structural**, not documentary: enforced in code and fail-closed at
session start, in the manner ADR 0047's evidence states were made structural rather than left to a
checklist.

### 1.2 Binding — store identity and corpus-manifest identity are BOTH mandatory

**Ruled: keep both. `store_identity_sha256` is not replaced.**

The correction was accepted. The existing value-level digest is the stronger runtime proof because it
binds to the rows actually consumed and is rechecked after the read; a manifest hash cannot do that,
and substituting one for the other would weaken the runtime proof.

| Field | Meaning | Proves |
|---|---|---|
| `store_identity_sha256` | value-level digest of the exact session-consumed rows; computed before or during the governed read; recomputed by `verify_store_unchanged` | the consumed dataset **did not change during execution** |
| `corpus_manifest_sha256` | identity of the governed base corpus plus ordered deltas; binds provenance, cutoff, universe, source artifacts, exclusions and countersignatures | **which governed corpus construction was authorized** |

**They must not be aliases or substitutes.** Both are mandatory in every observation.

**Enforced structurally, not by value comparison (ruling 2026-07-27).** Requiring the two digests to
differ is **rejected** as the proof: unequal values do not establish separate derivation, and a
defect hashing two different wrappers around one declaration would pass such a check. Instead
`corpus_manifest_sha256` must be *recomputed* from the canonical governed construction manifest,
`store_identity_sha256` may come only from the existing streamed value-level row digest, and the
runtime refuses either field sourced from the other. Equality is **recorded as an audit condition**,
never a governed refusal.

The deployment manifest additionally records all six of:

```
base_corpus_sha256
ordered_delta_manifest_sha256s
governed_universe_sha256
actions_manifest_sha256
corpus_manifest_sha256
store_identity_sha256
```

The first five describe the **authorized construction**. The last proves **what the session actually
consumed**.

### 1.3 The model extends to DGS3MO

**Ruled: extend immutable-base-plus-delta to the risk-free series.**

The July-21 snapshot is **not** frozen for the full forward year with the last yield silently carried
forward. That would create an avoidable benchmark distortion and make later observations depend on
stale cash-rate data.

```yaml
dgs3mo_base:
  exact frozen artifact
  sha256: 87d8ba2f…825d1
  coverage_through: 2026-07-21

dgs3mo_extensions:
  append-only
  session/date bounded
  separately hashed
  source and retrieval timestamp recorded
  no future-dated values
  ordered in the deployment manifest
```

`DGS3MO_SNAPSHOT_SHA256` is **retained, unchanged, and continues to identify the frozen base**. It is
explicitly **not** to be redefined as the digest of a mutable combined file — that would convert a
frozen pin into a moving target and destroy the property it was created to hold. Instead a separate
composed identity, `dgs3mo_manifest_sha256`, binds base plus ordered extensions, and the runtime
consumes the frozen base plus ordered extensions through the observation cutoff.

Fails closed on missing, duplicated, out-of-order, future-dated or unhashed extensions — the same
four conditions Ruling 1 imposes on corpus deltas.

This is consistent with what `CASH_OR_TBILL_RETURN_binding.md` §38–39 already required of the series
— *"must not auto-refresh during the forward run. Any extension is append-only, separately hashed,
and tied to a documented cutoff"* — which the single-constant preflight could not express.

---

## 2. Ruling — the four deployment inputs

**Authorized.** Artifacts live outside GitHub in controlled, versioned storage. Only their
schemas, durable configuration references and non-sensitive hashes are committed, per
GITHUB-OPS-001 §6.

> **Correction to the premise the question was raised on.** Two of the four artifacts **already
> exist, committed in-repo, byte-exact against the frozen preflight pins.** Verified 2026-07-27:
>
> | Artifact | Path | SHA-256 | Frozen pin |
> |---|---|---|---|
> | DGS3MO | `docs/review/momentum_daily/equal_weight_validation/data/DGS3MO.csv` | `87d8ba2f…825d1` | `DGS3MO_SNAPSHOT_SHA256` — **match** |
> | Trial ledger | `docs/review/momentum_daily/equal_weight_validation/TrialLedger_v1.0.json` | `b7d9d715…8eb6d` | `TRIAL_LEDGER_SHA256` — **match** |
>
> What does not exist is the **configuration file naming them** — no `forward_validation.json` is
> installed, so `load_forward_deployment_config` refuses on all four keys at once. That is a
> different defect from "the artifacts are missing", and it changes the work: for these two the
> action is **locate and install**, not create.
>
> ⚠ **Creating fresh DGS3MO or trial-ledger artifacts would produce different hashes, and the
> preflight would fail closed on every session — correctly.** The prereg froze these; they are
> governing inputs, not deployment-generated records.
>
> **Ruled 2026-07-27: correction accepted. Do not recreate either artifact — install the already
> governed files by exact hash.** A generated replacement, an empty ledger, a normalized CSV, a
> reordered JSON or a reserialized copy **is not equivalent unless its byte hash remains exact.**
> Only `build_info` and `deployment_manifest` remain to be generated.

### 2.1 `dgs3mo_path` — install the frozen base as-is; extend per §1.3

Session-bounded risk-free series containing exactly what the frozen validation logic requires.
Recorded per extension: source · coverage · retrieval time · file SHA-256 · latest value date · **no
future-dated values relative to the observation.**

Install `docs/review/momentum_daily/equal_weight_validation/data/DGS3MO.csv`, sha `87d8ba2f…825d1`,
as the immutable base. It carries the no-future-dating property *a fortiori*: its last observation
(2026-07-21) precedes the forward start (2026-07-24). Extensions beyond that cutoff are append-only,
separately hashed and manifest-ordered under §1.3.

### 2.2 `trial_ledger_path` — frozen, install as-is

The immutable governed trial ledger for the preregistered forward program. Identifies: strategy and
program · frozen hypotheses and trial inventory · prior trial count · prohibited post-start
additions · file SHA-256.

**Do not synthesize an empty ledger merely to satisfy configuration loading.** The governing ledger
is `TrialLedger_v1.0.json`, N=45, pinned by `EFFECTIVE_DSR_TRIAL_COUNT`. The DSR gate consumes N=45;
a synthesized ledger would silently change the gate's severity.

### 2.3 `build_info_path` — to be generated

A generated deployment record binding:

- exact merged commit;
- Python and dependency versions;
- host image and instance identity;
- application package hash;
- frozen Stage-2/3/4 replica hashes;
- creation timestamp.

The commit **must be the merged main commit**, never a branch head — the rule already carried from
Step 4D.

### 2.4 `deployment_manifest_path` — to be generated

The top-level manifest binding the entire session deployment:

- build-info identity;
- base corpus identity and **ordered** delta identities;
- DGS3MO identity;
- trial-ledger identity;
- Account 4 and strategy identifiers;
- witness KMS key, bucket and **operational prefix**;
- configuration hash;
- host identity;
- authorization state.

**Finalized and hashed before observation #1.**

⚠ The manifest names the witness **operational prefix**. Under ADR 0047 that is `witness/`, which
must remain **empty** until the first authorized observation, and the bucket is COMPLIANCE / 2555
days — anything written there is unremovable for seven years. Naming the prefix in a manifest does
not write to it; nothing in manifest generation may exercise a publication path.

---

## 3. Ruling — session host and data delivery

**A separate session-host role is authorized. The eight-action witness role is not to be modified.**

The session host is authorized for **read-only** access to the exact controlled prefixes holding:
the base corpus · session deltas · DGS3MO · trial ledger · build information · deployment manifest.

Grant only the minimum required S3 reads, plus KMS decrypt where applicable. The data-delivery path
inherits **no** bucket mutation, delete, IAM, Object Lock, or witness-signing permission.

**Standing witness role remains exactly eight actions:** `kms:GetPublicKey` · `kms:Sign` ·
`s3:GetBucketLocation` · `s3:GetBucketVersioning` · `s3:GetBucketObjectLockConfiguration` ·
`s3:ListBucket` · `s3:PutObject` · `s3:GetObject`. Not one action is to be added to it to simplify
data delivery — that is precisely what the separate role is for.

⚠ When verifying the new role with `simulate-principal-policy`, pass `ContextEntries` for
`s3:prefix`. `s3:ListBucket` granted under a `StringLike` prefix condition returns implicitDeny
without it — a false alarm that has already aborted one battery.

---

## 4. Authorization state

| Item | State |
|---|---|
| Account-4 live recheck now | **NOT NECESSARY** — verified 2026-07-27, protected by the active hold; re-verify **once, immediately before opening the window** |
| Corpus refresh model | **IMMUTABLE BASE + COUNTERSIGNED SESSION DELTAS** |
| Monthly full compaction | **AUTHORIZED** |
| Four required artifacts | **AUTHORIZED** |
| Separate session-host read role | **AUTHORIZED** (ADR 0047 implementation extension, no new ADR) |
| DGS3MO base plus ordered extensions | **AUTHORIZED** |
| ADR 0048 | **REQUIRED** |
| Recreating DGS3MO or the trial ledger | **PROHIBITED** — install by exact hash |
| Empty or regenerated trial ledger | **PROHIBITED** |
| Modify witness role | **NOT AUTHORIZED** |
| Broker orders / hold removal | **NOT AUTHORIZED** |
| Account-4 activation | **NOT AUTHORIZED** |

Account 4 remains `IDLE`, `operational_hold` ACTIVE `_rev 2`
(`AWAITING_PRODUCTION_SIZING_VALIDATION`), forward session count 0, window not open, cooldown not
started.

---

## 5. Immediate sequence

1. Commit the v2.0 countersignature record in the final batched PR.
2. Implement the base-plus-delta manifest contract.
3. Produce the four required artifacts.
4. Provision the separate session-host role and delivery path.
5. Install the full session runtime.
6. **Verify Account 4 remains IDLE and held.**
7. Open the forward-validation window.
8. Generate observation #1 **only after a complete session ingest**.

Step 8 has no "before market open" deadline: a Monday observation can only be produced after
Monday's close and ingest.

---

## 6. Field-design ruling (final)

| Field | Ruling | Role |
|---|---|---|
| `store_identity_sha256` | **RETAIN** | runtime value-level proof |
| `corpus_manifest_sha256` | **ADD** | governed corpus construction identity |
| `DGS3MO_SNAPSHOT_SHA256` | **RETAIN** | frozen base artifact identity |
| `dgs3mo_manifest_sha256` | **ADD** | base plus ordered extensions identity |
| ADR 0048 | **REQUIRED** | — |
| Empty or regenerated trial ledger | **PROHIBITED** | — |

Both §1.2 items are ruled; nothing on the manifest contract's field design is open.

### 6.1 Governance vehicle

**ADR 0048 is required.** The base-plus-delta model changes durable data-governance architecture and
introduces new fail-closed invariants; it must not exist only in an owner-ruling memo or a deployment
checklist. ADR 0048 governs: immutable base corpus · ordered SEP/ACTIONS deltas ·
historical-correction treatment · full-corpus compaction · `corpus_manifest_sha256` · preservation of
`store_identity_sha256` · immutable DGS3MO base plus extensions · session cutoff rules · fail-closed
delta validation · countersignature and supersession rules.

**The separate session-host role does not need its own ADR.** Its trust boundary does not materially
differ from the architecture ADR 0047 already approved — it is read-only, holds no witness authority,
and adds no action to the eight-action witness role. Document it as an ADR 0047 implementation
extension.

### 6.2 Branch and PR scope (authorized)

Branch `feat/adr0048-corpus-base-plus-deltas`, created from detached main tip `3408376`. One coherent
PR carries:

- governing-corpus countersignature v2.0;
- this owner-ruling record;
- ADR 0048;
- manifest/config contract changes;
- installation **references** for the existing DGS3MO and trial-ledger artifacts;
- generation of `build_info` and `deployment_manifest`;
- only the code needed to enforce the new manifest invariants.

**Excluded from this PR:** corpus files · generated evidence bundles · copied DGS3MO or trial-ledger
duplicates · session-host delivery artifacts · CI-tiering work · Step 4D operability-code cleanup.

### 6.3 One implementation deviation, disclosed

The six manifest identities of §1.2 are recorded across **two** artifacts rather than one.
`store_identity_sha256` is a property of a session's reads and does not exist until a session
performs them; a deployment manifest is finalized before observation #1. Requiring it in the manifest
would force the generator to invent a value — the same fabricated-evidence failure
`deployment_identity.py` exists to refuse. It is therefore mandatory in **observation evidence**,
where it is real, alongside `corpus_manifest_sha256`; the deployment manifest carries the other five
plus `dgs3mo_manifest_sha256`. A manifest **may** still declare a store identity (a per-session
manifest legitimately can) and it is then verified against the session's actual value rather than
trusted. Recorded in ADR 0048 (8); the "both identities, mandatory, never aliases" property of §1.2
is unchanged and is enforced by `require_observation_identities`.

---

## 7. What this ruling does and does not establish

**Establishes:** the maintenance model for the governing corpus, the provenance requirements for the
four deployment inputs, and the permission boundary between session-host data delivery and witness
authority.

**Does not establish and does not authorize:** any performance claim, the opening of the forward
window, a first observation, removal of the Account-4 operational hold, broker order submission, or
Account-4 activation. Activation remains a year-plus program — ≥252 completed sessions, ≥40
rebalances, one complete forward year, then the §7 gate battery, then a **separate** activation
adjudication.
