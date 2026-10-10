# RANGE-002 Execution Boundary and Registry Anchoring — Design v0.1 (DESIGN ONLY)

> **Status: DESIGN ONLY -- NOT IMPLEMENTED.** Level 2 controls described here (signed approvals H4, execution boundary M1, external anchoring M3, copied-registry detection, holdout recovery, exposure severity policy, torn-tail recovery) are not implemented. The merged PR #738 (`b31b5f7b`) and PR #739 (`d61f313a`) provide Level 1 only. Nothing in this document is signed, approved or selected by the owner; all owner decision tables are blank.
>
> **NOTE (2026-10-10, refreshed):** Current code facts (2026-10-10): PR #737 (docs), PR #738 (spec infrastructure) and PR #739 (Level 1 governance infrastructure) are MERGED; `main` is `d61f313a`, whose tree is identical to the reviewed PR 3 head `808d10fb` (tree `8b04684f`). The spec manifest `governance`/`manifest` fields are all-null (nothing is frozen or signed). The Linux acceptance verifier and its 33-id required-test manifest are on `main`. The run-registry/exposure ledger is strict JSON (not YAML); `MAX_ATTEMPT_LIMIT` = 10,000 is a technical ceiling only (not a policy value); attempt budgets are per (genesis, phase) across windows; phase P5 is refused at Level 1. Owner-accepted Level 1 properties (unchanged by this document): a fork-inherited capability is run-bound and is not a security boundary; directory aliases yield a consistent identity but no confinement; a torn registry tail fails closed and locks out (no governed recovery path; see the Registry Recovery Procedure design). Review finding R1-L1b (distinct signatories) is an accepted Level 1 limitation; its distinct-role follow-up (`57dadd52`) is a separate item. No Level 2 control (signed approvals, execution boundary, external anchoring, recovery tool) is implemented or enabled. Superseded statements: the header 'Code facts verified at `69c36654` (`fix/range002-review-findings` base)' and the B2 description of the guard and registry as they stood on that branch. The body is unchanged and was not re-verified against the merged code.

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. No code, no AWS call, no host, account or ACL change is authorized by this document.** |
| Date | 2026-10-09 |
| Covers | Owner direction 2026-10-09 items (B) M1 trusted execution boundary, (C) M3 externally anchored registry integrity, (D) defect-only holdout recovery review checklist, (F) exposure severity |
| Builds on | `RANGE-002_Governance_Hardening_Design_v0.1.md` (Sections 1, 2, 3 reused; refinements are called out, none is silent), `RANGE-002_Approval_Signing_and_Verification_Design_v0.1.md` (signing contract, allowlist, key custody), Plan v0.5 (R3, R8, R9, R17, WP0.4, WP4.0, WP4.2), ruling C12, ADR 0046 / 0047 |
| Code facts verified at | `69c36654` (`fix/range002-review-findings` base); governance package `results_guard.py`, `holdout_token.py`, `hashchain.py`, `run_registry.py`, `exposure_ledger.py` |

> **Nothing here is a decision.** Every "Recommendation (not a decision)" is a recommendation only. Options, costs, role holders and every decision-table row are **UNSELECTED and UNSIGNED**.

---

## Part B. M1 trusted execution boundary

### B1. Purpose

Say precisely where authorization is verified for the two protected assets (the **2022-2025 holdout data** and the **sealed strategy-results store**, with the governance state that guards them), and what actually stops a hostile or careless writer from bypassing the check.

### B2. What the process-local controls do and do not defend (honest statement)

The results guard (`results_guard.py`) uses: a module-private issue token `_ISSUE`, a module-private nonce table `_ISSUED_NONCES`, a `final` class with `__slots__`, blocked `__setattr__`/`__reduce__`/`__copy__`, and a `@requires_capability` decorator. The holdout token store uses `O_CREAT|O_EXCL` files; the registry is a hash chain in a file.

| Defends against | Does NOT defend against |
|---|---|
| An honest developer or agent calling an engine entry point directly, forgetting the guard, or copying/pickling a capability | **Any code running in the same Python process or the same OS user**: `import results_guard; results_guard._ISSUED_NONCES.add(n)`, reading `_ISSUE`, monkeypatching `authorize`/`require_capability`, `object.__setattr__`, editing the module on disk |
| Accidental reuse of a stale capability; lint-visible bypasses (the import-lint tests) | **Anyone who can edit the repository** (the guard, the tests and the lint are all in the writer's tree) |
| Typos and mis-ordered calls (e.g. consuming a token before the registry check) | **Anyone who can read or write the data files directly**: holdout bars on disk, the sealed store, token files, the registry JSONL, the ledger. Engine entry points check a capability; **file reads do not**. A script that opens the parquet files never meets the guard |
| Casual peeking by a cooperative collaborator | A process running as the same user can delete token files (hardening S1) or truncate the registry (S2) |

Conclusion: in-process capabilities are **defence against mistakes, not against a malicious writer with code-execution privileges.** A malicious writer in the research tree can already forge every in-process control. The platform's statement about R3/R8 integrity must therefore be: *enforced against mistakes by code; enforced against adversaries only by the boundary below, the external anchor (Part C) and the independent validator's offline checks.*

### B3. Threat model for the boundary

| Actor | Capability | In scope |
|---|---|---|
| A1 honest-but-mistaken developer/agent | runs code as the research user | yes (already covered by in-process guard) |
| A2 **malicious or prompt-injected agent / contributor with code execution as the research user** | edits repo, runs scripts, reads/writes anything the research user can | **yes: the main target** |
| A3 compromised Python dependency in the research environment | same as A2 | yes |
| A4 insider with admin on the research host | root on that host | partially (detect via anchor + off-host evidence; not prevented) |
| A5 holder of owner/witness/sink credentials simultaneously | | out of scope (hardening design section 4) |
| A6 AWS account administrator | | out of scope; detected, not prevented |

### B4. Proposed boundary: a data/governance broker as a separate security principal

**Core idea.** Authorization is verified **at the data-access boundary by a different principal than the one that runs strategy code.** The research user cannot read holdout data, the sealed store, or write governance state; only a small **broker** (separate OS account, separate process) can, and it releases data only after verifying a run authorization.

```
 research user (agents, engineers, notebooks)            broker user (deployed, root-owned code)
 --------------------------------------------            -----------------------------------------
 engine / stats code                                     verifies Run Authorization (B6)
   |  request(release, run_auth)  --- Unix socket --->   re-runs guard checks with ITS OWN state
   |  (SO_PEERCRED identity checked)                     writes release_begun (write-ahead, fsync, anchored)
   | <-- streamed data / handle ---------------------   releases data; writes release_completed
                                                          owns: holdout data, sealed store, token store,
                                                                registry, recovery chain, anchor writer creds
```

- **Governance state moves under the broker's ownership**: the run registry, holdout token store, recovery chain, sealed-store event chain and anchor credentials are owned by the broker account; the research user has **no write and no read** access to token/registry/anchor-writer files (read of the *registry* by the research user may be allowed via a broker read API). This closes hardening S1/S2 against A2, not just against honest error.
- **Holdout data is partitioned at ingest** into broker-owned storage. This has a loader consequence: the P1 pull (ruling C5 monthly-chunked SIP loader, PR 5) must not land 2022-2025 data in a research-readable location, and the vendor credential for those months must be broker-held, not research-held (Q-B3). Otherwise the research user can re-download the holdout from the vendor and no ACL helps.
- **Authorization is verified at release time inside the broker** using code the research user cannot modify: the broker is deployed from a pinned commit into a root-owned directory under a validator-signed release record (purpose `BROKER_RELEASE`, binding git commit and file-tree hash, signed under the Approval design). Editing the repo in the research tree does not alter the deployed broker.
- **The broker is small and boring**: stdlib + `cryptography`; no network listener (Unix domain socket, or Windows named pipe with ACL); no `eval`, no plugin loading; a fixed request schema; every request and response length-bounded; no raw-path parameters (clients name logical partitions and run ids, never file paths).

### B5. What the engine is allowed to learn: the honest limit of releasing data

If the broker streams **raw holdout bars to an engine process the adversary controls**, that adversary can compute anything on the holdout, including peeking. Authorization verification at the boundary controls **when and for which run** the data flows; it does not control **what the receiving code does with it**. Three levels follow.

| Level | What the receiving code is | Protects against | Does not protect against |
|---|---|---|---|
| L0 release to research-user process | any code | accidental early reads; direct file reads; token/registry tampering | a hostile engine reading the data it was lawfully handed |
| L1 release only to a **pinned engine identity** | process launched by the broker from an engine image/commit whose hash is in the signed authorization; no network; stdout/stderr captured by the broker; outputs written only through the broker to the sealed store | hostile or edited engine code; exfiltration over network or logs (subject to B7 side channels) | compromise of the broker host; a malicious pinned engine that the validator failed to review |
| L2 L1 plus cryptographic sealing of outputs to a key the research and broker hosts cannot use | | broker-root reading results before the ceremony | custom hybrid-encryption design is not trivial; a KMS-based design would need code under `app/validation/aws/` and an ADR 0046/0047 amendment (not proposed); a `cryptography`-only scheme needs its own review. **Not designed here** (Q-B6) |

### B6. Run Authorization (what the broker verifies)

Payload, strict JSON, canonical hashing as in `spec/hashing.py`, domain `range002.run-authorization.v1\n` (Approval design section 4):

```
schema_version, purpose "HOLDOUT_RUN_AUTHORIZATION" | "DEVELOPMENT_RUN_AUTHORIZATION"
spec_sha256, run_id, phase, partition, date_range{start,end}
registry_count, registry_head_hash          # as anchored at issue (Part C), so a stale authorization cannot ride a rewritten registry
exposure_ledger_sha256, approvals_allowlist_sha256
engine_identity { git_commit, image_or_tree_sha256 }      # REQUIRED for HOLDOUT
token_lineage { ordinal, parent_token_id|null, recovery_authorization_row_hash|null }
not_before / not_after  (minutes for development, hours for holdout), nonce, issuer { role, key_id }
```

- **HOLDOUT**: issuer is the **OWNER key** (human, KMS-signed, Approval design); an independent-validator co-signature is recommended for the first holdout run (Q-B4). A human signature on every holdout run is acceptable because the holdout opens once (R3); it also makes the opening an explicit, logged human act.
- **DEVELOPMENT_***: no per-run human signature (would be unworkable across many P3 runs). The authorization is the **broker's own re-evaluation of the guard checks against broker-owned state**: OPEN registry row written first, partition/phase, exposure policy, anchored head current. Registry-anchored, not KMS-signed. A KMS-signed development authorization is possible but not recommended (cost, friction, no added protection because the research user cannot influence broker state).
- The broker verifies: signature under the pinned allowlist (offline), every bound hash against its own state, window, nonce unused, `engine_identity` equals the process it is about to launch (L1) or the declared engine (L0), anchor verification **in this call** (Part C, rule I-A1).
- **Write-ahead rule**: the broker appends `release_begun` (run id, authorization hash, token ordinal) to its event chain, fsyncs, and has it **anchored** (Part C) **before** the first byte leaves. This is exactly the "unseal_begun written write-ahead" requirement of hardening 1.4 (E1); the broker's event chain **is** the sealed-store event chain that section assumes.
- Token consumption (two-phase INTENT / VERIFIED) happens inside the broker; the research process never sees or can create token files.

### B7. Residual side channels (stated, not solved)

Error messages, timing, resource usage, log lines and exit codes can leak information about results or data. Mitigations proposed: fixed-vocabulary refusals; the broker captures and scans engine stdout/stderr (hardening E4 denylist); engine has no network and no writable path except via the broker; results exist only in the sealed store. These reduce, not eliminate, leakage. Accepted residual: **R-B2**.

### B8. Least-privilege file/ACL layout (on one host; illustrative paths, not decisions)

```
/srv/range002/                       owner root, mode 0755 (traversal only)
  broker/                            root:root 0755   deployed broker code (validator-signed release)
  governance/                        broker:broker 0700
      registry.chain.jsonl             broker:broker 0600  (append-only; chattr +a where the filesystem supports it)
      recovery.chain.jsonl
      holdout_tokens/                  broker:broker 0700
      broker_events.chain.jsonl
      anchor_local.jsonl               broker:broker 0600
      sealed/<run_id>/                 broker:broker 0700
  data/dev/                          research:research-ro   P1 development partitions 2016-2021 (read-only to research)
  data/holdout/                      broker:broker 0700     2022-2025 only; invisible to research
  allowlist/ approvals/ packet/      root:validators 0644   public material; validator-controlled copy exists elsewhere
  run/broker.sock                    broker:research 0660   the only bridge; SO_PEERCRED checked
```

On Windows hosts the equivalent is separate local accounts plus explicit NTFS ACLs and a named pipe ACL; the production research environment is expected to be Linux (Q-B1). The existing `HoldoutTokenStore` and `HashChainFile` code is reused by the broker unchanged; what changes is **who runs it**.

### B9. What the isolated research environment (ruling C12) must provide

C12 says an approved, isolated, non-production research environment is required and **is not yet named**. For this design it must provide, at minimum:

1. A host that is **not** `ec2-paper`, not the warm-standby laptop and not any host that holds Alpaca or production Anthropic credentials. No production data workload (C12 text).
2. At least two OS accounts (research, broker) and, for L1, a container runtime or equivalent for the pinned engine; no sudo for the research account; the broker account has no interactive login.
3. Full-disk encryption; NTP-synchronised clock (approvals and windows depend on it); time source recorded in evidence.
4. Egress allow-list limited to the SIP vendor and the anchor sink (the latter reachable only by the broker/anchor account); no outbound path from the L1 engine container.
5. Off-host log shipping of broker and anchor events and of the host's auth log; the research user cannot delete them.
6. Separate cloud identities: the research account holds **no** AWS role with `kms:Sign` on approval keys and no write access to the anchor sink; anchor credentials belong to the broker/anchor account only.
7. A recorded provisioning journal (operator commands, hashes) stored with evidence per GITHUB-OPS-001.
8. Agent sessions (Claude Code etc.) run only as the research account.

### B10. Phased options, costs and complexity (none selected)

| Option | Scope | Protects | Cost / complexity | Residual |
|---|---|---|---|---|
| **B-0 baseline** | In-process capability only; token and registry files owned by research user; Part C anchor optional | Mistakes only | Zero | A2 bypasses everything; unacceptable for a decisive holdout under the owner's stated threat model |
| **B-1 minimum viable** | Separate broker OS account owning registry, token store, recovery/broker chains, anchor credentials; holdout data in broker-owned storage; Unix-socket release API; Run Authorization verified in the broker; `release_begun` write-ahead and anchored; broker deployed from a validator-signed commit | S1/S2 against A2; unauthorized or early holdout reads by files; token/registry tampering; gives a verifiable "opened" event for hardening 1.4 | Roughly: a broker module (~ few hundred lines), request schema, ACL provisioning, deployment/signing ceremony, ingest change for holdout months, ~2-3 PRs plus an environment build; ongoing: broker release process | Engine receiving holdout data is still research-controlled (L0): a hostile engine can read what it is handed; A4 root on host |
| **B-2 full** | B-1 plus L1: broker launches a pinned no-network engine container for HOLDOUT (and optionally P3 sealed stages), outputs only into the sealed store, stdout/stderr scanned; engine hash in the signed authorization | Hostile/edited engine code on holdout; exfiltration by network/logs | B-1 plus container build/pinning, image custody, sandbox hardening, result-extraction path, engine release signing; larger test matrix (container escape is out of scope); likely 2x B-1 | Broker-host root; side channels; trust in the validator's engine review |
| **B-3 hardened** | B-2 plus L2 sealing to an offline recipient key, and/or a second host/account for the broker with the research host unable to log in | Broker-root reading results; research-host compromise reaching broker | Needs a reviewed crypto design and possibly an ADR (a KMS-based variant needs an `app/validation/aws/` change); separate host operations | Human collusion; A5 |

**Recommendation (not a decision):** B-1 before any P1 holdout-bearing data is acquired (so the ingest design is right from the start), with B-2 required before the **P4 holdout run**. B-3 is deferred and its need is an owner risk-acceptance (Q-B5). The boundary must exist before the vendor data pull; retrofitting after the holdout data has sat in research-readable storage cannot be undone.

### B11. Residual risks and who accepts them

| ID | Residual risk | Owner of acceptance (UNSELECTED) |
|---|---|---|
| R-B1 | At B-1, an authorised engine can read the holdout it is handed | Owner and independent validator, in writing, or require B-2 |
| R-B2 | Side channels (errors, timing, logs, resource use) | Owner |
| R-B3 | Broker-host root or physical access (A4) | Owner; mitigated by off-host evidence and Part C |
| R-B4 | Collusion of owner and validator, or loss of both keys | Owner |
| R-B5 | Vendor credential or raw vendor files reachable by research user | Must be closed by ingest design (Q-B3), not accepted |
| R-B6 | A defect in the broker itself (single trusted component) | Validator review; B-1 keeps it minimal |

### B12. Invariants

- I-B1 The research principal can neither read holdout data, sealed results, token files nor write registry/recovery/anchor state.
- I-B2 Every release of protected data is preceded by a verified Run Authorization and a write-ahead, anchored `release_begun`.
- I-B3 No `boto3`/`botocore` import is added anywhere; the broker and anchor writer reach AWS only through the `witness.signer.factory` / `witness.sink.factory` strings (ADR 0046), and `range002` governance code never imports `app.validation.aws`.
- I-B4 The broker holds no private signing key of any human role.
- I-B5 No bypass parameter, flag, environment variable or "admin" request exists in the broker API.
- I-B6 No data path from vendor to research storage carries holdout months.

### B13. Fail-closed behaviour

Broker unreachable, authorization invalid or expired, anchor unavailable or unverifiable, allowlist/pin mismatch, engine identity mismatch, event chain unverifiable, or any internal exception: **release nothing**. A release that fails after `release_begun` is **spent** (the token is INTENT, per existing semantics). No local fallback, no "degraded" path.

### B14. Test plan (negative first)

1. As the research user: open holdout files, token files, registry, sealed dir directly (expect OS permission denial); attempt to create a token file; attempt to truncate the registry; attempt to replace the socket path.
2. Request with: bad signature, wrong role key, wrong spec, wrong partition/date range, expired, replayed nonce, stale registry head (rolled back), unanchored head, wrong engine identity, authorization from the Approval design's `P0_APPROVAL` domain (domain separation), authorization for another run id.
3. Fuzz/length-bound the request parser; path traversal in logical names; oversized frames; malformed JSON; duplicate keys.
4. Crash injection at each broker step (before/after `release_begun`, after anchor, mid-stream, before VERIFIED): never two usable releases; after `release_begun` the run is spent.
5. Concurrency: two processes request the same holdout release; exactly one wins.
6. Write-ahead ordering test: kill the broker after `release_begun` and before the first byte; confirm the event survives and is anchored.
7. Engine-level (B-2): container has no network; writes outside the sealed path fail; stdout/stderr denylist hit aborts and quarantines.
8. Import-lint and AST tests: no boto3 outside `app/validation/aws/`; `range002` code does not import `app.validation.aws`; no module in the research tree constructs broker-side token or chain writers.
9. A tampered deployed broker (hash differs from the signed release) is refused by the launcher/validator check.
10. Positive path last.

### B15. What Part B does not do

It does not build the broker, change ACLs or name the environment. It does not protect a decisive run against the broker host's root, against owner+validator collusion, or (at B-1) against a hostile engine that has been lawfully handed data. It does not change any gate, threshold, partition or spec value, and it does not alter the order path, `OrderRouter`, the risk engine or the audit log.

---

## Part C. M3 externally anchored registry integrity

### C1. Purpose and relation to the hardening design

Extend hardening Section 2 (Option A, reuse of the forward-validation witness) into a concrete protocol. Everything below uses existing mechanisms: `HashChainFile` rows, `witness_protocol` receipts, the `AnchorSigner` / `ExternalAnchorSink` interfaces, the production KMS signer and the S3 Object-Lock sink behind the `witness.*.factory` strings, and the GITHUB-OPS-001 S3 manifest pattern. **No new dependency; no boto3 outside `app/validation/aws/`.**

### C2. Facts that shape the protocol

- `hashchain.read_chain` verifies seq, `prev_hash`, `row_hash` and skips blank lines; it parses with plain `json.loads` (duplicate keys within a row are not refused, and the row hash is over the *re-serialised* body, so formatting and duplicate-key variants of a line verify). A tail truncation is valid; a fresh process cannot see it.
- Row 1 chains to the all-zero `GENESIS_HASH`, so a chain file from another program or directory is internally valid in this one.
- The witness machinery: a `WitnessedTip{sequence, session_date, commit_sha256, anchor_sha256}` is signed (domain `workbench.witness.v2\n`) and published to an append-only sink; the S3 sink writes with `IfNoneMatch='*'`, deterministic keys from sequence and date, and treats a second different payload for the same tip as `EXTERNAL_WITNESS_DIVERGES`. ADR 0047 pins one production bucket (Object Lock COMPLIANCE, 2555 days) and an eight-action role.
- **The witness signer signs whatever tip it is handed.** A RANGE-002 tip signed by the forward-validation key is indistinguishable in domain from a forward-validation tip. Reusing the *same key and bucket* therefore couples two trust roots and puts permanent (COMPLIANCE) research records in the production witness bucket.

### C3. Anchor targets (existing mechanisms only)

| Target | Role | Notes |
|---|---|---|
| **A. Witness sink + signer (dedicated instances)** | Primary, automatic, per checkpoint | Same code and factory strings, **separate** KMS key, bucket (or prefix with its own IAM scope) and deployment configuration block for RANGE-002. Dedicated provisioning is operator-side by recorded command (ADR 0047 style). May require an ADR 0047 amendment because that ADR fixes one bucket and one role (Q-C1) |
| **B. S3 manifest custody copy** | Owner-visible periodic copy | GITHUB-OPS-001: Version ID + SHA-256 manifest of the checkpoint chain export; cadence per phase gate |
| **C. Signed gate sign-off** | Human checkpoint | At each phase gate the owner/validator approval payload includes the latest checkpoint hash (Approval design `documents[]`) |
| Audit chain (Option B of the hardening design) | Not recommended | Couples isolated research to the application DB; forces enum + playbook work |
| Git commit of heads | Not recommended | Same writer can alter the clone; multiplies CI runs |

**Recommendation (not a decision):** A as the authority, B at every phase gate, C at every sign-off. A's signer/sink credentials are held by the broker/anchor account only (Part B), never by the research user.

### C4. Checkpoint record

Strict JSON, canonical (`canonical_json`), no floats:

```
schema_version      1
domain              "range002.checkpoint.v1"
checkpoint_seq      1, 2, 3 ... (strictly +1)
prev_checkpoint_sha256   null for seq 1, else the previous checkpoint_sha256
chains {
  registry:      { count, head_hash, genesis_row_hash }     # genesis_row_hash = row_hash of row 1 (binds chain identity); null iff count == 0
  recovery:      { count, head_hash, genesis_row_hash }
  broker_events: { count, head_hash, genesis_row_hash }
}
holdout_state_digest     sha256 over the sorted (spec_sha256, token state, intent_sha256) tuples      # S1 cross-check
run_counts               { partition -> {opened, closed, aborted} }                                   # cross-check against a replay of the registry
spec_sha256, exposure_ledger_sha256, approvals_allowlist_sha256
trigger { event_kind, chain, event_seq }
writer { broker_release_sha256 }                                                                     # which broker build wrote this
```

`checkpoint_sha256 = content_sha256(record)`. Mapping into the existing protocol: `sequence = checkpoint_seq`, `session_date =` UTC anchoring date, `commit_sha256 = checkpoint_sha256`, `anchor_sha256 =` digest of the local anchor core line. **Refinement of hardening 2.4**: that section mapped `sequence` to the registry record count; because three chains are anchored together, `checkpoint_seq` is the sequence and the registry count lives *inside* the signed commitment. Truncation detection is unchanged: a local count below the anchored count for any chain is a hard failure.

### C5. Cadence

- **Anchor on every event of every chain** (hardening Q2.2 recommendation), because the checkpoint is also the proof that "the event happened before the effect". The mandatory write-ahead order for irreversible effects:
  1. registry row appended and fsynced; 2. checkpoint written and verified; 3. only then the dependent effect; 4. the effect's own event row appended; 5. checkpoint again.
- For the holdout: `open_run` row → checkpoint → token `INTENT` + `release_begun` → **checkpoint** → first byte released. A truncation that erases `release_begun` is therefore detectable, which is what makes hardening E1 ("no unseal event") evidence rather than assertion.
- `REPLAY_RNG001` events (never citable) may be anchored at close only, with a bounded un-anchored backlog (owner value, Q-C3) that must be cleared before any result-bearing step.
- Cost: one KMS `Sign` and one S3 `PutObject` per checkpoint; the number of events in RANGE-002 is small (hundreds). Object Lock COMPLIANCE makes every checkpoint permanent for the retention period; keep checkpoints small and do not anchor liveness pings.

### C6. Complete chain verification algorithm

Runs in the broker/anchor process, and independently by the validator from copies. **Inputs are pinned trust roots from governed configuration (verifier public key, sink identity, allowlist pin), never from the data directory.** No step has a skip flag.

1. **Load trust roots.** Missing or unreadable → `ANCHOR_TRUST_ROOT_MISSING`, refuse.
2. **Read the sink completely** (`read_all`), verify every receipt with `verify_receipt` under the pinned identity **before** interpreting content. Require: sequences are exactly 1..N with no gap or duplicate; each object key equals the key recomputed from its content; each checkpoint's `checkpoint_sha256` equals the receipt's `commit_sha256`; `prev_checkpoint_sha256` chain intact from genesis; `checkpoint_seq == sequence`; counts and heads per chain are non-decreasing; `signed_at` non-decreasing (evidence). Failures: `EXTERNAL_WITNESS_GAP`, `..._DIVERGES`, `ANCHOR_SIGNATURE_INVALID`.
3. **Read each local chain as raw bytes.** Require: no BOM, no `\r`, ends with exactly one trailing `\n` (a missing final newline is a torn tail, Section C9), no blank lines, no lines after the last newline. For each line: `loads_strict` (duplicate keys and NaN refused), then **canonical re-serialisation must byte-equal the line** (rejecting any non-canonical variant), schema equals `CHAIN_SCHEMA`, `seq` contiguous from 1, `prev_hash` equals the previous `row_hash`, `row_hash` recomputed equals stated. (This tightens `read_chain`, which today skips blank lines and uses plain `json.loads`.)
4. **File identity and permissions.** Not a symlink; regular file; owner is the broker account; mode not wider than policy; same inode/device across the verification (no swap mid-verify); path inside the governed directory after `realpath`.
5. **Chain identity.** For each chain with `count_N > 0`, local row 1 `row_hash == genesis_row_hash` of every checkpoint (rejects substituting another valid chain).
6. **Replay every anchor against the local chain.** For each checkpoint `k` and each chain: local `count >= count_k`; the local record at index `count_k` has `row_hash == head_hash_k`. This single check detects:
   - **truncation** below any anchored count (local count < count_k);
   - **middle deletion / reordering / alteration** of any row at or before an anchored position (the hash at the anchored index differs, or step 3 fails);
   - **fork** (history rewritten after an anchor: the head at the next anchored index differs);
   - **replacement with an older valid copy** (local count < latest anchored count).
7. **Coverage of the tail.** Let `T` be local rows beyond the latest checkpoint's counts. `T` must be empty for result-bearing authorization. If non-empty: it is the *un-anchored tail* (a legal crash window); the broker anchors it (writing the next checkpoint) before any result-bearing step, after verifying each tail row's `prev_hash`/`row_hash` (already done in step 3) and that its event kinds are legal successors (below).
8. **Semantic replay.** Fold the registry (`run_registry` semantics) and recompute `run_counts` and `holdout_state_digest`; require equality with the latest checkpoint for the anchored portion. Check the state machine (no `closed` without `opened`; at most one HOLDOUT `run_opened` per spec unless a recovery chain row authorises another; a P4 `run_opened` implies token state INTENT or CONSUMED — **deleted token files are detected here**, closing S1 independent of the broker).
9. **Cross-chain.** Every recovery-chain row referencing a registry `run_id` or row hash must resolve; `release_begun` events resolve to a registry OPEN row and an authorization hash; no event references a future row.
10. **Local anchor log vs sink** (the existing `chain_anchor` two-sided check): local ahead of sink → `EXTERNAL_WITNESS_BEHIND` (sink missing a tip: refuse); sink ahead of local anchor log → `EXTERNAL_WITNESS_AHEAD` (stop; owner adjudication, never regenerated).
11. **Output.** `ANCHOR_VERIFIED(checkpoint_seq, per-chain count/head, tail_rows)` or one named failure code. Result is also logged (as a non-result-bearing broker event, anchored with the next checkpoint).

Time and ordering are *evidence only* (`recorded_at` is caller-controlled, hardening S5); no decision relies on a wall-clock comparison except the explicit validity windows of signed approvals.

### C7. Fail-closed rules for result-bearing runs

| Condition | Result |
|---|---|
| Sink unreachable, receipt unverifiable, key not pinned, sink identity mismatch | Refuse **every** result-bearing authorize/release. Read-only inspection may proceed and is marked `UNANCHORED` |
| Any failure in C6 | Refuse; incident to owner and validator; no auto-repair; no regeneration of anchors |
| Tail `T` non-empty and anchoring fails | Refuse |
| Backlog of un-anchored non-result events exceeds the owner limit | Refuse the next result-bearing step |
| Verification result older than the last local append | Re-verify (no cached "OK" across an append) |
| Reference (file) sink configured | Refuse unless an explicit, recorded, owner-signed acceptance record exists (hardening 2.3, Q2.1), never silently |

### C8. Recovery from anchor outage

1. During the outage: result-bearing work stops; non-result events may append locally up to the backlog limit; nothing is queued for "later release".
2. On recovery: verify the sink and all prior checkpoints (C6); write **one catch-up checkpoint** covering all rows; verify; resume.
3. If a crash left sink ahead of local (`EXTERNAL_WITNESS_AHEAD`): stop; the owner and validator review the sink object against the local chain; the resolution is a signed adjudication record (Approval design purpose `TORN_TAIL_ADJUDICATION` or a sibling), never regeneration.
4. **Permanent sink loss or key loss** (the case Object Lock is designed to prevent): a *re-anchor ceremony* — owner and validator co-sign a record naming the last checkpoint hash from the custody copy (C3 B/C), a new trust root is pinned, and the discontinuity is disclosed in every later evidence pack. Rare and explicit; its occurrence is itself an incident.
5. A compromised anchor *writer* can add bogus later checkpoints (it cannot remove earlier ones); this can deny service (divergence) but not erase history. Mitigation: dedicated key/bucket so ADR 0047 line-317 style damage is confined to RANGE-002.

### C9. Torn-tail handling (hardening S4)

A crash mid-append can leave a final partial line. Classification by C6 step 3: if the unterminated or invalid bytes lie **after** the last checkpointed count, they are an adjudicable torn tail; if they lie at or before it, no adjudication is possible (refuse). Adjudication is a signed `TORN_TAIL_ADJUDICATION` (owner, validator co-sign recommended) naming the byte offset and the expected last anchored `row_hash`; the tool moves the torn bytes to a quarantine file (retained as evidence) and the chain resumes. The adjudication is itself a chain row and is anchored. Never silent.

### C10. Invariants

- I-A1 No result-bearing authorize/release unless C6 passed in this call and the head is anchored.
- I-A2 The anchor only moves forward: sink writes are no-overwrite; a lower count/seq than any witnessed checkpoint is a hard failure.
- I-A3 The anchor signing key and sink credentials are not readable or usable by the registry-writing research principal; owner/approval keys, anchor key and forward-validation witness key are four distinct trust roots.
- I-A4 `range002` governance never imports `app.validation.aws`; the signer/sink arrive only through factory strings in governed deployment configuration.
- I-A5 Verification is a pure function of (local chain bytes, sink contents, pinned trust roots).

### C11. Test plan (negative first)

Registry and recovery chains:

1. Truncate N tail rows (N = 1, many, all) before / at / after the last anchored position, fresh process.
2. Truncate mid-line (torn) inside vs beyond anchored history.
3. Delete a middle row and renumber `seq` and recompute all downstream hashes (full rewrite attack).
4. Reorder two rows with recomputed hashes; edit a payload with recomputed hashes; insert a row.
5. Replace the file with an older valid copy; replace with a fork that diverges after an anchored index; replace with a valid chain from another directory (genesis mismatch).
6. Byte-level: blank lines, CRLF, BOM, trailing spaces, non-canonical key order, duplicate JSON keys within a row, NaN/Infinity, missing final newline, extra bytes after final newline.
7. Filesystem: symlink swap of the file or directory, hard link, wider permissions, wrong owner, inode swap during verification, read-only filesystem, ENOSPC mid-append, fsync failure.
8. Token/state: delete token files with a P4 row anchored (S1); delete the recovery chain; forge a token file.

Sink and protocol:

9. Sink empty with a non-empty registry; sink unreachable; corrupt object; gap in sequences; duplicate sequence with different bytes; object key mismatching content; forged signature; wrong key; wrong algorithm; receipt from the forward-validation key (domain/identity mismatch); regressing `signed_at`; sink ahead of local; local ahead of sink.
10. Crash injection at each numbered step of the write-ahead order (C5) and of the checkpoint write (sink written, local line not; local line written, sink not).
11. Reference sink configured without the owner acceptance record.

Concurrency:

12. Two **processes** (spawn, not threads) appending to the same chain: exactly one succeeds, the other raises the concurrent-writer error; no interleaved or torn rows.
13. Two processes writing the same `checkpoint_seq`: second gets divergence/no-overwrite.
14. A reader process verifying while a writer appends: reader sees a consistent prefix or a clean failure, never a false pass of a truncated state.
15. Property test: random single-edit mutations (delete, swap, flip a byte, truncate) of a valid chain with a random set of anchors are **always detected** unless the mutation is strictly beyond the latest anchored position and is a pure append.

Isolation and posture:

16. AST/import lint (no `boto3`, no `app.validation.aws` in `range002/**`); `check_aws_sdk_isolation.sh` still passes unchanged.
17. Verification determinism across platforms (Windows development vs Linux production); path/permission checks degrade to **refuse**, not to **skip**, where a platform cannot provide them.
18. Fresh-process subprocess test proving detection survives restart; positive anchoring flow and idempotent re-run last.

### C12. What Part C does not do

It does not add an anchor service, a bucket, a key or a role; it does not decide whether ADR 0047 needs amendment; it does not protect against an attacker who holds the anchor signing key, the sink credentials and the research host at once; it does not make `recorded_at` trustworthy; it does not repair or regenerate anything automatically.

---

## Part D. Defect-only holdout recovery: standalone review checklist

### D1. Purpose and scope

A reviewer-facing checklist for the process defined in hardening Section 1 (which remains the technical specification and is not restated in full). It answers: *who reviews what, on what evidence, and who signs, before a replacement holdout token can exist.* **Current behaviour is unchanged by this document: the holdout token is one-time and fail-closed; `INTENT` is treated exactly like `CONSUMED`; recovery is not implemented; until the sealed store with its write-ahead unseal log exists (WP4.0) and the broker/anchor exist, recovery is unavailable and a stuck holdout stays stuck.**

### D2. Reaffirmed rules

- There is **no unrestricted reissuance**. No operator, owner or administrator action issues a second token for a spec outside this process; no flag, environment variable or file edit does so.
- **Unsealed means spent.** Any `release_begun`/`unseal_begun` event, even without completion, makes the run unrecoverable forever.
- At most **one** recovery per defect and (recommended) per spec; the aborted run stays in the registry and in the trial count; the replacement run is an additional row; the P4 report discloses both.
- Result-dependent defects (found or selected by looking at results) are never recoverable.
- The recovery authority is a **signed owner record** (Approval design purpose `HOLDOUT_RECOVERY`) plus **independent review** (below); the signature does not substitute for machine evidence E1-E5.

### D3. Roles (all UNSELECTED; named by the owner under D08)

| Role | Function in recovery |
|---|---|
| Defect investigator | Technical author of the defect record; must not be the fix author's sole reviewer |
| Fix author | Writes the fix commit |
| Independent validator | Reviews evidence and fix independently; co-signs |
| Owner | Decides and signs the authorization (attestations A1-A4) |
| Key custodian / anchor operator | Provides anchor and event-chain exports; no authority to approve |

### D4. Review checklist (every row must be YES with evidence; any NO stops the process)

| # | Check | Evidence (stored with the evidence pack) | Reviewer | Result / sign-off (blank) |
|---|---|---|---|---|
| 1 | Aborted run state: token `INTENT`; registry run ABORTED or OPEN-turned-aborted with `audit_pack_sha256 = null` | token files; registry rows; verified chain (Part C, C6 output) | Validator | |
| 2 | **E1** No `unseal_begun`/`release_begun` event for the aborted run; event chain verifies, is contiguous and anchored | broker event chain export; anchor verification output | Validator | |
| 3 | **E2** Seal hash unchanged; permission fingerprint unchanged; no extra copy; if no seal exists, no sealed path exists | `seal_created` event; current hashes; ACL listing | Validator | |
| 4 | **E3** Run output directory contains only allowlisted control outputs; no audit pack, verdict, gates, orders/trades CSV, equity curve, diagnosis report | file manifest vs run manifest | Validator | |
| 5 | **E4** Log and trace scan clean under the pinned ruleset and scanner hash | scan report, scanner hash | Validator | |
| 6 | **E5** Defect reproduced on a non-holdout fixture without reading holdout output; `result_dependent = false` | reproduction command and output hash | Validator + investigator | |
| 7 | Fix diff touches only paths in the owner-approved defect-fix allowlist; no strategy rule, parameter, exit candidate, cost or gate code; fix commit descends from the aborted run's code SHA | git diff, path list derived from git by the verifier | Validator | |
| 8 | Defect record complete (schema 1.5), symptom contains no result values | defect record | Validator | |
| 9 | Nobody involved has seen results; statements A1-A4 attested | attestation text hashes | Owner, validator | |
| 10 | Broker/anchor posture: anchor reachable and verified in this call; allowlist pin current | verification output | Validator | |
| 11 | Cooling-off elapsed (recommended 24 h between defect record and authorization) and validity window set | timestamps | Owner | |
| 12 | Per-spec cap not exceeded; no prior authorization for this defect id | recovery chain | Validator | |
| 13 | Trial-ledger disclosure plan: two holdout rows reported; aborted verdict `INCONCLUSIVE_TECHNICAL`; sealed outputs quarantined | draft report fields | Owner | |
| 14 | Owner authorization record signed with the **owner key** (not witness/agent key), bound to defect record and attestation row hashes, single use | signature record, verifier output from the validator's environment | Validator verifies; owner signs | |
| 15 | Replacement token derivation recomputes from the chain; validate-time E1 re-run passes | verifier output | Validator | |

### D5. Sign-offs (blank; no one is named, nothing is signed)

| Sign-off | Name | Key id | Signature record hash | Date |
|---|---|---|---|---|
| Defect investigator | | | | |
| Independent validator (review complete, E1-E5 verified independently) | | | | |
| Owner (authorization) | | | | |

### D6. Stop conditions

Any NO above; any anchor or chain verification failure; evidence of any unseal event; an approval key revoked or suspect; a second defect appearing during the replacement run (that run is spent; no recovery of a recovery without a new defect, new authorization and an unexhausted cap).

---

## Part F. Exposure severity: all overlap stays BLOCKING

**Statement.** Until a **formally approved exposure classification policy** exists (approved and signed by the owner, with independent-validator review, under the Approval design), **all overlapping exposure remains `BLOCKING`**. This is today's behaviour: `authorize()` refuses on any ledger overlap, and the WP0.6 stop ("if 2022-2025 is materially exposed, stop") applies to any overlapping entry.

Operational consequences while the policy is absent:

- The hardening design's `ExposureSeverity` vocabulary and `RETURN_BLIND_STRUCTURAL` / `DISCLOSED_NON_MATERIAL` effects are **proposals only**; no code path honours them and no classification record is accepted. A ledger or record presenting a severity other than `BLOCKING` is refused, not downgraded.
- Every error path in classification handling resolves to `BLOCKING` (hardening I-E1).
- The migration of the ledger (hardening 3.6) may set every entry to `BLOCKING` and `observation_class = UNKNOWN`; it adds no classifications.
- No entry is deleted or silently reclassified; the R2 window and the spec `exposed` list are unaffected in all cases.
- The questions Q3.1-Q3.5 of the hardening design remain open and are prerequisites to approving a policy; this document does not answer them.

---

## Open owner questions (this document)

- **Q-B1** Operating system and location of the research environment (C12): Linux VM, container host, separate EC2 or cloud account? (B-1 and B-2 assume Linux.)
- **Q-B2** Option selection: B-1 now with B-2 required before the P4 holdout run (recommended), or another sequencing?
- **Q-B3** Vendor credential and ingest: may holdout months be pulled only by the broker account, and does the vendor licence allow separate credentials?
- **Q-B4** Is an independent-validator co-signature required on the HOLDOUT run authorization?
- **Q-B5** Is B-3 (sealed-to-offline-key outputs, separate broker host) wanted, or is residual R-B3/R-B1 accepted at B-2?
- **Q-B6** Is a reviewed crypto design for L2 sealing in scope, and may it use `cryptography` only?
- **Q-C1** Dedicated anchor key and bucket for RANGE-002 (recommended) — does this need an ADR 0047 amendment, and who provisions?
- **Q-C2** Anchor cadence: every event (recommended) vs result-bearing only.
- **Q-C3** Maximum un-anchored backlog for non-result-bearing events (a number only the owner sets).
- **Q-C4** Custody copy cadence and uploader (S3 manifest).
- **Q-C5** Re-anchor ceremony authority (owner + validator co-sign?).
- **Q-D1** Hardening Q1.1-Q1.6 remain open (cap, owner key location, fix-path allowlist, window, cooling-off, scope).
- **Q-F1** Who drafts, reviews and approves the exposure classification policy, and when?

## Decision table (all rows blank; none selected; none signed)

| ID | Decision | Options | Recommendation (not a decision) | Owner decision | Signature | Date |
|---|---|---|---|---|---|---|
| EB-1 | Execution-boundary option | B-0 / B-1 / B-2 / B-3 | B-1 before holdout-bearing data is acquired; B-2 before the P4 run | | | |
| EB-2 | Research environment named (C12) | | Linux, non-production, two OS accounts | | | |
| EB-3 | Holdout ingest and vendor-credential separation | | Broker-only for 2022-2025 months | | | |
| EB-4 | Run-authorization signers | Owner / owner + validator | Owner + validator co-sign for first holdout run | | | |
| EB-5 | Residual risks R-B1..R-B6 accepted by | | Owner and validator, in writing | | | |
| EB-6 | Anchor targets | A / A+B / A+B+C | A primary, B at gates, C at sign-offs; dedicated key and bucket | | | |
| EB-7 | Anchor cadence | every event / result-bearing only | Every event | | | |
| EB-8 | Un-anchored backlog limit | number | Owner sets | | | |
| EB-9 | ADR 0047 amendment for a RANGE-002 anchor | Yes / No | Decide before provisioning | | | |
| EB-10 | Approve Part D recovery checklist and roles | | Yes, with validator independence | | | |
| EB-11 | Exposure policy | confirm all-BLOCKING until a policy is approved | Confirm | | | |
| EB-12 | Implementation order | | Anchoring (C) and boundary (B-1) before ingest; Approval signing before P0 sign-off; recovery last | | | |

## What this document does not do

- It builds nothing and provisions nothing: no broker, host, ACL, key, bucket, role, ADR or CI change.
- It does not choose any option, role holder, number, cadence or key location, and it records no approval or signature.
- It does not weaken or bypass any invariant: no new boto3 import location, no new dependency, ADR 0002 / 0006 / 0046 / 0047 and the eighteen CI invariants stand; the order path, `OrderRouter`, risk engine and audit log are untouched.
- It does not change any gate, threshold, partition, spec value, or the R2 window.
- It does not claim to defeat a malicious writer using process-local controls, and it does not protect against broker-host root, owner-validator collusion, simultaneous possession of all trust roots, or an AWS account administrator.
- It does not make the replacement holdout run statistically equivalent to a first-time run.
