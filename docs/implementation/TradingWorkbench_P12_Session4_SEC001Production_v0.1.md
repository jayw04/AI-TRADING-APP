# P12 §4 — SEC-001 Sector Rotation Capability Promotion

| Field | Value |
|---|---|
| Session | P12 §4: SEC-001 Capability Promotion / Methodology Transfer |
| Date | 2026-06-23 |
| Owner | Jay Wang |
| Objective | **Demonstrate that Evidence Engineering is methodology, not magic** — promote SEC-001 from L2 (Validated) through governance into L4 (Paper) and L5 (Continuous Evidence), proving the platform is not a one-off strategy engine but a repeatable research + governance + execution system. |
| What this proves | MOM-001 → SEC-001 → LOW-001 → TREND-001 all travel the *same* Evidence Engineering lifecycle (Research → Governance → Paper → Continuous Evidence → L4/L5 promotion). The lifecycle is the product. |
| Acceptance | SEC-001 live on paper (standalone) for 4+ weeks; operational health clean; governance gate signed off; continuous evidence proves operational repeatability of the methodology. |

---

## 0. Strategic context: Methodology Transfer (not just "another strategy")

**Phase 2 of the SCAN-001 review's three-phase roadmap:**

1. ✅ **Phase 1** — Freeze Discovery Lab v1.0 (SCAN-001 validation + premarket gate built)
2. ⭐ **Phase 2** — Demonstrate **Methodology Transfer** (SEC-001 → LOW-001 through the *same* lifecycle) 
3. 📋 **Phase 3** — Commercialization (whitepaper, patent, UX, SaaS packaging)

The distinction matters: this is not "deploy another strategy." It is **proving that the Evidence Engineering lifecycle is transferable** — that MOM → SEC → LOW → TREND all follow the same governance and produce the same institutional rigor. SEC-001 is uniquely positioned:
- **Research Complete, Promotion Candidate** (research frozen, no new variants)
- **Construction archived** (V2 proved construction was not the limiter; no parameters to tune)
- **All frozen inputs known** (12m momentum, K=3 sectors, 200-name universe)

All we do is operationalize it and run it under governance to show the methodology works for *multiple* capabilities, not just the first one (MOM-001).

---

## 1. SEC-001 overview

| Property | Value |
|---|---|
| **Program** | SEC-001 — Sector Rotation |
| **Research verdict** | 🟡 **Diversifier (B)** — strong overlay, no standalone edge |
| **Key metrics** | Sharpe **0.51** (vs MOM 0.39); DD **−64.8%** (vs MOM −76.4%); Corr **0.38** (orthogonal enough) |
| **Edge** | V1 H1 standalone +0.16, CI [−0.03, 0.366] → spans zero; V2 matched V1 (construction ≠ limiter) |
| **Signal** | 12-month sector momentum (same window as momentum's 12-1) |
| **Construction** | Top-K sectors (K=3 frozen) as sector-neutral equal-weight baskets; construction **archived** |
| **Universe** | Same 200-name liquidity candidate set as MOM-001 |
| **Research artifacts** | `evidence/sec_001_v2_pure_baskets/` (V2 results); `evidence/sec_001_sector_rotation/` (V1) |

**Why now:** All research is done. SEC-001 is promoted as **a standalone paper capability** for operational validation and attribution analysis. Its intended long-term value is as a diversifying component alongside Momentum (corr 0.38), but we measure it *independently* first — this is how Evidence Engineering handles diversifiers. Demonstrates:
- **Methodology Transfer** (MOM → SEC on the *same* lifecycle)
- **Governance rigor** (a Diversifier verdict is not a pass/fail, it's a structural positioning choice)
- **Operational proof** (two independent research lines → two live books → one unified OrderRouter + risk engine)

---

## 2. Architecture: SEC-001 from research to continuous evidence

```
SEC Research (validated)
       ↓
Frozen Parameters (12m momentum, K=3, 200-name universe)
       ↓
SectorRotation.py (pure code, no broker/DB/LLM; read-only factor access)
       ↓
OrderRouter (ADR 0002 — every order goes through; no bypass)
       ↓
Risk Engine (ADR 0005 — risk gates applied; breaker live)
       ↓
Paper Deployment (standalone account)
       ↓
Execution Service (daily equity snapshots, P&L, breaker audits)
       ↓
Continuous Evidence (live_evidence.py, Evidence Dashboard)
       ↓
Governance Review (4-week operational health gate)
       ↓
Capability Promotion (L2 → L4 recommendation: Promote / Monitor / Escalate)
       ↓
L5 Continuous Monitoring (ongoing evidence as the book lives)
```

---

## 3. Implementation plan

### 3.1 Create the SEC-001 strategy file

**Target:** `apps/backend/strategies_user/templates/sector_rotation.py`

**Based on:** `momentum_portfolio.py` + the SEC-001 V2 research algorithm (`sector_rotation_v2_research.py`)

**Scope:**
- Pure sector-momentum (12-month, 0-day skip — identical to MOM-001's lookback window)
- Top-K=3 sectors, sector-neutral equal-weight baskets
- Weekly rebalance cadence (Monday 14:00 UTC, matching MOM-001)
- Same universe (201 symbols including SPY for regime filtering)
- Optional daily vol-scaling overlay (inherit from MOM-001 if enabled)
- Read-only via `ctx.factors`, no broker/DB/LLM; all risk checks via OrderRouter
- Advisory log signals for transparency

**Code structure:**
```
class SectorRotation(Strategy):
  - on_bar() → weekly rebalance gate
  - _rebalance() → compute sector scores + select top-K baskets + trade
  - _compute_sector_scores() → 12m momentum per sector from cached rankings
  - _select_targets() → top-K sectors as equal-weight baskets
  - _apply_targets() → trade toward the target (sell exiting names, buy new names)
  - [reuse] regime filter, vol-scaling overlay, market_filter_symbol
```

**Parameters:**
- `sector_momentum_lookback_days`: 252 (frozen, research)
- `sector_momentum_skip_days`: 0 (frozen, research)
- `top_k_sectors`: 3 (frozen from V2 headline)
- `sector_min_names`: 1 (each sector gets ≥1 name if held)
- `use_market_regime_filter`: True (inherit from MOM-001 discipline)
- `use_vol_scaling`: False (inherit from MOM-001, but can turn on)
- All other params: inherit standard MomentumPortfolio schema for consistency

### 2.2 Register SEC-001 strategy in the database

**Strategy metadata:**
- name: `sector-rotation`
- version: `1.0.0` (distinct from MOM's v0.8.0; fresh deployment)
- universe: same top-200 liquidity candidates + SPY (201 symbols)
- status: `IDLE` initially (owner-gated activation)

**Account assignment:**
- **Standalone paper account** (distinct from MOM-001) for clear attribution and operational isolation
  - Enables measuring SEC-001's independent behavior (sector allocation, correlation, P&L)
  - Avoids account-level risk cap blending between two independent strategies
  - Makes governance gate cleaner (each strategy's health is independent)
  - Later blending study (if desired) can optimize MOM+SEC on the *same* account post-validation

**Schedule:** 
- Same as MOM-001: `0 14 * * mon` (Monday 14:00 UTC ≈ 09:00 ET)
- Or offset by 30 seconds if risk engine prefers non-overlapping rebalances

### 2.3 Live activation & accrual

**Startup:**
1. Backend rebuild + restart (the image drifts, like vol-scaling)
2. Run database migrations (if any new tables/columns)
3. Activate strategy: `/start` via the web UI (owner selects PAPER / target account)

**Cadence:**
- First rebalance fires Monday 2026-06-30 14:00 UTC (a week after activation, to match the schedule)
- Subsequent rebalances every Monday at the same time
- Daily vol-scaling overlay (if enabled) on weekdays 15:00 UTC ≈ 10:00 ET

**Monitoring:**
- Live evidence report will include SEC-001 alongside MOM-001 (via `live_evidence.py`)
- Weekly P&L tracking, risk-gate audits, breaker clean
- Correlation with MOM-001 (target ~0.38 from research)

---

## 3. Files to create/modify

| File | Action | Notes |
|---|---|---|
| `apps/backend/strategies_user/templates/sector_rotation.py` | **NEW** | Pure sector-momentum strategy; reuses utility methods from MomentumPortfolio where applicable |
| `apps/backend/app/strategies/__init__.py` | MODIFY | Register SectorRotation class in the strategy registry (likely auto-discovered if in strategies_user/) |
| `Docs/implementation/evidence/p12_s4_sec001_production/` | NEW (dir) | Store live evidence, equity curves, risk audits as they accrue |

---

## 4. Research lifecycle verification

**Pre-deployment checklist (what makes SEC-001 production-ready):**

| Item | Status | Note |
|---|---|---|
| ✅ Research verdict determined | DONE | Diversifier (B), all evidence committed |
| ✅ Construction archived | DONE | V2 proved construction ≠ limiter; no further tuning planned |
| ✅ Parameters frozen | DONE | K=3, 12m momentum, 200-name universe, equal-weight per sector |
| ✅ Evidence reproducible | DONE | Research scripts + JSON artifacts versioned in `evidence/sec_001_*` |
| ✅ Risk-path validated | DONE | No order-path LLM (ADR 0006 v2), no broker-bypass (ADR 0002), all risk checks via OrderRouter |
| ✅ Code structure defined | TODO | Implement `sector_rotation.py` (this session) |
| ⭐ Paper deployment | TODO | Activate strategy, run for ≥2 weeks, accrue evidence |
| 📋 Production recommendation | TODO | After accrual, run verdict on live P&L (recommend/decline) |

---

## 5. Evidence accrual & post-deployment gate

Unlike research (ADR 0014: ≥40d forward data before a verdict), the **production gate** is a *confidence signal*, not a barrier:

- **Live P&L tracking:** daily equity snapshots, Sharpe/DD/Calmar (live versions of the backtested stats)
- **Risk audits:** risk gates fired, breaker trips, reconciliation mismatches (should be clean)
- **Correlation validation:** Pearson corr(SEC return, MOM return) vs the researched 0.38
- **Recommendation trigger:** after 4 weeks of clean operation, a final `run_gate_verdict(...)` call → recommend / monitor / escalate

---

## 6. Scope (what we do NOT do this session)

- ❌ **Multi-strategy portfolio optimization:** SEC-001 is paired with MOM-001 to demo multi-strategy capability, not to optimize their blend. Blend sizing = owner's discretion (50/50, 30/70, etc.).
- ❌ **Parameter tuning:** K, lookback, skip-days are research-frozen and must not be tuned live.
- ❌ **New research variants:** (e.g., SEC-002 with different K). Roadmap says no new research until repeatability is proven.
- ❌ **UI wiring:** the Candidate Report / Opportunities page does NOT need SEC-001-specific surfaces this session. Live evidence report is the surface.

---

## 7. Success criteria (Governance Gate)

**Phase 2 "Methodology Transfer" is proven when all of the following pass:**

| Criterion | Target | Why it matters |
|---|---|---|
| **Code Quality** | CI green, ruff/mypy clean | Operational health starts with clean code |
| **Activation** | First rebalance Monday 2026-06-30, no crashes | Strategy registers and fires on schedule |
| **Operational Health** | 100% clean | No failed jobs, no reconciliation errors, no breaker spurious trips, no risk violations | Proves the OrderRouter + risk engine handle two strategies without crosstalk |
| **Expected Positions** | Each rebalance holds top-3 sectors in equal-weight baskets | Validates that the selection logic is correct operationally |
| **Expected Turnover** | Weekly rebalance, sector names churn naturally (not anomalous) | Evidence the strategy is behaving as researched |
| **Correlation Direction** | Correlation with MOM stays in [0.28, 0.48] | Validates diversification hypothesis (research 0.38 ±0.10) |
| **Live Evidence Accrual** | 4+ weeks of daily snapshots, P&L, risk audits captured | Continuous evidence proves operational repeatability |
| **Governance Gate Signed** | Promotion Review completed → L4 recommendation issued | Formal promotion from L2 (Validated) → L4 (Paper) |

**NOT success criteria (per ADR 0014):**
- ❌ Sharpe/DD matching research exactly (4 weeks is too short for statistical evidence)
- ❌ P&L target achieved (market conditions differ; short-term returns ≠ edge evidence)

**Stretch (nice-to-have, post-validation):**
- Sector performance attribution (which sectors drove the weekly return?)
- MOM+SEC blend study (what allocation maximizes Sharpe while honoring the correlation?)

---

## 8. Lifecycle milestones (not calendar dates; more robust)

| Phase | Gate | What happens |
|---|---|---|
| **Implementation** | CI green, ruff/mypy clean, code review approved | `sector_rotation.py` ready for deployment |
| **Activation** | Database updated, backend rebuilt, strategy registered in IDLE state | Ready to `/start` on a paper account |
| **First Rebalance** | Monday cron fires, OrderRouter clean, no crashes | Validates that the strategy framework works |
| **Continuous Evidence** | 4+ weeks of daily snapshots, P&L, risk audits, no spurious breaker trips | Proves operational repeatability |
| **Governance Review** | Evidence package finalized, operational health audit passed | Governance sign-off before promotion |
| **Promotion Recommendation** | L2 → L4 gate decision: Promote / Monitor / Escalate | Formal promotion decision issued |

---

## 9. Pre-registration (operational validation hypotheses)

Per ADR 0014, short-term P&L is not evidence. Instead, these are operational and structural validations (note: none reference Sharpe or P&L targets):

**H1 (Execution Health):** 
- All rebalances fire on schedule (Monday 14:00 UTC or close)
- Zero failed orders within the strategy's risk envelope
- Zero breaker spurious trips attributable to SEC-001
- Zero reconciliation mismatches (filled qty matches ordered qty)

**H2 (Structural Correctness):**
- Each rebalance holds exactly 3 sectors (or fewer if the universe is thin)
- Each sector's names are equal-weight within their sector sleeve
- Sector allocations sum to 100% (or less if cash is held)
- No market proxy (SPY) is held in the portfolio

**H3 (Correlation Direction):**
- Pearson correlation(SEC daily returns, MOM daily returns) stays in [0.28, 0.48] (research 0.38 ±0.10)
- If correlation drifts outside this band, flag for investigation (market regime / data quality check)

**H4 (Operational Repeatability):**
- Four weeks of continuous evidence with zero critical operational gaps
- Daily equity snapshots consistently captured
- Risk audits show governance compliance (no rule violations)
- OrderRouter handles both MOM + SEC without crosstalk (shared position bugs would be a breach of ADR 0002)

---

## 10. Next steps (after this session)

1. **Implement** `sector_rotation.py` (this week)
2. **Activate** on paper (June 30 first rebalance)
3. **Accrue** evidence for 4 weeks (P12 §5 = the ops window, running in parallel with SCAN-001's forward accrual)
4. **Produce** `P12_Session4_SEC001Production_Results_v0.1.md` with live evidence + verdict

**Then:** Phase 2 is proven → **Phase 3** begins (LOW-001 production, then TREND-001, then commercialization).

---

