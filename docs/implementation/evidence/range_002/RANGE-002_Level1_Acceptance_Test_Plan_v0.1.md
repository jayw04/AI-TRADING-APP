# RANGE-002 Level 1 Acceptance Test Plan v0.1

> **Status: DESIGN ONLY -- NOT IMPLEMENTED.** Level 2 controls described here (signed approvals H4, execution boundary M1, external anchoring M3, copied-registry detection, holdout recovery, exposure severity policy, torn-tail recovery) are not implemented. The merged PR #738 (`b31b5f7b`) and PR #739 (`d61f313a`) provide Level 1 only. Nothing in this document is signed, approved or selected by the owner; all owner decision tables are blank.
>
> **NOTE (2026-10-10, refreshed):** Current code facts (2026-10-10): PR #737 (docs), PR #738 (spec infrastructure) and PR #739 (Level 1 governance infrastructure) are MERGED; `main` is `d61f313a`, whose tree is identical to the reviewed PR 3 head `808d10fb` (tree `8b04684f`). The spec manifest `governance`/`manifest` fields are all-null (nothing is frozen or signed). The Linux acceptance verifier and its 33-id required-test manifest are on `main`. The run-registry/exposure ledger is strict JSON (not YAML); `MAX_ATTEMPT_LIMIT` = 10,000 is a technical ceiling only (not a policy value); attempt budgets are per (genesis, phase) across windows; phase P5 is refused at Level 1. Owner-accepted Level 1 properties (unchanged by this document): a fork-inherited capability is run-bound and is not a security boundary; directory aliases yield a consistent identity but no confinement; a torn registry tail fails closed and locks out (no governed recovery path; see the Registry Recovery Procedure design). Review finding R1-L1b (distinct signatories) is an accepted Level 1 limitation; its distinct-role follow-up (`57dadd52`) is a separate item. No Level 2 control (signed approvals, execution boundary, external anchoring, recovery tool) is implemented or enabled. Superseded statements: 'PR 2 / PR 3 merge approval' and the references to branches `fix/range002-review-findings` and `fix/range002-review-round3` predate the merges. This plan is a Level 1 test plan and has not been executed; it is included because it records Level 2 gaps (X-H4, T-2). The body is unchanged.

| Field | Value |
|---|---|
| Status | DRAFT for owner review. Nothing in this document is approved or signed. Nothing has been run. |
| Purpose | The formal Level 1 acceptance test the owner requires before PR 2 / PR 3 merge approval |
| Code under test | PR 2 (spec schema, hashing, freeze) and PR 3 (results guard, run registry, exposure ledger, holdout token, verdict) as integrated, including the fixes on branches `fix/range002-review-findings` and `fix/range002-review-round3` |
| Related | Governance Hardening Design v0.1; Execution Boundary and Registry Anchoring Design v0.1; Registry Recovery Procedure v0.1; Approval Signing and Verification Design v0.1; Implementation Plan v0.5 |
| Convention | Recommendations are labelled "Recommendation (not a decision)". Nothing is selected. No workflow file is edited by this document. |

## 1. Threat model

### 1.1 In scope: Level 1

Level 1 means an honest-but-fallible or casually non-compliant operator, and ordinary system faults:

- accidental misuse (wrong path, wrong spec, stale handle, double invocation, wrong order of phases);
- casual bypass (hand-editing a JSON file, deleting a token file, reusing an old audit pack, constructing a helper object by hand, passing a duck-typed collaborator, a symlink to the same file);
- crashes (process killed mid-append or mid-authorize, power loss, partial writes);
- concurrency (threads, multiple processes, stale views of the chain);
- platform differences (Windows versus POSIX locking and symlink behaviour).

### 1.2 Out of scope: Level 2 (explicit list)

The following are NOT tested and NOT claimed by this plan:

1. An adversary with arbitrary write access to the registry, token and ledger directories who recomputes hashes, rebuilds a valid chain, or replaces the file with an older valid copy.
2. Tail truncation that leaves a valid shorter chain, detected by a fresh process (needs external anchoring, Execution Boundary design Part C).
3. Rollback of the whole state directory (registry, tokens, ledger) to an earlier consistent snapshot.
4. Forged signatures or compromise of any signing or witness key; supply-chain compromise of dependencies.
5. Malicious or compromised research code running in the same process or account as the guard (no trusted execution boundary; Execution Boundary design Part B), including reading unsealed results through the filesystem or memory.
6. Root or administrator on the research host, kernel-level or debugger interference.
7. Collusion between owner, reviewer and operator; AI-agent self-approval beyond what code checks.
8. Time manipulation (clock rollback) as an attack.
9. Side channels and covert channels.
10. Physical access, backups restored by an administrator, cloud-account compromise.

Where a test below touches a Level 2 theme, it records the **observed Level 1 behaviour** and marks the Level 2 residual risk; a passing result never upgrades the claim.

## 2. Roles and independence

- **Executor.** An independent reviewer (named by the owner; unselected). Not the agent or person who wrote or fixed the code under test, and not an AI agent that implemented any of PR 2, PR 3 or the fixes.
- The implementing agent may supply the plan's tooling questions and answer factual queries in writing, but does not run tests, edit tests during the run, or choose which results to report.
- Recommendation (not a decision): the executor also does not hold the owner or repairer role of the Registry Recovery Procedure for the same period.
- The owner decides the merge. The report is evidence, not approval.

## 3. Environments and result separation

| Env | Purpose | Reported as |
|---|---|---|
| W: Windows (developer/reviewer machine) | Windows locking (`msvcrt`), junctions, NTFS aliases, path semantics | "Windows results" |
| L: Linux CI (or an equivalent Linux host run by the reviewer) | POSIX `fcntl.flock` semantics, symlinks and hardlinks, kill-9 behaviour | "Linux results" |

Rules:

1. Windows and Linux results are reported in **separate tables**. A Linux pass never stands in for a Windows requirement or the reverse.
2. A test that was **SKIPPED** on either platform is reported as SKIPPED, never as passed (the existing tests already say "SKIPPED (not passed)"). The acceptance report lists every skipped test by node id with reason.
3. Previously skipped tests (known: the symlink/hardlink alias tests, for example `test_f9_symlink_alias_shares_the_lock`, `test_f9_hardlink_alias_shares_the_lock`, and the `test_freeze_hardening` symlink target tests) and all POSIX `fcntl` tests must run in Linux and show zero skips there (section 6). On Windows, symlink creation can need privilege; the Windows report states whether the privilege was available and if not, the tests are SKIPPED, and the Windows column stays "not demonstrated" for them.
4. Test code and commit SHA are frozen before execution. Any change to code or tests during execution invalidates the run and restarts it (section 10).

## 4. Evidence to capture (for every test)

Unless a row says otherwise: commit SHA under test; interpreter and OS versions; exact command; full stdout/stderr; exit code; before and after SHA-256 of the registry, token directory listing and ledger; for exploit tests, the exact refusal exception type and message; wall-clock and any seed. Raw logs are stored in controlled storage with a manifest (GITHUB-OPS-001), not in Git.

## 5. Test matrix

Columns: **ID**, **Setup**, **Exploit steps**, **Expected result**, **Pass criteria**, **Evidence**. Environment column: W, L, or both (B). All fixtures are synthetic; no real data, no real spec, no real holdout, no signing keys.

### 5.1 Re-run of previously demonstrated exploits

Every finding below is re-attempted against the final code. Reconstructed descriptions come from the design documents, the plan and the commit messages of `fix/range002-review-findings` (dbf8e3dc) and `fix/range002-review-round3` (a1b4368c). Where the repository does not contain a description, the row says so and the **owner or implementing agent must supply the original exploit text before the run** (STOP-4).

Naming note: plan v0.4/v0.5 and the P0 decision sheets also use "F1-F11" for feasibility items (for example F3 broker stop-order semantics). Those are unrelated to the review findings F1-F11 below; test IDs here use the prefix `X-` plus the review-finding label to avoid confusion.

| ID | Finding (reconstructed) | Setup | Exploit steps | Expected | Pass criteria | Evidence | Env |
|---|---|---|---|---|---|---|---|
| X-H1 | Holdout authority could be taken from a token directory instead of the registry | Registry with a P4 `holdout_authorized` row; empty or fresh token directory | Delete token/intent/verified files, re-issue, call `authorize()` for HOLDOUT | Refused; registry is the sole holdout authority | Named refusal; no capability minted; token files do not make the holdout usable again | refusal text; dir and registry hashes | B |
| X-H2 | PAPER/REPLAY ranges unbounded | Spec with PAPER and REPLAY partitions | Request ranges outside the declared bounds, overlapping DEVELOPMENT/HOLDOUT dates, inverted ranges | Refused | Every out-of-bound request refused with a named error | per-case refusal | B |
| X-H3 | Spec view / exposure ledger binding forgeable | Frozen synthetic spec and ledger | Hand-built `GuardSpecView`; `dataclasses.replace` of a real view; duck-typed collaborators; direct `ExposureLedger(...)`; subclassed registry | Refused by exact-type or mint check | All refused; only the load path is accepted | refusal text per route | B |
| X-H4 | Approval/signature part of H3/H4 (cryptographic approval signature) | n/a | Not implemented in PR 2/PR 3 by design (owner-reserved, Approval Signing design) | Recorded as NOT IN SCOPE for this run | Report states "H4 not implemented; not tested" and lists as a Level 2 / open item | statement | n/a |
| X-M1 | Trusted execution boundary absent | n/a | Not implemented (Execution Boundary design Part B) | Recorded as NOT IN SCOPE | Report states "M1 open" | statement | n/a |
| X-M2 | Capability not bound to its OPEN run | Two OPEN runs | Use capability from run A for run B; use after run closed | Refused | Named refusal both ways | refusals | B |
| X-M3 | Chain append not locked (concurrent fork) | Registry | See C-series (section 5.7) | See C-series | See C-series | See C-series | B |
| X-M4 | Import lint evadable | Governance modules | Import banned modules by alias, `importlib`, `__import__`, from-import, relative import, indirect through allowlisted module; add an unreviewed pure-function import | Lint test fails closed on each | Each evasion is detected; only the reviewed allowlist passes | lint output | B |
| X-M5 | Holdout check (f) and registry phase order | Registry at each phase | Open P5 without P4, P4 without P3B, out-of-order closes | Refused with named reason | All refused | refusals | B |
| X-L1 | Spec models permissive; blank lists treated as set; freeze overwrote or followed symlinks; future sign-off date accepted | Freeze tool, temp dir | Unknown keys; blank-list as value; freeze onto existing file; freeze to symlink and dangling symlink; sign-off date in the future | Refused | All refused; victim file byte-identical | before/after hashes | B (symlink: L) |
| X-L2 | Description not in repository | | **Owner or implementer must supply** | | | | |
| X-L3 | DateRange accepted datetime | Spec | Supply datetime where date required | Refused | Refused | refusal | B |
| X-F1 | Run-id allocation not unique under threads/stale handles; run closed twice via stale handle; duplicate `run_opened` id folded | Registry; two handles | Threads on one handle; second stale handle; close twice; inject duplicate `run_opened` | Unique ids; second close refused; fold refuses duplicates | All as expected | ids, refusals | B |
| X-F2 | Duck-typed collaborators accepted by `authorize`; ledger constructible directly | See X-H3 | See X-H3 | Refused by exact-type | Pass | | B |
| X-F3 | Hand-built or replaced spec view accepted | See X-H3 | See X-H3 | Refused | Pass | | B |
| X-F4 | Description not separable from the commit message ("F1-F4, F6-F11"; F4 and F5 in this commit group are not itemised) | | **Owner or implementer must supply**; if F5 was handled elsewhere state where | | | | |
| X-F6 | Predecessor evidence for P3B/P4/P5 unverified | Registry; audit packs | See phase-forgery series P-1..P-9 | See P-series | See P-series | | B |
| X-F7 | Holdout consumed on rejection, or not consumed after crash | Registry | Rejection before authorization; other pre-authorization refusals; failure after mark; crash after mark; delete token files/registry rows | Pre-authorization refusal leaves holdout usable; anything after the mark leaves it consumed | Exactly as stated | state dumps | B |
| X-F8 | Holdout once-per-window bypass by editing a P0 field, overlapping window, independence reference | Registry | See H-series | See H-series | | | B |
| X-F9 | Lock keyed on the path, bypassed by aliases | Registry file; symlink and hardlink aliases | See A-series | See A-series | | | L (W also for hardlink if available) |
| X-F10 | Chain reader/writer accepted: no trailing newline, duplicate JSON keys, blank lines, non-canonical lines, short writes, zero-byte write | Registry | See S-series | See S-series | | | B |
| X-F11 | Import lint (round 3 hardening) | | See X-M4 | | | | B |
| X-N1..N8 | **Descriptions are not present in the repository.** The N-labels found in the repo refer to unrelated work (witness negatives, SIP-cache negatives). Round-3 follow-up findings, including the torn-tail finding N6 (Registry Recovery Procedure), cannot be reconstructed from design docs or commit messages. | | **Owner or implementer must supply the original N1-N8 exploit texts** (STOP-4). Known: N6 = torn registry tail locks the chain with no governed repair path; expected behaviour is fail-closed refusal (test T-series), not auto-repair | | | | |

Rule: for every X-row the reviewer runs the **original exploit as first demonstrated** (as supplied by the owner/implementer) and, separately, the variant tests of the series cited. Passing the variant but not the original is not a pass.

### 5.2 Fresh-worktree initialization and registry enrollment (I-series)

| ID | Setup | Exploit steps | Expected | Pass criteria | Evidence |
|---|---|---|---|---|---|
| I-1 | Fresh clone/worktree, no registry file, no enrolled genesis | Call `authorize()` for each partition type | Fails closed; no registry silently created on an authorize path | Named refusal; no new files | file listing before/after |
| I-2 | Fresh worktree, registry path configured but empty file | Same | Refused as not enrolled | Pass | |
| I-3 | Enroll (explicit tool) then authorize | Positive control | Succeeds only after explicit enrollment | Pass | |
| I-4 | Two different registry paths configured (relative and absolute, different directories) with different genesis ids | Open run via path A, authorize via path B | Refused: genesis id or enrollment mismatch | Pass | |
| I-5 | Same registry reached via two path spellings (case variant on Windows, `..` segment, trailing dot, 8.3 name) | Writer through each spelling | One lock, one chain; no fork | Pass | chain hash |
| I-6 | Copy registry file to a new location, keep tokens at the old one | Authorize | Refused (genesis or enrollment mismatch) | Pass | |
| I-7 | Registry replaced by a registry with a valid chain but a different genesis id | Authorize | Refused | Pass | |

### 5.3 Phase-transition forgery (P-series)

| ID | Setup | Exploit steps | Expected | Pass criteria |
|---|---|---|---|---|
| P-1 | Registry with P3B never closed | Open P4 | Refused | named refusal |
| P-2 | Run closed by hand-appending a forged `run_closed` row (no hash recomputation) | Replay | Chain verification fails | RegistryIntegrityError |
| P-3 | Hand-closed run via direct file append with recomputed hashes (Level 1 casual attempt using the public chain API) | Open next phase | Refused if the closure lacks content-bound predecessor evidence; record outcome | Pass or documented Level 2 residual |
| P-4 | Audit pack from run A presented as predecessor evidence for run B | Open P4 or P5 | Refused: pack not bound to this spec and run | named refusal |
| P-5 | Audit pack reused for two successors | Open two P4s / P5s | Second refused | Pass |
| P-6 | Forged predecessor evidence (tampered pack, wrong digest, missing file, unreadable file) | Open P4 | Refused (missing / mismatch) | named refusal each |
| P-7 | Tampered selection record, reformatted selection record (must still pass, canonical JSON), legacy selection row without digest | Open P5 | Tampered refused; reformatted accepted; legacy cannot be verified and is refused | Pass |
| P-8 | Attempt limits: exceed per-phase attempt count; abort and retry; open under another handle | Open | Refused at the limit; aborted runs still count | Pass |
| P-9 | P4 of a different spec as predecessor | Open P5 | Refused | Pass |

### 5.4 Duplicate audit evidence (D-series)

| ID | Setup | Exploit steps | Expected | Pass criteria |
|---|---|---|---|---|
| D-1 | Two runs, same audit pack digest | Close both with it | Second refused | Pass |
| D-2 | Same selection record digest for two selections | Record twice | Second refused | Pass |
| D-3 | Same evidence under different file paths or formatting | Close | Refused (digest equality, canonical JSON) | Pass |
| D-4 | Evidence identical but different spec hash | Close | Refused or bound to spec | Pass |

### 5.5 Crash recovery inside authorize (K-series)

Crash injection uses a kill at defined points (fault hook or monkeypatch for in-process; `kill -9` / `taskkill /F` for process tests).

| ID | Crash point | Expected state afterwards | Pass criteria |
|---|---|---|---|
| K-1 | Before the holdout authorization mark | Holdout still usable; no capability | Re-run authorize succeeds once |
| K-2 | After the mark, before the registry/consume completes | Holdout recorded as consumed; no usable capability | Re-run refused; token files and registry consistent with "consumed" |
| K-3 | Mid-consume (intent written, verified not) | INTENT treated as CONSUMED | Refused |
| K-4 | After consume, before capability returned | Consumed; no recovery | Refused |
| K-5 | Crash during registry append (torn line) | Next reader fails closed (T-series); no automatic repair | Named refusal |
| K-6 | Crash between `open_run` and `authorize` | Run OPEN; abort possible; run still counts | Count unchanged by abort |
| K-7 | Deleting token files/registry rows after any of K-1..K-4 | Not a recovery path | Refused |

### 5.6 Holdout once-per-window (H-series)

| ID | Setup | Exploit | Expected | Pass criteria |
|---|---|---|---|---|
| H-1 | Holdout authorized for spec S1 window W | Authorize again, same spec | Refused | Pass |
| H-2 | Edit a P0 field to produce spec hash S2, same window | Authorize | Refused (window-level conflict) | Pass |
| H-3 | S3 with overlapping but not identical window | Authorize | Refused | Pass |
| H-4 | Disjoint window | Authorize | Allowed (control) | Pass |
| H-5 | Legacy authorized row without a range | Authorize any window | Blocks every window | Pass |
| H-6 | Independence reference supplied as the basis for a second opening | Authorize | Refused (not validatable) | Pass |
| H-7 | HOLDOUT run recorded without the spec window | Open | Refused | Pass |
| H-8 | Rejection before authorization (bad ledger, bad evidence) | Retry with fix | Holdout still usable | Pass |

### 5.7 Concurrency and kill mid-append (C-series)

| ID | Setup | Exploit | Expected | Pass criteria | Env |
|---|---|---|---|---|---|
| C-1 | N threads, stale views, one file | Concurrent appends | Single linear chain, no fork, unique ids | Full replay verifies; count equals sum of successes | B |
| C-2 | M processes (multiprocessing, spawn), one file | Concurrent appends | Same | Same; repeat at least 200 iterations (Recommendation (not a decision)) | B |
| C-3 | Lock held by process 1 | Process 2 appends | Refused on timeout, not forked | Pass | B |
| C-4 | Readers during a writer | Read | Readers not blocked | Pass | B |
| C-5 | Writer killed mid-append (SIGKILL / taskkill) at random byte offsets, repeat 200 times | Next reader and next writer | Either a complete record or a torn tail; torn tail fails closed (T-series); never a silently accepted partial record; lock released by OS | Pass | B |
| C-6 | Stale handle after another process appended | Append | Proceeds if chain still valid; refuses if history replaced | Pass | B |
| C-7 | Two process close of the same run | Concurrent close | Exactly one succeeds | Pass | B |

### 5.8 Torn tail, truncation and corruption (T-series)

| ID | Setup | Exploit | Expected | Pass criteria |
|---|---|---|---|---|
| T-1 | Partial final line | Read, append, authorize | Fail closed; no automatic repair; append refuses a file without trailing newline | Pass |
| T-2 | Truncate whole final record (clean newline) | Fresh process read | Level 1 observation: valid shorter chain accepted (known Level 2 gap S2); record that outcome, do not claim detection | Documented residual |
| T-3 | Mid-file byte flip, duplicate seq, gap, fork | Read | RegistryIntegrityError | Pass |
| T-4 | Same handle observes a shorter file than before | Read | Rollback detected within the process | Pass |
| T-5 | Recovery Procedure dry-read | Walk the Registry Recovery Procedure checklist on a scratch copy | Procedure is followable without editing complete records | Reviewer notes |

### 5.9 PAPER and REPLAY range abuse (R-series)

| ID | Setup | Exploit | Expected | Pass criteria |
|---|---|---|---|---|
| R-1 | PAPER partition bounded | Request range overlapping DEVELOPMENT or HOLDOUT | Refused | Pass |
| R-2 | REPLAY_RNG001 partition | Request strategy evidence, or range extending beyond the exposed window | Refused; replay never counts as strategy evidence | Pass |
| R-3 | Inverted range, zero length, huge range, datetime values, timezone-aware values | Request | Refused | Pass |
| R-4 | PAPER range in the future / today | Request | Refused or bounded per spec | Pass |
| R-5 | Reuse REPLAY authorization for result-bearing partition | Authorize | Refused | Pass |

### 5.10 Strict JSON and serialisation (S-series)

| ID | Setup | Exploit | Expected | Pass criteria |
|---|---|---|---|---|
| S-1 | Spec, ledger, chain line with duplicate keys | Load | Refused | Pass |
| S-2 | NaN, Infinity, -Infinity, huge ints, lone surrogates, BOM, CRLF, trailing commas, comments | Load | Refused or canonicalised identically | Pass |
| S-3 | Same content, different key order or whitespace | Hash | Same hash (canonical JSON) | Pass |
| S-4 | Different content with equal-looking Unicode (NFC vs NFD) | Hash | Different hashes; no collision acceptance | Pass |
| S-5 | Blank line inside chain; non-canonical line; short write; zero-byte write | Read/write | Refused or looped | Pass |
| S-6 | Extra unknown fields in spec models | Load | Refused (strict models) | Pass |

Note: stop criteria in section 9 use the STOP-n prefix to avoid confusion with the S-series test IDs.

### 5.11 Aliases: symlink, hardlink, junction (A-series)

| ID | Setup | Exploit | Expected | Pass criteria | Env |
|---|---|---|---|---|---|
| A-1 | Symlink to registry | Writers via both | Same lock, no fork | No skip on Linux | L (W if privileged) |
| A-2 | Hardlink to registry | Writers via both | Same lock (lock keyed on file identity) | No skip on Linux | B |
| A-3 | Windows directory junction and NTFS reparse points to the registry directory | Writers via both | Same lock or refusal | Pass | W |
| A-4 | Freeze output as symlink / dangling symlink | Freeze | Refused; victim untouched | No skip on Linux | L |
| A-5 | Symlinked token or ledger directory | Authorize | Refused or consistent single identity | Pass | B |
| A-6 | Case-variant paths on case-insensitive filesystems | Writers | Same lock | Pass | W |

### 5.12 POSIX fcntl locking semantics (L-series, Linux only)

| ID | Setup | Exploit | Expected | Pass criteria |
|---|---|---|---|---|
| L-1 | `fcntl.flock` exclusive non-blocking on the lock byte | Two processes | Second refused on timeout | Pass, not skipped |
| L-2 | Lock released when holder is killed | `kill -9` holder | Lock free immediately | Pass |
| L-3 | Lock inherited across `fork` (child holds duplicate descriptor) | Parent closes, child alive | Documented behaviour; no silent double-writer | Pass or documented |
| L-4 | Lock on file on a network or overlay filesystem (if used by CI) | Same | Document; refuse or note | Reviewer notes |
| L-5 | Lock byte far beyond EOF does not extend or block readers | Read during write | Pass | Pass |
| L-6 | Lock on NFS-like semantics is not claimed | n/a | Report states unsupported | Statement |

## 6. Linux CI job shape (proposal only; no workflow edited)

Constraint: any change to `.github/workflows/ci.yml` flags every project as FULL under GITHUB-OPS-001 and the classifier. It must therefore be **a separate, reviewed change, batched** with any other CI changes, and not made as part of this document or merged merely to run this plan.

Recommendation (not a decision): until that change is approved, the independent reviewer runs the Linux column on a Linux host or WSL they control, using the same commit SHA, and attaches the output as evidence. Cost-aware alternative: a `workflow_dispatch`-only job so it consumes Actions minutes only when triggered by the reviewer.

Proposed job shape (for the future reviewed CI change):

1. Runner: `ubuntu-latest`, Python 3.12, `uv` sync as the backend job does.
2. Run exactly the named test files for the governance and spec packages, with `-rs` (report skip reasons) and `--junitxml=range002_linux.xml`, with the node ids enumerated from this plan, not a glob alone.
3. **Skip gate.** After the run, a small script parses the JUnit XML and fails the job if any test from the "must not skip" list (the symlink/hardlink alias tests, the freeze symlink tests, all POSIX `fcntl` tests, all kill-mid-append tests) has `skipped` status, or is absent (missing = failure). Also fail if the total count of collected tests in the named set differs from the expected count recorded in the plan.
4. The job fails if the `fcntl` import branch was not exercised: a canary test asserts `sys.platform != "win32"` and that `fcntl.flock` is the implementation in use.
5. Upload the JUnit XML and logs as artifacts; the acceptance report quotes the exact run id and artifact digest.
6. Windows results come from a separate Windows run and are reported separately (section 3).
7. The job is not a required check for the `Python CI Gate` unless the owner decides so (Recommendation (not a decision): required only for PRs that touch `apps/backend/app/research/range002/**`, using the existing path classification so unrelated PRs do not pay for it).

## 7. Run procedure

1. Owner freezes the commit SHA and the test list (this plan with filled-in X-L2, X-F4, X-N rows).
2. Reviewer checks out the SHA in a clean worktree; records environment.
3. Reviewer runs the existing automated suites for the packages (collecting skip lists), then the matrix tests in section 5. Manual or scripted exploit steps are saved as scripts in the evidence bundle.
4. Every exploit is run at least twice (first run; repeat after a fresh checkout) and the concurrency/crash tests the stated number of times.
5. Reviewer writes the report (section 8) without edits from the implementing agent.

## 8. Report format

The report contains, in order:

1. Header: commit SHA, date, environments, reviewer identity, tool versions.
2. Scope and Level statement (sections 1 and 11).
3. Summary table: counts of PASS, FAIL, SKIPPED, NOT RUN, NOT IN SCOPE, separately for Windows and for Linux.
4. Full matrix result table (ID, env, result, evidence reference). Windows and Linux separate.
5. Skip register: every skipped test by node id, reason, platform; explicit confirmation that required Linux tests had zero skips, with the CI run id or reviewer log reference.
6. Failures and anomalies, each with reproduction and severity.
7. Residual risk register: every Level 2 theme observed, with the Level 1 behaviour found.
8. Deviations from this plan.
9. Missing inputs (X-L2, X-F4, X-N1..N8 texts) and how they were resolved.
10. Sign-off block (blank).

| Role | Name | Signature | Date |
|---|---|---|---|
| Independent reviewer | | | |
| Owner (receipt) | | | |

## 9. Stop criteria

The run stops, and is reported as "Level 1 acceptance NOT achieved", if any of:

- **STOP-1** Any exploit in sections 5.1 to 5.7 succeeds in Level 1 terms (bypasses a gate, forks a chain, re-opens a consumed holdout, mints a capability it should refuse, alters a complete record).
- **STOP-2** Any test required by this plan is skipped or missing on its required platform without an owner-recorded exception.
- **STOP-3** Any non-deterministic result: a test that passes and fails on repeat without code change.
- **STOP-4** Original exploit texts for X-L2, X-F4 and X-N1..N8 are not supplied by the owner or implementer, or cannot be reproduced.
- **STOP-5** The code or tests change after the SHA freeze.
- **STOP-6** The executor is found not to be independent of the implementation.
- **STOP-7** A Level 2 claim is needed to explain a pass.

A stop does not authorise ad hoc fixes inside the run; fixes happen in new commits, then a full re-run on the new SHA.

## 10. Re-run policy

Any code change under `apps/backend/app/research/range002/**` or its tests after a run invalidates the run. A documentation-only change does not. The report states the SHA it covers.

## 11. Claim wording

### 11.1 Level 1 claim the report may make (only if no stop criterion fired)

> "At commit <SHA>, an independent reviewer executed the RANGE-002 Level 1 Acceptance Test Plan v0.1 against the PR 2 / PR 3 governance and spec code. Every previously demonstrated Level 1 exploit listed in the plan was re-run and was refused or contained as specified. Windows results and Linux results are reported separately; the symlink, hardlink and POSIX fcntl tests ran on Linux with zero skips. The code resists accidental misuse, casual bypass, crashes, concurrent writers and wrong-path use as tested. This is a Level 1 result only."

### 11.2 Claims the report must NOT make

- That the registry, holdout or run counts are tamper-proof, tamper-evident against a determined actor, or "secure".
- That tail truncation or rollback of the registry is detected by a fresh process (it is not, without external anchoring).
- That holdout integrity is guaranteed against an actor with write access to the state directories.
- That research code cannot read unsealed results (no trusted execution boundary exists).
- That approvals or sign-offs are cryptographically authenticated (H4 not implemented).
- That the exposure ledger or spec are independently attested.
- That a Level 2 or "adversarial" review has been passed, or that the system is "production ready", "audited", or "certified".
- That any strategy, spec or result is valid; this plan tests governance mechanics only.
- That passing implies merge approval; the owner decides.

## 12. Open owner questions

- **Q-A1** Who is the independent reviewer, and is an external (non-AI) person required? (unselected)
- **Q-A2** Will the owner or implementer supply the original exploit texts for X-L2, X-F4 and N1-N8, or should the reviewer reconstruct them from the review transcripts (location?).
- **Q-A3** Repeat counts for concurrency and kill tests (this plan proposes 200; Recommendation (not a decision)).
- **Q-A4** Is a Linux run by the reviewer on a host they control acceptable for this acceptance, or must the Linux column come from CI (which needs the separate reviewed ci.yml change)?
- **Q-A5** Should the Linux job be required in the `Python CI Gate`, path-scoped, or dispatch-only (cost, GITHUB-OPS-001)?
- **Q-A6** Is Windows symlink privilege to be provided for the reviewer (developer mode), or are those Windows cases recorded as not demonstrated?
- **Q-A7** Is T-2 (clean truncation accepted by a fresh process) an acceptable documented residual for Level 1 acceptance, pending external anchoring?
- **Q-A8** Is H4 (approval signatures) and M1 (execution boundary) absence acceptable for the merge of PR 2 / PR 3, given they are reported as out of scope?

Nothing in this document is approved or signed.
