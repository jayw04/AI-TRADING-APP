# RANGE-002 Registry Recovery Procedure v0.1 (torn or corrupted run-registry tail)

> **Status: DESIGN ONLY -- NOT IMPLEMENTED.** Level 2 controls described here (signed approvals H4, execution boundary M1, external anchoring M3, copied-registry detection, holdout recovery, exposure severity policy, torn-tail recovery) are not implemented. The merged PR #738 (`b31b5f7b`) and PR #739 (`d61f313a`) provide Level 1 only. Nothing in this document is signed, approved or selected by the owner; all owner decision tables are blank.
>
> **NOTE (2026-10-10, refreshed):** Current code facts (2026-10-10): PR #737 (docs), PR #738 (spec infrastructure) and PR #739 (Level 1 governance infrastructure) are MERGED; `main` is `d61f313a`, whose tree is identical to the reviewed PR 3 head `808d10fb` (tree `8b04684f`). The spec manifest `governance`/`manifest` fields are all-null (nothing is frozen or signed). The Linux acceptance verifier and its 33-id required-test manifest are on `main`. The run-registry/exposure ledger is strict JSON (not YAML); `MAX_ATTEMPT_LIMIT` = 10,000 is a technical ceiling only (not a policy value); attempt budgets are per (genesis, phase) across windows; phase P5 is refused at Level 1. Owner-accepted Level 1 properties (unchanged by this document): a fork-inherited capability is run-bound and is not a security boundary; directory aliases yield a consistent identity but no confinement; a torn registry tail fails closed and locks out (no governed recovery path; see the Registry Recovery Procedure design). Review finding R1-L1b (distinct signatories) is an accepted Level 1 limitation; its distinct-role follow-up (`57dadd52`) is a separate item. No Level 2 control (signed approvals, execution boundary, external anchoring, recovery tool) is implemented or enabled. Superseded statements: the 'Code baseline' row describes the pre-merge branch registry. The recovery procedure has no code implementation; Level 1 still fails closed with `RegistryIntegrityError` and performs no repair. The body is unchanged.

| Field | Value |
|---|---|
| Status | DRAFT for owner review. Nothing in this document is approved, selected or signed. |
| Finding addressed | N6 (no governed path after a torn run-registry tail); design observation S4 in the Governance Hardening Design v0.1 section 0.1 |
| Related designs | Governance Hardening Design v0.1 (sections 1, 2.7); Execution Boundary and Registry Anchoring Design v0.1 (Part C); Approval Signing and Verification Design v0.1 |
| Code baseline | The code fails closed on a damaged registry (`RegistryIntegrityError`) and deliberately implements NO automatic repair. This procedure does not change that. It describes what an authorized human may do **outside** the code path, and what a future tool must enforce. |
| Convention | Every recommendation is labelled "Recommendation (not a decision)". Role-holders, thresholds and tooling are unselected. |

## 0. Scope and non-goals

In scope: a run-registry (hash-chained JSONL) whose final line is incomplete, or a registry that no longer verifies under a full replay.

Not in scope and not authorized by this document:

- any change to a complete, authenticated record (it is evidence);
- any reset, re-issue or recovery of the holdout (that is the separate defect-only recovery design, Governance Hardening Design section 1);
- any automatic or "self-heal" repair, flag, environment variable or override in code;
- running or authorizing any strategy computation during the incident.

## 1. Guarantee statement (Level 1 vs Level 2)

| Level | What this procedure guarantees | What it does not |
|---|---|---|
| Level 1 (accidental misuse, crash, casual bypass) | A crash that leaves a partial final line can be resolved without anyone hand-editing the chain; every step leaves evidence; complete records are never altered; the holdout stays consumed under any doubt. | Nothing is technically enforced against a determined actor. The procedure is **procedural only** until a repair tool exists and is tested per section 10. |
| Level 2 (adversary with local write access, collusion, root on research host) | **None.** Without external anchoring (Execution Boundary design Part C) a registry owner can truncate complete records and present a valid shorter chain; this procedure cannot distinguish that from a crash on its own. | Detection of truncation of complete records, rollback to an older valid copy, or a forged "torn" claim. Those need an externally witnessed head. |

Recommendation (not a decision): until external anchoring exists, treat every recovery under this procedure as a Level-1 control and state that limitation in the recovery record.

## 2. Classification: torn tail versus security incident

The first decision is classification, made before any authorization is sought. The operator proposes it, the independent reviewer confirms it from the preserved evidence (section 3).

A **torn tail** is exactly this and nothing else:

1. the file's last bytes after the final newline-terminated record form a partial line (no terminating newline, or a line that fails to parse as a complete JSON record);
2. every preceding line is a complete record and the full replay of those lines verifies (sequence, `prev_hash`, `row_hash`) with no gap;
3. the partial bytes are explainable by an interrupted append (the crash/process evidence of section 3 shows a writer was active at the time);
4. no externally recorded head, count, audit pack or token file refers to a record that is not among the complete lines.

Anything else is a **security incident, not a repair**. In particular:

- **Rule T1.** A truncation that removes one or more complete records is NOT a torn tail. Indicators: the chain verifies but its count or head is lower than any previously observed value (prior copy, audit pack, token file, holdout state, backup, log line, CI artifact, reviewer notes); a `seq` gap; a fork; a valid chain shorter than a run's recorded `run_opened`.
- **Rule T2.** A mid-file parse failure, hash mismatch, altered record, duplicate `seq`, or a file replaced by an older copy is a security incident.
- **Rule T3.** If classification is uncertain, it is a security incident until the reviewer states otherwise in writing.
- **Rule T4.** A security incident is escalated to the owner as an incident (no repair, no quarantine by the operator), the registry is left read-only and untouched, and all result-bearing authorization stays blocked. How incidents are tracked and who is notified is an owner question (Q-R7).

## 3. Establishing the incident (evidence preservation)

Performed by the operator **before** anything else. The original file is never modified, renamed, truncated, opened for write, or "fixed in place". Work happens on copies.

| Step | Action | Notes |
|---|---|---|
| E-1 | Stop writers. Halt any process holding the registry (research jobs, schedulers). Record who stopped what and when. | Prevents further appends onto a damaged tail. Do not delete lock files. |
| E-2 | Record the incident header: UTC time, host, user, registry path (as configured and resolved), file size, mtime, inode/file id. | Include genesis id and spec hash if readable. |
| E-3 | Create a byte-exact **copy** of the registry (and any sibling lock, token, intent, verified, exposure ledger, holdout-state files) to a write-protected evidence location. | Copy tool and flags recorded; never move. |
| E-4 | Compute SHA-256 of the original and of the copy; compare; record both digests, size and file ids. Repeat the hash of the original at the end of the incident to prove it was not modified. | Two independent hash computations if tooling allows. |
| E-5 | Capture process and crash logs: process list at stop time, crash dumps, application logs, OS event log, disk-full or power events, container/CI logs, git SHA and environment of the writer. | Absence of any crash evidence is itself recorded and weighs toward rule T3. |
| E-6 | Capture last-known good observations: latest backup, last audit pack, reviewer's last recorded count/head, any CI artifact listing counts. | Used for rule T1. |
| E-7 | Hex-dump the final N bytes (Recommendation (not a decision): at least the last 4 KiB) and the offset of the last newline. Record the byte offset where the partial line begins. | Read-only, from the copy. |
| E-8 | Hand the evidence bundle (manifest of paths and digests) to the independent reviewer. | The bundle is itself hashed; the manifest digest goes into the recovery record. |

Evidence storage location and retention are an owner question (Q-R3). Large artifacts follow GITHUB-OPS-001 (controlled storage with a manifest pinning version and SHA-256, not Git).

## 4. Authorization

| Requirement | Statement |
|---|---|
| Authorizers | The **owner** and an **independent reviewer**. Both must sign the same authorization; neither may be the operator who executed section 3 nor the person who performs the repair. |
| Separation of duties (D08) | Roles are those named in decision D08. The role names, the number of distinct humans and who holds each are **unselected**. Recommendation (not a decision): operator, repairer, reviewer and owner are four distinct humans; no AI agent holds any of them; an AI agent never signs, executes or authorizes a repair. |
| What is authorized | A specific action on a specific file state: registry path, SHA-256 of the preserved original, byte offset of the torn bytes, SHA-256 of the torn bytes, expected last complete `seq`/`row_hash`/count, and the classification (torn tail). |
| Scope limit | The authorization covers one incident and one repair, expires after a stated window (Q-R4), and cannot be reused. |
| Signature form | Level 1: written, dated, named sign-off recorded in the recovery record (human attestation). Cryptographic signing follows the Approval Signing design if and when that is built; neither form is selected here (Q-R5). |
| Reviewer's checks | Independently recomputes the evidence digests, replays the chain from the copy, applies rules T1-T4, confirms no external reference exceeds the last complete record, and states "torn tail" or "security incident" in writing. |

If either signature is missing, expired or refers to a different file state, no repair occurs.

## 5. What a repair may and may not do

May do (only after section 4, only on the **live** file, only a torn partial final line):

1. Move the torn partial final line, byte-for-byte, into a quarantine file (new file, exclusive create, never overwrite), and truncate the live registry to end exactly at the last newline of the last complete record.
2. Compute and record SHA-256 of the quarantined bytes, their offset and length.
3. Fsync both files and the directory; leave the original evidence copy (section 3) untouched.

May not do:

- **Never delete or alter a complete authenticated record.** No rewrite, reorder, re-hash, re-number, re-sign, "normalize", or newline fix of any complete line.
- Never repair by rebuilding the chain, recomputing hashes, or appending a replacement for a lost record.
- Never repair anything the classification did not cover (mid-file damage, hash mismatch, fork, gap, shortened chain).
- Never drop, ignore or "forgive" a record on the strength of its content (for example an ABORTED run).
- Never touch holdout state files as part of this repair (section 9).
- Never repair silently: a repair without the recovery record of section 7 is invalid.

Pre-conditions the repairer verifies immediately before acting: SHA-256 of the live file equals the authorized original digest; the offset and bytes match the authorization; no writer holds the file. Any mismatch aborts with no change.

## 6. Re-verification

1. **Full replay** of the repaired registry from byte zero by a process that did not perform the repair, using the production verifier (sequence, `prev_hash`, `row_hash`, genesis id, strict JSON, run-state folds).
2. Compare count and head hash with the authorized expected values; they must equal the last complete record of the preserved original.
3. The reviewer replays the **preserved original minus the quarantined tail** and confirms byte equality with the repaired file.
4. Confirm quarantined bytes plus repaired file bytes equal the preserved original byte-for-byte.
5. Run the registry-integrity subset of the Level 1 Acceptance Test Plan against the repaired file in a scratch copy.
6. Failure at any step: stop, restore nothing automatically, escalate as security incident (rule T3).

## 7. Recovery record (immutable, appended)

An immutable recovery record is appended to a recovery log. Recommendation (not a decision): a separate append-only hash-chained file (reusing the existing chain primitive) rather than a row in the damaged registry, so the registry's public API and fold semantics are untouched; whether the record also appears as a registry row is Q-R6.

Fields (all required):

| Field | Content |
|---|---|
| `incident_id`, `opened_utc`, `closed_utc` | identifiers and times |
| `classification` | `TORN_TAIL` (the only value that permits repair) |
| `original_evidence_ref` | location, SHA-256 and size of the preserved original copy; manifest digest of the full evidence bundle |
| `original_sha256_at_close` | re-hash of the original at close (equal to the opening digest) |
| `quarantine_ref` | location, SHA-256, byte offset and length of the quarantined bytes |
| `expected_last_complete` | `seq`, `row_hash`, record count |
| `repaired_sha256`, `replay_result` | digest of repaired file; full-replay output reference |
| `authorization_ref` | reference to the owner authorization (digest of the signed text) |
| `reviewer_ref` | reviewer identity, classification statement, digest of review notes |
| `operator`, `repairer` | identities (distinct from owner and reviewer) |
| `inflight_runs` | list of run ids and their disposition (section 8) |
| `holdout_state_at_incident` | holdout state observed and the statement in section 9 |
| `limits_statement` | "Level 1 procedural control; no external anchor; Level 2 not claimed" |
| `owner_signature`, `reviewer_signature` | blank until signed |

The recovery log is append-only: no record is edited. A mistaken record is superseded by a later record that references it.

## 8. In-flight runs

- Any run OPEN in the registry at the incident is recorded as **ABORTED** (by the existing abort mechanism, appended after the repair and re-verification). It **still counts** toward run counts and attempt limits forever; nothing is deleted, hidden, reclassified or re-opened.
- A run whose `run_opened` record lies in the quarantined torn bytes is unknown to the registry. It is listed in the recovery record as "possible lost open", and the reviewer determines from process logs whether it could have started computing. Absent an owner decision (Q-R8), the attempt is treated as consumed.
- No capability minted before the incident remains usable after it. All pre-incident capabilities are considered void; a new authorization is required.
- Results produced by a run whose registry state is uncertain are not evidence (no verdict may be issued from them).

## 9. Interaction with holdout state

- **A holdout authorization mark is never undone.** Repair does not delete, reset, re-issue or rewrite any holdout token, intent, verified or authorization record, and must not be used as a route to the defect-only holdout recovery design.
- **Any uncertainty about holdout access keeps the holdout consumed.** If the quarantined bytes might have contained a holdout authorization, if holdout state files and registry disagree, or if the reviewer cannot rule out an authorization, the holdout is recorded as consumed.
- Holdout state present but not reflected in the registry (for example the mark was written and the registry append was torn) is recorded as consumed and noted in the recovery record; the registry is not edited to match.
- Any later wish to re-open the holdout follows only the owner-authorized defect recovery design, with its own evidence tests.

## 10. Future implementation: required behaviour and negative tests

A repair tool, if ever built, must be a separate, reviewed module with no default behaviour and no path from `authorize()` or the registry to it. It must refuse unless all authorization inputs verify. Required negative tests (all written before the tool and all fail closed):

| ID | Case | Expected |
|---|---|---|
| RN-1 | Truncation removing one complete record (file ends cleanly on a newline) | Tool refuses; reports "not a torn tail" |
| RN-2 | Truncation removing several complete records while leaving a partial line | Refuse |
| RN-3 | Mid-file corrupted line, altered byte, hash mismatch, duplicate `seq`, fork, gap | Refuse |
| RN-4 | File replaced by an older valid copy | Refuse |
| RN-5 | Live file digest differs from authorized original digest | Refuse, no change |
| RN-6 | Offset or torn-bytes digest differs from authorization | Refuse |
| RN-7 | Missing, expired, reused, or wrong-incident authorization; missing reviewer; owner equals reviewer; operator equals repairer | Refuse |
| RN-8 | Any attempt to alter a complete record, including a trailing-newline "fix" | Refuse; byte-equality test on complete lines |
| RN-9 | Quarantine file exists, is a symlink/hardlink, or is reached through a path alias | Refuse (exclusive create) |
| RN-10 | Crash injected at each step (before quarantine write, after quarantine before truncate, after truncate before record) | Every state either unchanged or resumable with evidence; never a state where bytes exist in neither file |
| RN-11 | Concurrent writer or second repairer | Exactly one proceeds; the other refuses |
| RN-12 | Repair attempted while a holdout mark exists or state is uncertain | Holdout state byte-identical after; recorded as consumed |
| RN-13 | In-flight OPEN run at repair | ABORTED and still counted |
| RN-14 | Public API pin: no force, skip, override, env-var or "emergency" parameter exists; no module outside the tool references it | Test passes |
| RN-15 | Full replay of repaired file by a separate process fails to match expected count or head | Repair marked failed; escalation |

## 11. Operator checklist (blank)

All sign-off cells are blank. Nothing here is completed.

| # | Step | Evidence to attach | Reviewer check | Sign-off (name / date / signature) |
|---|---|---|---|---|
| 1 | Writers stopped, incident header recorded (E-1, E-2) | stop record, header | | |
| 2 | Byte-exact copy of registry and sibling files made (E-3) | copy location, tool and flags | | |
| 3 | SHA-256 of original and copy recorded and equal (E-4) | digests | | |
| 4 | Process and crash logs captured, or absence noted (E-5) | log bundle | | |
| 5 | Last-known-good count/head observations gathered (E-6) | list with sources | | |
| 6 | Tail hex dump and torn-line offset recorded (E-7) | dump, offset | | |
| 7 | Evidence bundle manifest hashed and handed over (E-8) | manifest digest | | |
| 8 | Classification: rules T1-T4 applied | reviewer written classification | | |
| 9 | If not TORN_TAIL: escalate as security incident, STOP | incident reference | | |
| 10 | Owner authorization signed, scope and expiry stated | authorization text digest | | |
| 11 | Independent reviewer authorization signed | reviewer notes digest | | |
| 12 | Pre-conditions rechecked immediately before repair (digest, offset, no writer) | recheck output | | |
| 13 | Torn bytes quarantined, hashed, fsynced | quarantine digest, offset, length | | |
| 14 | Full replay by a different process; count/head equal expected | replay output | | |
| 15 | Byte-equality: quarantine + repaired = preserved original | comparison output | | |
| 16 | In-flight runs ABORTED and counted; pre-incident capabilities void | registry extract | | |
| 17 | Holdout state unchanged and recorded as consumed if any doubt | before/after state digests | | |
| 18 | Recovery record appended with all fields | record digest | | |
| 19 | Original re-hashed at close and equals opening digest | digest | | |
| 20 | Owner and reviewer close-out | | | |

## 12. Owner/role table (blank, unselected)

| Role | Holder | Signature | Date |
|---|---|---|---|
| Owner | | | |
| Independent reviewer | | | |
| Operator (evidence) | | | |
| Repairer | | | |

## 13. Open owner questions

- **Q-R1** Are the roles of section 4 mapped onto the four D08 roles, and may any be combined? Recommendation (not a decision): none combined.
- **Q-R2** Is a torn-tail repair permitted at all before external anchoring exists, or does the registry stay locked and the project restart from a newly enrolled registry (old one retained as evidence)? Recommendation (not a decision): permit only under this procedure and only for rule-conforming torn tails.
- **Q-R3** Where is evidence stored, for how long, and who can read it?
- **Q-R4** Authorization expiry window.
- **Q-R5** Level-1 attestation form (written sign-off) versus cryptographic signing now.
- **Q-R6** Recovery record location: separate recovery log, a registry row, or both.
- **Q-R7** Security-incident handling: who is notified, and what blocks resumption of governed runs.
- **Q-R8** Treatment of a possibly lost `run_opened` in the torn bytes (count as consumed attempt, or require positive proof it never ran).
- **Q-R9** Whether a repair counts toward a per-spec cap on recoveries.
- **Q-R10** Whether to adopt Governance Hardening section 2.7 (signed adjudication against an externally witnessed head) in place of this procedure once anchoring exists.

Nothing in this document is approved or signed.
