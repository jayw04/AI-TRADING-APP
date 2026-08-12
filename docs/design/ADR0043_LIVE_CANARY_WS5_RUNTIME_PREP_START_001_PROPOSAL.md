# ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 (EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 |
| Status | **EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED** (amendment-1 effective `2026-08-02T21:56:47Z`; WS5 not started — the §15.1 Stage-1 operator invocation is still required and has not been issued) |
| Status of the authorization in force | **EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED.** The §15 sequencing hold is discharged: §15 is now satisfiable in two stages. Execution remains un-invoked. |
| Amendment scope | §15 split into a two-stage invocation (Stage 1 opening / Stage 2 resource-binding checkpoint); §14 amendment continuity, **post-invocation amendment rule**, and **superseded-hash retirement**; §15.1 **application-level database access prohibited before Stage 2** (provider control plane only); three new §10 stop conditions; §4B cross-reference. **No change to any scope item, ceiling, prohibition, dry-run flag, disposition, exit criterion, source commit, schema head, or the expiration formula.** |
| **Effective** authorization body SHA-256 | `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` (over §§1–16 per §17; **independently re-verified from `main` post-merge**) |
| Superseded body SHA-256 | `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0` (merge `f1646719…`, PR #594) — **PERMANENTLY RETIRED** as an authorizing credential at `2026-08-02T21:56:47Z` per §14 *Superseded-hash retirement*. REFUSED for Stage-1 invocation, Stage-2 checkpointing, resource creation, and resource adoption. |
| Withdrawn draft hash (never effective) | `f44c9a53a46a382734ea604ac3fa132ef06294d874c9e390fafd2ce3c5580c34` — the first amendment draft, superseded by the owner's REVISE ruling **before** it was ever approved or merged. It never authorized anything. |
| Amendment merge SHA | `af2dfc16b8294edd649f2a19fcac2cb954fff00b` (PR #596, base `3920484…`, reviewed head `f57ff64c…`) |
| Amendment effective at | 2026-08-02T21:56:47Z |
| Authorization merge SHA (superseded) | `f1646719dde08af497e6dcf1da4e0369cfba7754` (PR #594, base `7342ebb…`, reviewed head `0bc173e…`) |
| Authorization effective at | 2026-08-02T20:39:37Z — **preserved; not reset by amendment** (§14 *Amendment continuity*). The 14-day clock still runs from the original effectiveness moment. |
| Absolute expiration | 2026-08-16T23:59:59 America/Chicago (`effective_at + 14d`, §14) — **unchanged by the amendment** |
| Derived runtime identity | `adr0043-canary-ws5-52b3ff136196` — supersedes `adr0043-canary-ws5-99f045e09532` and the withdrawn draft identity `adr0043-canary-ws5-f44c9a53a46a`. **No resource exists under any of the three identities**; WS5 has never been invoked. |
| Date | 2026-08-02 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0 (WS5) |
| Contract layer | ADR0043-CANARY-MANIFEST-v1.2 — **APPROVED — WS4A CONTRACT FREEZE** (2026-08-02) |
| Readiness plan | ADR0043-LIVE-CANARY-WS5-READINESS-PLAN-001 v0.1 — **APPROVED AS NON-EXECUTABLE PLAN** (2026-08-02) |
| Baseline design | ADR0043-CANARY-BASELINE-DESIGN-001 v0.2.1 (Model A) |
| Code capability | WS3 on `main` at merge `0462c25…` (WS3 code `92cbd30…`, PR #591) |
| Prior publication | Published NON-EFFECTIVE via PR #593 → `main` `7342ebb…` |
| Effect | **No execution.** Effectiveness and execution are **separate events** (§18). The authorization is EFFECTIVE as amended — merged, body hash verified, merge SHA recorded — but WS5 execution begins only through the separate **§15.1 Stage-1 operator invocation**, which has **not** been issued. |

> ✅ **EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED.** The original authorization became effective at `2026-08-02T20:39:37Z` (`99f045e0…`, PR #594), but its §15 operator record required `runtime_resource_ids`, `database_identity`, and `image_digest` **before** execution may begin — values that, under CREATE-AND-ATTACH (§3), do not exist until WS5 itself creates them. §15 was therefore unsatisfiable and invocation was held. **Amendment-1 corrects the sequencing** and merged to `main` at `af2dfc16…` (PR #596) at `2026-08-02T21:56:47Z`; its body hash was independently recomputed from the `main` blob (`a53651e…`) as `52b3ff13…` (§17) and the merge SHA recorded. The amendment is **EFFECTIVE**; `99f045e0…` is **permanently retired**.
>
> **This does NOT start WS5.** Effectiveness and execution remain separate events (§18). No provisioning, database access, broker access, migration, dry-run capture, or readiness-evidence production has been or may be started; WS5 begins **only** through the explicit **§15.1 Stage-1 operator invocation**, which **has not been issued**. The §15.2 Stage-2 checkpoint then gates everything beyond creation.
>
> **All runtime and broker HOLDs remain in force.** Effectiveness auto-expires per §14 at `2026-08-16T23:59:59 America/Chicago` — the amendment did **not** reset `authorization_effective_at` and did **not** extend that ceiling.

---

## 1. Authorized scope, if made effective

Scoped strictly to preparing a **fresh isolated** canary runtime and resolving the WS4A **[WS5/WS6-BOUND]** facts, with **no authoritative baseline capture**:

1. Create **one** isolated WS5 runtime (§3, §4) and record its resource identities in the WS5 opening record (§4B) before any DB or broker access.
2. Create **one** isolated database (or clone) dedicated to WS5; apply governed migrations to **that** DB only (§7). A clone must not copy authoritative or executable state (§5).
3. Deploy the governed application image **built from exactly `authorized_source_commit` (§4A)**; record its digest at invocation.
4. Read-only identity and account reconciliation (§6) — Workbench account/user IDs, broker→Workbench mapping, MSFT:19 condition, open orders, reservations, effective risk limits, scheduler/strategy state, broker connectivity.
5. Dry-run capture validation with **technical incapacity** for authoritative persistence (§8).
6. Publish the runtime-opening readiness record with planning reachability (§9), non-persistence proof (§12), and pre/post mutation proof (§12).

## 2. Non-negotiable prohibitions

- authoritative session-baseline capture / persistence (Start A only);
- Start A / Phase 0 / Start B;
- any broker **order** (submit / replace / cancel), fund transfer, account-setting change, or paper-account reset;
- canary-specific ENFORCE activation; global session-baseline flags stay OFF;
- D-WIRE;
- migration application to any shared / non-isolated database;
- scheduler or strategy activation; deployment into an existing strategy runtime;
- converting the verification account or the WS5 runtime into a strategy / production host.

## 3. Runtime mode — CREATE-AND-ATTACH (frozen)

**CREATE-AND-ATTACH.** WS5 provisions a **fresh isolated runtime** rather than attaching to an existing long-lived environment, to minimize contamination from prior experiments, unknown state, stale credentials, or unrelated services. Creation authority is limited to WS5 readiness; the runtime must **not** become a strategy runtime or production host.

## 4. Isolated-runtime identity and ownership (frozen)

**Deterministic logical identity:**

```
runtime_name = adr0043-canary-ws5-<authorization_body_sha256_first12>
```

(`<authorization_body_sha256_first12>` = first 12 lowercase hex chars of the final authorization body SHA-256 per §17.)

**Required ownership / tags** (every created resource must carry these; a resource that cannot carry or prove them is **unauthorized**):

```
program_id        = ADR0043
workstream        = WS5
purpose           = runtime-readiness-only
execution_enabled = false
broker_account    = PA34USW0Q8UO
owner             = jayw04
authorization_sha = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
expires_on        = 2026-08-16T23:59:59 America/Chicago
```

### 4A. Frozen source and schema identity (frozen)

The final authorization freezes the exact code and schema; no open-ended "descends from" or "covered later":

```
authorized_source_commit = 7342ebbd8e061518ba9bd0524803f8e20d760a78
authorized_alembic_head  = b2d8f4c6a901
```

(`authorized_source_commit` is the exact current `main` tip — it carries the accepted WS3 code `92cbd30…`, the approved WS4A/WS5 planning docs, and the published non-effective WS5 proposal; the intervening changes were documentation-only. It is fixed and knowable before this authorization is committed, so it is part of the hashed body — **not** an excluded finalization value.)

- The runtime image **must be built from exactly `authorized_source_commit`**; its digest is recorded at invocation (§15).
- The isolated database schema **must equal `authorized_alembic_head` exactly**.
- **Any** later source commit or schema head requires either **a formally approved authorization amendment** naming the exact successor, **or** a **new** WS5 start authorization. An "approved successor" or "covered later" that does not identify the exact successor in the authorization body is **not** permitted.

### 4B. WS5 opening record — required before any DB or broker access (frozen)

Record all of:

- exact GitHub **merge SHA** of the effective authorization;
- **independent body-hash verification** result (§17);
- exact **source commit** (= `authorized_source_commit`);
- exact **Alembic head** (= `authorized_alembic_head`);
- **image build provenance** (builder, source commit, resulting digest);
- **cloud account ID and region**;
- **network resource IDs** (VPC/subnet/security-group);
- runtime **instance/container ID**;
- **database identity** (§7) and **evidence-store identity**;
- broker **credential identifier or fingerprint — never the secret** (§6).

The pre-provisioning half of this record is asserted at the §15.1 Stage-1 invocation; the runtime-created half is recorded and verified at the §15.2 Stage-2 checkpoint, which is the point at which this record is completed.

A resource or run that cannot produce this record is **unauthorized** → REFUSED.

## 5. Infrastructure mutation ceiling (frozen)

**Authorized:**

- creation of **one** isolated runtime;
- **one** isolated database or database clone dedicated to WS5;
- narrowly scoped network access needed for administration, database access, and broker **HTTPS reads**;
- deployment of the governed application image (built from `authorized_source_commit`, §4A);
- application of governed migrations to the **isolated** database;
- **attachment of an existing approved read-only** broker credential (no creation/rotation, §6);
- temporary evidence storage.

**Prohibited:**

- changes to shared production networks;
- shared database migrations;
- modification of existing production credentials;
- inbound public access other than explicitly allowlisted administrative access;
- scheduler or strategy activation;
- deployment into an existing strategy runtime;
- changes to global feature flags.

**Database-clone isolation (frozen):** creating the isolated database clone **must not copy** effective Start A authorizations, authoritative Model A baselines, pending reservations, or executable scheduler state. Any such copied state causes **REFUSED** (§10) — **not** cleanup-in-place.

All created resources are tagged with the authorization hash (§4) and must be **removable without affecting another environment**.

## 6. Broker-access ceiling (frozen)

**Authorized broker operations (read-only):** account details; positions; open and historical orders needed for reconciliation; account activity required to identify capital adjustments; market clock/calendar; asset/tradability metadata; quotes needed for **non-authoritative** planning calculations.

**Prohibited broker operations:** submit / replace / cancel orders; modify account settings; reset the paper account; transfer funds; change credentials; stream into any component capable of automatic order submission.

**Credential rules (frozen, three-tier):**

- **Preferred** — broker-issued **read-only** credentials.
- **Conditionally permitted** — trading-capable credentials **only if** (a) the inability to obtain read-only credentials is **recorded** in the opening record (§4B), **and** (b) **independent** technical controls (application configuration **and** network/application policy) make write/order calls **impossible**.
- **REFUSED** — any **unmitigated** write capability, or failure to prove the controls.

**No credential rotation or modification of the broker account is authorized.** Only **attaching an existing approved credential** to the isolated runtime is allowed. A credential mismatch or unexpected write capability → **REFUSED**.

## 7. Database-access ceiling (frozen; identity named after creation)

Named after creation, recorded in the WS5 opening record:

```
database_role         = ADR0043_WS5
database_identity     = <recorded provider/database identifier>
governed_schema_head  = b2d8f4c6a901   # = authorized_alembic_head (§4A)
```

**Permitted writes:** schema migrations in the isolated database; WS5 readiness/evidence rows in **dedicated WS5 evidence tables** (`authoritative=false`); operational audit records identifying WS5 activity.

**Role privilege (frozen):** the `ADR0043_WS5` role has **no INSERT/UPDATE/DELETE privileges** on `risk_canary_start_a_authorizations` or `risk_canary_session_baselines` — **read-only** on both authoritative control tables (§8).

**Prohibited writes:** EFFECTIVE Start A authorization; authoritative Model A baseline; `CANARY_MODEL_A_BASELINE_CAPTURE`; loss-control state transition; breaker trip; reservation; order; strategy or scheduler enablement; mutation of broker/account identity; modification of live or shared databases.

## 8. Dry-run technical incapacity (frozen — enforced, not merely checked)

The dry-run must be **incapable** of authoritative execution. All of the following configuration flags are required:

```
capture_mode                         = DRY_RUN
authoritative_persist_enabled        = false
start_a_effective_writes_enabled     = false
broker_order_adapter_enabled         = false
scheduler_enabled                    = false
strategy_execution_enabled           = false
session_baseline_enforcement_enabled = false
session_baseline_shadow_enabled      = false
```

**Concrete enforcement mechanism (frozen):** the `ADR0043_WS5` database role has **no write privileges** (no INSERT/UPDATE/DELETE) on `risk_canary_start_a_authorizations` or `risk_canary_session_baselines`; dry-run diagnostics are written **only** to dedicated WS5 evidence tables with `authoritative=false`. Enforcement is by **database-role grants**, not by status-sensitive row rules (which cannot reliably distinguish an EFFECTIVE row from another status, or an authoritative baseline from a diagnostic row).

Additionally:

- no valid EFFECTIVE Start A ID may be supplied;
- capture must use a **dry-run-specific** function or transaction path;
- the broker-facing order method must be **unavailable or hard-disabled** (`broker_order_adapter_enabled=false` + network/application policy);
- post-run assertions must verify **zero** forbidden artifacts.

Any inability to prove these controls → **REFUSED**.

## 9. Reachability handling (bound by WS5 plan §3.1)

WS5 computes **planning reachability** only, against a clearly labeled **non-authoritative** baseline estimate (`planning_baseline_estimate` + source + timestamp + uncertainty band). **Start A authoritative reachability** (recomputed from the exact captured baseline before the first Phase 0 order) is out of scope here. A WS5 planning PASS **cannot** override a later Start A reachability failure.

## 10. Mechanical stop conditions (frozen → REFUSED before readiness completion)

Immediately stop WS5 and classify **REFUSED** upon any of:

- runtime name or authorization-hash mismatch;
- broker identity other than `PA34USW0Q8UO`;
- Workbench mapping ambiguity;
- missing or non-19-share MSFT position;
- unexpected open order or reservation;
- schema conflict or multiple Alembic heads;
- code/image identity **not built from exactly `authorized_source_commit`**, or governed schema head **≠ `authorized_alembic_head`**;
- database clone containing an effective Start A authorization, authoritative baseline, pending reservation, or executable scheduler state;
- credential permitting unbounded or unmitigated broker writes;
- scheduler or strategy unexpectedly active;
- any forbidden database row, audit event, risk-state mutation, or broker mutation;
- unexplained pre/post snapshot difference;
- migration touching a shared or non-isolated database;
- **a body-changing amendment approved or merged after Stage-1 invocation** (§14 *Post-invocation amendment rule*) — the attempt terminates as REFUSED; resources and evidence are preserved for adjudication and must not be retagged, adopted, or continued;
- **presentation of a superseded authorization body hash** at Stage-1 invocation, Stage-2 checkpointing, or resource creation / adoption (§14 *Superseded-hash retirement*);
- **application-level database access before the Stage-2 checkpoint passes** — any SQL session, query, schema or Alembic inspection, clone-content validation, or migration attempted at Stage 1 beyond the provider control-plane exception (§15.1).

**INCONCLUSIVE** is used **only** when WS5 began validly but evidence collection or connectivity failed **without** proving an unauthorized mutation. A **proven unauthorized mutation is REFUSED** and requires remediation review.

## 11. WS5 dispositions (frozen)

| Disposition | Meaning |
|-------------|---------|
| `READY_FOR_WS6` | Every readiness check passes, all runtime bindings are resolved, and non-persistence / mutation proofs pass |
| `REFUSED` | A precondition, identity, isolation, or safety rule fails, or an unauthorized mutation occurs |
| `INCONCLUSIVE` | Valid WS5 work began but evidence or connectivity prevents a trustworthy conclusion, with no unauthorized mutation proven |

Only `READY_FOR_WS6` may be submitted as input to WS6. It does **not** authorize the WS6 seal or Start A.

## 12. Non-persistence proof and pre/post mutation proof (required to close WS5)

**Non-persistence proof.** The dry-run must demonstrate it created **none** of: a `risk_canary_session_baselines` row; an EFFECTIVE `risk_canary_start_a_authorizations` row; a `CANARY_MODEL_A_BASELINE_CAPTURE` audit event; a raw evidence object labeled authoritative; any risk-state mutation; any broker order.

**Pre/post mutation proof.** Pre- and post-exercise snapshots/hashes for broker positions, broker open orders, local positions, reservations, effective risk limits, the Start A authorization table, and the Model A baseline table — proving the exercise did not open the execution boundary. Any unexplained difference → §10 (REFUSED).

## 13. Exit criteria

- Every WS4A **[WS5/WS6-BOUND]** field populated with a verified value.
- The WS5 opening record (§4B) complete: merge SHA, body-hash verification, source commit, Alembic head, image provenance, cloud/network/DB/evidence identities, credential fingerprint.
- Readiness record published; planning reachability recorded as non-authoritative (§9).
- Non-persistence proof and pre/post mutation proof attached (§12).
- Explicit statement that **no authoritative baseline was persisted and no order was submitted**.
- Terminal disposition (§11). Only `READY_FOR_WS6` feeds **WS6**; WS5 does **not** authorize the WS6 seal, Start A, or any capture.

## 14. Expiration (frozen — single governing rule)

The authorization expires **automatically** on the first of:

- **`absolute_expiration`** (the single absolute rule below);
- production of a terminal WS5 disposition (§11);
- runtime identity change **other than** the identity re-derivation that follows a formally approved amendment (see *Amendment continuity* below);
- authorization document or body-hash change **not effected by a formally approved amendment** (an amendment **supersedes**; it does not expire — see *Amendment continuity* below);
- source-commit or governed schema-head change not covered by a formal amendment or new authorization (§4A);
- broker-account or Workbench mapping change;
- discovery of an unauthorized mutation;
- owner revocation.

**Single governing absolute rule:**

```
absolute_expiration = authorization_effective_at + 14 calendar days, ending 23:59:59 America/Chicago
```

`authorization_effective_at` is the effective-merge moment (§18). The **concrete** timestamp is inserted into the final authorization once that date is known (the earlier "publication date + 14 days" and any hardcoded 2026-08-16 value are removed in favor of this one rule). An expired authorization **cannot** be resumed; a new ruling is required.

**Amendment continuity (frozen).** A **formally approved amendment** — one the owner approves over the amended frozen body, merged to `main`, with its new body hash independently re-verified (§17, §18) — **supersedes** the prior effective body hash rather than expiring the authorization, **provided no Stage-1 invocation has occurred** (see *Post-invocation amendment rule* below). Until that amendment is itself effective, the prior authorization remains in force with **execution held**; an amendment never creates a window in which nothing governs. Two limits are absolute:

- **The expiration clock does not restart.** `authorization_effective_at` is the **original** effectiveness moment and is **not** reset by an amendment, so `absolute_expiration` is unchanged and **cannot be extended by repeated amendment**. Additional time requires a new authorization, not an amendment.
- **Superseded identities are dead.** Amendment re-derives `runtime_name` and the §4 `authorization_sha` tag from the new body hash. Any resource still carrying a superseded `authorization_sha` is **unauthorized** (§4) → REFUSED. Before an amendment is invoked, the operator must confirm that **no resource exists** under the superseded identity.

**Post-invocation amendment rule (frozen).** Amendment continuity applies **only** while no Stage-1 invocation has occurred and no resource exists under the superseded identity. Once Stage 1 has been invoked, any body-changing amendment **terminates the current WS5 attempt as REFUSED** (§10, §11). The amendment must **not** hot-patch, retag, adopt, or continue resources created under the superseded authorization. State and evidence are **preserved for adjudication**; cleanup or teardown requires **separate authority**. A **new** authorization and a **newly derived runtime identity** are required for any further attempt.

**Superseded-hash retirement (frozen).** When an approved amendment becomes effective, the prior authorization body hash is **permanently retired as an authorizing credential**. It must not be accepted for Stage-1 invocation, Stage-2 checkpointing, resource creation, resource adoption, or any subsequent WS5 action. An invocation or resource binding that presents a superseded hash is **REFUSED**. Resources carrying a superseded `authorization_sha` remain unauthorized (see *Superseded identities are dead* above).

The effectiveness record of an amendment (§18) must contain:

```
superseded_authorization_body_sha256
effective_authorization_body_sha256
superseded_at_utc
amendment_merge_sha
independent_new_hash_verification
```

Any document or body-hash change **not** carried by an approved amendment expires the authorization under the bullet above.

## 15. Explicit operator invocation — two stages (frozen — merge alone must not start WS5)

Under CREATE-AND-ATTACH (§3) the runtime, database, and image **do not exist** until WS5 creates them. A single operator record that required their identities before execution could never be truthfully produced. Invocation is therefore **two ordered stages**: Stage 1 authorizes creation only; Stage 2 is a resource-binding checkpoint that must pass before any migration, database read, broker read, or dry-run activity. Neither stage may be skipped, merged into the other, or back-filled after the fact.

### 15.1 Stage 1 — WS5 opening invocation (pre-provisioning)

Required operator record — every value is knowable before any resource exists:

```
authorization_document_id
authorization_body_sha256
authorization_merge_sha
runtime_name
authorized_source_commit
authorized_alembic_head
broker_account_id
operator_identity
invoked_at_utc
```

Stage 1 may begin **only** when:

- the authorization is **EFFECTIVE** on `main` (§18) — merged, body hash recorded and independently verified, merge SHA recorded;
- the invoked body hash matches the recorded authorization body hash;
- the `runtime_name` derives from that hash (§4);
- `authorized_source_commit` and `authorized_alembic_head` equal the §4A frozen values **exactly**;
- `broker_account_id` is the authorized account (§10);
- the operator explicitly issues the WS5 Stage-1 start invocation.

**Stage 1 authorizes only:**

- creation of the **one** isolated runtime (§3, §4, §5);
- creation of the **one** isolated database or clone (§5, §7), **without** applying migrations;
- build and deployment of the governed application image from **exactly** `authorized_source_commit` (§4A);
- creation of the WS5 opening record (§4B).

**Database access at Stage 1 — provider control plane only (frozen).** Stage 1 does not authorize any application-level database connection, query, read, write, schema inspection, Alembic inspection, or migration. Only provider **control-plane** operations strictly required to create, identify, tag, and establish network reachability for the isolated database resource are permitted.

*Permitted at Stage 1 (control plane only):*

- provider create / describe / status APIs;
- retrieval of the generated database resource ID and endpoint;
- network reachability configuration;
- recording those values in the opening record (§4B).

*Not permitted at Stage 1:*

- opening an application SQL session;
- inspecting schemas or tables;
- querying Alembic state;
- validating cloned content;
- applying migrations;
- reading Workbench mappings or risk data.

**Stage 1 does not authorize database access of any kind beyond the provider control-plane creation exception above**; application-level database reads and writes, migration, broker access of any kind, dry-run capture, and readiness-evidence production remain **prohibited**.

### 15.2 Stage 2 — resource-binding checkpoint (post-provisioning)

Once the Stage-1 resources exist, and **before any further WS5 activity**, record and verify:

```
runtime_resource_ids
database_identity
image_digest
image_source_commit
cloud_account_id
region
network_resource_ids
evidence_store_identity
credential_fingerprint
```

These are the runtime-created half of the §4B opening record; Stage 2 is the point at which §4B is **completed and verified**. The checkpoint passes only when:

- every created resource carries the §4 ownership tags, with `authorization_sha` equal to the effective body hash;
- `image_source_commit == authorized_source_commit` (§4A) and `image_digest` is recorded;
- `database_identity` names the isolated WS5 database **only** (§7); no shared or production database is bound;
- the broker credential is an existing approved credential under §6, recorded by **fingerprint — never the secret**;
- no §10 stop condition is present.

**Only after the Stage-2 checkpoint passes** may WS5 continue to: apply the governed migration to the isolated database (§7); perform database and broker reads (§6); run the non-authoritative dry-run (§8); and produce readiness evidence (§9, §12, §13).

The **observed** governed schema head is verified against `authorized_alembic_head` after that migration, under §10 — it is deliberately not a Stage-2 field, because the migration is not authorized until Stage 2 has passed.

**Any mismatch at either stage → REFUSED (§10, §11).** A Stage-2 checkpoint that cannot be produced or cannot be verified is **unauthorized** (§4B) → REFUSED. Stage 2 is never waived on the grounds that Stage 1 succeeded.

## 16. Governed-head / continuity notes

- Runtime schema must equal `authorized_alembic_head` (§4A) exactly = `b2d8f4c6a901`. Any later governed migration requires a **formal authorization amendment or a new WS5 start authorization** — no implicit "covered later."
- The execution continuity boundary does **not** open under WS5. It opens later, under Start A, after WS6 is sealed and countersigned.

## 17. Authorization body-hash computation (self-reference resolution)

`authorization_body_sha256` = SHA-256 over the **canonical UTF-8 bytes of the frozen authorization body** — this document, sections **1–16** as finalized, **with the exact `authorized_source_commit` included** — **excluding only** the values that genuinely cannot be known until after the body is frozen or until execution resources exist:

- the derived `runtime_name` value (§4);
- the `authorization_sha` resource-tag value (§4);
- the concrete `expires_on` tag value (§4) and the concrete `absolute_expiration` timestamp (§14) — the expiration **formula** remains in the hash;
- the runtime-created `database_identity` (§7);
- the §15 operator-record field blocks — **both** the §15.1 Stage-1 block and the §15.2 Stage-2 block (populated at invocation and at the resource-binding checkpoint respectively);
- ruling/status metadata and the §19 document-control history;
- the authorization merge SHA.

**Known frozen values included in `authorization_body_sha256`:**

```
authorized_source_commit = 7342ebbd8e061518ba9bd0524803f8e20d760a78
authorized_alembic_head  = b2d8f4c6a901
all normative scope, ceilings, flags, stop conditions, dispositions, and the expiration formula
```

**Canonicalization (reproducible).** Extract sections **1–16** (from the line `## 1.` up to, but not including, `## 17.`); for each excluded scalar field, replace its value with the sentinel `<EXCLUDED>` (`runtime_name`, `authorization_sha`, `expires_on`, `database_identity`); replace **every fenced block that appears inside §15**, including its opening fence and any language label, with `` ``` `` + the sentinel + `` ``` `` (a structural rule — it covers the §15.1 and §15.2 operator-record blocks and any future §15 block, and it is scoped to §15 so that the hashed fenced blocks in §4, §4A, §7, §8, and §14 are unaffected); normalize line endings to `\n`; strip trailing whitespace per line; drop trailing blank lines; UTF-8 encode; SHA-256.

The verifier **fails closed**: it requires exactly **two** fenced operator-record blocks in §15, exactly **one** occurrence of each excluded scalar assignment (`runtime_name`, `authorization_sha`, `expires_on`, `database_identity`), `authorized_source_commit` present as a full 40-character hex SHA, and `authorized_alembic_head = b2d8f4c6a901`. Any deviation is an error, not a silently different hash. The canonical reference implementation is the **tracked** `scripts/governance/hash_ws5_authorization.py`, with regression fixtures pinning the original and amended hashes; a byte-identical mirror is kept in the review folder. The hash is recorded in §18 and **independently recomputed from `main`** at effectiveness (§18); `runtime_name` then uses its first 12 hex chars.

## 18. Effectiveness and invocation (revised §9 ruling)

**Two separate events — effectiveness precedes invocation:**

```
final document approved (owner: APPROVED FOR AUTHORIZATION)
  → authorization revision merged to main
  → final body hash recorded + independently verified, merge SHA recorded
  → authorization becomes EFFECTIVE
  → explicit §15 operator invocation starts WS5
```

**The authorization becomes EFFECTIVE when the exact owner-approved revision is merged to `main`, its final body hash is recorded and independently verified, and the merge SHA is recorded. Merge does not begin execution. WS5 begins only through the separate §15 operator invocation.**

**Effectiveness record (satisfied):** merged to `main` at `f1646719dde08af497e6dcf1da4e0369cfba7754` (PR #594) at `2026-08-02T20:39:37Z`; body hash independently recomputed from the `main` blob (`265a31c…`) = `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0` (matches §17); merge SHA recorded above. The authorization became **APPROVED / EFFECTIVE — EXECUTION NOT YET INVOKED**. No WS5 execution has been invoked; no §15 operator record has been created. *(PR #595 subsequently recorded effectiveness in this document; it touched only hash-excluded metadata — §§1–16 were byte-identical and the body hash was unchanged.)*

**Amendment-1 record (in progress — §15 sequencing).** The merged §15 required `runtime_resource_ids`, `database_identity`, and `image_digest` in the operator record **before** execution could begin, while §1, §3, and §5 make creating those very resources a WS5 activity. The requirement was therefore unsatisfiable, not merely awkward: no operator could produce a truthful record. Because §15 sits inside the hashed body (§§1–16), the correction necessarily changes the body hash, and is handled as a **formally approved amendment** under §14 *Amendment continuity* — superseding the prior hash rather than expiring the authorization.

| Step | State |
|------|-------|
| Amendment drafted, body frozen, hash computed | ✅ draft hash `f44c9a53…` |
| Owner review of the draft | ✅ **REVISE** — three corrections required (Stage-1 database reads; post-invocation amendment; explicit superseded-hash retirement) |
| Corrections applied; body re-frozen; hash recomputed | ✅ `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` (draft `f44c9a53…` **withdrawn, never effective**) |
| Owner *APPROVED FOR AUTHORIZATION* over the corrected body | ✅ 2026-08-02 — owner independently recomputed `52b3ff13…` and it matched |
| Amendment merged to `main`; merge SHA recorded | ✅ `af2dfc16b8294edd649f2a19fcac2cb954fff00b` (PR #596, squash of reviewed head `f57ff64c…`) at `2026-08-02T21:56:47Z` |
| Amended body hash independently re-verified from `main` (§17) | ✅ **PASS** — recomputed from the `main` blob `a53651e…` = `52b3ff13…` |
| Prior hash `99f045e0…` retired per §14 *Superseded-hash retirement*; `runtime_name` re-derived | ✅ retired `2026-08-02T21:56:47Z`; `runtime_name = adr0043-canary-ws5-52b3ff136196` |
| Stage-1 operator invocation requested (§15.1) | ☐ **NOT ISSUED** — every box above is checked, but the invocation is a **separate owner act** and has not been made |

**Amendment effectiveness record (§14 *Superseded-hash retirement*) — satisfied:**

```
superseded_authorization_body_sha256 = 99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0
effective_authorization_body_sha256  = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
superseded_at_utc                    = 2026-08-02T21:56:47Z
amendment_merge_sha                  = af2dfc16b8294edd649f2a19fcac2cb954fff00b
independent_new_hash_verification    = PASS (recomputed from main blob a53651e…, verifier taken from main)
```

`99f045e0…` is **permanently retired** as an authorizing credential from `superseded_at_utc`. It must not be accepted for Stage-1 invocation, Stage-2 checkpointing, resource creation, or resource adoption; presenting it is **REFUSED** (§10, §14). `f44c9a53…` was a withdrawn draft and never carried authority. **No resource exists under any of the three identities.**

`authorization_effective_at` remains `2026-08-02T20:39:37Z` and `absolute_expiration` remains `2026-08-16T23:59:59 America/Chicago` — the amendment did not restart the clock (§14).

Until the amendment is effective, the authorization in force remains the `99f045e0…` revision, with **execution held** — there is no interval in which nothing governs (§14).

**Status lifecycle:**

| Phase | Status |
|-------|--------|
| Approved, pre-merge | `APPROVED FOR AUTHORIZATION — PENDING EFFECTIVE MERGE` |
| Merged `f1646719…`, hash re-verified, merge SHA recorded | `APPROVED / EFFECTIVE — EXECUTION NOT YET INVOKED` |
| §15 found unsatisfiable; amendment drafted and approved | `APPROVED / EFFECTIVE — EXECUTION NOT YET INVOKED; OPERATOR INVOCATION HELD PENDING §15 SEQUENCING AMENDMENT` |
| **Now (amendment merged `af2dfc16…`, hash re-verified from `main`, `99f045e0…` retired)** | **`EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED`** |
| After §15.1 Stage-1 operator invocation | `EFFECTIVE — WS5 INVOKED (STAGE 1: CREATION ONLY)` |
| After the §15.2 Stage-2 checkpoint passes | `EFFECTIVE — WS5 INVOKED (STAGE 2 BOUND)` |

**Owner ruling block (intended, for final review):**

| Decision | Value |
|----------|-------|
| Authorize WS5 runtime preparation | **APPROVED, subject to exact scope** (this document, §1–§17) |
| Runtime mode | **CREATE-AND-ATTACH** |
| Runtime identity | `adr0043-canary-ws5-<authorization_body_sha256_first12>` |
| Frozen source commit | `authorized_source_commit = 7342ebbd8e061518ba9bd0524803f8e20d760a78` (exact current `main` tip) |
| Frozen schema head | `authorized_alembic_head = b2d8f4c6a901` |
| Owner | jayw04 |
| Expiration | `authorization_effective_at + 14d`, ending `23:59:59 America/Chicago` (§14) |
| Automatic execution on merge | **PROHIBITED** |
| Required operator invocation | **YES**, bound to final body hash (§15, §17) |
| **Authorization body SHA-256** (over §§1–16, §17 rule) | `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0` |
| Derived runtime identity | `adr0043-canary-ws5-99f045e09532` |
| Authorization merge SHA | `f1646719dde08af497e6dcf1da4e0369cfba7754` (PR #594; base `7342ebb…`; reviewed head `0bc173e…`) |
| Authorization effective at | `2026-08-02T20:39:37Z` |
| Concrete absolute_expiration | `2026-08-16T23:59:59 America/Chicago` (`effective_at + 14d`, §14) |
| Post-merge body-hash re-verification | **PASS** — recomputed from `main` blob `265a31c…` = `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0` |
| Countersignature | Owner ruling, 2026-08-02 |
| Date | 2026-08-02 |

*(The ruling above is the countersigned record of the original authorization and is preserved unaltered. The amendment ruling below is separate.)*

**Amendment-1 ruling block (for owner ruling — NOT yet issued):**

| Decision | Value |
|----------|-------|
| Amendment | **AMENDMENT-1 — §15 invocation sequencing** |
| Reason | The merged §15 required post-provisioning identities before execution could begin; under CREATE-AND-ATTACH (§3) those resources do not exist until WS5 creates them, so the record was **unsatisfiable** |
| Change 1 | §15 split into **§15.1 Stage 1** (opening invocation — authorizes creation of runtime, isolated DB, and image only) and **§15.2 Stage 2** (resource-binding checkpoint — must pass before migration, DB reads, broker reads, dry-run, or evidence) |
| Change 2 | §14 **Amendment continuity** — an approved amendment supersedes rather than expires; `authorization_effective_at` is **not** reset; superseded `authorization_sha` identities are dead |
| Change 3 | §4B cross-reference to the two stages (no change to the required fields) |
| **Change 4** *(owner correction 1)* | §15.1 — **no application-level database connection, query, read, write, schema inspection, Alembic inspection, or migration at Stage 1**; only provider control-plane create/describe/status, resource ID and endpoint retrieval, network reachability configuration, and recording those values in §4B. The Stage-1 negative sentence is restated so the closed authority list leaves nothing to inference. |
| **Change 5** *(owner correction 2)* | §14 **Post-invocation amendment rule** — amendment continuity applies **only** before Stage-1 invocation; afterwards any body-changing amendment terminates the attempt as **REFUSED**, with no retag / adopt / continue, evidence preserved for adjudication, teardown requiring separate authority, and a new authorization plus newly derived runtime identity for any further attempt. Mirrored as a §10 mechanical stop condition. |
| **Change 6** *(owner correction 3)* | §14 **Superseded-hash retirement** — on amendment effectiveness the prior body hash is **permanently retired as an authorizing credential** and is REFUSED for Stage-1 invocation, Stage-2 checkpointing, resource creation, and resource adoption; the amendment effectiveness record must carry `superseded_authorization_body_sha256`, `effective_authorization_body_sha256`, `superseded_at_utc`, `amendment_merge_sha`, `independent_new_hash_verification`. Mirrored as a §10 stop condition. |
| Change 7 (non-hashed) | §17 canonicalization states the §15 exclusion structurally, covering both blocks and optional fence language labels, and names the fail-closed verifier contract and its tracked path |
| Stop conditions added (§10) | (a) body-changing amendment after Stage-1 invocation; (b) presentation of a superseded body hash; (c) application-level database access before the Stage-2 checkpoint passes |
| Unchanged | Every scope item, ceiling, prohibition, dry-run flag, disposition, exit criterion, the expiration formula, `authorized_source_commit`, and `authorized_alembic_head`. §10's pre-existing stop conditions are unaltered — the three above are additions. |
| `authorized_source_commit` | `7342ebbd8e061518ba9bd0524803f8e20d760a78` — **unchanged** |
| `authorized_alembic_head` | `b2d8f4c6a901` — **unchanged** |
| Absolute expiration | `2026-08-16T23:59:59 America/Chicago` — **unchanged; not extended by amendment** |
| **Amended body SHA-256** (over §§1–16, §17 rule) | `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` |
| Superseded body SHA-256 | `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0` |
| Withdrawn draft SHA-256 (never effective) | `f44c9a53a46a382734ea604ac3fa132ef06294d874c9e390fafd2ce3c5580c34` |
| Derived runtime identity | `adr0043-canary-ws5-52b3ff136196` — **no resource exists** under this, the superseded, or the withdrawn-draft identity |
| Canonicalization regression | **PASS** — the tracked verifier reproduces `99f045e0…` on the pre-amendment fixture and `52b3ff13…` on this document (`--selftest`), so the exclusion change is behavior-preserving |
| Verifier | `scripts/governance/hash_ws5_authorization.py` (tracked), fail-closed, with fixtures pinning both hashes |
| Automatic execution on merge | **PROHIBITED** (unchanged) |
| Required operator invocation | **YES — two stages**, bound to the amended body hash (§15.1, §15.2, §17) |
| Owner ruling | ✅ **APPROVED FOR AUTHORIZATION** — issued over the corrected body; owner independently recomputed `52b3ff13…` under the §17 rules and confirmed exactly one occurrence of each excluded scalar and exactly two §15 operator-record fenced blocks |
| Identities not authorized for future invocation | `99f045e0…` (effective only until this amendment is effective, then **permanently retired**); `f44c9a53…` (withdrawn draft, **never carried authority**) |
| Amendment merge SHA | `af2dfc16b8294edd649f2a19fcac2cb954fff00b` (PR #596; base `3920484…`; reviewed head `f57ff64c…`; all required checks passed, no override) |
| Amendment effective at | `2026-08-02T21:56:47Z` |
| Post-merge body-hash re-verification | **PASS** — recomputed from `main` blob `a53651e…` using the verifier as committed to `main` = `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` |
| Countersignature | Owner ruling, 2026-08-02 |
| Date | 2026-08-02 |

## 19. Document control

| Rev | Date | Change |
|-----|------|--------|
| proposal | 2026-08-02 | Drafted and returned for owner ruling |
| published | 2026-08-02 | Owner ruling *APPROVED FOR PUBLICATION ONLY — NOT YET EFFECTIVE*; published NON-EFFECTIVE via PR #593 (`7342ebb…`) |
| revised | 2026-08-02 | Owner calls folded: CREATE-AND-ATTACH; deterministic identity + tags; infra/broker/DB ceilings; dry-run incapacity; stop conditions; dispositions; expiration; operator invocation; body-hash computation |
| revised-2 | 2026-08-02 | Five blocking corrections: (1) effectiveness separated from invocation with status lifecycle (§18); (2) exact `authorized_source_commit` + `authorized_alembic_head` frozen, no "descends-from/covered-later" (§4A, §1, §10, §16); (3) concrete DB-role privilege enforcement — no writes on control tables, evidence in dedicated WS5 tables (§7, §8); (4) broker-credential three-tier rules reconciled + no rotation, attach-existing-only (§6); (5) single expiration rule `effective_at + 14d America/Chicago` (§14). Precision: opening-record fields (§4B); clone must-not-copy authoritative/executable state (§5). Status **REVISED PROPOSAL — PENDING FINAL AUTHORIZATION REVIEW** — not effective. |
| revised-3 (final) | 2026-08-02 | Final consistency correction (§17): `authorized_source_commit` **included** in the hashed body and frozen to `7342ebbd8e061518ba9bd0524803f8e20d760a78` (exact current `main` tip); exclusion list narrowed to genuinely-unknowable values (derived `runtime_name`, `authorization_sha` tag, concrete `expires_on`/`absolute_expiration`, `database_identity`, §15 operator record, ruling/status/doc-control, merge SHA). Canonical body hash computed via `hash_ws5_authorization.py` and recorded: `99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0`; derived `runtime_name = adr0043-canary-ws5-99f045e09532`. Status **FINAL — PENDING OWNER *APPROVED FOR AUTHORIZATION* RULING** — not effective; not committed. |
| authorized | 2026-08-02 | Owner issued **APPROVED FOR AUTHORIZATION** over the frozen body (hash `99f045e0…` unchanged; §§1–16 untouched — only header/warning/§18/§19 metadata edited). Status set to **APPROVED FOR AUTHORIZATION — PENDING EFFECTIVE MERGE**. Committed to a docs-only branch (reviewed head `0bc173e…`) for the effective-merge PR #594. Merge does not start WS5 (§15). |
| effective | 2026-08-02 | PR #594 merged to `main` at `f1646719…` (`2026-08-02T20:39:37Z`); body hash independently re-verified from the `main` blob (`265a31c…`) = `99f045e0…` (matches §17); merge SHA + effective timestamp + concrete `absolute_expiration = 2026-08-16T23:59:59 America/Chicago` recorded; §4 `authorization_sha`/`expires_on` scalar tags filled (hash-excluded per §17). §§1–16 byte-identical to the reviewed head — hash unchanged. Status set to **APPROVED / EFFECTIVE — EXECUTION NOT YET INVOKED**. WS5 not invoked; §15 operator record not created; all execution HOLDs remain. |
| amendment-1 draft (withdrawn) | 2026-08-02 | **§15 sequencing amendment, first draft — returned by owner ruling REVISE; never approved, merged, or effective.** Defect: the merged §15 required `runtime_resource_ids`, `database_identity`, and `image_digest` in the operator record *before* execution may begin, but under CREATE-AND-ATTACH (§3) those resources are created *by* WS5 (§1, §5) — so no operator could truthfully produce the record and §15 was unsatisfiable. Correction: (1) §15 split into **§15.1 Stage 1** (opening invocation; authorizes creation of the isolated runtime, the isolated DB *without* migration, the image built from `authorized_source_commit`, and the §4B opening record — and nothing else) and **§15.2 Stage 2** (resource-binding checkpoint; records and verifies the runtime-created identities, and must pass before migration, DB reads, broker reads, dry-run, or evidence production); (2) §14 gains **Amendment continuity** — an approved amendment supersedes rather than expires the authorization, `authorization_effective_at` is **not** reset (so `absolute_expiration` stays `2026-08-16` and cannot be extended by repeated amendment), and resources under a superseded `authorization_sha` are unauthorized; (3) §4B cross-references the two stages; (4) §17 (non-hashed) states the §15 exclusion structurally so it covers both blocks. **No scope, ceiling, prohibition, dry-run flag, stop condition, disposition, exit criterion, source commit, schema head, or expiration value changed.** Draft body hash `f44c9a53a46a382734ea604ac3fa132ef06294d874c9e390fafd2ce3c5580c34`. Status **AMENDMENT-1 DRAFT — RETURNED BY OWNER RULING REVISE**; never approved, never merged, never effective. |
| amendment-1 rev-2 (final) | 2026-08-02 | **Owner ruling REVISE — three governance corrections applied; pending owner ruling; not effective, not merged.** (1) **§15.1 Stage-1 database reads prohibited** — no application-level connection, query, read, write, schema inspection, Alembic inspection, or migration; only provider control-plane create/describe/status, resource-ID and endpoint retrieval, network reachability configuration, and recording those values in §4B; the Stage-1 negative sentence restated so the closed authority list leaves nothing to inference. (2) **§14 Post-invocation amendment rule** — amendment continuity applies only before Stage-1 invocation; afterwards a body-changing amendment terminates the attempt as REFUSED, with no hot-patch / retag / adopt / continue, evidence preserved for adjudication, teardown requiring separate authority, and a new authorization plus newly derived runtime identity for any further attempt. (3) **§14 Superseded-hash retirement** — the prior body hash is permanently retired as an authorizing credential and REFUSED for Stage-1 invocation, Stage-2 checkpointing, resource creation, and resource adoption; the amendment effectiveness record must carry `superseded_authorization_body_sha256`, `effective_authorization_body_sha256`, `superseded_at_utc`, `amendment_merge_sha`, `independent_new_hash_verification`. All three mirrored into **§10** as mechanical stop conditions. Body hash recomputed: `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae`, superseding `99f045e0…` and withdrawing the never-effective draft `f44c9a53…`; derived `runtime_name = adr0043-canary-ws5-52b3ff136196`. Verifier hardened and moved to the tracked path `scripts/governance/hash_ws5_authorization.py` (fail-closed; fixtures pin `99f045e0…` and `52b3ff13…`). **No scope item, ceiling, prohibition, dry-run flag, disposition, exit criterion, source commit, schema head, or expiration value changed.** Status **AMENDMENT-1 rev-2 — FINAL, PENDING OWNER *APPROVED FOR AUTHORIZATION* RULING**; authorization in force stays the `99f045e0…` revision with **operator invocation HELD**; all runtime and broker HOLDs remain. |
| amendment-1 approved | 2026-08-02 | Owner issued **APPROVED FOR AUTHORIZATION** over the corrected amendment body, having **independently recomputed** the canonical hash from the byte-exact document under the §17 rules: `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` — matched, with exactly one occurrence of each excluded scalar and exactly two §15 operator-record fenced blocks. Approved identity `runtime_name = adr0043-canary-ws5-52b3ff136196`. Identities **not authorized for future invocation**: `99f045e0…` (effective only until this amendment becomes effective, then permanently retired per §14) and `f44c9a53…` (withdrawn draft, never carried authority). Owner confirmed all governance defects closed: Stage-1 creation-only; application-level DB access barred until Stage 2; control-plane creation narrowly distinguished from SQL access; migration / broker reads / DB reads / dry-run / readiness evidence only after the Stage-2 checkpoint; post-Stage-1 body-changing amendment ⇒ REFUSED; no retag or adoption of existing resources; superseded hashes expressly retired; no clock restart; expiration remains `2026-08-16T23:59:59 America/Chicago`; no resource exists under any identity; merge alone remains non-executing. Status **APPROVED FOR AUTHORIZATION — PENDING EFFECTIVE MERGE**. §§1–16 unchanged from the reviewed body — hash unchanged. **This ruling does not invoke Stage 1**; all runtime, database, image, broker, migration, dry-run, evidence, baseline, Start A/B, Phase 0, A1–A5, ENFORCE, and D-WIRE HOLDs remain in force. |
| amendment-1 effective | 2026-08-02 | **PR #596 merged to `main` at `af2dfc16b8294edd649f2a19fcac2cb954fff00b`** (`2026-08-02T21:56:47Z`), squash of the exact reviewed head `f57ff64c1a869ba6ba49ab4d4dd66dd3335edeff`; five files, one commit, base `3920484…` unchanged during review; all required checks (`Detect changes`, `Python (backend)`, `Python FULL (backend)`, `Python CI Gate`) passed with **no bypass, waiver, or administrative override**. Amended body hash **independently recomputed from the `main` blob `a53651e…`, using the verifier as committed to `main`** = `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` — matches §17. Effectiveness record filled per §14 *Superseded-hash retirement*: `superseded_authorization_body_sha256 = 99f045e0…`, `effective_authorization_body_sha256 = 52b3ff13…`, `superseded_at_utc = 2026-08-02T21:56:47Z`, `amendment_merge_sha = af2dfc16…`, `independent_new_hash_verification = PASS`. **`99f045e0…` is permanently retired** as an authorizing credential; `f44c9a53…` never carried authority; **no resource exists under any of the three identities**. `authorization_effective_at` preserved at `2026-08-02T20:39:37Z` and `absolute_expiration` preserved at `2026-08-16T23:59:59 America/Chicago` — the amendment did not restart the clock. This entry is **metadata-only and hash-excluded** under §17: §§1–16 are byte-identical to the merged amendment and the body hash is unchanged. Status set to **EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED**. **Stage 1 is NOT invoked**; no §15.1 operator record has been issued or constructed; all runtime, database, image, broker, migration, dry-run, readiness-evidence, authoritative-baseline, Start A/B, Phase 0, A1–A5, ENFORCE, and D-WIRE HOLDs remain in force. |

*End of ADR0043-LIVE-CANARY-WS5-RUNTIME-PREP-START-001 (EFFECTIVE (AMENDED) — EXECUTION NOT YET INVOKED; STAGE 1 NOT INVOKED; ALL EXECUTION HOLDS IN FORCE).*
