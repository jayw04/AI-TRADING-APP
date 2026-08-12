# ADR0043 Canary — F0 / F1 / F4 / Q1 / Q2 Code Inventory

| Field | Value |
|-------|-------|
| Document ID | ADR0043-CANARY-CODE-INVENTORY-001 |
| Status | **APPROVED** as Workstream 3 package scope |
| Version | v0.2.1 (implementation acceptance criteria folded) |
| Date | 2026-07-31 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 **v1.0** |
| Baseline design | ADR0043-CANARY-BASELINE-DESIGN-001 **v0.2.1 (Model A) APPROVED** |
| Package scope | Canary-scoped PR only |
| Global flags | Remain **OFF** |
| Execution / WS4A–WS5 prep | **NOT AUTHORIZED** by this approval — code package only |

## 1. Purpose

Exact Workstream 3 scope: F0 → F1 → F4 → Q1 → Q2 → canary-only telemetry, bound to Model A.

## 2. Scope boundary

| In scope | Out of scope |
|----------|--------------|
| F0/F1/F4/Q1/Q2 + canary telemetry | Legacy F2/F3/F5-class hardenings |
| Model A opening-window capture | Model B substitution; WS5/WS6 capture |
| Behavioral equivalence when canary config off | Global ENFORCE / D-WIRE / runtime provisioning |

## 3. Exact account / freeze binding

Canary mode requires: broker `PA34USW0Q8UO`; actual Workbench account ID; freeze ID + body hash; baseline design version; sealed configuration digest; image/commit identity. Unbound or mismatched → **refuse**.

## 4. Q1 ruling

| Basis | Control |
|-------|---------|
| Model A session-open `equity` | Authorized |
| `LEGACY_LAST_EQUITY` | Telemetry only |
| Cumulative fallback | Not authorized |
| Missing/stale/out-of-window/unverifiable | Fail closed / REFUSED |

## 5. Shared observation + central policy mapper

### 5.1 Observation fields

`status` (`AVAILABLE`\|`UNAVAILABLE`\|`STALE`\|`CONFLICT`\|`INVALID`); `basis_source`; `baseline_id`; `raw_response_hash`; `projection_hash`; `session_date`; `baseline_equity` (exact Decimal); `baseline_equity_canonical_4dp` (serialization); `current_equity`; `daily_pnl` (from exact decimals when AVAILABLE); `reason_code`; canary freeze/config identity.

### 5.2 Status → surface policy (single mapper)

| Observation status | Phase 0 | New risk | Verified reduction | Recovery |
|--------------------|---------|----------|--------------------|----------|
| AVAILABLE | Evaluate | Evaluate | Permit if reducing | Evaluate |
| UNAVAILABLE | Refuse | Reject | Permit reduction | Fail/incomplete |
| STALE | Refuse | Reject | Permit reduction | Fail/incomplete |
| CONFLICT | Refuse | Reject | Permit only under frozen ADR-0042 safety rule | Fail |
| INVALID | Refuse | Reject | Permit only if independently proven reducing | Fail |

Reduction treatment for CONFLICT/INVALID must preserve ADR-0042’s risk-reducing escape **without** pretending the daily-loss basis is valid.

## 6. Deferred items (approved scope)

### F0 — Authoritative capture/persistence (Model A)

Start A-only entry validating a **durable authorization binding** (not a lone env Boolean): Start A ruling ID; sealed freeze ID + body hash; broker account ID; Workbench account ID; configuration digest; image/commit identity; authorized session date; opening window; authorization status.

Also: Alpaca `equity` extraction; window gate `[09:30, 09:35)` ET; raw retention + dual hashes; unique `(account_id, session_date, design_version, freeze_id)`; schema carries design_version, freeze_id, Start A ID, config digest, image digest, broker account ID; idempotent retry / conflict refuse; atomic persist (object-store sequence per baseline §6.1); audit event; retrieval by ID; shared validation; crash tests; WS5 dry-run without authoritative persist.

**Shadow semantics:** do **not** upgrade existing `risk_session_baselines` shadow rows into Model A authority. Authoritative rows originate only via Start A path. Legacy/shadow rows remain explicitly non-authoritative for Model A.

**Migration safety:** no fabricated hashes/identities on historical rows; leave legacy rows non-authoritative; add constraints without silently converting shadow rows; upgrade + downgrade tests; prove production behavior unchanged when canary config off.

### F1 — Consumers (breaker, engine, lock provenance)

Shared observation only; no silent cumulative; surface fail-closed via §5.2; structured provenance. Lock-state: do not modify pure `state_machine.py` unless required; `service.py` may attach baseline provenance on daily-loss-origin trips under canary only; legacy F3 out of scope.

### F4 — Recovery/preflight

Align with Q1; 12-check **set identity**; no vacuous PASS.

### Q1 / Q2 / Telemetry

As previously approved.

## 7. Implementation order (authorized now)

1. Schema + F0 producer  
2. Canonicalization + atomic persistence  
3. Shared observation contract + policy mapper  
4. F1 breaker/engine/lock provenance  
5. F4 recovery/preflight  
6. Q2 recovery expectation tests  
7. Residual telemetry  
8. Focused Tier-3 tests → full backend / coverage / invariants  
9. One coherent review-ready PR  

Return for review after the complete code PR + local Tier-3 evidence. **Do not** begin WS4A/WS5 execution preparation merely because coding has started.

## 8. Still not authorized

Execution-runtime provisioning; WS5 opening; authoritative capture; Start A; Phase 0; Start B; A1–A5; broker submission; canary ENFORCE activation; global config changes; D-WIRE.

## 9. Owner decision block

| Decision | Value |
|----------|-------|
| Inventory as WS3 scope | **APPROVED** |
| Implementation acceptance criteria A–E | **Accepted** |
| Date | 2026-07-31 |

*End of ADR0043-CANARY-CODE-INVENTORY-001 v0.2.1.*
