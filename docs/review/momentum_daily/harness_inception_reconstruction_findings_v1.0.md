# momentum-daily — Stage 2-4 Harness Inception Reconstruction (Findings v1.0)
**Purpose:** resolve the cold-start repair classification (Case A/B/C) by reconstructing how the
Stage 2-4 VALIDATION backtests established the initial portfolio.
**Date:** 2026-07-20. **Base:** worktree `fix/momentum-daily-cold-start-seed` @ `4172530` (== origin/main, incl. PR #435). Read-only.
**Status:** RATIFIED by owner 2026-07-20 — classification accepted; conformance-directional repair (adopt day-1 inception; do NOT preserve the live delay). The drift-audit (plan §8) must prove live/validation decision-equivalence through `_evaluate`.

## Verdict
**Case C (structural) → Case A (behavioral). Definitively NOT Case B.**
- **Structural (C):** the harness never instantiates the live `MomentumDaily` class and never calls `_evaluate` / `on_bar` / `_fired_triggers` / `_backstop_due`. It reimplements the selection core as standalone functions and drives its own simulator.
- **Behavioral (A):** that simulator's trade trigger includes `changed = set(target) != held`; on a flat book this is `True` on the first scorable day, so **the validated book deployed at inception (day 1)**. It does NOT reproduce the live template's ~10-session flat-book gap.

## Evidence

### 1. Separate constructor, not the live class (→ Case C)
- Harness does not import/instantiate `MomentumDaily`. Selection re-derived in plain functions:
  - `compute_day()` — `apps/backend/scripts/backtest_momentum_stage2.py:74-85` — calls `momentum_scores(...)` + the raw>0 AND z>=0 filter (mirror of template `_eligible`, `momentum_daily.py:366-376`).
  - `conditional_select()` — `stage2.py:92-128`; `select_n()` — `stage3.py:57-105` — explicit re-implementations of `_select_targets` (`momentum_daily.py:378-407`). Docstrings say so: *"Replicate momentum_daily._select_targets"* (`stage2.py:94`); *"momentum_daily §5.1 selection generalized to an N-name book"* (`stage3.py:58`).
- Template confirms duplication is deliberate and drift-prone: *"the selection logic is reproduced here rather than imported… The two must not drift"* (`momentum_daily.py:12-16`).
- The shared `run_momentum_backtest` engine (`app/factor_data/backtest.py:519`) is a different weekly-quintile engine the Stage 2-4 scripts do NOT call; it too is `score_fn`-seam based and instantiates no `Strategy`.

### 2. First portfolio seeded on the first scorable day (→ Case A behavior)
- Simulator opens empty: `held: set[str] = set()` (`stage2.py:178`, `stage3.py:171`, `stage4.py:164`).
- Variant-C decision (`stage2.py:282-290`, identical `stage3.py:201-209`, `stage4.py:199-208`):
  ```
  target  = conditional_select(ds, held, prev_rank)  # held=∅ → fills to top-5 → non-empty
  changed = set(target) != held                      # {top5} != ∅ → True
  backstop = since >= BACKSTOP_DAYS
  return (changed or drift or backstop), target       # TRADES on day 1
  ```
- `changed` ("did the selection SET change?") is **not** one of the six §5.1 triggers (prereg enumerates exactly six: `PREREG_Stage2 §54-63`). It is a harness-only OR-term that performs inception.
- **Contrast (why NOT Case B):** live `_evaluate` gates trading on `_fired_triggers` + `_backstop_due` (`momentum_daily.py:283-288`). On a flat book all six no-op (every trigger loops `for h in held:` over ∅; displacement needs `len(held) >= max_names` `:319`; `_weight_drift_exceeded` returns False when `not held` `:336`) → `_fired_triggers` = ∅; `_backstop_due` returns False on the first review (`:353-354`), deploying only after `backstop_max_days*7//5` = 14 cal days ≈ 10 trading days (`:362`). The harness has no such gap.

### 3. No lookback-induced delay
- Result JSONs carry only aggregate metrics (no per-trade dates): `VariantResult`/`ConfigResult` have no date fields (`stage2.py:144-159`).
- Window block is decisive: `window.start="2005-01-03"`, `trading_days=5395`, **`usable_score_days=5395`** (`MR_MomentumDaily_Stage2/3_full.json`). Every in-window day has a valid score incl. day 1 → the 273-day (252/21) 12-1 lookback is served by pre-window store history (`_CachedPriceStore` loads floor..ceil). ⇒ **first trade = 2005-01-03 (window start)**, no delay.

### 4. Docs state no inception convention
- No prereg/report states an inception/seeding rule. `PREREG_Stage2 §32` mentions a *data* warm-up ("≥273 trading-day warm-up before the first rebalance") — history to compute 12-1, not a flat-book wait. §54-67 lists the six triggers; the day-1 `changed` seed is an **undocumented emergent property of the harness code**, not a stated convention, and corresponds to none of the six live triggers.

## Implications for the repair
1. The ~10-session live cold-start delay is a **divergence from validated behavior**, never a validated/intentional property. ⇒ the earlier "preserve delay vs adopt day-1" question is **resolved: day-1 inception is what was validated.**
2. `initial_seed` (seed at first eligible review) **restores conformance to the validated inception** — it is the correct, conformance-directional fix.
3. ⚠ **But validation ran a reimplementation, not the live class.** The template's own "must not drift" warning + the proven cold-start drift mean the equivalence work (§8 of the plan) must **bound the drift surface**: prove the live `_eligible`/`_select_targets` are decision-equivalent to the harness `compute_day`/`conditional_select`/`select_n`, ideally by driving the ACTUAL live `MomentumDaily` (with `initial_seed`) through the historical window — not merely re-running the harness.
4. **Governance follow-up (candidate for ADR 0044 or a note):** validating governed strategies via a *reimplementation* rather than the live class is the root cause that let this defect ship. Recommend either (a) a validation harness that drives the real strategy class, or (b) a CI drift-check asserting the harness replica == the template selection core.

### Key file:line references
- Reimplemented selection: `scripts/backtest_momentum_stage2.py:74-128`; `stage3.py:57-105`; `stage4.py:199-208`
- Day-1 seed via `changed`: `stage2.py:282-290`, `stage3.py:201-209`, `stage4.py:199-208`; empty-book init `stage2.py:178`
- Live cold-start gap: `strategies_user/templates/momentum_daily.py:283-293` (gate), `295-327` (`_fired_triggers` no-op on ∅), `351-362` (`_backstop_due`)
- Unused shared engine (seam-based): `app/factor_data/backtest.py:519-655`
- Window evidence: `docs/implementation/evidence/momentum_daily_stage2_4/MR_MomentumDaily_Stage2_full.json`
- Warm-up (data, not flat-book): `PREREG_Stage2_RebalancePolicy_v1.0.md:32`; six triggers `:54-67`
