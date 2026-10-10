# RANGE-002 Governance Hardening — Design v0.1 (PR 3, DESIGN ONLY)

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. No code is authorized by this document.** |
| Date | 2026-10-09 |
| Base | integration branch `ae0b165a` (`apps/backend/app/research/range002/governance/`) |
| Governing | Plan v0.5 (R3, R8, WP0.4, WP0.6, WP0.7, WP4.0, WP4.2, section 9 stops), Addendum A1, ADR 0037 |
| Scope | Three governance gaps: (1) owner-authorized holdout recovery after a verified technical defect, (2) registry-head anchoring against tail truncation, (3) exposure severity classification |
| Not in scope | Any change to a gate, threshold, spec value, partition set or strategy rule. No new external dependency (an ADR would be required and none is proposed). |

> **Owner approval gate.** The owner must approve this design (item by item; Sections 1, 2 and 3 are separable) **before any implementation begins**. Every "Recommendation (not a decision)" below is a recommendation only. Open owner questions are collected at the end of each section and again in Section 5. Nothing here is a `P0:` value; agents will not choose one.

---

## 0. Baseline: what the code does today (read before the designs)

Facts verified in the code on `ae0b165a`:

- **Holdout token** (`holdout_token.py`): one file per transition under a directory, `<spec>.token.json` (ISSUED), `.intent.json` (INTENT), `.verified.json` (CONSUMED), each created `O_CREAT|O_EXCL` + fsync. `INTENT` is treated exactly like `CONSUMED` (`HoldoutAlreadyOpenedError`). `errors.py` states re-issue "requires the defect-record + owner-approval path, which is deliberately not implemented here."
- **Consume timing.** `results_guard.authorize()` calls `holdout_store.consume(token, run_id)` *last*, after the registry OPEN-row check, but **before any compute and before any unseal**. So a token is burned when the capability is minted, not when strategy results are read. A crash at any point after `begin_consume` therefore does not tell us whether results were produced or seen. This is the property the recovery design must exploit with *evidence*, not assumption.
- **Run registry** (`run_registry.py`, `hashchain.py`): hash-chained JSONL; every read re-verifies seq, prev_hash and row_hash. `abort_open_runs` appends ABORTED; all statuses count in `count_runs`; no delete path (public API pinned by test).
- **Known limit, stated in `hashchain.py`'s own docstring:** truncating the tail leaves a valid shorter chain. A *handle* detects rollback only against the count/head it saw in this process (`records()`); a **fresh process has no memory** and accepts a truncated file. `head_hash` is "surfaced so callers can anchor it externally" but nothing anchors it.
- **Exposure ledger** (`exposure_ledger.py`): YAML, `signoff` is a `{signed_by, signed_on}` string pair (no cryptographic binding), `authorize()` refuses on **any** overlapping entry (`hits` non-empty -> `ExposureOverlapError`). There is no severity concept. Entries have no classification field, so "materially exposed" (WP0.6 stop) is undefined in code.
- **Not yet in the tree:** the sealed store (WP4.0), the unseal event log, the audit pack and the verdict-binding to a run. Design item 1 depends on the sealed store's logging being built as specified in Section 1.4; it cannot be satisfied by the current code alone.

### 0.1 Security observations found while reading (also reported to the caller)

These are findings, not fixes, and none is addressed by silently editing code in this PR:

| # | Observation | Where | Severity | Addressed by |
|---|---|---|---|---|
| S1 | **Token reset by deleting files.** The token store trusts directory contents only. An actor with write access to the token directory can delete `.token/.intent/.verified` and call `issue()` again; `issue()` succeeds because the file is absent. The registry still holds the earlier P4 run row, but nothing cross-checks it. This is the largest bypass of R3 in the current code. | `HoldoutTokenStore.issue/state` | High (needs local write access; trivial once had) | Section 1.9 (invariant I-R6: issue/recovery cross-check the registry and anchored head) and Section 2 |
| S2 | **Tail truncation of the registry is undetectable by a fresh process**, including truncating the P4 `run_opened` row; combined with S1 that re-opens the holdout and erases the trial count (R8). | `hashchain.py` | High | Section 2 |
| S3 | **Exposure-ledger sign-off is a plain string**, and the ledger file's sha256 is recorded in the capability but not pinned by the frozen spec or any signed manifest. Replacing the ledger with an empty-but-"signed" one is accepted. YAML duplicate keys silently take the last value (`yaml.safe_load`). | `exposure_ledger.py` | Medium | Section 3.6 (hash-pin + signed envelope; strict loader) |
| S4 | **Torn tail line = permanent lockout.** A crash mid-append can leave a partial last line; `read_chain` raises `RegistryIntegrityError` forever. Fail-closed is correct, but there is no governed repair path, which pressures operators toward ad-hoc editing. | `hashchain.read_chain` | Low-Medium (availability, and a social-engineering risk) | Section 2.7 (owner-signed torn-tail adjudication; never silent repair) |
| S5 | `recorded_at` is caller-controllable (`now=`) and unchecked for monotonicity. Not a bypass of any gate, but chain timestamps are not evidence of order in time. | `hashchain.append` | Low | Section 2.4 (anchor carries a witness-signed time) |
| S6 | `authorize()` can be called more than once for the same OPEN non-holdout run (each call mints a capability). Not a bypass; noted for run-count accounting. | `results_guard.authorize` | Low | No action proposed; mentioned to owner |

---

## 1. Owner-authorized holdout recovery after a verified technical defect

### 1.1 Threat / failure addressed

- **Failure:** a crash (process kill, OOM, power loss, a bug in the engine or sealed-store code) after `begin_consume` leaves the token in `INTENT`, permanently. R3 permits a defect-only rerun with a logged defect record and owner approval, but no mechanism exists, so the only options today are "abandon the holdout" or an ad-hoc file edit (which is the S1 bypass).
- **Threat to avoid:** the recovery path becoming the way to *peek and retry*. A second look at the holdout after seeing results is exactly the data-mining R3/R4 forbid. The design must make "the first run's strategy results were never seen" a **verified, machine-checked fact**, make the owner's approval a **signed, bound, single-use** record, and leave **no operator discretion** between "defect verified" and "replacement token usable".

### 1.2 What is recoverable, and what is never recoverable

| Situation of the aborted holdout run | Recoverable? |
|---|---|
| Crash before the engine wrote anything strategy-related; no seal created | Yes (evidence set E1-E5 below) |
| Stage-1 control failure (WP4.0 step 2): strategy outputs written to the sealed store, controls failed, seal never opened | Yes, if E1-E5 hold. The sealed outputs stay sealed and quarantined forever (Section 1.7) |
| Crash after seal creation, before any unseal-begin | Yes, same as above |
| **Any run where an `unseal_begun` event exists, even without `unseal_completed`** | **No. Permanent.** |
| **Any run whose results, metrics, equity curve, trade list, gate values or verdict were rendered/printed/logged/copied to any location outside the sealed store** | **No. Permanent.** |
| Any case where the sealed-store event log is missing, unreadable, non-contiguous, or its own chain does not verify | **No** (absence of evidence is not evidence of absence) |
| Any case where the defect's trigger or detection depended on result values (e.g. "the run crashed on the date where the strategy lost most") | **No**; see attestation A3 |
| A second recovery for the same defect, or a recovery after the per-spec cap is reached | **No** |
| Token state `NOT_ISSUED` or `ISSUED` | n/a (nothing to recover) |

Rule: **unsealed means spent.** There is no "partial unseal" category, because a human or agent can retain information from any partial view.

### 1.3 Mechanism overview

A new append-only hash chain, `holdout_recovery.chain.jsonl`, built on the existing `HashChainFile` (no new hashing code), **separate from the run registry** so the registry's pinned public API and fold semantics do not change. It carries four record kinds in strict order per recovery:

1. `defect_recorded` - the defect record (1.5), with the evidence bundle digest.
2. `nonread_attested` - machine-verified outcome of E1-E5 (1.4), written by the verifier, not by a person.
3. `owner_authorization` - the signed owner record (1.6), verified against a pinned public key.
4. `recovery_token_issued` - the replacement token (1.7), bound to 1-3.

Each kind may only follow the previous kind for the same `defect_id`; the chain's `prev_hash` makes the sequence tamper-evident, and the chain head is anchored under Section 2 like the registry head. The state of the holdout token store is *derived* (as today) from files, but `HoldoutTokenStore.state()` gains a cross-check (I-R6) so file deletion cannot reset it (closing S1).

### 1.4 Evidence that the holdout was NOT read (machine-checked, all required)

All five must hold; any failure -> refusal, defect stays recorded, nothing issued. The verifier is a pure read-only function with no override parameter.

| ID | Evidence | Source of truth | What it proves |
|---|---|---|---|
| E1 | **No unseal event.** The sealed-store event chain (new, written by the WP4.0 sealed-store code with `HashChainFile`) contains no `unseal_begun` / `unseal_completed` for the aborted `run_id`, and the chain verifies and is contiguous up to a head that is itself anchored (Section 2). The sealed store MUST write `unseal_begun` **write-ahead**, fsynced, before it derives or touches any decryption key or opens the sealed blob. | Sealed-store event chain | The code path that exposes results never started |
| E2 | **Sealed blob unchanged.** If a seal exists for the run, its recorded sha256 (from `seal_created`, hashed before any read) equals the current on-disk hash, and the file is still encrypted/access-controlled (permissions/ACL fingerprint recorded at seal time equal current). If no seal exists, E2 requires that no sealed path exists either. | Sealed store + `seal_created` event | Nothing replaced or altered the sealed outputs; no second copy emitted |
| E3 | **No result-bearing artefact outside the seal.** For the run's output directory: no `audit_pack`, `verdict`, `gates`, `orders.csv`, `diagnosis_report` or other artefact from the plan's section 7 list; registry row for the run is `OPEN` or `ABORTED` with `audit_pack_sha256 = null`. Checked by an allowlist of file names/hashes (only control outputs and logs listed in the run manifest may exist), not by a denylist. | Run manifest + filesystem + registry | No results leaked as artefacts |
| E4 | **Log/trace scan clean.** Process logs and stdout captures for the run contain none of the strategy-result record types (the engine's result emitters write to the sealed store only; the logger is configured with a result-field denylist enforced by a unit test), and the scan tool's own hash and ruleset are pinned. | Run logs | No results leaked through logging |
| E5 | **Defect independence from outcomes.** The defect record's `symptom` and `root_cause` identify a defect reproducible on a **non-holdout** fixture (synthetic, `REPLAY_RNG001` or P3 data) without reading any holdout output, and the `fix_commit` diff does not touch strategy rules, spec-derived parameters, exit candidates, costs or gate code (an allowlisted-paths check: the fix may touch only paths in a defect-fix allowlist the owner approves, e.g. IO, serialization, process management, sealed-store plumbing). | Defect record + git diff | Fix cannot encode knowledge of results (plan: "why the fix does not encode knowledge of results") |

Where a machine check is impossible (E5's judgment part), the **owner attestations A1-A4** in 1.6 are required in the signed record. They supplement, never replace, E1-E4.

**Dependency note:** E1-E4 require the sealed store to exist with the event log above. Until WP4.0 is built, **holdout recovery is unavailable** and a stuck holdout stays stuck (fail closed). This is deliberate.

### 1.5 Defect record schema (`defect_recorded` payload)

All fields required, unknown keys rejected, nothing defaulted (same loader discipline as `exposure_ledger.py`). Canonical JSON, then sha256.

```
schema_version: 1
defect_id: "<spec12>-D<nn>"          # unique within the recovery chain
spec_sha256: <64hex>
parent_run_id: "range002-run-NNNNNN"  # the aborted P4 run; must be ABORTED in the registry
parent_token_id: <32hex>              # from <spec>.intent.json
parent_intent_sha256: <64hex>         # sha256 of the intent file bytes
detected_at: <UTC ISO-8601>
detected_by: <str>                    # role/identity, not free text "someone"
symptom: <str>                        # what was observed; MUST NOT quote result values
root_cause: <str>
reproduction: {fixture_id: <str>, command: <str>, repro_output_sha256: <64hex>}
                                      # reproduces the defect on non-holdout data
fix_commit: <40hex>                   # the corrected code; must be a descendant of parent run's code_sha
fix_diff_paths: [<str>, ...]          # derived by the verifier from git, not typed by a person
encodes_no_result_knowledge: <str>    # justification (human text; also attested A2)
evidence_bundle_sha256: <64hex>       # digest over the E1-E4 inputs (event chain head, seal hash, file manifest, log-scan report)
result_dependent: false               # must be exactly false; true -> refusal (E5/A3)
```

### 1.6 Signed owner authorization record

`owner_authorization` payload (owner signs the canonical envelope):

```
schema_version: 1
domain: "RANGE002-HOLDOUT-RECOVERY-v1"     # domain separation
spec_sha256, defect_id, parent_run_id, parent_token_id, parent_intent_sha256
defect_record_row_hash                      # binds to the defect_recorded chain row
nonread_attestation_row_hash                # binds to the machine verdict (E1-E5)
fix_commit
recovery_ordinal: 1                         # which recovery of this spec this authorizes
not_before / not_after                      # UTC; validity window (see Q1.4)
attestations: {A1: "I have not seen any result of the aborted run",
               A2: "the fix does not encode knowledge of results",
               A3: "the defect was not detected or selected by reference to results",
               A4: "I accept this recovery counts as a trial-ledger row and will be disclosed in the P4 report"}
signer_key_id, algorithm, signature
```

- **Signature mechanism (existing, no new dependency):** Ed25519 via `app.validation.witness_protocol.build_verifier` / the `AnchorVerifier` pattern in `chain_witness.py` (`cryptography` is already used there). The owner key is *distinct* from the witness signing key (separate trust root; the agent environment never holds it).
- **Where the owner public key is pinned:** a hash-pinned entry (key id + public bytes) in a signed governance manifest outside the agent-writable tree. Pinning it only in a file the agent can edit would defeat the point. See Q1.2.
- **Verification is stateless and strict:** signature valid under the pinned key; `domain` exact; every bound hash re-derived from the chain rows (not trusted from the record); `now` inside `[not_before, not_after]`; `recovery_ordinal` equals (number of prior `recovery_token_issued` rows for this spec) + 1; no prior `owner_authorization` for this `defect_id`.
- **Single use.** The authorization is consumed by the `recovery_token_issued` row that references its row hash; a second issue referencing the same row hash is refused (O_EXCL file named by that hash as well as chain check).
- **No discretionary bypass.** There is no parameter, environment variable, flag or CLI option that skips E1-E5, the signature, the window or the count. The only inputs are the chain, the stores and the pinned key. A test enumerates the public API and signature of the recovery module to pin this (same technique as `REGISTRY_PUBLIC_API`).

### 1.7 Replacement token: derivation and binding

- File: `<spec_sha256>.recovery<k>.token.json` (k = recovery_ordinal), created `O_CREAT|O_EXCL`, fsynced, alongside the existing state files. The original `intent.json` / `token.json` are **never modified or deleted** (they are the evidence).
- `token_id' = sha256("RANGE002-HOLDOUT-RECOVERY-TOKEN-v1" || parent_token_id || defect_id || owner_authorization_row_hash || k)`, hex-truncated to 32 chars for parity with `secrets.token_hex(16)`. It is **derived, not random**, so any verifier can recompute it from the chain; a token that does not recompute is `HoldoutTokenInvalidError`.
- The replacement token file records `parent_token_id`, `parent_run_id`, `defect_id`, `authorization_row_hash`, `recovery_ordinal`, and the chain row hash of `recovery_token_issued`. `HoldoutToken` gains optional lineage fields; `validate_unused` for a recovery token additionally re-verifies the whole chain (defect -> attestation -> authorization -> issue) and that the parent is still unseen (E1 re-run at validate time, so a change in the sealed store after issue is caught).
- The replacement token is consumed by the **same two-phase INTENT/VERIFIED protocol** (`<spec>.recovery<k>.intent.json` / `.verified.json`). A crash during the replacement run leaves it `INTENT` = spent. There is no "recovery of a recovery" unless the cap allows and a **new** defect and authorization exist.
- **Counts:** one recovery per defect_id; **recommended hard cap of 1 recovery per spec** (a code constant, not a configuration value, so changing it is a reviewed code change). See Q1.1.
- **Run binding:** the replacement run is a normal new registry row (`open_run`, holdout partition, new `run_id`), and its `run_opened` payload carries the recovery ordinal and authorization row hash (additive optional field; `_fold` ignores unknown payload keys today, but the payload schema change is a reviewed change). `authorize()` for a recovery token additionally requires that field to match.

### 1.8 Trial-ledger treatment (R8)

- The aborted run **stays in the registry as ABORTED and keeps counting** in `count_runs`; nothing is deleted, reclassified or hidden. (`close_run` cannot re-close a closed run, so the DEFECT classification lives in the recovery chain, not by rewriting the registry row. If the owner prefers registry status DEFECT, `abort_open_runs` would need a defect-aware variant; recorded as Q1.5, not recommended.)
- The replacement run is an additional row; the holdout's total run count for the spec becomes 2 and **both are reported** in the P4 evidence pack ("holdout opened twice; attempt 1 technical abort, defect D-nn"). The multiplicity family does not change: it is the same single hypothesis (m = 1), and a recovery is not a new test of a different idea. The verdict of the aborted run is `INCONCLUSIVE_TECHNICAL`.
- The sealed outputs of the aborted run (if any) remain sealed and quarantined: the seal hash stays in the ledger, and any later attempt to unseal them is a permanent refusal (a `quarantined` event in the sealed-store chain).

### 1.9 Invariants

- I-R1 Unsealed means spent; no override.
- I-R2 Recovery requires E1-E5 AND a valid owner signature AND an unused ordinal; all are checked at **issue** and again at **validate/consume**.
- I-R3 Originals are immutable evidence; recovery only adds files and chain rows.
- I-R4 Aborted run counts forever; recovery adds exactly one run row.
- I-R5 At most 1 recovery per defect and (recommended) per spec.
- I-R6 `issue()` and `state()` consult the registry (any P4 `run_opened` row for the spec) and the recovery chain, so deleting token files cannot make the token appear ISSUED/NOT_ISSUED again (closes S1). Registry/chain integrity is itself protected by Section 2.
- I-R7 No code path takes a "force", "skip_checks", "owner_override" or environment-variable bypass.

### 1.10 Fail-closed behaviour

Every exception is a named `HoldoutTokenError` subclass (new, e.g. `RecoveryEvidenceError`, `RecoveryAuthorizationError`, `RecoveryLimitError`), none caught-and-continued. Missing sealed-store log, unverifiable chain, unreadable key, anchor unavailable (Section 2), clock outside window, ordinal mismatch, dirty git tree for the fix commit -> refuse. A partially written recovery (crash between chain rows) leaves the earlier rows in place and issues nothing; a restart resumes verification from the chain and never infers progress.

### 1.11 Test plan (negative tests written first; each must fail on the unfixed design)

1. Unsealed run: `unseal_begun` present (no `unseal_completed`) -> `RecoveryEvidenceError`; also with completed.
2. Sealed-store event chain missing / corrupt / truncated / not anchored -> refuse.
3. Seal hash differs, permission fingerprint differs, extra sealed copy exists -> refuse.
4. Unlisted artefact (audit pack, `verdict.json`, CSV) in run dir -> refuse; result-field denylist hit in log -> refuse.
5. `result_dependent: true`, or fix touches a path outside the allowlist, or fix_commit not a descendant of the parent's code_sha -> refuse.
6. Authorization: bad signature, wrong key id, wrong domain, wrong spec, wrong defect, wrong parent token/intent hash, tampered attestation text, expired, not-yet-valid, replayed (second issue with same row hash), wrong ordinal, second recovery for same defect, recovery beyond cap -> each its own named refusal.
7. Authorization signed by the agent/witness key (not the owner key) -> refuse (key separation).
8. S1 regression: delete token files and call `issue()` with a P4 row in the registry -> refuse; truncate chain tail (with Section 2 anchor) -> refuse.
9. Replacement token: tampered `token_id'`, wrong lineage, parent unseen at issue but unsealed afterwards (validate-time re-check) -> refuse; replacement token cannot validate against a different spec.
10. Crash injection during each recovery step (reuse the `test_crash_injected_inside_consume` style): no state ever yields two usable tokens; replacement-run crash after intent = spent.
11. Concurrency: two racing recovery issues -> exactly one wins (O_EXCL).
12. Public-API pin test: no bypass parameter exists; AST test that no module outside `governance/` references recovery-token constructors.
13. Positive path last: complete defect -> attestation -> authorization -> token -> consume -> registry shows 2 runs, aborted still counted, report disclosure fields populated.
14. Coverage: new module is high-stakes; target >= 95% (same bar as `app/risk/`).

### 1.12 Open owner questions (Section 1)

- **Q1.1** Cap: 1 recovery per spec (recommended), or 1 per defect with a larger spec cap?
- **Q1.2** Where does the owner public key live (signed execution manifest, spec governance block, or an out-of-tree file with S3 version-pinned manifest)? Does an independent reviewer co-sign (two-key)? Recommendation (not a decision): owner key pinned in the signed execution manifest, with independent-reviewer co-signature required for the first recovery.
- **Q1.3** Fix-path allowlist contents (which paths may a defect fix touch)?
- **Q1.4** Authorization validity window (recommended: short, e.g. 14 days) and whether a cooling-off delay applies between defect record and authorization (consistent with the repo's cooldown philosophy; recommended 24 h, owner to set).
- **Q1.5** Accept that the DEFECT classification lives in the recovery chain rather than the registry row?
- **Q1.6** Confirm that recovery is unavailable whenever strategy results were unsealed, even if the crash happened later (this design already says unavailable).

---

## 2. Registry-head anchoring (detect tail truncation by a fresh process)

### 2.1 Threat / failure addressed

A fresh process re-reads `run_registry.jsonl`, verifies the chain and sees a self-consistent file even if the last N rows were removed (S2). Consequences: a run (including the holdout run) can be erased from the trial ledger (R8 violated) and, with S1, the holdout can be reopened. The in-handle rollback check (`HashChainFile.records`) does not help across processes. The goal: a fresh process, **given only the pinned trust roots**, detects that the file has less history than was ever recorded.

### 2.2 Options (existing repo mechanisms only)

| | Option | How | Pros | Cons |
|---|---|---|---|---|
| A | **Reuse the forward-validation witness** (`app/validation/chain_witness.py`, `witness_protocol.py`, `chain_anchor.py`): sign the registry head as a `WitnessedTip` and publish to an `ExternalAnchorSink` | Map `sequence` = registry record count, `session_date` = UTC anchor date, `commit_sha256` = registry `head_hash`, `anchor_sha256` = digest of a local anchor core line. Verify with `AnchorVerifier`; a tip count lower than any witnessed tip = truncation. | Reuses signing, no-overwrite external sink, receipt serialization, `verify_receipt`, and (in production) KMS + S3 Object Lock per ADR 0046/0047; designed for exactly "truncate local log, can't remove externally recorded tip"; fail-closed error codes already exist | The shipped `FileExternalAnchorSink` is development-only (`IS_REFERENCE_IMPLEMENTATION`); production sink and KMS signer sit behind the `witness.*.factory` config strings (ADR 0046 `aws-sdk-isolation`: governance code must **not** import `app.validation.aws`). RANGE-002 research runs in an isolated non-production environment (owner ruling C12), which may not have the production witness. `WitnessedTip` field names are observation-shaped (reuse is by mapping, not renaming). |
| B | **Anchor the head into the audit chain** (`audit_log`, `AuditLogger`) | New `AuditAction` value for "range002 registry checkpoint" with `{count, head_hash}` | Existing hash chain + DB-level immutability triggers; no new store | Couples a research governance package to the application DB (the research env is isolated, C12); requires an `AuditAction` enum change **and** a new on-call playbook scenario (CLAUDE.md "proven costly"); the audit chain has no external anchor for this purpose; a different trust domain from the owner-held keys |
| C | **Signed append-only manifest in controlled S3** (GITHUB-OPS-001: manifest pinning Version ID + SHA-256, `manifests/s3/`) | Periodic/at-event checkpoint file `{count, head_hash}` uploaded to a versioned bucket; manifest records Version ID | Uses an existing governed custody pattern; independent of the local box; owner-visible | Human-in-the-loop upload, so freshness is only as good as the cadence (an erased tail between checkpoints is undetectable); must be fetched and verified (needs network); a fresh process needs the manifest path |
| D | **Owner-held head in the signed approval log** (`approval_log.md` sign-offs) | Owner records `{count, head_hash}` at each sign-off | Zero infrastructure | Manual, coarse, easy to forget; weakest freshness |
| E | **Git-committed checkpoint** | Commit head hashes to the repo | Simple | A local attacker who can edit the registry can also edit a local clone; only meaningful after push; conflicts with GITHUB-OPS-001 (pushes per checkpoint multiply CI); not signed |

### 2.3 Recommendation (not a decision)

**Option A as the automatic, per-event mechanism, with Option C as the owner-visible periodic custody copy, and Option D at each phase sign-off.** Rationale: only A provides *automatic, signed, independently stored* anchoring that a fresh process can verify offline given a pinned public key; it is the repo's existing answer to exactly this threat, so no new dependency or ADR is needed. B is not recommended (couples isolated research to the application DB and forces enum + playbook work). If the research environment cannot reach the production sink, the minimum viable fallback is A with a **separately-credentialed** sink **plus** C, and then the owner must explicitly accept, in writing, that the reference sink is not tamper-resistant (existing enforcement refuses it for governed forward sessions; RANGE-002 would need its own explicit, recorded owner acceptance, Q2.1).

### 2.4 Proposed mechanism (Option A)

- **When to anchor (checkpoints):** after every `open_run`, `close_run`, `record_selection`, recovery-chain row, and on every `authorize()` that is about to mint a capability for a *result-bearing* partition (DEVELOPMENT_*, HOLDOUT, PAPER). REPLAY_RNG001 (never citable) is anchored at close only.
- **What is anchored:** `{registry_count, registry_head_hash, recovery_chain_count, recovery_chain_head_hash, exposure_ledger_sha256, spec_sha256}` folded into the `WitnessedTip` mapping (the extra fields are inside the digest that `anchor_sha256` commits to, so the signature binds them).
- **Write order (copied from `chain_anchor.append_anchor`):** external sink first, local anchor line second; a crash between leaves local behind the sink, diagnosed as `EXTERNAL_WITNESS_AHEAD` and stopped, never "repaired" by regeneration.
- **Verification on open (every process start, and before every result-bearing `authorize()`):** read the external sink, verify each receipt with the pinned verifier, require (i) the local registry has `count >= max witnessed count`, (ii) the local record at index `witnessed_count` has `row_hash == witnessed head_hash`, (iii) the local anchor log and sink agree. Truncation, replacement, or a fork all fail closed with the named codes already used by `chain_anchor` (`EXTERNAL_WITNESS_BEHIND`, `...DIVERGES`, etc.) mapped to a new `RegistryAnchorError(GovernanceError)`.
- **Semantics of "behind":** local rows beyond the last witnessed tip are legal (a crash between append and anchor); such rows are *un-anchored* and the next operation must anchor them before any further result-bearing step.
- **Pinned trust roots:** verifier public key bytes (algorithm-qualified per ADR 0045) and sink identity come from the governed deployment configuration, never from the registry directory.

### 2.5 Invariants

- I-A1 No result-bearing `authorize()` succeeds unless the registry head (and recovery-chain head) is anchored and verifies *in this call*.
- I-A2 The anchor can only move forward: the sink is no-overwrite (O_EXCL / Object Lock); a lower count than any witnessed tip is a hard failure.
- I-A3 The signing key is not writable by the registry writer; owner and witness keys are distinct.
- I-A4 Governance code does not import `app.validation.aws` (the aws-sdk-isolation invariant stays intact; the sink/signer arrive via the factory strings).

### 2.6 Fail-closed behaviour

| Condition | Result |
|---|---|
| Sink unreachable / receipt unreadable / signature invalid / key not pinned | **Refuse every result-bearing run** (`authorize()` raises). Non-result-bearing read-only inspection (listing runs, verifying the chain) may continue but is flagged `UNANCHORED` in its output |
| Local chain shorter than any witnessed tip, or head mismatch at that index | Refuse; report `EXTERNAL_WITNESS_BEHIND`/`DIVERGES`; the incident is an owner escalation, not an auto-repair |
| Local rows beyond the last witnessed tip | Anchor them first; if anchoring fails, refuse |
| Sink ahead of local anchor log | Stop; owner adjudication (existing `EXTERNAL_WITNESS_AHEAD` behaviour) |

### 2.7 Torn-tail handling (S4)

A torn final line is *not* repaired automatically. If the torn line is **after** the last witnessed head, the owner may sign a torn-tail adjudication record (same signed-envelope mechanism as Section 1.6) naming the byte offset and the expected last witnessed `row_hash`; the tool then moves the torn bytes to a quarantine file (retained as evidence) and the chain resumes. If the torn bytes lie within witnessed history, no adjudication is possible (refuse). The adjudication itself is a chain/anchor event.

### 2.8 Test plan

Negative first: (1) truncate N tail rows, fresh process -> refuse; (2) truncate then re-append different rows (fork) -> refuse; (3) replace file with older valid copy -> refuse; (4) sink empty/unreachable/corrupt/forged signature/wrong key -> refuse result-bearing authorize; (5) local behind sink; (6) sink ahead of local; (7) crash between sink write and local write; (8) unanchored rows block the next result-bearing authorize; (9) recovery-chain truncation detected the same way; (10) torn tail inside vs after witnessed history; (11) reference sink rejected unless the explicit owner acceptance record exists; (12) import-lint: governance does not import `app.validation.aws`; (13) positive anchoring flow and idempotent re-run; (14) fresh-process test using a subprocess to prove detection survives process restart.

### 2.9 Open owner questions (Section 2)

- **Q2.1** Is the production witness (KMS + Object-Lock sink, ADR 0046/0047) available to the RANGE-002 research environment (C12)? If not, do you accept the reference-sink fallback plus Option C, in writing?
- **Q2.2** Anchor cadence: all events (recommended) or only result-bearing ones?
- **Q2.3** Same KMS key/sink as forward validation, or dedicated ones (separate trust root recommended)?
- **Q2.4** Option C custody bucket and who uploads.

---

## 3. Exposure severity classification

### 3.1 Threat / failure addressed

Today every exposure-ledger entry blocks every partition that overlaps it, and "materially exposed" (WP0.6 stop: *"If 2022-2025 is materially exposed, stop; the holdout must be replaced by owner decision"*) has no definition. Two failure modes: (a) **over-blocking** pressure: a trivial contact (e.g. an agent listing file names for a year) blocks a partition, tempting someone to delete or edit entries; (b) **under-blocking by judgment**: with no vocabulary, "not material" becomes a discretionary call made in prose. Both erode R2/D01.

### 3.2 Closed vocabulary

`ExposureSeverity` (StrEnum, closed; unknown value = loader error):

| Level | Meaning (what was observed) | Effect on DEVELOPMENT_SELECTION / CONFIRMATION | Effect on HOLDOUT | Effect on REPLAY_RNG001 / PAPER |
|---|---|---|---|---|
| `BLOCKING` (**default**) | Any outcome-bearing observation of returns, P&L, win rate, trade-level results, signal hit rates on that window, or anything not provably less | Overlap refused (`ExposureOverlapError`), as today | Overlap refused; also triggers the WP0.6 stop if the entry covers the holdout window and is not reclassified | REPLAY: unchanged (exempt, engine validation only, never citable); PAPER: not a historical partition, unchanged |
| `RETURN_BLIND_STRUCTURAL` | Structure only, no outcome-bearing information: calendar/coverage counts, symbol lists, missing-minute reports (e.g. WP1.8 coverage report), schema/column inspection | Allowed, **recorded** in the capability as `exposure_notes`; the run may proceed | Allowed only if the owner signature for this entry explicitly names HOLDOUT (see 3.4); otherwise refused | n/a |
| `DISCLOSED_NON_MATERIAL` | A real contact judged not to bias the partition (e.g. aggregate volume stats unrelated to strategy rules), with a written rationale | Allowed + recorded | **Never** allowed in v1 | n/a |

There is deliberately **no "ignored" level** and no way to delete an entry: a reclassification is a new signed record that supersedes by reference; the old entry stays.

Rationale for the asymmetry: the holdout is a one-shot resource (R3); development partitions are the iterative ones where recorded, return-blind exposure is acceptable.

### 3.3 Who classifies

- **Classification is a signed owner act, with an independent-validator co-sign recommended** (Q3.2). A classification downgrading an entry below `BLOCKING` requires a signature; **no signature = `BLOCKING`**. An entry with a missing, malformed, unverifiable or not-yet-valid classification is `BLOCKING` (most conservative default; matches the repo's "conservative defaults" rule).
- Agents may *propose* a classification as text; the loader does not read proposals.
- Signature mechanism: the same Ed25519 envelope/pinned-key approach as Section 1.6 (owner key; domain `RANGE002-EXPOSURE-CLASS-v1`), binding `{entry_id, entry_binding_sha256, severity, rationale, partitions_permitted, signed_on}`.

### 3.4 Effect rules (deterministic, pure function)

`effective_severity(entry) = BLOCKING` unless a valid signed classification record for that `entry.id` exists and its binding hash matches the entry's current content. `authorize()` evaluates, per overlapping entry:

- partition in `DEVELOPMENT_*`: pass iff severity is `RETURN_BLIND_STRUCTURAL` or `DISCLOSED_NON_MATERIAL`; record entry ids + severities into the capability (`exposure_ledger_sha256` stays; add an `exposure_notes` tuple);
- partition `HOLDOUT`: pass iff severity is `RETURN_BLIND_STRUCTURAL` **and** the signed record lists `HOLDOUT` in `partitions_permitted`; otherwise refuse;
- any `BLOCKING` overlap: refuse as today;
- the R2 window and the spec `exposed` list remain independent hard refusals, unchanged and **not** subject to classification.

### 3.5 How "materially exposed" (WP0.6 stop) is decided

Defined mechanically, not by prose: **the 2022-2025 holdout is materially exposed iff at least one ledger entry overlapping the spec's holdout window is not `RETURN_BLIND_STRUCTURAL` with an owner-signed HOLDOUT permission** (i.e. any `BLOCKING`, `DISCLOSED_NON_MATERIAL` or unclassified entry overlapping it). A pure function `holdout_materially_exposed(ledger, spec)` returns the entries that cause it. If non-empty: the plan's stop applies (report to owner; the holdout must be replaced by owner decision), the results guard refuses the holdout regardless, and P4 readiness (G0 "Holdout independence") cannot be signed. The decision rule is the code; the owner's decision is only to classify entries and sign. Whether an AI-session contact with 2022-2025 *outcome* data is `BLOCKING` is a classification the owner makes; by default it is.

### 3.6 Ledger schema migration (YAML -> JSON in this PR line)

- **Schema v2 (JSON)**, canonical JSON (the repo's `spec/hashing.canonical_json`), strict loader: rejects unknown keys, rejects **duplicate JSON keys** (`object_pairs_hook`; closes the S3 duplicate-key weakness), requires `schema_version: 2`.
  ```
  schema_version: 2
  entries: [ {id, start, end, description, source, observed_by,
              severity: "BLOCKING"|"RETURN_BLIND_STRUCTURAL"|"DISCLOSED_NON_MATERIAL",
              observation_class: "OUTCOME_BEARING"|"STRUCTURAL_ONLY"|"UNKNOWN"} ]
  classifications: [ {entry_id, severity, rationale, partitions_permitted: [..],
                      entry_binding_sha256, signed_on, signer_key_id, signature} ]
  signoff: { signed_by, signed_on, signer_key_id, signature }   # now cryptographic (closes S3 part 1)
  migrated_from_sha256: <64hex> | null
  ```
- **Migration is a one-way, deterministic, audited tool, not an edit:** `v1 YAML -> v2 JSON` sets every entry's `severity` to `BLOCKING` and `observation_class` to `UNKNOWN`, carries all other fields verbatim, writes the v1 sha256 into `migrated_from_sha256`, and produces **no** classifications. Behaviour is therefore identical to today until the owner signs reclassifications. The migration output must be re-signed by the owner (v1 `signoff` strings do not carry over as v2 signatures).
- The v1 loader is retained read-only for one release so the migration can verify the source; the v2 loader refuses v1 files and vice versa (named errors). The frozen spec (or the signed execution manifest) pins the **v2 ledger sha256**, closing the "swap the ledger" gap (S3 part 2); `authorize()` refuses if the supplied ledger's sha256 differs from the pinned one.
- Backward-compatibility test: v1 fixtures migrate to v2 and produce identical `authorize()` outcomes (all refusals preserved).

### 3.7 Invariants

- I-E1 Default and every error path = `BLOCKING`.
- I-E2 Closed vocabulary; classification is signed, bound to entry content, append-only, never deleting an entry.
- I-E3 The R2 window and `spec.exposed` are unaffected.
- I-E4 HOLDOUT can never pass on `DISCLOSED_NON_MATERIAL` (v1).
- I-E5 `materially_exposed` is a pure function of the signed ledger and the spec.

### 3.8 Fail-closed behaviour

Unsigned ledger, bad signature, unknown severity, duplicate key, binding-hash mismatch (entry edited after classification), classification for a nonexistent entry, ledger sha256 != pinned -> `ExposureLedgerError` / `ExposureLedgerNotSignedError` / `ExposureOverlapError` as appropriate; never downgrade silently.

### 3.9 Test plan

Negative first: unsigned classification; wrong key; entry edited after classification; unknown severity string; duplicate JSON key; classification for unknown entry id; `DISCLOSED_NON_MATERIAL` on HOLDOUT; `RETURN_BLIND_STRUCTURAL` on HOLDOUT without the permission list; missing severity -> BLOCKING; ledger swapped (sha mismatch vs pinned); v1 file given to v2 loader and reverse; migration determinism and idempotence; v1-vs-v2 authorize parity (all refusals preserved); capability records `exposure_notes`; `holdout_materially_exposed` table-driven over every severity x partition; R2/exposed-list refusals unaffected by any classification.

### 3.10 Open owner questions (Section 3)

- **Q3.1** Is the three-level vocabulary right, or fewer (e.g. only `BLOCKING` and `RETURN_BLIND_STRUCTURAL`)? Recommendation (not a decision): keep all three, but permit only `RETURN_BLIND_STRUCTURAL` (signed, HOLDOUT-listed) and `BLOCKING` on the holdout, as drafted.
- **Q3.2** Owner-only signature, or owner plus an independent-validator co-signature for any downgrade?
- **Q3.3** Is `observation_class` a required field, or only `severity`?
- **Q3.4** Is the WP1.8 coverage report and the `crossed_before_arm` share (plan, around line 381) classified `RETURN_BLIND_STRUCTURAL`, as the plan asks you to confirm?
- **Q3.5** Pin the ledger sha256 in the spec or in the signed execution manifest?

---

## 4. What this design deliberately does not do

- It does not add any external dependency, service or ADR-requiring component; it reuses `HashChainFile`, the witness protocol/sink/signer interfaces, Ed25519 verification and the S3 manifest pattern.
- It does not provide any override, force flag, environment variable or "emergency" path around recovery evidence, the owner signature, the anchor, or exposure classification.
- It does not allow recovery of any unsealed run, any partially unsealed run, or any run lacking a verifiable sealed-store log.
- It does not change a gate, threshold, partition set, the R2 window, the spec, the exit-candidate set, the selection rule or any `P0:` value.
- It does not remove, rewrite or reclassify existing registry rows or exposure entries; recovery and reclassification only append.
- It does not touch the order path, `OrderRouter`, the risk engine, `audit_log` (Option B is described but not recommended) or any CI invariant script; no CI workflow change is proposed.
- It does not build the sealed store or the unseal event log (WP4.0); it states the requirements Section 1 places on them.
- It does not decide who the owner/validator keys are, where they are stored, or who operates the witness; those are owner questions.
- It does not protect against an attacker who holds the owner signing key, the witness key and the sink credentials simultaneously.
- It does not make the replacement holdout run statistically equivalent to a first-time run; the disclosure (two attempts, one aborted) is mandatory in the P4 report.

## 5. Consolidated owner decisions needed before any code

Q1.1-Q1.6, Q2.1-Q2.4, Q3.1-Q3.5. Also: (a) approve or reject each of Sections 1, 2, 3 independently; (b) confirm implementation order (recommendation, not a decision: Section 2 first because Sections 1 and 3 both rely on anchored heads; then Section 3 migration; Section 1 last because it depends on WP4.0 sealed-store logging); (c) confirm the walk-away interval for the implementing PRs (the recovery path is a consequential change; CLAUDE.md suggests a minimum of 2 hours for consequential PRs).

**No implementation starts until the owner has approved this design in writing.**
