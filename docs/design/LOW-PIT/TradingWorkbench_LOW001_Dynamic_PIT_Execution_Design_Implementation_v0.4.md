# Trading Workbench — LOW-001 Dynamic PIT Execution
## Design & Implementation Specification v0.4

**Strategy:** LOW-001 (`low-volatility`) · **Strategy ID:** 8 · **Paper account:** Account 6 / user 6
**Deployed runtime:** v1.0.1 (merge `7bd35f1c`, PR #661)
**This branch:** v1.0.2 — PR S safety/conformance · **Reserved:** v1.0.3 — Dynamic PIT acquisition
**Status:** PR S IMPLEMENTATION-COMPLETE CANDIDATE — not merged, not deployed, **not yet the safe rollback baseline**
**Date:** 2026-08-22

> **Numbering correction.** The next state sync was referred to as "v0.5". No v0.4 was ever
> written: the series is v0.2 → v0.3 → **v0.4** (this document). Leaving a phantom v0.4 in a
> governed series would be worse than correcting the number, so this is v0.4 and it
> supersedes v0.3 in full.

---

## 0. What changed since v0.3, and why it matters

v0.3 was written *before* S5.5–S7 executed. Implementation then produced findings that
change the architecture rather than merely filling it in. The three that matter most:

1. **A ticker-equality fallback was found and removed** (S5.5). It was in code v0.3
   described approvingly, and only a real-store integration test exposed it.
2. **The activation service is LIVE-only by design**, so the PAPER safety exit needed its
   own authorized entrypoint and, later, its own trigger (S5.6, S5.7).
3. **`version` tracks the runtime implementation for this strategy**, settled by LOW-001's
   own history rather than by cross-book inference (S8.1).

---

## 1. Implementation record

Base: **`7bd35f1c`** (`main`, PR #661 merge). Branch `lowpit/scaffold`.

| Tranche | Commit | Delivered |
|---|---|---|
| docs | `9e46a53` | v0.3 spec + LOW-PIT-01 characterization |
| S1 | `525d1cd` | Test-harness fidelity; defect anchor |
| S2 | `53b7ff8` | Acquisition-provenance resolver |
| S3 | `d80dc0c` | READ-authority widening |
| S4 | `e1a7410` | Normal rebalance exit |
| S5 | `2d0039d` | LIVE liquidation by ownership |
| S5.5 | `9287382` | Permaticker identity + production wiring |
| S5.6 | `a4aec0b` | Shared liquidator + PAPER capability |
| S6 | `ab747d5` | Operator diagnostics |
| S7 | `d3bebce` | Schedule-semantics correction |
| S5.7 | `bba5d5e` | Stop/liquidate control seam |
| S8.1/S8.3-A | `236a400` | Version 1.0.2 + observability-only proof |

**Actual order differed from the plan.** S5.5 was inserted when S5 revealed the capability
was production-inactive; S5.6 when S5 revealed `ActivationService` is LIVE-only; S5.7 when
S5.6 revealed the capability had no caller. Each was discovered by finishing the previous
tranche, not foreseen — which is the argument for the tranche discipline itself.

---

## 2. The identity contract, as implemented

```
acquisition identity = acquisition ticker + EXCHANGE-LOCAL fill date
holding identity     = current broker ticker + current applicable session
attributable         <=> the two permanent identities match
```

Both resolve through `permaticker` + effective interval
(`PERMATICKER_EFFECTIVE_INTERVAL_V1`). The dates are deliberately different: a rename means
one security was reached from two tickers at two times, and resolving both on one date
fails in both directions.

Fill timestamps convert to the **exchange-local** date. A fill at 01:30 UTC belongs to the
previous New York session; the UTC date would compare an acquisition against the wrong side
of a lineage boundary.

### 2.1 ★ Ticker fallback is absolutely prohibited

```
current identity resolves      -> compare permanent identities
current identity does NOT      -> AMBIGUOUS / identity_unresolved
NEVER: resolution fails        -> fall back to ticker equality
```

**This was a real defect, not a hypothetical.** S3 matched a held ticker against the
acquisition's ticker list when current resolution failed. The S5.5 integration test showed
what that does: `REUSED`, acquired in March under one issuer and whose lineage *ended* in
May, resolved to `None` today and was then matched to its own stale acquisition and
admitted as OWNED. The fallback was most tempting exactly at a reuse boundary — the case
the contract exists to prevent. A date-insensitive fake could not have caught it.

---

## 3. Architecture as built

```
                    app/universe/
                    ├── strategy_ownership.py   S2  provenance classification
                    ├── owned_holdings.py       S3  ownership ∩ live positions
                    ├── security_identity.py    S5.5 permaticker adapter  ── factor store
                    ├── liquidation.py          S5.6 shared mechanics
                    ├── diagnostics.py          S6  operator vocabulary
                    └── dynamic_symbol_resolver.py   PR B ── broker  (NOT PRESENT)
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
  StrategyContext      ActivationService     PaperStrategyLiquidation
  (READ scope)         (LIVE only)           (explicit policy)
        │                     └──────────┬──────────┘
        │                     StrategyControlService  S5.7 (the ONLY mode router)
```

`security_identity` couples to the factor store; the future `dynamic_symbol_resolver`
couples to the broker. They stay separate modules so the two planes remain separable.

**Authority split** (§4.7 of v0.3, unchanged and now enforced):
`READ = registered ∪ strategy-owned-held`; `BUY = v1.0.1 rules only`. `ctx.symbols` is
never widened — it drives dispatch, selection and buy planning. PIT-T16 proves the split.

**Ownership contract:** provenance says *which strategy may claim*; the broker position says
*how much exists*. No retrospective quantity reconstruction, ever (§4.8) — enforced by an
AST test, not prose.

---

## 4. Disposal, in three paths

| Path | Entry | Authorization |
|---|---|---|
| Normal rebalance exit | `_current_holdings()` → position book | ownership only |
| LIVE liquidation | `ActivationService.deactivate(liquidate=True)` | unchanged ADR 0005 semantics |
| PAPER liquidation | `StrategyControlService.deactivate(liquidate=True)` | **default-deny** `PaperLiquidationPolicy` |

All three converge on `StrategyPositionLiquidator`, so attribution, quantity source,
current-ticker routing and fail-closed refusals cannot diverge.

- **`ActivationService` is not PAPER-aware.** Every existing paper strategy keeps its
  behaviour; `deactivate(liquidate=True)` still liquidates nothing for them.
- **`PaperLiquidationPolicy` is default-deny by construction** (`enabled=False`, empty
  allow-list). `for_pr_s()` grants `low-volatility` and nothing else. Neither
  `mode is PAPER` nor the strategy name alone suffices.
- **Mode routing exists in exactly one place**, asserted structurally: `Account.mode` is
  queried once and branched once inside `StrategyControlService`.
- **A denied liquidation denies the liquidation, not the stop** — `denied_reason` is set.
- **`/stop` gained `{liquidate: false}`**; an absent body is byte-identical to pre-PR-S.
- ⛔ **A circuit-breaker trip is not a liquidation request.** The breaker stops *new* risk
  while preserving risk-reducing activity; redefining a trip as "flatten the book" would
  change platform risk semantics under cover of a bug fix. Pinned by test.

---

## 5. Readiness (G-C)

`assert_pr_s_capability_ready()` is invoked from the engine's registration path.

```
PR-S safety-critical (low-volatility only):
    no provider                     -> cannot RUN
    provider present but not ready  -> cannot RUN
    provider ready                  -> may RUN
static strategies                   -> unaffected
```

Readiness checks the capability can **answer**, not that an object was injected: a provider
with no identity store resolves everything to `None`, and "nothing is ours" reads as
healthy. *Runtime* lookup failures still fail closed to registered-only; only
*initialization* absence is fatal.

---

## 6. Operator diagnostics (S6)

```
ownership_ambiguous               warning   competing ownership/acquisition
ownership_identity_unresolved     warning   security-lineage problem
ownership_evidence_missing        warning   held, no acquisition record
ownership_unclaimed               INFO      legitimately someone else's
liquidation_position_excluded     warning   a liquidation pass skipped one
```

Fields: `strategy_id, strategy_name, account_id, account_mode, current_ticker, permaticker,
classification, reason, operation, scope_id, source`.
`operation ∈ {normal_rebalance_exit, live_liquidation, paper_liquidation}`.

Dedupe key `(strategy_id, account_id, operation, permaticker-or-ticker, classification,
scope_id)`. The 200-symbol storm reports once; a later rebalance reports again;
`scope_id=None` (liquidation) disables dedupe. Never permanent — a persistently unresolved
identity that goes quiet reads as resolved.

**Observability-only** (S8.3-A): emission never feeds selection, BUY authority,
classification or liquidation authorization. Proven structurally (AST: no production caller
consumes an emitter result) and by mutation (silencing the emitter yields byte-identical
orders and dispositions).

---

## 7. Schedule semantics (S7)

```
class default = "32 10 * * mon"  ->  Monday 10:32 America/New_York
```

Schedule strings are exchange-local; the engine pins `CronTrigger.from_crontab(...,
timezone="America/New_York")`. The old default `"0 14 * * mon"` documented as "14:00 UTC ≈
09:00 ET" was true before that pinning and wrong after, in two ways. Re-registering from
defaults would have moved the book 3½ hours silently.

Two assertions, catching different regressions: a literal guard (someone edits the string)
and a timezone-resolving test asserting the **wall-clock** instant across EST and EDT (the
interpretation moves while the string stays). Mutation-verified: changing the engine
timezone fails the semantic tests and *not* the literal one.

Cadence (weekly) remains frozen economics; the clock time is a runtime conformance default.
`test_research_frozen_defaults` was reframed to stop implying the 2pm value was validated.

---

## 8. Version ruling (S8.1)

```
1.0.1  conformance repair       deployed
1.0.2  PR S safety/conformance  this branch
1.0.3  Dynamic PIT acquisition  reserved (PR B)
```

Settled by LOW-001's own history: `1.0.0 → 1.0.1` was itself a pure conformance repair with
no economics change, so `version` already tracks the runtime implementation for this
strategy. Two materially different runtimes both reporting 1.0.1 would break rollback and
evidence attribution far worse than an unnecessary bump.

---

## 9. Known residuals — carried deliberately

1. **`_legacy_registration_liquidation`** remains reachable for a static LIVE strategy when
   no provider is wired. It still trusts registration. Retained so an un-wired deployment
   does not lose LIVE liquidation entirely; the readiness assertion is what prevents
   LOW-001 depending on it in a healthy deployment. Removing it would turn PR S into a
   platform-wide migration.
2. **Repo formatting baseline.** Pristine `main` fails a repo-wide `ruff format --check`
   (689 files). The differential rule applies: PR-touched files are format-clean, no
   unrelated file is reformatted. Six of the seven touched pre-existing files carried
   format debt, so their diffs interleave formatting with logic; `store.py` has none.
3. **Pre-existing mypy error** in `app/research/disc001/engine.py`, verified at base
   `7bd35f1c`. The differential is unchanged: no new errors.

---

## 10. Gate status

| Gate | Status |
|---|---|
| G-A risk allow/deny | CLOSED — measured, no allowlist exists |
| G-B ownership design | RULED — set provenance + broker quantity, no schema change |
| G-C startup readiness | **CLOSED** — assertion invoked from the engine |
| G1 static-strategy regression | CLOSED — denial proven by policy, not by absence of calls |
| G4 exit safety (normal) | CLOSED |
| G4b capability | CLOSED |
| G4b operational reachability | **CLOSED** — S5.7 end-to-end through the control seam |
| G0 Account-6 boundary | **OPEN** — deployment-time |
| G2/G3/G5/G6/G7 | **OPEN** — Dynamic PIT gates, PR B |

### Terminology, held until earned

```
today                       PR S = implementation-complete candidate
after S8 local + CI gates   PR S = merge-qualified
after merge + deploy proof  PR S = SAFE ROLLBACK BASELINE
```

**Dynamic BUY remains PROHIBITED** until that last line is true.

---

## 11. Deployment proof required before PR B (S8.6)

- running version = **1.0.2**; running source SHA = the PR-S merge SHA
- `owned_holdings_provider` READY · security identity READY
- PAPER liquidation authorized for LOW-001 **only**
- schedule = Monday 10:32 America/New_York
- orphan `use_market_regime_filter` removed; `fractional_shares` corrected
- restart does not invent a second completed-week rebalance
- owned-unregistered exit available; explicit PAPER liquidation operationally reachable

Routing may be established by production-safe synthetic or read-only evidence; what must
not recur is the capability existing as an uncalled object.

---

## 12. Unchanged from v0.3

Economics frozen (252-session realized vol, lowest quintile, equal weight, weekly cadence).
No Account 5 change. No live-money authorization. No `positions` schema migration — the six
reopening triggers of v0.3 §5.4.2 stand. No symbol-table writes. LOW-001 remains
**Diversifier (B)**. The acquisition/disposal symmetry invariant (§4.6) and the READ/BUY
split (§4.7) govern unchanged; PR S implements the disposal half of the former.
