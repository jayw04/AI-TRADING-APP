# ADR-0043 Phase-0 D-BOX — Evidence-Gap Design (Prospective Collection)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** |
| Status | **DESIGN-ONLY — NON-EXECUTABLE** |
| Created (UTC) | 2026-07-30 |
| Parent close-out | ADR0043-PH0-D-BOX-V12-CLOSE-001 **EFFECTIVE** (merge `4232c1a`) |
| Closed campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** |
| Bound freeze (closed) | FREEZE-MANIFEST-003 body `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Bound start (exhausted) | START-002 merge `952848c` — **no remaining execution authority** |
| Evidence root (closed run) | `docs/design/evidence/dbox_campaign_v1_2_run_001/` |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| Prior acquisition design | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 (construction rules retained; gaps refined herein) |
| Broker order submission | **HOLD — not authorized** |
| Gate package execution | **Not authorized** |
| Archive enrichment / reconstruction | **Forbidden** against sealed QUALIFIED archives |
| Production / `b0058bf` | **Reference-only — do not use or modify** |
| D-WIRE | **Fail-closed / BLOCKED** until QUALIFIED evidence exists under a **new** auth → freeze → start |

This package specifies **prospective** collection requirements to close the evidence gaps
that produced INCONCLUSIVE dispositions under CAMPAIGN-001 v1.2. It does **not** collect
evidence, does **not** modify production, does **not** submit broker activity, and does
**not** reopen any gate.

---

## 1. Purpose

Translate v1.2 INCONCLUSIVE findings into a narrow, bindable collection design so a
**future** authorization / freeze / start sequence can produce QUALIFIED archives that
make O3, O4-A, O4-B (and eventually O5) **adjudicable to APPROVE or REJECT** rather than
forced INCONCLUSIVE from missing surfaces.

---

## 2. Findings that define the gaps (binding)

| Package | v1.2 disposition | Gap (do not “fix” sealed archives) |
|---------|------------------|----------------------------------------|
| O3 | INCONCLUSIVE — replay surfaces absent | 0/292 rows had complete `quote_provenance`, `checkpoint_tuple`, `loss_accounting_inputs`, `recovery_inputs` (authority present; others null) |
| O4-A | INCONCLUSIVE — decision-time quotes absent | 0/287 rows had usable two-sided decision-time quotes; `run_o4a` → `STALE_EVIDENCE` vs expected `INSUFFICIENT_EXECUTION_COST` |
| O4-B | INCONCLUSIVE — day_change absent | 286/286 rows had fills/terminal completeness but `day_change` null; `run_o4b` → `INDETERMINATE` vs expected `UNREACHABLE_WITHIN_CAPS` |
| Combined O4 | INCONCLUSIVE | Both halves incomplete |
| O5 | INCONCLUSIVE | `anchors: []`; no Tier-A anchors; new live fills remain forbidden under HOLD |

Structural/hash/`ord:`/exclusion/no-mix controls **passed**. Gaps are **missing governed
surfaces**, not pin or adapter failures.

---

## 3. Non-goals (hard)

| Forbidden under this design | Status |
|-------------------------------|--------|
| Collecting, capturing, or reconstructing evidence now | **Forbidden** |
| Enriching or mutating sealed QUALIFIED O3/O4 archives from QUAL-001 | **Forbidden** |
| Rerunning O3/O4/O5 under FREEZE-003 / START-002 | **Forbidden** |
| Broker orders / new live fills / new observations for convenience | **Forbidden** |
| Production imports / deployed-path observation / modifying `b0058bf` | **Forbidden** |
| Canary / ENFORCE / caps / July 24 limits-digest changes | **Forbidden** |
| Treating this document as campaign start or freeze | **Forbidden** |
| Claiming D-WIRE eligibility | **Forbidden** |

---

## 4. Gap A — O3 replay-surface capture

### 4.1 Required surfaces (per observation / `ord:<orders.id>`)

| Surface | Requirement |
|---------|-------------|
| `quote_provenance` | Non-null governed provenance object sufficient for historical replay |
| `authority_inputs` | Retain (already present on QUALIFIED O3); must remain account-3 scoped |
| `checkpoint_tuple` | Non-null checkpoint binding fields used by O3 protocol |
| `loss_accounting_inputs` | Non-null inputs needed for loss reconcile / false-reachable scoring |
| `recovery_inputs` | Non-null recovery path inputs required by protocol |
| Identity | Continue `plan_id=ord:<orders.id>` **or** document a superseding episode identity with adapter contract in the **new** freeze |

### 4.2 Prospective collection rules

| Rule | Requirement |
|------|-------------|
| Source | Pre-existing sealed / reconstructable account-3 records only, under a future acquisition auth; **no invention** |
| Cutoff / window | Explicit UTC eligibility window frozen **before** selection |
| Completeness bar | Observation eligible for QUALIFIED O3 only if **all** §4.1 surfaces non-null |
| Exclusions | Reason-code every incomplete episode (e.g. `MISSING_REPLAY_SURFACE:<field>`) |
| No look-ahead | Must not import O4-B fills or terminal state into O3 rows |
| Output | New archive id (not a mutation of `O3-CAND-20260730T022316Z`) |

### 4.3 Acceptance for a future campaign

Future O3 may leave INCONCLUSIVE only for protocol-defined residual conditions — **not**
because the corpus systematically lacks §4.1 surfaces.

---

## 5. Gap B — O4-A two-sided decision-time quote capture

### 5.1 Required surfaces (per observation)

| Surface | Requirement |
|---------|-------------|
| Two-sided quote | For each intended symbol: `bid`, `ask`, and freshness/age as required by `phase0_reachability` / Tier-D rules |
| Timing | Quote must be valid **at or before** first-broker-submission cutoff |
| `model_available` | Explicit boolean at decision time |
| Prohibitions | `fills`, `terminal_broker_state`, `post_submit_quotes`, and all O4-B-only fields **must remain null/absent** |
| Identity | `plan_id=ord:<orders.id>` (or superseding contract bound in new freeze) |

### 5.2 Prospective collection rules

| Rule | Requirement |
|------|-------------|
| Cutoff | First-submission boundary (same family as QUAL-001); unreconstructable cutoff → exclude with `MISSING_CUTOFF` |
| Empty quotes | **Not QUALIFIED** for O4-A gate binding; record as `MISSING_DECISION_TIME_QUOTE` |
| Expected protocol target | `INDETERMINATE` + `INSUFFICIENT_EXECUTION_COST` (or `MODEL_UNAVAILABLE`) under frozen caps — not `STALE_EVIDENCE` from empty books |
| No mix | Separate archive from O4-B; no payload merge |
| Output | New archive id (not mutation of `O4A-CAND-20260730T022316Z`) |

### 5.3 Acceptance for a future campaign

A QUALIFIED O4-A set must support `run_o4a` expected-verdict adjudication on the eligible
population without reconstructing quotes at evaluation time.

---

## 6. Gap C — O4-B forensic baseline (`day_change` or equivalent)

### 6.1 Required surfaces (per observation)

| Surface | Requirement |
|---------|-------------|
| Fills | Retain completeness bar from QUAL-001 (`terminal_completeness.complete`, 1:1 plan/fill reconcile) |
| `fill_loss_per_round_trip` | Required |
| Forensic baseline | Governed **`day_change`** (preferred) **or** an equivalent baseline explicitly accepted in a future controlling/integration amendment and freeze — sufficient for `assess()` to evaluate distance-to-target under frozen caps |
| Terminal loss/accounting | Retain non-null terminal loss-accounting inputs |
| Prohibitions | Must not substitute O4-A decision-time-only fields for forensic truth |

### 6.2 Prospective collection rules

| Rule | Requirement |
|------|-------------|
| Baseline provenance | Document source, as-of time, and account-3 scope; pin in archive provenance |
| Null `day_change` | **Not QUALIFIED** for O4-B gate binding unless an approved equivalent baseline field is present and freeze-bound |
| Expected protocol target | `UNREACHABLE_WITHIN_CAPS` under frozen caps for eligible forensic rows |
| Exclusions | Continue O4B_INCOMPLETE family; add `MISSING_FORENSIC_BASELINE` where fills exist but baseline absent |
| Output | New archive id (not mutation of `O4B-CAND-20260730T022316Z`) |

### 6.3 Acceptance for a future campaign

QUALIFIED O4-B must allow `run_o4b` to reach the expected unreachable verdict on eligible
rows without inventing `day_change` at evaluation time.

---

## 7. Gap D — O5 Tier-A anchor acquisition

### 7.1 Required properties

| Property | Requirement |
|----------|-------------|
| Tier | **Tier-A** only for load-bearing O5 (pre-existing sealed live-fill anchors) |
| Policy | D-BOX does **not** authorize generating new live fills to create anchors |
| Array | Non-empty `o5_live_fill_anchors.anchors[]` with identity + SHA-256 + provenance |
| Floors | Honor WP5 / statistical design floors (or one governed replacement) before evaluation |
| Fail closed | Empty `anchors: []` → O5 INCONCLUSIVE; D-WIRE remains blocked |

### 7.2 Prospective collection rules

| Rule | Requirement |
|------|-------------|
| Locate-first | Search and qualify **pre-existing** sealed Tier-A anchors under a future O5 acquisition auth |
| No generation | Creating fills/orders to “populate” anchors remains **HOLD** |
| Inadequate set | Predetermined INCONCLUSIVE; do not invent placeholders |

---

## 8. Shared construction / qualification posture (future)

When (and only when) a **separate** owner authorization is issued:

1. Seal a **new** acquisition freeze (do not mutate FREEZE-003 or O34-ACQ-FREEZE-001 in place).  
2. Construct **new** candidate archives with gap surfaces filled per §§4–7.  
3. Independently QUALIFY (hash, schema, no-mix, exclusion reason codes, completeness bars).  
4. Amend or supersede campaign scope; seal a **new** campaign freeze; issue a **new** start.  
5. Execute gates only after opening controls analogous to START-002 §4.

Until steps 1–4 complete with QUALIFIED artifacts, **no gate execution** and **no D-WIRE**.

Episode identity: retain `plan_id=ord:<orders.id>` unless a future freeze binds a different
deterministic contract and readiness fails closed without it.

Account scope: **3 only**. Runtime for any future execution: **isolated harness only**.

---

## 9. Relationship to sealed QUALIFIED archives (QUAL-001)

| Archive | Status under this design |
|---------|--------------------------|
| `O3-CAND-20260730T022316Z` | Historical QUALIFIED candidate — **immutable**; insufficient for O3 APPROVE |
| `O4A-CAND-20260730T022316Z` | Historical QUALIFIED candidate — **immutable**; insufficient for O4-A APPROVE |
| `O4B-CAND-20260730T022316Z` | Historical QUALIFIED candidate — **immutable**; insufficient for O4-B APPROVE |

They remain valid evidence of what was available to v1.2. They are **not** templates to
overwrite.

---

## 10. Disposition of this package

**DESIGN-ONLY EVIDENCE-GAP PACKAGE — NON-EXECUTABLE.**

| Item | Status |
|------|--------|
| Collection / capture | **Not authorized** |
| Gate reopen | **Not authorized** |
| FREEZE-003 / START-002 | **Exhausted / closed** |
| D-WIRE | **BLOCKED** (fail-closed) |
| HOLD | **Unchanged** |
| Next executable step | Separate owner **authorization** for acquisition (not this document) |

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 v1.0.*
