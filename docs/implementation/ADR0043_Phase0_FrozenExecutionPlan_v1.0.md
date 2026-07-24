# ADR‑0043 Phase‑0 — Frozen Execution Plan v1.0 (prep complete; broker submission HELD)

> ## ⛔ 2026‑07‑24 — two of this plan's controls are currently DISARMED
>
> `docs/incidents/ADR0043_Harness_AccountState_Missing_Defaults_To_Zero_20260724.md`: the harness
> reads its authoritative loss from `accounts_state.day_change` for account 3, a row that does not
> exist on the validation host, and substitutes zero for the missing row. As a result **§5's loss
> objective / terminal range and §10's hard overshoot floor cannot fire as written.** The frozen
> values below remain the governing intent; the *measurement* behind them must be corrected (to
> `current equity − immutable current-session session-baseline equity`, with named refusals for
> missing/mismatched/contradictory state) in a dedicated reviewed PR before any Phase‑0 session.
>
> Independently, the operator tooling that produces the readiness package is not yet version
> controlled, so no authoritative baseline may be captured. See the runbook's status banner.

> **Status:** non‑session‑bound preparation COMPLETE and frozen. Session baseline capture, the
> read‑only preflight, the **binding** in‑session quote re‑derivation, and the loss‑generating breach
> are **HELD** for a single future market session under separate authorization. **No broker orders have
> been or will be submitted under this document.**
>
> Governing contract: `docs/implementation/ADR0043_Canary_Manifest_v1.0.md` (body = v1.1, MSFT‑only).
> Procedure: `docs/runbook/ADR0043_Live_Canary_Runbook.md` (v1.0). Same‑session execution steps:
> `docs/runbook/ADR0043_Phase0_SameSession_Runbook_v1.0.md`. Deployed artifact `f98d082`
> (impl baseline `c8b3ac2` ancestry verified). Runtime: EC2 `adr0043-canary` / `3.80.11.61`
> (⚠ **not** the `ssh workbench` alias — that is the production paper stack `ec2-paper`).

## 1. Approved limits row + audit identity (FROZEN)

| Field | Value |
|---|---|
| Row | `risk_limits` id **3** · `GLOBAL` / `user_id=3` / `broker_mode=paper` · `scope_id=null` |
| max_daily_loss | **3000.00** |
| max_position_qty | 1000 |
| max_position_notional | 30000.00 |
| max_gross_exposure | 100000.00 |
| max_orders_per_minute | 30 |
| max_orders_per_day | 100 |
| allow_short | false |
| allowed_symbols | `["MSFT","IEUS","KOKU"]` |
| denied_symbols | `[]` |
| Audit event | `audit_log` id **153** · `RISK_LIMITS_UPDATED` · target `risk_limits/3` · user 3 |
| Install method | governed service‑path reproduction of `PUT /risk-limits` (row + audit event); NOT ad‑hoc SQL |

**`limits_before_sha256 = da6659334909a68a2e800d429ff36e7c7de1d18f169082836c07de2973ef706f`**
Must remain EQUAL through countersignature. Any change (including raising) invalidates continuity →
new plan + baseline.

## 2. Account‑3 reconciliation proof (broker → DB, FROZEN)

- Broker identity: **`PA34USW0Q8UO`** (canary; ≠ momentum `PA3QRX9KSPXA`), paper, ACTIVE, credential prefix `PKZYTY`.
- Local ledger after sanctioned `position_sync` (account‑3 scoped): **MSFT 19 LONG** (mv $7,270.54), **no other position**.
- **0** non‑terminal orders · **0** HELD reservations.
- `run_reconciliation` = **pass**, 0 discrepancies (`reconciliation_runs` id **1**).

## 3. Runtime configuration (FROZEN — set explicitly for the run, not defaulted)

```
ADR0043_USER=3
ADR0043_ACCOUNT=3
ADR0043_PROTECTED=MSFT
ADR0043_LEGS=MSFT:19
ADR0043_CHURN=IEUS,KOKU
WORKBENCH_LOSS_CONTROL_MODE=ENFORCE   (ambient on the box; the run also injects it)
```

## 4. Frozen driver caps (tighter than the risk‑limit row; NOT relaxable)

| Cap | Value |
|---|---|
| max order (setup) notional | $25,000 |
| max round trips | 12 |
| max churn legs | 24 |
| target overshoot | $250 |
| hard max overshoot | $750 |
| quote‑age freshness ceiling | 10 s |
| settlement timeout / leg | 45 s (SETTLEMENT_TIMEOUT_S) |

## 5. Loss objective (FROZEN)

- Loss target: **−$3,000** (= effective `max_daily_loss`).
- Target terminal range: **−$3,000 to −$3,250**.
- Hard overshoot floor: **−$3,750** (driver CHURN_OVERSHOT stop if `day_change < −(3000+750)`).

## 6. Reachability calculation — PRELIMINARY (stale after‑hours quotes)

Captured after‑hours (markets closed); **NOT binding** — the binding sizing is re‑derived in‑session
with fresh (≤10 s) quotes at step 8.

| Symbol | bid | ask | spread | sized shares (⌊25000/ask⌋, ≤1000) | conservative loss/RT (spread×shares) | quote age |
|---|---|---|---|---|---|---|
| KOKU | 128.09 | 131.03 | 2.94 | 190 | **$558.60** | ~12 h (STALE) |
| IEUS | 66.87 | — (no ask) | — | — | unusable after‑hours | ~5.8 h (STALE) |

- Current `day_change` (prior session close): −$145.92 → remaining to target ≈ **$2,854.08**.
- Best conservative loss/RT = **$558.60** (KOKU) → **round trips needed ≈ 6** (≤ 12 cap).
- Max reachable in 12 RT ≈ **$6,703.20**.
- **PRELIMINARY verdict: REACHABLE.**

> ⚠ **This verdict depends on KOKU's abnormally wide after‑hours spread ($2.94 ≈ 2.2%).** In RTH the
> spread will tighten and per‑RT loss will fall; if the fresh in‑session spread makes ≤12 RT unable to
> cross $3,000, the in‑session result is **BREACH_UNREACHABLE** — preserved as‑is, **never** worked
> around by widening caps, adding symbols, or lowering the target.

## 7. Selected churn symbol ordering

**KOKU first** (widest spread → highest deterministic loss/RT), **IEUS second**. Re‑ranked in‑session
by fresh spread×shares. Both are disjoint from the protected leg (`MSFT`), enforced in code (`NEVER_CHURN`).

## 8. Worst‑case order accounting

- Worst‑case order count: **24 legs** (12 round trips × BUY+SELL), plus A2/A3 (2) + recovery + reconciliation calls — all within `max_orders_per_minute=30` / `max_orders_per_day=100`.
- Per‑order notional ceiling: **$25,000** (KOKU 190 sh ≈ $24,896 at the stale ask — within ceiling; re‑sized in‑session).

## 9. Retry / settlement / checkpoint behavior

- Alpaca identity/account/quote reads: **bounded retry on 5xx** (`50010000` flaps observed), ~5–6 attempts with backoff, then fail‑closed.
- Per‑leg settlement barrier: **45 s** to broker‑terminal; a leg that does not settle → stop (no advance on an unsettled position).
- Checkpoints (single‑instance lock + idempotent `client_order_id`): churn `/app/data/adr0043_churn_state.json`; canary `/app/data/adr0043_canary_state.json`; lock `/app/data/adr0043_canary.lock`. Run id generated + persisted by the harness (operator evidence run id captured separately).

## 10. Stop / rollback conditions (any → STOP, preserve evidence, do not engineer around)

- Adapter resolves `PA3QRX9KSPXA` (momentum) or any account ≠ `PA34USW0Q8UO`.
- Non‑paper environment; account not ACTIVE; credential prefix ≠ `PKZYTY`.
- `limits_before_sha256` ≠ current limits SHA (limits changed).
- Protected leg MSFT moved from 19; any unrelated position appears; open order or HELD reservation before a leg.
- Loss‑control state ≠ NORMAL at preflight (already locked); wrong trip class (breaker/rate/velocity trips first → `REDUCTION_ONLY_BREAKER` is unsuitable → STOP, not reclassified).
- `day_change < −$3,750` (hard overshoot) → CHURN_OVERSHOT stop.
- Stale/absent/crossed/untrusted quote (>10 s) → refuse to size.
- In‑session reachability < $3,000 within 12 RT → **BREACH_UNREACHABLE** (preserved).

## 11. Same‑session sequence (HELD — separate authorization required)

1. Confirm market session eligible. 2. Reconfirm broker `PA34USW0Q8UO`. 3. Confirm MSFT:19, no unrelated positions. 4. Confirm open orders = 0, HELD reservations = 0. 5. Confirm limits SHA unchanged (`da665933…`). 6. Capture authoritative current‑session baseline. 7. Read‑only Phase‑0 preflight. 8. Freeze the fresh quote‑derived sizing plan (re‑run reachability; may be BREACH_UNREACHABLE). 9. Return final package for broker‑submission authorization. 10. **Submit no orders until explicit authorization.**

Continuity invariant: same instance / image / config / database / credentials / baseline from baseline
capture through the formal canary.
