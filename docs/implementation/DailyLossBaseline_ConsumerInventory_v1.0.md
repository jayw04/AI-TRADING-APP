# Daily-Loss Baseline — Consumer Inventory (Phase-0 shipping gate)

**Frozen against:** `origin/main` @ `71d346d` (2026-07-30)
**Purpose:** conformance artifact proving every risk-decision consumer of the daily-loss
baseline uses ADR 0043 correctly. Not a discovery exercise for new architecture —
ADR 0043 already supplies the framework. **Governing rule: extend ADR 0043; do not duplicate it.**

**Scope of the search.** Every production read (`apps/backend/app/**`, excluding
`app/db/models/**` and `tests/**`) of: `last_equity`, `day_change`, `day_change_pct`,
`day_change_basis`, `select_daily_loss_basis`, `allow_cumulative_fallback`,
`PRIOR_SESSION_CLOSE_PROXY`, `UNAVAILABLE`, `BROKER_LAST_EQUITY`, `UNMEASURED`.

**Production flag state at freeze** (`ec2-paper`, verified live):

```
loss_control_mode                    = OFF
session_baseline_enforcement_enabled = False
session_baseline_shadow_enabled      = False
```

⇒ every ADR-0043 path below is **dormant in production**; the legacy broker-`last_equity`
basis is what actually runs.

---

## 1. Classification summary

| # | Consumer | Class |
|---|---|---|
| C1 | `app/risk/circuit_breaker.py::_compute_daily_pnl` | RISK_DECISION |
| C2 | `app/risk/engine.py::_daily_loss_day_change` → step 9 | RISK_DECISION |
| C3 | `app/risk/lock_state.py::current_lock_state` | RISK_DECISION |
| C4 | `app/risk/loss_control/preflight.py::_daily_loss_recomputed` | RISK_DECISION |
| C5 | `app/risk/loss_control/daily_loss_basis.py::select_daily_loss_basis` | RISK_DECISION (shared selector) |
| C6 | `app/api/v1/account.py` + `schemas/account.py` | PRESENTATION |
| C7 | `app/services/equity_snapshot.py:33` | ANALYTICS (propagates `day_change_pct`) |
| C8 | `app/services/account_sync.py::_normalize_account` / `_resolve_day_change` | PRODUCER |
| — | `continuous_evidence.py:360`, `portfolio_analytics.py:108`, `api/v1/account.py:56` | ANALYTICS — read `EquitySnapshot.equity` **only**; no baseline dependency ⇒ **CLEAN, out of scope** |

---

## 2. RISK_DECISION detail

### C1 — `circuit_breaker.py::_compute_daily_pnl` (L327–390)

| Attribute | Finding |
|---|---|
| Accepted basis values | Flag ON: whatever `select_daily_loss_basis` returns. Flag OFF: `equity − last_equity` when `last_equity > 0` |
| Unavailable behavior | **Manufactures `realized + unrealized`** |
| Cumulative fallback | **PERMITTED — at three separate surfaces** |
| ADR 0042 classifier | Not invoked |
| ADR 0034 scope | Preserved (account-scoped) |
| Tests | `tests/risk/test_p5_circuit_breaker.py`, `tests/risk/test_daily_loss_basis.py`, `tests/risk/test_daily_loss_enforcement_wiring.py` |

Call sites: `:110` (`status()`), `:148`, `:193`.

### C2 — `engine.py::_daily_loss_day_change` (L641–675), gate at L382–385

| Attribute | Finding |
|---|---|
| Accepted basis values | Flag ON: session baseline chain, `allow_cumulative_fallback=False`. Flag OFF: persisted `state.day_change` verbatim |
| Unavailable behavior | `state is None` → returns `None` → **gate silently skipped** (F2) |
| Cumulative fallback | Prohibited (correct) |
| ADR 0042 classifier | Not invoked at this gate |
| ADR 0034 scope | Preserved — explicitly documented at L368 |
| Tests | `tests/risk/test_daily_loss_enforcement_wiring.py` |

### C3 — `lock_state.py::current_lock_state` (L54, L68–74) — **not previously enumerated**

| Attribute | Finding |
|---|---|
| Accepted basis values | Persisted `state.day_change`, **with no `day_change_basis` check** |
| Unavailable behavior | Basis `UNAVAILABLE` ⇒ `account_sync` persists `day_change = 0` (`UNMEASURED`) ⇒ read as a **measured flat day** ⇒ `LOCK_DAILY_LOSS` never applies (F3). `state is None` ⇒ `daily_pnl = None` ⇒ check skipped |
| Cumulative fallback | N/A |
| ADR 0042 classifier | N/A — this function *produces* the lock state ADR 0042 consumes |
| ADR 0034 scope | Preserved |
| Tests | `tests/risk/test_engine_locked_reduction.py`, `tests/risk/test_cancel_gate.py`, `tests/orders/test_adr0042_end_to_end.py`, `tests/risk/test_decision_service.py` — none pin the `UNAVAILABLE` case |

### C4 — `preflight.py::_daily_loss_recomputed` (L316–328) — **not previously enumerated**

| Attribute | Finding |
|---|---|
| Accepted basis values | Any, including cumulative (`allow_cumulative_fallback=True`, L324) |
| Unavailable behavior | Pass condition is `basis.day_change is not None and basis.basis_source is not None` ⇒ **the gate goes GREEN on the cumulative fallback** (F4) |
| Cumulative fallback | **PERMITTED** |
| ADR 0042 classifier | N/A |
| ADR 0034 scope | Preserved |
| Tests | `tests/risk/test_daily_loss_basis.py` |

⚠ `preflight.py` is part of the ADR-0043 recovery-verification procedure hardened and
countersigned in `bbfc0b3` / `cb86377` / `5729dc0`. Changing this check's outcome
requires re-countersignature, not a silent edit.

### C5 — `daily_loss_basis.py::select_daily_loss_basis` (L126–217)

Shared selector; correct by construction. `allow_cumulative_fallback` is a **caller-supplied
option** (L129, L144, L174) — the defect lives in the callers, but the parameter is what
makes the defect representable.

---

## 3. Defect register

| ID | Location | Defect |
|---|---|---|
| **F1** | `circuit_breaker.py:376`, `:384`, `:390` | Cumulative `realized + unrealized` reachable at **three** surfaces: the `allow_cumulative_fallback=True` argument; the caller re-manufacturing it when the selector declines (`:384`, **inside the flag-ON branch**); and the flag-OFF terminal return (`:390`) |
| **F2** | `engine.py:659` | `state is None` → step-9 daily-loss gate silently skipped. Flag-independent |
| **F3** | `lock_state.py:54` | Reads `day_change` **without checking `day_change_basis`**; the `UNAVAILABLE` placeholder `0` is consumed as a measured flat day, so `LOCK_DAILY_LOSS` cannot fire. `state is None` likewise skips |
| **F4** | `preflight.py:324` | ADR-0043 preflight check "daily loss is recomputable" is satisfiable by the cumulative fallback |
| **F5** | `circuit_breaker.py:339–350` | Docstring asserts the fallback "can only trip the breaker EARLIER, never later — so an absent baseline never weakens the gate". False in both directions |
| **F6** | no component | Nothing compares broker `last_equity` against an independently reconstructed prior-session official close. ADR 0043's baseline is captured at session *open* and cannot detect this class of drift |

**F3 is the sharpest instance of the defect class.** `day_change_basis` was added precisely so
that "unknown" is distinguishable from "flat"; `api/v1/account.py:77` honours it, `lock_state.py`
does not. The label exists and one consumer ignores it.

---

## 4. Measured residuals at freeze (F6 evidence)

`residual = broker_last_equity − (Σ qty × prior-session SIP close + cash)`, computed only for
books with no fills on 07-29 or 07-30.

| DB acct | Label | Residual | Reported | True |
|---|---|---|---|---|
| 3 | Conservative | +53.39 | +1.418% | +1.483% |
| **5** | **Sector Rotation** | **+2,628.28** | **+1.212%** | **+4.162%** |
| 6 | Low Volatility | +216.73 | −1.380% | −1.173% |
| 7 | Combined Book | +379.56 | +0.356% | +0.741% |

All residuals positive ⇒ gate currently biased **tighter**. A negative residual would weaken it.

⚠ **Account mapping.** `.env ALPACA_PAPER_N` ≠ `accounts.id`: base→1, `_1`→2 Range, `_2`→3
Conservative, `_3`→**4 Growth**, `_4`→**5 Sector Rotation**, `_5`→6 Low Volatility, `_6`→7
Combined Book. The 2.95pp book is **account 5**, not account 4. DB account 4 is flat at
$100,000 with zero positions ⇒ no residual, **removed from the contamination inquiry**.

### Contamination disposition

| Area | Disposition |
|---|---|
| Equity-curve return / volatility / drawdown | CLEAN |
| Portfolio analytics (`EquitySnapshot.equity`) | CLEAN |
| API total return | CLEAN |
| Daily-loss control (broker-derived basis) | CONTAMINATED_CONTROL_INPUT |
| API day-change fields | CONTAMINATED_PRESENTATION_ONLY |
| SNS day-P/L and thresholds | CONTAMINATED_ALERTING |

---

## 5. Consequences for the approved Phase-0 scope

1. Scope item "set every circuit-breaker call to `allow_cumulative_fallback=False`" is
   **insufficient** — F1 shows two further surfaces in the same function, one inside the
   flag-ON branch.
2. **Two consumers were missing from the scope: C3 (`lock_state.py`) and C4 (`preflight.py`).**
   C3 carries an independent fail-open; C4 touches a countersigned procedure.
3. Deleting the cumulative fallback changes `status()`, which feeds
   `app/services/activation.py` and `app/api/v1/activation.py` — the **activation** path
   (ADR 0005 cooldowns), not only the breaker. `status().daily_pnl` needs a decided
   no-baseline representation before deletion.
4. Removing `allow_cumulative_fallback` from the shared selector requires deciding C4's
   behavior first; it is not a `circuit_breaker.py`-local change.
5. Residual telemetry (F6) should **not** live under `app/risk/` — that tree carries the
   ≥95% coverage gate (`check_risk_coverage.py`), and this is evidence, not admission
   control. `app/services/` or `app/observability/` keeps the measure/enforce boundary
   visible in the layout.
6. Any CI invariant guarding the fallback must be **wired into `.github/workflows/ci.yml`
   and shown failing on a deliberate reintroduction**. Precedent: `check_adr0002.sh` is
   named in `CLAUDE.md`, does not exist, and is not run.

---

## 6. Phase-0 resolution (this PR)

| ID | Disposition |
|---|---|
| **F2** | **CLOSED.** `engine.py` step 9 refuses risk-increasing orders with `DAILY_LOSS_BASIS_UNAVAILABLE` when `state is None` or the basis is `UNAVAILABLE`. VERIFIED reductions still pass via the ADR 0042 classifier. **The breaker is NOT tripped** — a trip is durable and needs a human reset. `_daily_loss_day_change` is untouched, so no enforcement-branch edit |
| **F3** | **CLOSED.** `lock_state.py` consults `day_change_basis`; new `LOCK_BASELINE_UNAVAILABLE` (20 chars, fits `String(24)`, **no migration**). `daily_pnl` returns `None` whenever unmeasured. With no `max_daily_loss` configured the account stays `UNLOCKED` — no protection exists to lose |
| **F5** | **CLOSED.** Docstring corrected; the false claim is recorded as an error so it is not reintroduced |
| **F1** | **DEFERRED** to the coordinated ADR 0043 basis correction — two of its three surfaces are inside the enforcement branch |
| **F4** | **DEFERRED** pending re-countersignature of the recovery procedure |
| **F6** | **DORMANT.** `app/services/daily_baseline_residual.py` — pure calculation, unreferenced by the runtime, no persistence/config/logging/broker reads. Activation is a separate governed step |

**Sync-before-admit** (`app/services/account_state_readiness.py`): startup awaits the first
baseline-bearing sync, bounded, after `broker_registry.load_all()` and before the RiskEngine is
built. Non-fatal — on expiry it alerts and boot continues; safety rests on the F2 gate, not on
this. It also emits the previously unmeasured `account_state_ready.elapsed_seconds`.

**Fixture correction.** 57 tests across 15 files failed on the change — 19 because their account
had no `accounts_state` row, 38 because `day_change_basis` defaults to `UNAVAILABLE`. Both groups
were relying on the defect: they modelled an account with a populated `day_change` that had never
synced, which cannot occur in production (sync is what populates `day_change`; all seven live
accounts carry `BROKER_LAST_EQUITY`). `tests/account_state_helpers.synced_account_state()` now
expresses "a synced account" once. `test_p5_engine_gates::test_circuit_breaker_trips_on_loss_during_evaluate`
was asserting the cumulative fallback directly and now requires a **measured** day loss.

## 7. Open questions requiring a ruling before implementation

- **Q1 — OPEN, blocks F1.** What does `status().daily_pnl` return when no basis exists, given
  `app/services/activation.py` and `app/api/v1/activation.py` consume it? `None` propagates into
  the ADR 0005 activation path; `0` re-creates F3 in a new place. This is why F1 could not be a
  local `circuit_breaker.py` change.
- **Q2 — OPEN, blocks F4.** Should C4's preflight check fail when the only basis is cumulative?
  Correct on the merits, but it alters a countersigned recovery procedure.
- **Q3 — ANSWERED.** C3 is a control (it feeds `LOCK_DAILY_LOSS`), so `UNAVAILABLE` is
  non-admitting with ADR 0042 reductions permitted. Closed by F3 above.

## 8. Known gap

`allow_cumulative_fallback` remains a parameter on `select_daily_loss_basis`, so the defect stays
representable at the shared layer. Removing the parameter outright — stronger than a CI grep,
since it makes the option unspellable — requires Q2 to be answered first, because `preflight.py`
is one of its two remaining `True` callers. Sequence: settle Q2 → delete the parameter → add the
CI check as a backstop. Any such check must be **wired into `.github/workflows/ci.yml` and shown
failing on a deliberate reintroduction**: `check_adr0002.sh` is named in `CLAUDE.md`, does not
exist, and is not run — this repo has live precedent for a decorative invariant.
