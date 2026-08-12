# ADR0043-CANARY-BASELINE-DESIGN-001

| Field | Value |
|-------|-------|
| Document ID | ADR0043-CANARY-BASELINE-DESIGN-001 |
| Status | **APPROVED** |
| Version | v0.2.1 (Model A + freeze-time clarifications) |
| Date | 2026-07-31 |
| Governing plan | ADR0043-LIVE-CANARY-IMPL-PLAN-001 **v1.0** |
| Companion | ADR0043-LIVE-CANARY-REVALIDATION-001 (**APPROVED**) |
| Owner ruling | **Model A** — true regular-session opening broker-equity baseline. Model B is **not** authorized as a substitution within this canary program. |
| Scope | Canary freeze-bound ENFORCE semantics only — **not** global production policy |
| Authoritative capture | **HOLD** until Start A after WS6 seal, inside the frozen opening window |
| WS4A/WS6 | Must bind the clarifications in §3.1, §5, §6, §8, §9 |

## 1. Purpose

Define the authoritative **session-daily-loss** baseline for the governed canary so that a `REDUCTION_ONLY_DAILY_LOSS` trip validates ADR-0043’s real daily-loss behavior — not merely state-machine plumbing from an arbitrary run-start equity.

## 2. Owner ruling — Model A only

**Authoritative baseline:** the first successfully persisted Alpaca **`equity`** response for **PA34USW0Q8UO** captured during the approved regular-session **opening window**, before any canary-generated order.

| Model | Status in this program |
|-------|------------------------|
| **A — true session baseline** | **Required** |
| **B — canary-run-start equity** | **Not authorized** here. If Model A is operationally impractical, refuse/close the attempt and open a separately named diagnostic program with the narrower claim made explicit. |

Missing the frozen opening window → **REFUSED**. Do **not** substitute a later run-start baseline.

## 3. Opening-window contract (frozen)

| Parameter | Frozen value |
|-----------|--------------|
| Session timezone | `America/New_York` |
| Session boundary | US equity **regular** session |
| Target opening time | **09:30:00** a.m. ET |
| Permitted capture window | **[09:30:00, 09:35:00)** a.m. ET |
| Start A timing | Must be **effective before or within** that window |
| First canary / Phase 0 order | Only **after** the baseline persistence transaction **commits** |
| Missed window | **REFUSED**; do not substitute a later baseline |
| Pre-market movement | Included in broker `equity` as of capture |
| Authoritative field | Alpaca account **`equity`** |
| `last_equity` | **Telemetry only** |
| Cumulative fallback | **Prohibited** |

### 3.1 Timestamp authority

| Timestamp | Role |
|-----------|------|
| Broker/source response timestamp | Preferred when present |
| Local receipt timestamp | Always recorded; **controls opening-window admissibility** (ET) |
| Persistence timestamp | Always recorded (commit time) |

If broker response timestamp is present and disagrees with local receipt on window membership → **REFUSED** (v1: zero skew tolerance).

## 4. Operational consequence — schedule-sensitive run

Before Start A: WS6 sealed; runtime ready; connectivity verified; image/config pinned; limits frozen; account reconciled; no open orders; capture tooling dry-run without authoritative persist; operator available pre-open. Fail readiness → **refuse**; do not slide the window later.

## 5. Canonical equity representation

| Rule | Frozen value |
|------|--------------|
| Currency | USD |
| Broker string | Retained in raw payload |
| Parse | Exact `Decimal`; no float intermediate |
| **Control calculation** | Use the **exact parsed Decimal** for daily-P&L vs threshold |
| **Canonical serialization** | Quantize to **4 decimal places**, `ROUND_HALF_EVEN`, for projection JSON / projection hash only |
| Monetary threshold comparison | Separately frozen monetary precision rule (default: compare using exact parsed daily P&L against limit Decimal; do not round P&L before compare unless freeze proves 4-dp cannot change admission) |
| Canonical JSON | UTF-8; sorted keys; no insignificant whitespace; numbers as decimal strings; no null required fields; reject `-0`, scientific notation, trailing junk |
| Qualifier | Verifies **both** exact source value and canonical serialized value |

## 6. Hash semantics and payload retention

1. Persist raw broker response (DB blob **or** content-addressed immutable object) + SHA-256(raw).
2. Canonical control projection + SHA-256(canonical JSON bytes).
3. Qualifier must re-fetch raw content; hash-only without retrievable bytes is insufficient.

### 6.1 External object-store atomicity

If raw bytes live outside the DB:

1. write raw bytes to content-addressed immutable object;
2. verify digest;
3. commit DB row + projection + reference **atomically**;
4. unreferenced objects after crash = harmless cleanup residue;
5. **never** permit an authoritative DB row without a verified retrievable object.

Governing requirement: **no authoritative partial baseline** (not necessarily zero orphan objects).

## 7. Required baseline fields

broker account ID (`PA34USW0Q8UO`); Workbench user + account IDs; session date; broker/source response timestamp (if any); local receipt timestamp; persistence timestamp; equity raw string + exact Decimal; baseline source `SESSION_OPEN_BROKER_EQUITY`; raw + projection hashes; raw retention ref; capture mechanism/version; immutable baseline ID; daily-loss limit; **design_version**; **freeze_id**; **Start A ID**; configuration digest; image digest; configuration + image identity.

## 8. Atomic persistence transaction

Commit atomically (or fail with no authoritative claim):

1. raw response (or verified object reference)
2. canonical projection
3. both hashes
4. unique identity claim
5. return baseline ID

Partial write → no ACTIVE baseline; Start A **REFUSED**.

## 9. Immutability and uniqueness

**Unique identity:** `(account_id, session_date, design_version, freeze_id)` (or equivalent immutable execution-contract identity).

| Retry case | Outcome |
|------------|---------|
| Same account/session/design/freeze **and** identical hashes | Return existing baseline |
| Mismatch in freeze, payload, projection, configuration, image, or account identity | **Conflict → refuse** |

No in-place update. All control paths receive the same baseline ID and both hashes.

## 10. Residual telemetry (measurement only)

Authoritative session-open equity vs legacy `last_equity` vs P&L under each basis — non-admitting. Global session-baseline flags remain **off**.

## 11. Predetermined disposition rules

| Condition | Disposition |
|-----------|-------------|
| Baseline not persisted within opening window | **REFUSED** |
| Capital adjustment before first Phase 0 order | **REFUSED** |
| Capital adjustment after Phase 0 execution begins | **INCONCLUSIVE** |
| Adjustment misclassified as trading P&L and used for control | **RED** |
| Baseline unverifiable before assertion execution | **REFUSED** |
| Integrity fails after execution begins; no false behavior proven | **INCONCLUSIVE** |
| System continues using invalid/conflicting baseline | **RED** |

| Context | Response |
|---------|----------|
| Before Phase 0 loss generation | **REFUSED**; no orders |
| New-risk admission under lock | **Reject** |
| Verified reduction under lock | **Permit** |
| Recovery preflight without trusted basis | **FAIL** / **INCOMPLETE** |
| Outside canary | Not governed here |

## 12. Who may capture

WS5/WS6: **no** authoritative capture. Start A only, inside opening window, after durable Start A authorization binding (not a lone env Boolean).

## 13. Required tests

Inside-window success; outside-window refuse; no later substitution; exact vs serialized precision; dual hash + retention; object-store sequence if used; atomicity/crash; retry/conflict with freeze_id; dispositions §11; telemetry non-admitting; canary config off → behavioral equivalence.

## 14. Exit criterion

**Met for design approval.** Clarifications above bind into WS4A/WS6 and the code package. Implementation proceeds under CODE-INVENTORY-001; execution remains HOLD.

## 15. Owner decision block

| Decision | Value |
|----------|-------|
| Model A (09:30–09:35 ET) | **APPROVED** |
| Model B substitution | **NOT AUTHORIZED** |
| Freeze-time clarifications A–C | **Accepted** — bind in WS4A/WS6 + code |
| Date | 2026-07-31 |

*End of ADR0043-CANARY-BASELINE-DESIGN-001 v0.2.1.*
