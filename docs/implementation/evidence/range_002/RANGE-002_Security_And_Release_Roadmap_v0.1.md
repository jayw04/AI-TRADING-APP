# RANGE-002 Security and Release Roadmap v0.1

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. Every classification, ordering and effort figure below is a Recommendation (not a decision).** Nothing is approved, signed, scheduled, implemented or applied. |
| Written | 2026-10-10 against `origin/main` = `d61f313a` (PR #737, #738, #739 merged; Level 1 only) |
| Branch | `docs/range002-level2-designs-v2` (same commit as the Level 2 design documents; it is a documentation-only change) |
| Method | Read of the five Level 2 design documents, the implementation plan v0.5, the CI/release proposals and read-only `gh` GET queries. No code, workflow, setting, bucket, key or AWS resource was touched. |
| Related | Level 2 Design Index v0.1; Approval Signing design (ASV); Execution Boundary and Anchoring design (EBA); Registry Recovery Procedure (RRP); Governance and Release Policy Proposals v0.2; CI Nightly Remediation Proposal v0.2 |

## 0. Scope statements (read first)

1. **This roadmap covers the RANGE-002 research-integrity track and the CI/release controls around the repository. It is separate from live and paper trading.** The trading platform's invariants in CLAUDE.md (single `OrderRouter`, risk gates, hash-chained audit log, no LLM in the order path, activation cooldowns, the eighteen CI invariants) are unaffected. **Nothing in this roadmap touches production trading code, the live paper application on `ec2-paper`, risk limits, broker adapters or credentials.** Nothing here authorises a deployment of any strategy.
2. **No Level 2 control is implemented.** Merged `main` provides Level 1 only. The design documents are designs; their decision tables are blank. Where this roadmap says an item is "mandatory before X", that is a recommended ordering for the owner to accept or change, not a rule already in force.
3. Threat model used for the classification (from the design documents):
   - **Level 1** defends against accidental misuse, casual bypass, crashes, concurrent writers and wrong-path use. It is what `main` has.
   - **Level 2** defends against an adversary (or a careless insider, or a compromised agent) who has **filesystem or code-execution access** on the research host or the repository: editing or truncating the registry, forging approvals, reading sealed results, replaying or copying state.
   - Owner-accepted Level 1 properties that Level 2 would close, unchanged here: a fork-inherited capability is run-bound but not a security boundary; directory aliases give a consistent identity but no confinement; a torn registry tail fails closed and locks out (no governed recovery); distinct signatories (R1-L1b) is an accepted limitation, with the distinct-role follow-up (`57dadd52`) tracked separately.
4. The only party who can be hurt by research-integrity failures is the research conclusion (a biased or tampered holdout result), not the trading book. That is why the gates are tied to research phases, not to the production path.

## 1. The gates, in chronological order

The plan (v0.5) sequence is: hypothesis, return-blind feasibility, **P0 signed freeze**, P1 data, P2 engine and controls, P3 guarded development screen (P3a, P3b), **P4 single independent holdout**, P5 dedicated paper, P6 human decision. The classification letters requested by the owner are mapped to the earliest gate that needs the control:

| Letter | Gate | Chronological position |
|---|---|---|
| (c) | Before the real spec freeze / P0 sign-off | first |
| (b) | Before the protected holdout run (P4). Some (b) items have an earlier trigger, noted per item (holdout data acquisition in P1; first result-bearing P3 run) | middle |
| (a) | Before any live or paper-trading deployment of a RANGE-002-derived strategy (P5 and later; P5 is refused at Level 1). This is also where repository-wide controls that protect the trading code path sit | last |
| (d) | Deferrable beyond research readiness | none |

Each item is assigned to the **earliest** gate that needs it, so a (c) item is also needed for (b) and (a).

## 2. Classification table (Recommendation (not a decision))

Effort: **S** = about a day of work and one small PR or one settings change; **M** = a few days, one or two PRs; **L** = weeks, several PRs and/or environment provisioning. Effort excludes the owner's waiting time and walk-away intervals. "RI" = could materially affect research integrity.

| ID | Item | Source | Class | RI | Rationale tied to the threat model | Depends on | Effort | Owner decisions (decision-table ids) |
|---|---|---|---|---|---|---|---|---|
| S1 | Capture and hash the live Actions artifacts for #738/#739 (local download only) | Governance proposals 0.2, 2.5 | (c) time-boxed: do before **2026-11-08** | no | Artifacts expire about 2026-11-09. Level 1 acceptance evidence is lost otherwise; this is an accidental-loss risk, not an adversary risk. | none | S | Authorise the download (Gov. Q10) |
| S2 | Level 1 formal acceptance by an independent reviewer (matrix, Windows and Linux, claim wording) | Level 1 Acceptance Test Plan | (c) | no | The freeze should rest on a Level 1 result the owner has accepted; the plan prohibits Level 2 claims. | S1 for evidence; named reviewer | M | Reviewer identity; seven-criteria wording (Gov. Q8, Q9) |
| S3 | Permanent evidence retention (versioned S3 package, Version ID + SHA-256 manifest) | Gov. proposals section 2 | (c) | partial | Makes the acceptance record outlive 30-day artifacts. Tamper resistance only with Object Lock; otherwise it is retention, not tamper-evidence. | S1; bucket/prefix/lock decision | M | Bucket, Object Lock mode and period, writers/readers (Gov. Q6, Q7); needs separate AWS authorisation |
| S4 | Remove the two transitional `hashFiles` guards from the RANGE-002 Linux acceptance step | local branch `ci/range002-remove-hashfiles-guards-v2` | (c) | indirect | With the guards a PR that deletes the tests or the manifest skips the step and stays green. That is a casual-bypass gap in the evidence that Level 1 acceptance relies on. Re-verified: with guards removed, deleting the tests directory or the manifest FAILS the step (pytest rc 4 / verifier rc 2). | none (tests, manifest, verifier are on `main`) | S (one ci.yml PR; global FULL run, about 30-35 runner minutes) | Approve push and PR; 2-hour walk-away |
| S5 | Distinct-role safeguard: owner, validator and approver roles named; code check that approvals from one identity cannot satisfy two roles (follow-up `57dadd52`) | ASV section 9; R1-L1b | (c) | **yes** | A "freeze" signed by one person in every role is not independent approval. A technical check cannot prove two keys are two people (the design states this limit), so the named roles and the validator's real independence are the control; the check only stops accidents. | S6 design acceptance; role naming (D08) | S for the check; the naming is an owner task | AS-3, AS-4, AS-5 (roles, SoD rule, required signatures) |
| S6 | **Approval signing and verification (H4)**: KMS P-256 signatures over a canonical approval message, two-phase freeze, pinned allowlist, offline verification, rotation and revocation | ASV | (c) | **yes** | Today an approval is three typed strings. An adversary with file or code-execution access (or a careless agent) can write an "approval". The freeze and every later phase gate rest on approvals, so forged or replayed approvals invalidate the research record. Needed before "formal approvals" mean anything. | Dry-run key ceremony (AS-9); separate approval-key account (AS-2); S5 roles; ADR 0045/0046 patterns | L | AS-1 to AS-9 (mechanism, key account and admin, roles, SoD, validity window, allowlist custody, ledger binding, ceremony) |
| S7 | Exposure ledger bound to the approved spec (H3 binding) with co-signature | ASV section 10 | (c) | **yes** | The exposure ledger decides which data is excluded from decisive runs (R2: 2026-01-01 to 2026-07-31 is exposed). If it can be edited after approval, contamination can be hidden. | S6 | M (part of S6 implementation) | AS-8 |
| S8 | `hashchain.py` docstring sentence suggested by the delta reviewer | delta review | (d) | no | Documentation inside code; no behaviour. Explicitly **not** part of the docs PR. | none | S (batch into the next code PR) | none |
| S9 | **Execution boundary B-1**: separate broker OS account owning registry, token store, holdout data; Unix-socket release API; Run Authorization verified in the broker | EBA Part B | (b) with an **earlier trigger: before any holdout-bearing data (2022-2025 months) is acquired in P1** | **yes** | The process-local capability is not a security boundary (Level 1 accepted). Holdout data that has sat in research-readable storage cannot be un-seen, so retrofitting after the pull is useless. This is the item the owner called data-boundary B-1. | Research environment named (Q-B1, Linux, two OS accounts); vendor credential separation (Q-B3); S6 for signed run authorisations | L (about 2-3 PRs plus an environment build) | EB-1, EB-2, EB-3, EB-4, EB-5, EB-12 |
| S10 | **External anchoring (M3)**: dedicated signer/sink and KMS key and bucket for RANGE-002, checkpoint records, chain-identity check, backlog limit | EBA Part C | (b); recommended trigger: **before the first result-bearing P3 run, if the attempt budget is to be relied on against tampering** | **yes** | A valid shorter chain (truncation) and a copied or forged registry sharing the public genesis are both accepted at Level 1, so the attempt budget and "holdout opened once" can be reset by an adversary with filesystem access. Without an external anchor the budget is only an accident guard. | S6 (approval/sign-off embeds the checkpoint hash); ADR 0047 amendment decision (EB-9); S3 for custody copy | L | EB-6, EB-7, EB-8, EB-9 |
| S11 | **Execution boundary B-2**: broker-launched pinned no-network engine container for HOLDOUT; outputs only into the sealed store | EBA B10 | (b), before the P4 holdout run | **yes** | At B-1 a hostile or edited engine can read the holdout it is handed. B-2 closes engine-side exfiltration. | S9, container/image custody | L (about 2x S9) | EB-1, Q-B5 (is B-3 wanted?) |
| S12 | Approve Part D (defect-only holdout recovery) review checklist and roles | EBA Part D | (b) | **yes** | The holdout may open once per frozen spec; a defect-only rerun path with undefined rules invites unregistered second tries. Approving the checklist is paper work, no code. | Roles (S5) | S | EB-10, Hardening Q1.1-Q1.6 |
| S13 | Exposure severity policy (Part F): all overlap stays BLOCKING until a signed policy exists | EBA Part F | (d), conservative default already in effect | no | The default (block all overlap) is the safe direction. Upgrade to (c) only if the frozen spec needs data that overlaps exposure. | none | S (policy text) | EB-11, Q-F1 |
| S14 | Registry recovery tool and torn-tail procedure (RRP) | RRP | (d) | no | Level 1 fails closed and locks out on a torn tail; recovery is needed only after an incident, and the lock-out protects integrity. The cost of deferral is possible inability to continue a run, not corrupted evidence. Revisit if a torn tail occurs. | S10 (anchoring changes what recovery must prove) | L | RRP Q-R series |
| S15 | Remove `--allow-pending` from the pull_request verifier call (manifest now has no `pending_pr` entries, so it is a no-op today) | `ci.yml`, verifier | (d) | indirect | Hygiene: stops a future "pending" marker from tolerating a missing test on PRs. Can be batched with S4's ci.yml change or a later one. | S4 | S | Whether to batch with S4 (cost: another global FULL if separate) |
| S16 | Execution boundary B-3: outputs sealed to an offline key and/or a separate broker host | EBA B-3 | (d) | partial | Protects against broker-host root and research-host compromise reaching the broker; requires a reviewed crypto design. Residual R-B3 is an owner risk acceptance. | S11 | L | Q-B5, Q-B6 |
| C1 | Restore the nightly CI: fix defect A (`Argument list too long`) | CI Nightly Remediation Proposal v0.2 | (a) recommended: before the next deployment of trading code from `main` | no | The scheduled run is the only periodic run of all four FULL suites and the invariants; it has been red since 2026-08-30 (latest 2026-10-10). Per-PR CI still runs, so this is lost assurance, not a bypass. One-line env gating; separate narrow PR; global FULL run. | none | S | Approve push and PR; packaging (nightly decision 4); alerting L1/L2 |
| C2 | Fix defect B (fresh-resolution-proof header mismatch + upstream drift) | same | (d); raise to (a) if the owner wants dependency reproducibility proven before a deployment | no | A supply-chain reproducibility proof that has never passed; its clean-install step has never run. Needs a policy choice (B2 vs B3) and Linux uv verification first; separate PR after C1. | C1; uv 0.12.0 on Linux x86_64 CPython 3.12.13 | M | Nightly decisions 2, 3, 7 |
| C3 | Enable secret scanning and push protection (repository is **public**; both are currently `disabled`) | `gh api` read-only, 2026-10-10 | (a) | no | A public repository with no automated detection of committed credentials (Alpaca, Anthropic, AWS). It is a settings write, not code, and costs no Actions minutes. Verify the plan allows it. | none | S | Owner authorises the settings write |
| C4 | Review-requirement decision for `main`: ruleset with a second reviewer, or an ADR-recorded risk acceptance | Governance proposals 0.2, section 1 | (a) as a **decision** (ADR option D at minimum); a real second human reviewer is (c) for any claim of independent review | **yes** (independence of review of governance code) | `main` has no required human review; the owner is the only collaborator and the author, so the "approval by someone other than the author" rule is **unsatisfiable today (solo-owner lockout)** and `enforce_admins: true` removes the admin bypass. Any change to `main` including order-path code merges with CI plus the owner's own merge only. | A second person (option A) or an ADR (option D); CODEOWNERS (names users with write access only) | S to write; M if a reviewer must be onboarded and the dry run run for a week | Gov. options A to D, ruleset variant, evaluate mode, reviewer identity (Gov. Q1-Q5, Q11) |
| C5 | CODEOWNERS for workflows, `range002`, risk, orders, ADRs, manifests | Gov. proposals 1.8 | (d) until C4 has a second reviewer | no | Without a second code owner it only documents ownership; with one it routes sensitive paths. | C4 | S | Reviewer identity; whether to include the catch-all line |
| C6 | Actions hardening: SHA-pin third-party actions, consider restricting allowed actions (currently `allowed_actions: all`, `sha_pinning_required: false`; token default is read-only, which is good) | read-only `gh api` | (d) | no | Supply-chain hardening of CI. A ci.yml change flags every project FULL; batch with other ci.yml work. | batch with S4/C1 | S to M | Whether to batch |
| C7 | Alerting for scheduled failures (owner notification setting; optional issue-on-failure job) | Nightly proposal section 6 | (d) | no | About 41 consecutive nightly failures went unnoticed. L1 (notification setting) is free and immediate. | none (L2 rides with C1) | S | Nightly decision 6 |

## 3. Top priorities (Recommendation (not a decision))

Ordered by the earliest gate and by how much research integrity depends on the item:

1. **S1** Capture the Actions artifacts before 2026-11-08 (time-boxed, small).
2. **S4** Remove the `hashFiles` guards (small, closes a silent-skip hole in the evidence step).
3. **C3** Enable secret scanning and push protection on the public repository (small, settings only).
4. **C4** Decide the `main` review control honestly: either a real second reviewer or an ADR-recorded risk acceptance. This is a decision, not a build, and it also answers who the independent Level 1 reviewer is.
5. **S2 and S3** Level 1 formal acceptance and permanent retention.
6. **S6, S5, S7** Approval signing, distinct-role safeguard and exposure-ledger binding: the largest block, and a hard prerequisite for a real P0 sign-off.
7. **S9** Execution boundary B-1: must exist **before the holdout months are pulled** (P1 trigger, earlier than P4).
8. **S10** External anchoring before relying on the attempt budget against tampering (P3 trigger).
9. **C1** Fix nightly defect A.
10. **S11, S12** B-2 and the Part D checklist before the P4 run.

## 4. Dependency order

```
S1 -> S3 -> (S2: Level 1 acceptance record)
S4, C3, C1 (independent; small; any order, one push each)
C4 decision --> (names the reviewer used by S2, S5, S12, C5)
S5 roles + AS-2 key account + AS-9 dry-run ceremony --> S6 signing --> S7 ledger binding --> P0 REAL FREEZE / SIGN-OFF
Q-B1 environment + Q-B3 vendor separation --> S9 (B-1) --> [P1 holdout-bearing data pull allowed]
S6 + EB-9 ADR decision --> S10 anchoring --> [relying on attempt budget; before first result-bearing P3 run]
S9 --> S11 (B-2) + S12 (Part D) --> [P4 holdout run]
S14, S16, S13, S15, S8, C5, C6, C7 : deferrable
```

Two orderings worth the owner's attention: (1) S9 has an earlier trigger than its letter suggests (P1 data acquisition), and (2) S6 and S10 are linked, because the signed sign-off embeds the latest anchor checkpoint hash (EBA C3, option C).

## 5. Items that could materially affect research integrity

| Concern | Control | Why it matters | Recommended trigger |
|---|---|---|---|
| Holdout isolation | S9 (B-1), then S11 (B-2) | Data the research user could read cannot be un-seen; a hostile engine can read what it is handed at B-1 | B-1 before holdout months are pulled; B-2 before P4 |
| Forged or replayed approvals | S6 (signing/KMS), S7 | Approvals are three typed strings at Level 1 | Before formal approvals and the real freeze |
| Resettable attempt budget / holdout-once rule | S10 (external anchoring) | Truncated or copied chains are valid at Level 1 | Before relying on the budget against tampering (first result-bearing P3 run) |
| One person in every role | S5 (distinct-role safeguard) and real role separation | A technical check cannot prove two keys are two people | Before the freeze |
| Unregistered second tries on the holdout | S12 (Part D checklist) | Defect-only reruns need defined rules | Before P4 |
| Evidence loss | S1, S3 | Artifacts expire in 30 days | Now / before sign-off |

## 6. Owner decisions required (summary)

Nothing is decided here. The decisions that unblock the most work, in order: (i) the review-control path (C4: second person, or ADR risk acceptance); (ii) who is the independent validator and the named D08 roles (S5); (iii) the research environment and vendor-credential separation (Q-B1, Q-B3; gates S9); (iv) the approval key account and whether a dry-run ceremony is approved (AS-2, AS-9; gates S6); (v) whether a dedicated RANGE-002 anchor key and bucket need an ADR 0047 amendment (EB-9; gates S10); (vi) authorisations for settings writes and AWS actions (C3, S3), each separate and explicit.

## 7. What this document does not do

- It does not implement, enable or schedule any Level 2 control, and it makes no claim that one exists.
- It does not touch trading code, the live application, the audit log, risk limits or credentials, and it does not authorise a deployment, a settings change, a push, a workflow dispatch or an AWS call.
- It does not name any person, fill any decision table, select any option or record any approval.
- Effort and ordering figures are estimates by the author for planning and are not commitments.
