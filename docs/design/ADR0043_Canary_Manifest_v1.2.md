# ADR0043 Canary Manifest v1.2 (WS4A Contract Freeze)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-CANARY-MANIFEST-v1.2 |
| Status | **REVISED DRAFT — PENDING OWNER APPROVAL** (blockers A & B corrected; non-blocking items folded) |
| Layer | Contract (WS4A) — stable execution contracts only |
| Date | 2026-08-02 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 v1.0 |
| Baseline design | ADR0043-CANARY-BASELINE-DESIGN-001 v0.2.1 (Model A) |
| Code capability | WS3 merge SHA `92cbd30efe819885e0fdf34e701af5d19dcb3557` (PR #591) |
| Supersedes for execution | `ADR0043_Canary_Manifest_v1.1` (2026-07-21) — historical A1–A5 reference only |
| Design version token (frozen) | `ADR0043-CANARY-MANIFEST-v1.2` (carried as `design_version` in Start A authorization + baseline identity) |
| Authorization ceiling | Contract document only. Does **not** authorize provisioning, WS5, WS6 seal, Start A, Phase 0, broker activity, ENFORCE, or D-WIRE. |

> **Scope discipline.** This manifest freezes only **stable execution contracts** — facts that are knowable and fixed independent of the live runtime. It deliberately contains **no runtime-resolved facts**: no actual image digest, no configuration digest value, no Workbench database IDs, no runtime host identity, no `freeze_id` / `freeze_body_sha256`, and no live risk-limit row values. Those are resolved in WS5 (readiness) and bound in WS6 (seal). Every such field below is marked **[WS5/WS6-BOUND]** and must contain no placeholder that could be mistaken for a real value.

---

## 1. Broker identity and account role

| Item | Frozen value |
|------|--------------|
| Broker account (Alpaca paper) | `PA34USW0Q8UO` (code constant `EXPECTED_BROKER_ACCOUNT_ID`) |
| Account role | Dedicated permanent risk-engine **verification** account |
| Workbench account ID / user ID | **[WS5/WS6-BOUND]** — resolved at runtime reconciliation; `account_id=3` is **not** assumed authoritative |
| Broker-identity enforcement | Any authorization or baseline whose `broker_account_id ≠ PA34USW0Q8UO` → `CONFLICT` / refuse |

## 2. Protected starting leg policy

| Item | Frozen rule |
|------|-------------|
| Protected leg | `MSFT:19` (19 shares MSFT) |
| Provenance | **Runtime-verified**; no manufacture of a missing leg |
| Absent / different at readiness | Readiness **FAIL** → refuse; do not slide or fabricate |
| Post-A2 flatten | **Do not** fully flatten (frozen); A4 evaluated against reduced remaining qty (§8) |

## 3. Assertions A1–A5 (frozen definitions)

| # | Assertion | Pass criterion |
|---|-----------|----------------|
| **A1** | `state_authoritative` | Durable state is `REDUCTION_ONLY_DAILY_LOSS` — not breaker column alone, not inferred, not breaker-origin |
| **A2** | `verified_reduction_allowed` | Frozen risk-reducing MSFT **sell admitted** (`PERMIT_REDUCTION`) **and** qualifying fill ≥ minimum qualifying reduction with broker/local reconciliation (§7.4); risk-reducing qty; no new exposure; durable trail |
| **A3** | `new_risk_refused` | Frozen new-risk **BUY rejected** with **`LOSS_CONTROL_STOP`** (not another gate); no broker order; no reservation leak; durable rejection + audit |
| **A4** | `reached_recovery_cooldown` | Frozen recovery → parent preflight PASSED; **exactly the frozen 12-check set**, all PASS; committed `PREFLIGHT_PASS`; state `RECOVERY_COOLDOWN` |
| **A5** | `evaluator_holds` | Evaluator returns exactly **`HOLD`**; remains in cooldown; no `NORMAL` / `COOLDOWN_COMPLETE` / `INTEGRITY_STOP` / ungoverned re-arm |

## 4. Model A opening-window rule (frozen)

| Parameter | Frozen value |
|-----------|--------------|
| Session timezone | `America/New_York` |
| Session boundary | US equity **regular** session |
| Target opening time | 09:30:00 ET |
| Permitted capture window | **[09:30:00, 09:35:00) ET** |
| Authoritative field | Alpaca account **`equity`** |
| `last_equity` | **Telemetry only** — never control |
| Cumulative fallback | **Prohibited** |
| Window-admissibility clock | Local receipt timestamp (ET) controls; broker response timestamp preferred when present; disagreement on membership → **REFUSED** (zero skew tolerance) |
| First canary / Phase 0 order | Only **after** the baseline persistence transaction **commits** |
| Missed window | **REFUSED** — no later run-start substitution (Model B not authorized) |
| Baseline source constant | `SESSION_OPEN_BROKER_EQUITY` (`BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY`) |
| Canonical serialization | quantize 4 dp, `ROUND_HALF_EVEN` (projection JSON / projection hash only); control math uses exact parsed `Decimal` |
| Baseline unique identity | `(account_id, session_date, design_version, freeze_id)` — no in-place update; mismatch → conflict/refuse |
| Dual retention | raw broker response + `SHA-256(raw)`; canonical projection + `SHA-256(projection)`; qualifier re-fetches raw bytes |
| Capture audit event | `AuditAction.CANARY_MODEL_A_BASELINE_CAPTURE` |

## 5. Observation status and surface policy (frozen — single mapper)

Source of truth: `app/risk/loss_control/daily_loss_observation.py::map_surface_action`. Every consumer (breaker, engine step 9, preflight) must route through it.

**Statuses** (`ObservationStatus`): `AVAILABLE`, `UNAVAILABLE`, `STALE`, `CONFLICT`, `INVALID`.
**Surface actions** (`SurfaceAction`): `EVALUATE`, `REFUSE`, `REJECT`, `PERMIT_REDUCTION`, `FAIL_OR_INCOMPLETE`, `FAIL`, `PERMIT_REDUCTION_ADR0042_ONLY`.

| Status | `phase0` | `new_risk` | `verified_reduction` | `recovery` |
|--------|----------|------------|----------------------|------------|
| AVAILABLE | EVALUATE | EVALUATE | PERMIT_REDUCTION | EVALUATE |
| UNAVAILABLE | REFUSE | REJECT | PERMIT_REDUCTION | FAIL_OR_INCOMPLETE |
| STALE | REFUSE | REJECT | PERMIT_REDUCTION | FAIL_OR_INCOMPLETE |
| CONFLICT | REFUSE | REJECT | PERMIT_REDUCTION_ADR0042_ONLY | FAIL |
| INVALID | REFUSE | REJECT | PERMIT_REDUCTION_ADR0042_ONLY | FAIL |

**Frozen reason codes** (fail-closed provenance): `CANARY_BINDING_CONFLICT`, `MODEL_A_BASELINE_MISSING`, `MULTIPLE_BOUND_MODEL_A_BASELINES`, `BASELINE_BINDING_MISMATCH`, `BROKER_IDENTITY_MISMATCH`, `BASELINE_EVIDENCE_INCOMPLETE`, `CURRENT_EQUITY_MISSING`.

**Binding rule:** an EFFECTIVE Start A authorization (`START_A_STATUS_EFFECTIVE`) with a missing/invalid bound baseline yields a structured fail-closed status — **never** a silent return to `last_equity` or cumulative control. `PERMIT_REDUCTION_ADR0042_ONLY` preserves ADR-0042's risk-reducing escape without asserting the daily-loss basis is valid.

## 6. Exact recovery-check registry (frozen — A4)

Set identity from `constants.PREFLIGHT_CHECK_REGISTRY`. The qualifier verifies **set identity and registry order**, not merely a count of 12. Duplicates invalidate; unknown extra checks invalidate; prerequisite graph is load-bearing.

| # | Check name |
|---|------------|
| 1 | `state_known_and_recoverable` |
| 2 | `recovery_origin_proven` |
| 3 | `broker_reachable` |
| 4 | `broker_account_active` |
| 5 | `positions_reconcile` |
| 6 | `open_orders_reconcile` |
| 7 | `reservations_reconcile` |
| 8 | `session_baseline_valid` |
| 9 | `daily_loss_recomputed` |
| 10 | `trip_cause_classified` |
| 11 | `control_state_consistent` |
| 12 | `no_unresolved_integrity_condition` |

Terminal results per check ∈ {`PASS`, `FAIL`, `INCOMPLETE`}. A4 requires all twelve `PASS`, committed `PREFLIGHT_PASS`, state `RECOVERY_COOLDOWN`. Checks 8 and 9 must consume the Model A observation (§5); a non-authoritative basis cannot yield `PASS`.

## 7. A2 and A3 order-contract requirements (frozen structure)

Every **structural** contract field is assigned a frozen value here. Only the numeric **quantities** and buying-power figures depend on the runtime; they are **[WS5/WS6-BOUND]** and set in the Phase 0 budget (§9). "Default" is not used in this contract — each cell below is the frozen value.

| Field | A2 (verified reduction) | A3 (new risk) |
|-------|-------------------------|---------------|
| Symbol | `MSFT` (from protected leg) | `MSFT` (see §7.1 rationale) |
| Side | SELL | BUY |
| Risk direction | Risk-**reducing** only; no new exposure | New risk (would increase exposure) |
| Quantity | ≥ frozen **minimum qualifying reduction** (§7.3); ≤ remaining MSFT; exact share count **[WS5/WS6-BOUND]** | **≥ 1 share**; smallest size that still passes every non-loss-control gate; exact share count **[WS5/WS6-BOUND]** |
| Order type | `MARKET` | `MARKET` |
| Price rule | None (market order; exact `Decimal` fill price captured; no float intermediate) | None (market order) |
| TIF | `DAY` | `DAY` |
| Extended hours | `false` (regular session only) | `false` (regular session only) |
| `client_order_id` | Deterministic construction: `adr0043-canary-{freeze_id}-{start_a_id}-A2-{attempt}` (idempotent per attempt) | `adr0043-canary-{freeze_id}-{start_a_id}-A3-{attempt}` (idempotent per attempt) |
| Submission path | Full path: RiskEngine → OrderRouter → broker (this is a real risk-reducing order) | **RiskEngine evaluation only** — OrderRouter / broker adapter **must not be reached** |
| Submission timeout | Frozen bound; on timeout **never resubmit** — reconcile by `client_order_id` | N/A (no submission expected; see §7.2) |
| Permitted reconciliation attempts | ≤ frozen bound; deterministic identity only | N/A |
| Terminal interpretation | filled / partially-filled / canceled / rejected / unknown → reconcile per §10.1 | Local risk rejection = pass; any crossing of the broker-facing boundary (§7.2) ⇒ **RED** |
| Expected outcome | Risk **admitted** (`PERMIT_REDUCTION`); qualifying fill + reconciliation (§7.4) | **Rejected** with `ReasonCode.LOSS_CONTROL_STOP` only; no broker order; no reservation leak |

### 7.1 A3 symbol selection and authority proof (frozen)

**A3 symbol = `MSFT`, side BUY, MARKET, DAY, extended-hours false, quantity ≥ 1 share.** MSFT is selected deliberately: the protected leg is already MSFT, so reusing it introduces **no second security-eligibility dependency** — the account already holds and trades MSFT, so eligibility, tradability, and price availability are established. A BUY adds new long exposure, which is genuinely new risk under a `REDUCTION_ONLY_DAILY_LOSS` lock.

The frozen A3 order must be constructed so it would **otherwise pass** every non-loss-control gate: buying power, security eligibility, concentration, price availability, order sizing, market-hours, duplicate-order rules. The **only** admissible reason for rejection is loss-control authority — attributable specifically to `LOSS_CONTROL_STOP` (not PDT, not concentration, not buying-power, not any other gate). WS5 must **prove** the selected order passes those gates; WS5 does **not** choose the symbol or structure — those are frozen here.

### 7.2 A3 broker-acceptance definition (frozen — any of these ⇒ RED)

The A3 assertion passes only when the order is rejected by **local risk admission before broker submission**. It is **RED** if the order crosses the risk-admission boundary into the broker-facing submission path, evidenced by **any** of:

- a broker order ID assigned;
- broker acknowledgement;
- broker `accepted` or `pending_new` (or equivalent) status;
- any fill (partial or full).

A local `LOSS_CONTROL_STOP` rejection with no broker order ID, no acknowledgement, and no reservation leak is the expected **pass**.

### 7.3 Minimum qualifying reduction (frozen formula)

```
minimum_qualifying_reduction = max(1 share, floor(frozen_A2_order_qty × 0.50))
```

`frozen_A2_order_qty` is bound at WS6 within the Phase 0 budget; the **formula** is frozen here at WS4A. The resulting numeric value is recorded in the WS6 seal and is not discretionary.

### 7.4 A2 admission vs. execution (frozen)

A2 asserts that a verified risk-reducing order is **admitted** under the loss-control lock. A2 **passes** only when **both** hold:

1. **Admission proven** — the RiskEngine admits the reduction (`PERMIT_REDUCTION`, no `LOSS_CONTROL_STOP`) and it is routed to the OrderRouter; **and**
2. **Qualifying execution** — a fill ≥ `minimum_qualifying_reduction` (§7.3) with deterministic broker↔local reconciliation.

If admission is proven but a **broker-side condition unrelated to risk admission** (e.g. external cancel, venue halt) prevents a qualifying fill, A2 is **INCONCLUSIVE** (the execution leg is untestable), **not** RED. If admission itself fails — the system wrongly refuses a verified reduction — that is **RED**. Admission-plus-zero-fill therefore does **not** pass A2 on its own; a completed qualifying reduction is part of the assertion.

## 8. Post-A2 state (frozen)

| Item | Frozen rule |
|------|-------------|
| Expected remaining MSFT | original − A2 filled qty (reconciled); **[WS5/WS6-BOUND]** exact numbers |
| A4 permission | Recovery evaluated against the reduced remaining qty |
| Readiness compare | original vs post-A2 positions must reconcile deterministically |
| Full flatten | **Not** default; only the frozen risk-reducing qty is sold |

## 9. Phase 0 capacity rules (frozen; numeric budget bound later)

| Item | Frozen rule |
|------|-------------|
| Purpose | Generate a genuine daily-loss breach vs the Model A baseline within a bounded budget |
| Loss basis | `daily_pnl = current_equity − baseline_equity` (exact Decimals; §5) |
| Budget inputs | expected baseline; daily-loss threshold; max Phase 0 loss qty; MSFT reserved for A2; order/round-trip capacity for A2/A3/recovery; buying-power/concentration; reachability — all **[WS5/WS6-BOUND]** |
| Reachability failure | Breach unreachable while preserving A2+later capacity → `BREACH_UNREACHABLE` / **REFUSED** |
| Partial fill (Phase 0) | Reconcile cumulative loss and frozen capacity; **do not** resubmit blindly |
| Prohibition | Never convert "unknown P&L" into a fabricated measured breach |
| Contract schema pins | `PHASE0_CONTRACTS_SCHEMA_VERSION=2`, `PLAN_SCHEMA_VERSION=2`, `QUOTE_PROVENANCE_SCHEMA_VERSION=1`, `CHECKPOINT_SCHEMA_VERSION=1` |

## 10. Result classifications (frozen, predetermined)

| Disposition | Meaning |
|-------------|---------|
| **GREEN** | All A1–A5 pass; evidence complete; qualification passes |
| **RED** | Assertion conclusively false (A3 reaches broker / any A3 fill; A5 → `NORMAL`; control uses invalid/conflicting baseline) |
| **REFUSED** | Precondition / frozen identity / window fails before a valid assertion sequence begins |
| **INCONCLUSIVE** | Execution began but evidence integrity / broker / continuity prevents a valid determination |

Only **GREEN** proceeds to countersignature. No discretionary reclassification: disposition follows these rules mechanically.

### 10.1 A2 partial-fill / execution disposition (frozen — mechanical)

Evaluated in order; the first matching row determines the disposition. `minimum_qualifying_reduction` per §7.3.

| A2 outcome | Disposition |
|------------|-------------|
| Filled qty ≥ `minimum_qualifying_reduction`; no exposure increase; broker/local reconciles; evidence complete | **Continue — A2 satisfied**, evaluate remaining assertions |
| Filled qty > 0 but below `minimum_qualifying_reduction`; broker/local state reconciles | **INCONCLUSIVE** |
| Fill increases absolute exposure, crosses through zero, creates a short, or violates the frozen maximum | **RED** |
| Broker accepted a quantity greater than the frozen A2 order quantity | **RED** |
| Fill status cannot be deterministically reconciled | **INCONCLUSIVE** |
| Zero fill and order rejected/canceled before any broker execution | **A2 fails: RED** if the system wrongly refused a verified reduction; **INCONCLUSIVE** if an external broker condition (unrelated to risk admission) makes the assertion untestable |

### 10.2 A3 and Phase 0 partial-fill dispositions (frozen)

| Case | Disposition |
|------|-------------|
| A3 partial fill or **any** fill, or any crossing of the broker boundary (§7.2) | **RED** — new risk reached the broker |
| Phase 0 partial fill | Reconcile cumulative loss + frozen capacity; do not resubmit blindly |
| Unknown partial status (any surface) | **INCONCLUSIVE** after deterministic reconciliation is exhausted |

## 11. Evidence requirements (frozen schema)

Evidence bundle must include: Phase 0 package hash; baseline **raw** + **projection** hashes (raw bytes re-fetchable); 12-check **set identity** with per-check PASS evidence; residual telemetry (non-admitting); post-A2 MSFT qty; **A3 rejection reason code = `LOSS_CONTROL_STOP`**; baseline identity tuple `(account_id, session_date, design_version, freeze_id)`; Start A authorization identity + `authorization_body_sha256`; configuration + image identity **[WS5/WS6-BOUND]**. Qualifier verifies frozen **check names** and A3 `LOSS_CONTROL_STOP` **authority**, not row counts.

## 12. Stop and refusal conditions (frozen)

- **Baseline:** missed opening window; capital adjustment before first Phase 0 order; baseline unverifiable before assertions → **REFUSED**. Capital adjustment after Phase 0 begins → **INCONCLUSIVE**. Adjustment misclassified as trading P&L and used for control → **RED**. System continues on invalid/conflicting baseline → **RED**.
- **Broker ambiguity:** stop/classify on API timeout after submission; local-accept/unknown broker status; duplicate `client_order_id`; contradictory local/broker fields; partial fill; market closed; external cancel; API flapping. Posture: reconcile by deterministic identity; **never resubmit** because the first response timed out.
- **Continuity:** after the boundary opens (Start A onward), any image/config change, DB replace/migrate, credential rebind, limit mutation, scheduler change, broker rebind, or process restart voids the run (default refuse).
- **Non-GREEN aftermath:** preserve loss-control state, breaker, positions, DB; no auto-reset; no account reuse; separate remediation decision required.

## 13. Explicit non-authorizations

Approval of this manifest as a **contract** does **not** authorize any of the following. Each remains separately gated:

- runtime provisioning or the WS5 opening;
- migration execution on any canary runtime;
- WS6 freeze seal or countersignature;
- authoritative baseline capture;
- Start A / Phase 0 / Start B;
- A1–A5 live execution;
- broker order submission;
- canary-specific ENFORCE activation;
- global session-baseline flags (`session_baseline_shadow_enabled`, `session_baseline_enforcement_enabled` stay OFF);
- D-WIRE / broad production activation;
- converting the verification account into an ordinary strategy account.

A **GREEN** result does **not** authorize strategy conversion or global ENFORCE; WS4A approval does **not** authorize provisioning.

## 14. WS5/WS6 binding fields (must be resolved before seal — no placeholders permitted in the sealed copy)

`freeze_id`; `freeze_body_sha256`; configuration digest value; image digest + commit SHA of the canary runtime; Workbench account ID + user ID; effective risk-limit row values (daily-loss limit as applied); authorized session date; positions/orders/reservations reconciliation snapshot; Phase 0 numeric budget (expected baseline, threshold, max loss qty, reserved MSFT, capacity). WS4A leaves each **[WS5/WS6-BOUND]**; WS6 must populate every one with a verified value before the seal body hash is computed.

## 15. Owner review checklist (for WS4A ruling)

- [x] A3 symbol and full structural order contract frozen at WS4A (§7, §7.1) — no "default", only quantities are **[WS5/WS6-BOUND]**.
- [x] All order-contract "defaults" replaced with frozen values (§7).
- [x] A2 partial-fill / execution disposition mechanical and exhaustive (§10.1); minimum-qualifying-reduction formula frozen (§7.3).
- [x] A2 admission-vs-execution frozen — a qualifying fill is part of the assertion (§7.4).
- [x] A3 broker-acceptance defined; any boundary crossing ⇒ RED (§7.2).
- [x] No placeholders in **stable** contract fields (§1–§12); every runtime fact is explicitly **[WS5/WS6-BOUND]**.
- [x] No discretionary result classification (§10 mechanical).
- [x] A3 rejection attributable specifically to `LOSS_CONTROL_STOP` (§7.1).
- [x] GREEN does not authorize strategy conversion or global ENFORCE (§13).
- [x] WS4A approval does not authorize provisioning (§13).

## 16. Document control

| Rev | Date | Change |
|-----|------|--------|
| draft-1 | 2026-08-02 | Initial WS4A contract freeze returned for owner ruling |
| draft-2 | 2026-08-02 | Owner ruling **REVISE** folded: **Blocker A** — A3 order contract fully frozen (symbol `MSFT`, BUY, MARKET, DAY, ext-hours false, qty ≥ 1 share, RiskEngine-evaluation-only, `LOSS_CONTROL_STOP`-only); **Blocker B** — A2 partial-fill disposition made mechanical (§10.1) + minimum-qualifying-reduction formula frozen (§7.3); non-blocking A (all "defaults" replaced with frozen values), B (A3 broker-acceptance defined, §7.2), C (A2 admission-vs-execution frozen, §7.4). Returned for final approval. |

## 17. Owner decision block

| Decision | Value |
|----------|-------|
| Approve WS4A contract freeze (revised draft-2)? | **PENDING** |
| Countersignature | |
| Date | |

*End of ADR0043-CANARY-MANIFEST-v1.2 (REVISED DRAFT — pending owner approval).*
