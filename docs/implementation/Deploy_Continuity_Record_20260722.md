# Deploy Continuity Record — reviewed superset → ec2-paper — 2026-07-22

**Purpose.** Governed continuity record for deploying the reviewed superset to the live paper box
`ec2-paper`. This is a **reviewed superset**, explicitly **NOT application-identical** to the prior
canary baseline `80a6c043`; it therefore carries a fresh tree SHA, a fresh artifact digest, this
continuity record, and a recorded session baseline (below).

**Boundary.** This deploy ships reviewed code + one Alembic column, then relabels one operational
hold. It does **NOT** clear any hold, start any cooldown, activate any strategy, or seed any book.

---

## 1. Deploy identity

| item | value |
|---|---|
| deployed_repository_commit | `b0058bf335628f8dbde09a93915314f3a1f7743b` |
| archive_sha256 | `d12323f5cad0cafae2b28acd18212d783c605a25c55ba967fbd59dae36f8a49c` |
| adr0043_implementation_commit | `ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c` (#463 settlement barrier — governs the ADR-0043 paths) |
| adr0043_original_baseline | `c8b3ac24…` (historical PR8, recorded only) |
| governed ADR-0043 paths match baseline | **true** (byte-identical) |
| reviewed superset delta (non-ADR-0043) | `backtest_context.py`, `test_context_pending_buy_parity.py`, `test_adr_0002_invariant.py` |
| build script | `deploy/aws/build-deploy-archive.sh` at `e817a83` (path-scoped model, #468) |

## 2. Reviewed superset contents

| PR | merge | what |
|---|---|---|
| #462 | `f573922` | §8 drift-audit infrastructure + completed 21-year census |
| #465 | `6be564e` | ADR-0042 capacity-overlap fix + proof-bounded absorption (migration `a4c7e1b93d20`) |
| #466 | `d2200b3` | backtest-context P2 coverage restored |
| #461 | `d03af06` | weighting-defect correction + durable blocker + hold-reason mechanism |
| #463 | `ea6db6e` | ADR-0043 per-order settlement barrier + CI invariant |
| #467 | `b0058bf` | BacktestContext `pending_buy_qty` parity + contract test |

**NOT application-identical to `80a6c043`** (the prior canary baseline). Recorded as a reviewed
superset per owner ruling.

## 3. Pre-deploy verification

| gate | result |
|---|---|
| exact-main FULL CI on `b0058bf` | ✅ success — run `29964633608` |
| provenance-script change #468 FULL CI | ✅ success — run `29966683690` |
| live Alembic read-only preflight (ec2-paper) | ✅ current `e7b3f2a9c4d1` → target `a4c7e1b93d20`, one `ADD COLUMN position_qty_at_reservation`, single head, no drift, in-graph |
| governed-artifact build | ✅ exit 0, governed paths match, delta classified `reviewed_non_adr0043_superset` |

## 4. Session baseline (recorded)

| item | value |
|---|---|
| account | 4 — "Alpaca Paper (Growth)" |
| strategy 11 (momentum-daily) | status `idle` (PAUSED, dispatch removed), 200-symbol universe |
| operational_hold | `AWAITING_COLD_START_FIX`, **ACTIVE**, rev **1**, effective_at `2026-07-20T22:48:22Z` |
| **retired baseline** | **`84466.41` and the prior realized loss are RETIRED — MUST NOT be reused.** |
| fresh authoritative baseline | Account 4 does **not** activate in this deploy; no live session baseline is established or reset here. A fresh authoritative session baseline is established at activation time, only after the independent equal-weight validation succeeds and is adjudicated — never from the retired `84466.41`. |

## 5. Authorized hold transition (this deploy)

Exactly one, after the artifact deploys and its digest is verified:

```
strategy 11:  AWAITING_COLD_START_FIX  →  AWAITING_PRODUCTION_SIZING_VALIDATION
expected_rev = 1 · expected_reason_code = AWAITING_COLD_START_FIX
effective_at 2026-07-20T22:48:22Z PRESERVED · _rev → 2 · hold continuously ACTIVE · no cooldown
```

## 6. NOT authorized by this deploy

Hold clearing · cooldown start · Account 4 activation · manual seed · reuse of the `84466.41`
baseline. Activation remains gated on a new preregistered equal-weight validation program and a
favorable adjudication.

## 7. Rollback

Pre-deploy online DB backup taken first (recorded at deploy time); the box's own per-deploy backup
pattern (`workbench.pre-*-deploy-*.sqlite`) is retained. Rollback = restore the pre-deploy DB
snapshot + redeploy the prior image. The migration is a single additive nullable `ADD COLUMN`
(reversible by the migration's own `downgrade`).
