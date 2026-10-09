# RANGE-002 — Opening-Range Breakout Continuation: Implementation Plan — Evidence-Driven Edge Development (Developer & Agent Edition)

| Field | Value |
|---|---|
| Document | RANGE-002 Implementation Plan |
| Version | **v0.4 (review of v0.3: reconciled with research design v0.4; gaps closed)** |
| Date | 2026-10-09 |
| Audience | Platform developers and the implementation agent |
| Program status | **PROPOSED / NO RUN AUTHORIZED.** No RANGE-002 returns have been computed. This revision did not access the repository, governed datasets, or broker; the live repository state must be verified in WP0.1. |
| Governing documents | `RANGE-002_开盘区间突破延续策略_验证与实施方案_v0.4.docx` (research design v0.4, Chinese, 2026-10-09). RNG-001 Rejection Summary Report (2026-10-09). ADR 0014, ADR 0033, ADR 0037. |
| Precedence | **Research design v0.4 wins.** This revision was checked against the v0.4 design text (see §0A reconciliation matrix). ADR texts were not available and are cited as summarized in the design and the RNG-001 report. Do not silently change a gate or strategy rule in code. |
| Repository | `jayw04/AI-TRADING-APP` (backend under `apps/backend/app/`) |

> **What this document is.** Developer/implementation-agent revision of v0.1, incorporating v0.2 diagnostics plus v0.3 execution and statistical corrections. It preserves the economic hypothesis, the two variants, the seven phases (P0–P6), ledger/holdout protection, broker isolation and the precedence of research design v0.4. v0.4 of this plan reconciles the added work packages and decisions against the design (§0A); none of them changes a v0.4 gate or strategy rule. Values marked `P0:` need explicit owner approval, are never guessed by agents and must be loaded from the approved frozen spec.
>
> **Success criterion.** The target is an honestly demonstrated, reproducible, cost-adjusted trading edge with realistic risk and execution, **not** a backtest engineered to avoid rejection. Neither this plan nor AI can guarantee profitability. A prompt rejection of an unprofitable candidate is a correct platform result; any further hypothesis is separately registered, justified and tested on genuinely independent evidence.
>
> **Evidence scope.** This revision was checked against research design v0.4 and the RNG-001 Rejection Summary Report. It did **not** inspect the repository, the ADR texts, archived RNG-001 evidence files, or broker/data providers. RNG-001 figures are quoted from the rejection report and are re-verified by the WP2.6 replay.

---

## Change summary (v0.3 → v0.4)

v0.3's structure and safety additions are kept. v0.4 fixes the following.

| # | Finding in v0.3 | Severity | v0.4 disposition | Where |
|---|---|---|---|---|
| F1 | D13–D16 were held as "not approved" because the research design was unavailable. Checked against v0.4: almost all of them refine decisions v0.4 already requires (decisions 05, 06, 07 and the cost-itemization row). | High (blocks progress for no reason) | D13–D16 folded into existing v0.4 decisions; only behavior-changing items still need owner sign-off. Appendix A.1 merged into Appendix A. | §0A, §10 |
| F2 | **P3 advance criteria are never defined** — neither in v0.4 ("事前批准的开发期标准") nor in v0.3 — yet P3 STOP/ADVANCE depends on them. | Blocking | New decision D17 with options; `results_guard` refuses P3 while `p3.criteria` is null. | WP4.1, §10 |
| F3 | Gates do not say which trade set they are computed on (portfolio-constrained fills vs all signals) or what counts as a "trade" for G1. These give different numbers. | Blocking | New decision D18; gates computed on one declared basis, the other reported as a diagnostic. | §5.1, §10 |
| F4 | v0.3 requires "no fill until acknowledged and armed" but gives no rule for **simulating** arming on historical 1-minute bars. First-minute breakouts after 10:00 are exactly where this matters. | High | Concrete simulated-arming rule plus a frozen crossed-before-arm policy (D14), with a mandatory sensitivity report. | WP2.1A |
| F5 | OR completeness treats every absent minute as missing data. On SIP, a minute with no trades has no bar; that is not a data gap. | Medium | Separate `NO_TRADE_MINUTE` from `DATA_GAP`; completeness rule applies only to data gaps. | §2.1, WP1.7 |
| F6 | The bootstrap is not tied to the platform convention, and the "Holm-adjusted CI" construction is left vague. | Medium | Platform stationary block bootstrap over trading days; Holm on one-sided bootstrap p-values; paired day-level estimand for G5 specified. | WP3, §5.1 |
| F7 | Negative controls in a guarded run are evaluated after strategy results are visible, so a failing control cannot cleanly void the run. | Medium | Two-stage sealed run: controls first; strategy results unsealed only if controls pass. | WP4.0, R17 |
| F8 | Verdict labels are inconsistent (`PASS-HISTORICAL` vs `PASS_HISTORICAL_PENDING_PROSPECTIVE`); P3 has no INCONCLUSIVE path; no P5/P6 states; no mapping to v0.4's four states. | Medium | One closed enum across P3–P6, mapped to v0.4 §6.1. | §5.2 |
| F9 | The P4 Holm family is not fixed if only one variant advances from P3. | Medium | The P4 family is declared at P0 as "variants that advance"; the rule is frozen, not chosen after P3. | WP4.2, D02 |
| F10 | The RNG-001 replay computes returns but has no `results_guard` partition type. | Low | New `REPLAY_RNG001` partition: exposed data, engine validation only, never strategy evidence. | WP0.4, WP2.6 |
| F11 | Structure: P2 exit gate placed before WP2.11; P0/P2 gate dependencies omit PR 4A/12A/12B; §11 sits after the appendices; R16 row has a stray cell; the D10 note attributes the platform gate to "v0.1" (it comes from the RNG-001 report). | Low | Fixed. | throughout |

## 0A. Reconciliation with research design v0.4

| v0.3 proposal | v0.4 source | Status in v0.4 plan |
|---|---|---|
| D13 economic thesis + trading-expert sign-off | §10.3 roles (trading expert verifies hypothesis and trade logic); §3.3 AI provenance | **Within v0.4.** Required P0 artifact; non-binding diagnostics stay non-binding. No addendum needed. |
| D14 data availability, latency, order type, order state machine, tie-break, EOD protocol | §5.2 (order effective time, trigger ≠ fill, partial fills, cancel delay, duplicates, restart recovery); decision 05 | **Within v0.4 decision 05.** Values still need owner sign-off because they change simulated fills. |
| D15 cost accounting mode (all-in vs itemized) | §4 cost row ("逐笔列出价差、佣金/费用、冲击、滑点的计入方式，避免重复或遗漏") | **Within v0.4.** Must be frozen at P0. |
| D16 diagnosis taxonomy, P5 shadow run, execution-quality evidence | §9.2 P5 template (comparable cost items, aggregation, tail rules; operational quality); decision 07 | **Within v0.4 decision 07.** The taxonomy is explanatory only. |
| Order reservation / chronological portfolio scheduler | §5.2 capacity and participation; §4.1 R_pre/R_fill | Engineering requirement; no rule change. |
| P3 advance criteria | §7 P3 row ("达到事前批准的开发期标准或停止") — **criteria not given** | **Gap.** New D17. |
| Gate computation basis / trade definition | §6 gate table — not specified | **Gap.** New D18. |

## Change summary (v0.1 → v0.3)

| Theme | Why it matters | Where implemented |
|---|---|---|
| **Economic edge thesis and feasibility before construction** | Building flawless code cannot make a structurally unprofitable OR breakout profitable | §2.4–2.7, WP0.9–0.12 |
| **Corrected simulation and order lifecycle** | OHLC-bar hits, capital competition, order timing and wide-stop risk can create imaginary profits | §3.3, WP2.2–2.4, WP2.8–2.10 |
| **Full opportunity-to-net-return attribution** | Determines whether rejection arises from absent edge, costs, missing signals, risk sizing or infrastructure | WP3.1–3.4, §7 |
| **Explicit statistical/test-family decisions** | Prevents arbitrary pass/fail judgments and successor-variant leakage | §5.3, D13–D16 |
| **Safe continuous improvement** | Enables *future* research after failure without changing RANGE-002 post-outcome | §2.7 and §11 |
| **Operational readiness and shadow execution** | Closes the gap between historical fills and paper broker behavior | WP5.9–5.12, §6 |

### v0.3 corrections after implementation review

| Issue | v0.3 disposition | No-regression test |
|---|---|---|
| Random-entry control may generate entries below its OR-low stop or condition on future breakout | Require an explicitly defined causal, risk-comparable baseline with infeasible draws accounted for | `test_random_control_no_future_conditioning`, `test_baseline_risk_eligibility` |
| Minute-bar timestamps can refer to bar open or bar close, creating accidental premature orders | Normalize vendor bar interval and distinguish `event_time`, `bar_available_at`, `decision_at`, `ack_at` | `test_vendor_bar_interval_and_late_bar` |
| Buy-stop becomes executable only after broker acceptance; already-crossed trigger creates race | Define stateful `UNPLACED → SUBMITTED → ACKED → ARMED` protocol and a deterministic crossed-at-ack decision | `test_crossed_before_ack_cannot_backfill` |
| Cost ratio has undefined/unstable denominator when modeled cost is zero or negative | Freeze comparable all-in execution shortfall and robust aggregation with `UNDEFINED` handling | `test_cost_ratio_zero_denominator` |
| Same-bar OHLC assumptions can determine profitability | Require high-resolution/quote-level sensitivity where available, and explicit fragility disclosure otherwise | `test_intrabar_path_sensitivity` |
| Strategy success cannot be engineered by retroactive filtering | Use diagnostics to inform future, separately registered hypotheses; keep RANGE-002 A/B fixed | `test_no_mutation_after_p3`, `test_holdout_single_use` |

**Implementation authorization boundary:** This revision is a **plan**, not a research design approval. Do not execute governed P3/P4 computations, open the holdout, connect a broker, change the approved threshold, or deploy a paper strategy based solely on this file. The owner and independent reviewer must first sign the P0 decisions, and WP0.1 must confirm the ADR texts match the §0A matrix.

## 0. Read this first: hard rules for the implementation agent

These rules are enforced by mechanisms described later in this plan. Until each mechanism exists, follow the rule by hand. If you cannot follow a rule, stop and report.

| # | Rule | Why | Enforced by |
|---|---|---|---|
| R1 | **Do not compute or look at any RANGE-002 return, P&L, profit factor or win rate before the spec is frozen and signed (P0 exit).** Coverage and data-quality reports are allowed only if they are return-blind. | Seeing results before freezing the spec turns the test into tuning. That is how RNG-001's filters "passed" in-sample. | `results_guard` (WP0.4) |
| R2 | **Never use 2026-01-01 → 2026-07-31 data in any decisive run (P3/P4).** This data is exposed by RNG-001 and gave rise to the RANGE-002 idea. | Data that suggested a hypothesis cannot confirm it. | Exposure ledger + partition check in `results_guard` |
| R3 | **The P4 holdout (2022–2025) is opened at most once per frozen spec.** Defect-only reruns need a logged defect record and owner approval. | One decisive run. A failed holdout is not retried with a changed strategy. | Holdout token (WP4.2) |
| R4 | **Do not tune.** No change to levels, buffers, filters, exit rules, universe, N, costs or thresholds after results are seen. A materially changed hypothesis requires a distinct owner-approved research registration, not merely a version bump. | RNG-001 lesson: more levels, buffers or gates is data mining. | Spec hash check on every run |
| R5 | **Do not touch user 2 (`range@local.dev`) or the RNG-001 code paths.** User 2 stays the RNG-001 execution benchmark. | Separation of evidence. | Code review; no imports from RNG-001 strategy modules into RANGE-002 except the replay harness (WP2.6) |
| R6 | **Pin the feed to `sip` in every governed path.** Never fall back to IEX silently. | IEX quotes can diverge sharply from the consolidated market (GLD incident, 2026-08-14). | Data manifest + loader assertion |
| R7 | **No research-plane code may hold broker credentials or place orders.** Only the P5 executor, through the existing authenticated OrderRouter and risk engine, can place orders. | Research recommends, governance authorizes, core executes. | Module boundaries, CI import check |
| R8 | **Every run goes into the trial ledger**, including failed, aborted and defect runs. An unledgered result is inadmissible. | Multiplicity accounting. | `run_registry` writes before compute |
| R9 | **Do not pick a value for any open `P0:` decision.** If code needs one, read it from the frozen spec. If the spec is not frozen, fail closed. | Defaults chosen by a developer become silent decisions. | Spec schema: required fields, no defaults |
| R10 | **Stop and escalate** on any condition in §9. Do not work around it. | | |
| R11 | **A profitable chart is not a fillable trade.** Never treat minute-bar `high`/`low` alone as proof of executable trigger, exit order or tradable liquidity. | Prevent phantom alpha. | Temporal order-event test, execution quality report |
| R12 | **Never choose the day's best breakout in hindsight.** Portfolio entries must be processed chronologically under capital and concurrency limits; tie-breaking is frozen before results. | Prevent impossible portfolio selection. | Global event scheduler + replay fixtures |
| R13 | **No automatic “AI improvement loop” on P4 or P5.** AI may explain failures and propose separately registered successor ideas, but cannot modify frozen RANGE-002 for another try. | Protect honest independent tests. | Spec-hash checks, exposure inheritance, workflow approvals |
| R14 | **No paper/live orders until the executor passes isolated dry-run, idempotence, risk and stop-protection tests.** | Avoid operational loss even with promising research. | Order-state machine / shadow replay / owner release |
| R15 | **No retroactive fill at an already-crossed stop after the order is armed.** Broker/order acknowledgement and price crossing are separate events; choose the approved policy for a crossed trigger. | Backfilled fills inflate realized opportunity capture. | ACK/ARM fixtures and event ledger |
| R16 | **Do not make an invalid random baseline appear weak by skipping its difficult observations.** Random controls must have causal risk eligibility and log invalid/skipped draws with equivalent opportunity accounting. | Biased controls can manufacture incremental alpha. | Baseline matching report and reproducible seeds |
| R17 | **Controls before strategy.** In every guarded P3/P4 run, engine-validation controls are computed and checked while strategy results stay sealed. Strategy results are unsealed only if the controls pass. | A failing control seen after the results cannot cleanly void the run. | Two-stage sealed run (WP4.0) |

---

## 1. Scope

### 1.1 In scope

- Research harness for RANGE-002: data, PIT universe, signal, fill simulation, risk sizing, baselines, statistics, and the audit pack.
- Governance plumbing: frozen spec, trial and exposure ledgers, results guard, holdout token, and the ADR 0037 non-equivalence check.
- RNG-001 replay chain (reproduce the archived evidence with the old engine) as an engine-validation control.
- P5 paper executor on a **new** dedicated paper account, with reconciliation and monitoring.
- The P6 decision pack (evidence bundle only; the decision is the owner's).

### 1.2 Out of scope

- Live trading. P6 can at most approve a restricted small live pilot under a separate plan.
- Any change to RNG-001, user 2, or other strategies.
- Futures, options, short selling, overnight holds.
- Any variant beyond A and B (§2.2). New variants need a **separate research registration and independent validation evidence**; the automatic naming convention is subject to platform registry rules (do not assume RANGE-003 is available).
- ORM-001 (opening-range reclaim). Its relationship to RANGE-002 is an open P0 decision (D09).

---

## 2. Strategy specification (implementation view)

This restates v0.4 chapter 4 as a config contract. **The source of truth is the frozen spec file**, not this table.

### 2.1 Rules

| Element | Rule | Config key |
|---|---|---|
| Instruments | US common stocks on major exchanges, including later-delisted names | `universe.instrument_types` |
| Universe | Rebuilt monthly. Uses only information visible on the prior trading day: top-N by 20-day average dollar volume, prior close > $10 | `universe.n` (`P0:` initial proposal 100), `universe.min_price`, `universe.adv_window` |
| Data | Licensed SIP 1-minute bars, regular trading hours, `America/New_York`, exchange calendar including half-days | `data.feed = "sip"`, `data.vendor` (`P0:`) |
| Opening range (OR) | High and low of bars 09:30:00–09:59:59. Frozen at 10:00:00. No later bar may change it. | `signal.or_start`, `signal.or_end` |
| Eligibility | Symbol-day needs a complete OR under the `P0:` rule. **A minute with no trades (`NO_TRADE_MINUTE`) is not missing data**; only a vendor/data gap (`DATA_GAP`) counts against completeness. OR width must be > 0 and ≥ `P0:` minimum. | `signal.or_completeness_rule`, `signal.min_or_width_ticks` |
| Entry trigger | Buy-stop at OR high + 1 valid tick. Active 10:00:00–14:59:59. First trigger only. One entry per symbol per day. No add-ons, no re-entry. Long only. | `signal.entry_window`, `signal.tick_offset = 1` |
| Initial stop | OR low | `exit.stop = "or_low"` |
| Variant A (primary) | Exit at the stop, or at the end-of-day flat time | `variants.A` |
| Variant B (secondary) | Target = fill price + 2·R_fill. Otherwise the stop or the end-of-day flat. | `variants.B.target_r = 2.0` |
| End-of-day flat | 15:55 ET on full days. On half-days, a `P0:` offset before the early close. | `exit.eod_flat`, `exit.halfday_offset_min` (`P0:`) |
| Costs | Base 5 bps per side; stress 15 bps per side. Spread, fees, impact and slippage are itemized and not double-counted. | `costs.base_bps_per_side`, `costs.stress_bps_per_side`, `costs.components` |
| Risk per trade | 0.25% of equity divided by R_pre (proposal) | `risk.per_trade_pct` (`P0:`) |
| Portfolio limits | Gross exposure, per-name cap, max concurrent positions, daily loss limit, participation cap | `risk.*` (all `P0:`) |

### 2.2 Variants and test order

- Exactly two variants: **A (primary)** and **B (secondary)**.
- Test order, whether B can be promoted on its own, and the Holm family are `P0:` (D02). They are encoded in `stats.hypothesis_family`.
- Code must reject a spec that declares a third variant.

### 2.3 Non-equivalence to RNG-001 (ADR 0037)

| | RNG-001 | RANGE-002 |
|---|---|---|
| Economic idea | Mean reversion inside the range | Continuation out of the range |
| Entry | Buy near support / OR low | Buy-stop above OR high |
| Exit logic | Sell near resistance | Stop at OR low; time exit or 2R target |
| Filters | VWAP bands / VWAP reclaim + SPY gate | None |

This table is the **input** to the ADR 0037 automated check (WP0.5). It is not the verdict. Registration is blocked until the check passes.

### 2.4 Economic thesis — required before expensive data/engineering work (NEW)

**Candidate thesis, not a proven fact:** A liquid stock making a first upward break of the fully formed 09:30–10:00 range *might* continue because price discovery, delayed institutional participation or information repricing persists after the first 30 minutes. Competing explanations include random volatility, opening-auction reversal, crowded breakouts, spread/impact costs and market beta. The test must distinguish these alternatives.

**Research questions the trading expert and developer must sign off before P0:**

1. **Why this entry should work:** What behavior is expected between 10:00 and 15:55, and why should one tick above OR high be a meaningful trigger? What observable outcomes would falsify it?
2. **When it cannot work:** Whipsaws, wide opening ranges, trendless markets, news halts, excessive gaps, thin quotes and strong adverse reversal. Describe failure modes **without retroactively filtering them out**.
3. **Reward/risk mechanics:** With the stop at OR low, is `R_pre` so large that `2R` is rarely reachable before close? Compare *distributions* of OR width, entry-to-stop distance and available time, not post-hoc successful subsets.
4. **Independent value:** Is performance explained by exposure to SPY/sector momentum or by a plain ORB rule? Pre-register diagnostic baselines; do not make a new winner-selection criterion after seeing data.
5. **Tradability:** Are the signals frequent enough to reach 300 P4 trades and 100 P5 trades given monthly top-N, portfolio limits and order rejection? Eligibility and theoretical capacity **may be assessed return-blind**, but realized opportunity frequency that depends on future high prices is a return-derived signal statistic and requires `results_guard`.

**Deliverable:** `docs/implementation/evidence/range_002/economic_thesis.md`, signed by research lead and a trading expert. Include the hypothesis, predicted failure modes, causal alternatives, measurement plan, and which observations are descriptive versus binding gates. **Do not fabricate a narrative to justify a later result.**

### 2.5 Return-blind feasibility and unit economics (NEW)

Before P1, validate only authorized *non-return* information: data licensing/coverage, PIT identity, exchange hours, quote availability, vendor rate limits, estimated data cost, expected compute/storage budget, broker order types, and simulation feasibility. Predefine formulas and decision constraints for:

- Break-even: `expected_gross_edge_per_trade > spread + fees + slippage + impact` **after** accounting for turnover and order failures; an expectancy estimate is not available until an authorized P3 run.
- Capital efficiency: portfolio return should reflect capital actually tied up, including simultaneous signals, unfilled orders, marketable order buffers and abandoned opportunities.
- Stop width: wide OR → larger `R_pre` → fewer shares. Record rejected-for-capacity/risk cases; **do not narrow the stop or pick a favorable width filter after P3/P4**.
- Costs: specify whether 5/15 bps per side represents an **all-in** assumption or a component. If all-in, do not add spread/slippage twice; if additive, name the separate fields and stress semantics. Decide before returns.
- Session termination: 15:55 exit and half-day handling need an attainable execution protocol (when order sent, cancel/replace, and fallback); a zero-overnight guarantee is not technically possible during halts/market outages—define protective response and alerting rather than asserting impossible fills.

**Deliverable:** `feasibility_report.md` with PASS / BLOCKED / UNKNOWN per requirement and named open decisions. Do not label the strategy economically viable using return-blind data.

### 2.6 Preserve A and B; document *potential* ideas without trading them (NEW)

Keep the approved candidate unchanged: A = OR-low stop / end-of-day exit; B = OR-low stop / fixed 2R target / end-of-day exit. **No additional filters or ATR stop, VWAP, volume, market-regime entry gate, dynamic target, or late-day cut-off may be activated in RANGE-002 merely because it appears promising.**

Instead, create a **non-executable successor hypothesis backlog** for trading-expert review, for example:

- OR-width relative to recent volatility as an *a priori* risk-efficiency hypothesis;
- breakout confirmation using causal, timestamped relative volume;
- SPY/sector trend alignment, market breadth or volume expansion;
- reject late or overextended breakouts on execution-risk grounds;
- dynamically scaled exits only where a new economic thesis exists.

Every item must identify the mechanism, required PIT features, anticipated costs, potential leakage, variant family, baseline and untouched future evaluation set. Backlog items are **not** implementation instructions or approved RANGE-002 modifications. Before a future strategy is run, the owner registers it and accounts for the accumulated search/multiple testing across related programs.

### 2.7 Success-path workflow and decision boundaries (NEW)

`Human hypothesis → return-blind feasibility → P0 signed freeze → P1 data → P2 engine/controls → P3 guarded development screen → P4 single independent holdout → P5 dedicated paper → P6 human decision`.

- **Success** means enough evidence of positive *net* economic value across relevant environments, realistic fills, costs and risks, then successful forward operations.
- **P3 STOP** or **P4 REJECT** means *this exact hypothesis* failed the declared test. Export unbiased diagnostics; do not quietly tune and rerun this candidate.
- **INCONCLUSIVE** means insufficient trustworthy evidence, not hidden PASS and not necessarily economic failure. Explain cause and obtain an explicit governance ruling for further work.
- **A successor** may be built from diagnosed weaknesses, but must keep predecessor exposure in its ledger and require genuinely new independent evidence. If no unexposed history remains, prospective evidence is often the only credible option.

---

## 3. Architecture

### 3.1 Planes and boundaries

```
┌──────────────────────── Research plane (no broker creds) ────────────────────────┐
│                                                                                   │
│  spec/ (frozen YAML + hash) ──► results_guard ──► run_registry (trial ledger)     │
│                                      │                                            │
│  data/: sip_loader ─► integrity_check ─► bar_store ─► pit_universe ─► calendar    │
│                                      │                                            │
│  engine/: or_signal ─► fill_model ─► risk_sizer ─► position_sim ─► trade_log      │
│                                      │                                            │
│  controls/: random_entry · naive_orb · time_shuffle · rng001_replay               │
│                                      │                                            │
│  stats/: day_cluster_bootstrap · holm · walk_forward · regime_split ·             │
│          half_split · cost_stress · redundancy · funnel (CAP-025)                 │
│                                      │                                            │
│  audit/: audit_pack writer (immutable, hashed)                                    │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │ governed artifact (spec hash + verdict)
                                        ▼
┌──────────────── Execution plane (P5 only, after P4 PASS + owner approval) ────────┐
│  range002_executor ─► OrderRouter (authenticated) ─► risk engine ─► broker (paper) │
│  reconciler · daily-flat watchdog · alerts (SNS) · fill-vs-model comparator        │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Proposed layout

> **WP0.1 must confirm this against the repo before any file is created.** Follow the existing conventions (where research scripts, strategies, evidence docs and ADRs live). If the repo's convention differs, use the repo's and record the mapping in the PR description.

```
apps/backend/app/research/range002/
    spec/            schema.py, loader.py, hashing.py
    governance/      results_guard.py, run_registry.py, exposure_ledger.py, holdout_token.py, nonequivalence.py
    data/            sip_loader.py, integrity.py, bar_store.py, pit_universe.py, calendar.py, corp_actions.py
    engine/          or_signal.py, fill_model.py, risk_sizer.py, position_sim.py, trade_log.py
    controls/        random_entry.py, naive_orb.py, time_shuffle.py
    stats/           bootstrap.py, multiplicity.py, walk_forward.py, splits.py, costs.py, redundancy.py, funnel.py
    audit/           audit_pack.py
apps/backend/app/strategies/range002/
    executor.py      (P5 only)
    reconciler.py
apps/backend/scripts/research/range002/
    freeze_spec.py, build_data.py, coverage_report.py, run_p2_validation.py, run_p3.py, run_p4.py, build_audit_pack.py
apps/backend/scripts/research/range/        (existing RNG-001 scripts: read-only; used by rng001_replay)
docs/implementation/evidence/range_002/
    RANGE-002_frozen_spec_v1.yaml, exposure_ledger.md, nonequivalence.md, evidence/…
apps/backend/tests/research/range002/  (unit, property, integration)
```

### 3.3 Event-time, data and order architecture requirements (NEW)

**Mandatory global ordering:** build per-symbol candidate events, then process a single merged chronological event stream across the portfolio. For same-timestamp candidates, use a P0-frozen priority rule that does not depend on future profit. Reserve cash/risk at order submission, release on cancel/expiry/fill, and reconcile partial fills and overlapping orders. **A symbol-by-symbol backtest followed by a portfolio merge must not retroactively award scarce capital to the best trades.**

**Order-state machine:** `ELIGIBLE → SIGNAL → ORDER_PENDING → PARTIAL/FILLED/CANCELLED/REJECTED → PROTECTED → EXIT_PENDING → FLAT/EXCEPTION`. Record source time, decision time, submission time, acknowledgement time, exchange/broker event time and ingestion time separately. State transitions must be idempotent across retries/restarts; exactly-once intent is enforced with client order IDs and reconciliation, not assumed from the broker.

**No future availability:** Freeze the OR only after all contributing bars are available and final; define bar timestamp semantics and vendor delay. A 09:59 minute bar is not necessarily visible at exactly 10:00:00. The research harness and paper executor must use the same **decision-available-at** rule and latency assumption. Missing/delayed bars block entries; never retrospectively trade a signal with a later timestamp.

**Order-type parity:** Define whether the breakout is entered using stop-market, stop-limit, or an emulated stop through the broker; define gaps, extended fills, time-in-force, duplicate/partial orders, and the protective stop activation *after confirmation of entry fills*. Verify actual supported broker semantics instead of assuming a bracket order protects an unfilled trade.

**Risk accounting:** Keep proposed order price/risk estimate distinct from actual fill, portfolio equity, trading cash and mark-to-market exposure. Never count a hypothetical exit at the stop as a guaranteed worst-case loss. Track stop-gap overrun and potentially unbounded loss when stops cannot execute.

---

## 4. Work packages

Each work package lists its tasks, the files involved, the acceptance criteria, and its phase gate. **A work package is done only when every acceptance criterion passes in CI and the evidence is committed.**

### WP0 — Registration and governance plumbing (phase P0)

| ID | Task | Acceptance criteria |
|---|---|---|
| WP0.1 | **Repo reconnaissance.** Map existing modules this plan reuses: range backtest engine and replay scripts, CAP-025 funnel, PIT/permaticker identity, session calendar, trial ledger, governed-artifact envelope, OrderRouter and risk engine, paper-account provisioning. | `docs/implementation/evidence/range_002/recon.md` lists each reusable module with its path and SHA and states reuse / wrap / do-not-use. Do not create new files before this is merged. |
| WP0.2 | **Spec schema.** Pydantic (or the repo's equivalent) schema for every key in §2.1 and §5. Every `P0:` field is required and has no default. Unknown keys are rejected. More than two variants is rejected. | Loading a spec with a missing `P0:` field fails with a named error. Loading a valid spec gives a canonical JSON with a stable `spec_sha256`. Tests cover key order, whitespace and float formatting so the hash stays stable. |
| WP0.3 | **Freeze tool.** `freeze_spec.py` writes `RANGE-002_frozen_spec_v1.yaml` plus `spec_sha256`, applicable initial toolchain SHA and owner sign-off fields. **Engine code does not yet exist at P0**; its SHA is pinned after P2 in a signed append-only execution manifest rather than mutating the frozen research spec. The frozen research spec is immutable after sign-off. | A frozen spec with an empty sign-off cannot be used by `results_guard`. Editing a frozen file changes the hash and every later run refuses it. The P2 execution manifest references the original unchanged spec SHA. |
| WP0.4 | **Results guard.** The single entry point for any computation that produces returns. A **runtime authorization capability** is required by the engine/statistics entry points; static CI import rules are a second line of defense, not the only guard. It checks: (a) the spec is frozen and signed; (b) the requested partition is authorized for this phase; (c) the partition does not overlap the exposure ledger; (d) a trial-ledger row was written first; (e) for P4, a valid unused holdout token exists. It fails closed. Partition types are a closed set: `DEVELOPMENT`, `HOLDOUT`, `PAPER`, and `REPLAY_RNG001` (exposed 2026 data, engine validation only; its outputs can never be cited as RANGE-002 evidence). | Unit tests show refusal for each failure case. Integration tests prove direct imports, scripts, notebook-like access, batch jobs and unregistered runs cannot obtain a valid results capability. CI import-lint also covers known entry points. |
| WP0.5 | **ADR 0037 non-equivalence check.** Run the platform's rejected-pattern auto-check against the RANGE-002 spec. Commit `nonequivalence.md` with the §2.3 table, the check output, and the ORM-001 relationship (D09). | The check output is attached. If the check flags equivalence, **stop** (§9). |
| WP0.6 | **Exposure ledger.** Record exposed data: RNG-001 backtest window 2026-01-02 → 06-12, the entry study (18 names, 126 sessions, through July 2026), E-vwap+gate splits, and any AI-session contact with 2016–2025 data (who, when, what was seen). | Machine-readable `exposure_ledger.yaml` that `results_guard` consumes. The 2022–2025 contact audit is signed (D01). If 2022–2025 is materially exposed, **stop**: the holdout must be replaced by owner decision. |
| WP0.7 | **Trial ledger entry.** Register RANGE-002 in the existing ledger, declaring prior exposure and the two-variant family. | Ledger row exists with spec hash, family, and planned runs (P3 ×1, P4 ×1). |
| WP0.8 | **AI provenance record.** Record the model identifiers, prompt/input summaries, and generated-code SHAs that contributed to the spec and engine, plus the human who confirmed the final logic. | `ai_provenance.md` committed and linked from the spec. |
| WP0.9 | **Economic thesis sign-off (NEW).** Research lead and experienced trading reviewer write why first upward OR breakout might have a net continuation edge and what would disprove it. | `economic_thesis.md` records mechanism, competing explanations, predeclared diagnostics and signatures; no return-derived examples added after P3. |
| WP0.10 | **Return-blind feasibility (NEW).** Verify order support, SIP minute-history rights, quote/timestamp limitations, market calendar, cost attribution, storage budget and research-capacity bounds. | `feasibility_report.md` gives PASS/BLOCK/UNKNOWN with evidence and cannot contain performance metrics. |
| WP0.11 | **Candidate-selection audit (NEW).** Document all prior breakout studies, A/B ideas, rejected hypotheses and access to development/holdout results; distinguish historical exposure from newly proposed assumptions. | `hypothesis_lineage.yaml` linked to exposure ledger; all related runs and AI-assisted ideation accounted for. |
| WP0.12 | **Portfolio/order contract.** Agree tie-break, buying power reservation, order type, fill latency, simulated arming and crossed-before-arm policy (WP2.1A), stop activation, same-minute causality, late-day cancellations and failure states (D14). | Executable state-machine schema and deterministic fixtures approved before engine implementation. |

**P0 exit gate.** The spec is frozen and signed, with `spec_sha256` recorded. The non-equivalence check passes. The exposure ledger is signed. Decisions D01–D18 (§10) are recorded in the spec; D13–D16 are within v0.4 scope (§0A) and need owner values, not a design addendum. WP0.9–0.12 are signed and any economic/technical feasibility blockers are resolved.

### WP1 — Data (phase P1, return-blind)

| ID | Task | Acceptance criteria |
|---|---|---|
| WP1.1 | **ADR 0033 pre-check.** Confirm the bar-cache writer (a) scopes `.empty` markers to the returned range only, (b) treats an exactly-page-limit response as possibly truncated, and (c) chunks cold fetches. If not, use the RANGE-002 monthly-chunked SIP loader for all RANGE-002 fetches (D11); do not modify the shared cache. | A written finding with code references. Test: a simulated 10,000-row page triggers continuation or failure, never a silent `.empty`. |
| WP1.2 | **SIP 1-minute loader.** Fetch 2016–2025 regular-hours bars for the union of all monthly universes, in monthly chunks. The feed is asserted to be `sip`. Raw and normalized checksums are stored. | `data_manifest.json` with vendor, feed, adjustment rule, date range, row counts, and per-file SHA-256. The loader raises if the feed resolves to anything except `sip`. |
| WP1.3 | **Vendor coverage check.** Confirm the licensed history starts on or before 2016-01-01 and covers delisted symbols. | If history or delisted coverage is short, **stop** (§9). The period may be shortened only by a rule pre-agreed in P0. |
| WP1.4 | **Calendar.** Exchange calendar with holidays, half-days and DST. 10:00 and 15:55 are correct in ET year-round. | Tests: DST transition days, Black Friday and Christmas Eve half-days, July 3, market-closure days. |
| WP1.5 | **PIT universe.** Monthly rebuild using only data visible on the prior trading day. Uses permaticker identity (not ticker strings) and includes delisted names. Daily data for ADV and price comes from the survivorship-free source. | `universe_YYYYMM.parquet` with permaticker, ticker as-of, ADV, price, and rank. A test shows a known delisted name appears before its delisting. A look-ahead test passes (shifting future data does not change any universe). |
| WP1.6 | **Corporate actions.** Split/dividend handling for intraday bars consistent with the daily source. Note: Sharadar `open`/`close` are **not** spinoff-adjusted (only `closeadj` is). Do not mix raw and adjusted series in a computation. | Test fixtures for a split day and a spinoff day. OR and stop prices are in the same price basis as fills. |
| WP1.7 | **Halts and anomalies.** Flag halts, price jumps and zero-volume minutes per symbol-day. Classify every absent minute as `NO_TRADE_MINUTE` (no trades printed; confirmed by daily volume/trade-count consistency or vendor metadata) or `DATA_GAP` (vendor gap, truncation, outage). | Counts by year and month, and for the 09:30–10:00 window specifically, split by class. A fixture shows a thin minute is not treated as a data gap. |
| WP1.8 | **Coverage report (return-blind).** Symbol-day coverage overall, by year, by month, and for the first 30 minutes. | Overall coverage ≥ 98% of symbol-days (v0.4 threshold). The report contains **no** return, trade-entry-trigger hit, strategy P&L or win-rate fields; a CI check fails if it does. Report explicit denominators and exclusion reasons so 98% cannot be achieved by silently dropping unavailable symbols. |

**P1 exit gate.** The ADR 0033 finding is resolved, coverage is ≥ 98%, the data manifest hash is recorded, and no returns were read. **Verify coverage against the actual PIT eligible population, not merely symbols that the loader happened to fetch.** Document data-availability latency for paper execution, licensing of historical and delisted symbols, and quote absence where intrabar validation is needed.

### WP2 — Engine and controls (phase P2)

#### WP2.1 OR signal — `engine/or_signal.py`

```python
def compute_or(bars_0930_0959: Bars, rule: CompletenessRule) -> OpeningRange | Ineligible:
    """High/low of 09:30:00–09:59:59. Returns Ineligible(reason) if incomplete or width < min."""

def entry_trigger(or_: OpeningRange, tick: Decimal) -> Decimal:
    """OR high + 1 valid tick (tick size by price band per exchange rules)."""
```

- **Normalize the feed's timestamp convention before aggregation.** A SIP bar stamped `09:59:00` may represent the half-open interval `[09:59,10:00)`; some feeds label bars at the interval end. Store `bar_start`, `bar_end` and `available_at` explicitly. Verify the vendor's documented convention and delay before writing signal code.
- The OR object is immutable and has separate `window_end`, `finalized_at` and `available_at` timestamps. Never generate an order before **all** required opening-range bars are available; the clock may be later than 10:00. Any access to future bars inside `compute_or` raises an error. Trading begins only after required data is available (without retroactive execution).
- A buy-stop is **eligible to fill only after it has been acknowledged and armed** according to the frozen P0 order-state contract. If price crosses the trigger before acknowledgement, do not invent a fill at the stale trigger; record the crossed-before-arm state and apply the signed skip/reprice/cancel policy (no implicit choice).
- The tick size follows the price band. Sub-$1 names are excluded by the universe filter but still asserted.

#### WP2.1A Simulated order arming on historical bars (v0.4)

The historical harness has no broker acknowledgement, so arming must be modeled. All parameters are D14 values.

```python
decision_at = max(or_window_end, last_or_bar_available_at)     # vendor delivery delay applied
armed_at    = decision_at + latency.submit_ms + latency.ack_ms   # frozen latency model
first_active_bar = first bar with bar_start >= armed_at          # the order cannot fill before this bar
crossed_before_arm = any bar with bar_start < armed_at and bar_start >= 10:00 has high >= trigger
                     # plus the bar containing armed_at, since intrabar order is unknown
```

- If `crossed_before_arm` is true, apply the frozen policy: `SKIP` (no trade), `MARKET_AT_NEXT_ACTIVE_BAR_OPEN` (treat as an immediately triggered stop, filled at the first active bar's open plus slippage), or `REQUIRE_RETRACE` (arm only after price trades back below the trigger). The broker capability check (WP2.11) decides which of these the paper executor can actually reproduce; the research policy must match it.
- **This choice is outcome-relevant.** Fast breakouts at 10:00–10:02 may be a large share of signals, and `SKIP` removes them while `MARKET_AT_NEXT_ACTIVE_BAR_OPEN` fills them at a worse price. Report the share of signals with `crossed_before_arm = true` in the return-blind P1 funnel (it needs only prices relative to OR high, not P&L; confirm with the owner that this counts as return-blind, otherwise move it into the sealed P3 diagnostics). Report the result under both policies in P3 diagnostics; only the frozen policy counts for gates.
- Fixtures: breakout in the 10:00 bar with latency 0 vs 2 s; breakout before arming then retrace; gap above trigger at the first active bar.

#### WP2.2 Fill model — `engine/fill_model.py`

The defaults below are conservative. Values marked `P0:` come from the spec (D05).

| Event | Simulated fill |
|---|---|
| Buy-stop triggers inside a bar (`bar.high ≥ trigger`, `bar.open < trigger`) | **Candidate assumed fill only**, at `trigger + adverse slippage` under the frozen OHLC model; 1-minute high alone does not prove executable bid/ask, queue position, sufficient volume or that the stop order was active. Mark uncertainty. |
| Bar opens above the trigger (gap through) | `bar.open + slippage` (adverse). No fill at the trigger price. |
| Stop hit inside a bar | `stop − slippage` |
| Bar opens below the stop (gap down) | `bar.open − slippage` |
| Target (B) hit | `target − slippage`. A target is **never** credited in the same bar as the entry. |
| Entry and stop in the same bar | Assume entry, then stop (worst case). Mark the trade `path_ambiguous = True`. |
| Stop and target in the same bar | Assume the stop. Mark the trade `path_ambiguous = True`. |
| End-of-day flat | The liquidation intent is issued at `eod_flat − lead` (D14). The simulated fill is the open of the first bar starting at or after `intent + latency`, minus slippage. The fill may never come from a bar that started before the intent. |
| Halt during a position | **`P0:` decision required.** If the market is halted, label position `EXIT_UNAVAILABLE` and accrue gap/overnight risk; do not assume exit at an unavailable bar or claim guaranteed flat. |
| No executable quote at the trigger | No entry. Log the reason. |

- The share of `path_ambiguous` trades and the sensitivity of results to that assumption are mandatory report fields.
- Partial fills: v0.4 requires a rule. In backtest, model a participation cap per minute (`risk.max_participation`, `P0:`). The unfilled remainder is cancelled, not carried. The fill size must not exceed **causally available** liquidity assumptions; bar-volume assumptions are disclosed.
- **Avoid double counting costs.** If base/stress bps already include execution spread/slippage, do not add a second fill adjustment. Produce an auditable transaction-cost bridge and label which parts are price adjustments versus P&L debits.
- Exits and entries must respect order-active timestamps; same-bar high/low ambiguity and unexecutable quotes are separate categories. Do not infer event chronology from OHLC ordering.
- Fill-model realism must be compared with broker paper acknowledgments and, where available, quote-level replay; paper fills are not proof of production exchange execution quality.

#### WP2.3 Risk sizing — `engine/risk_sizer.py`

```python
R_pre  = est_entry - stop                 # est_entry = trigger + expected_slippage
qty    = floor(risk_budget / R_pre)
qty    = min(qty, floor(notional_cap / est_entry), participation_cap_shares,
             floor(cash_available / est_entry), max_shares_after_portfolio_limits)
# after fill:
R_fill = avg_fill - stop                  # must be > 0, else the trade is invalid → exit immediately, log
actual_risk = qty_filled * R_fill
if actual_risk > risk_budget * (1 + tol): apply P0 rule (reduce / protective exit)   # D05
```

- Concurrency, gross-exposure and daily-loss limits are checked before **submitting** each order; reserve estimated notional and risk until it is filled or cancelled. A breach blocks the entry. Exits are never blocked by limits.
- The estimated stop-risk `R_pre` is a sizing quantity, **not a guaranteed realized loss**. Gap-through entries, gap-down exits and stop failures can exceed the nominal per-trade limit. Separate `estimated_risk`, `worst_modeled_risk`, `actual_stop_risk`, `realized_loss` and `unprotected_duration_ms`.
- Round **every** quantity limit down to nonnegative whole shares and test buying power, pending orders, long-only enforcement, corporate actions, and partial fills. Invalid or zero share quantities skip the entry, never force one share.
- Every trade logs R_pre, R_fill, the budget, the binding constraint, and any adjustment.

#### WP2.4 Position simulation — `engine/position_sim.py`

- Build symbol-level candidate events, but **execute a single portfolio-wide chronological event loop** with deterministic tie-breaking, pending-order reservations and simultaneous-event handling. A post-hoc per-symbol merge is not sufficient to enforce scarce capital, order limits or daily risk.
- Deterministic: same inputs, spec and seed give byte-identical `trades.csv`.
- No overnight positions. An assertion at end of day fails the run if any position is open.

#### WP2.5 Controls — `controls/`

| Control | Definition | Purpose |
|---|---|---|
| Random-entry baseline | Define the assignment population causally at 10:00, **never conditioned on future breakout success**. Randomize among predeclared feasible entry instants with risk `R_pre > 0` under the identical OR-low stop, same portfolio constraints/costs and causal order activation. Excluded or infeasible observations must be counted rather than silently dropped; compare matched portfolios or clearly justify matching. The baseline's feasibility filter itself must not use future prices. Lock seeds, repetition count, trial unit and treatment of `no feasible random entry` before results. | Primary paired comparison (G5); prevent future-conditioned baselines, invalid stop geometry and selective control attrition. |
| Naive ORB | Pre-frozen simple breakout (e.g. OR high touch, no tick offset, same exits) | Tests whether the specified rules add value |
| Time-shuffle negative control | Entry minutes permuted across days following a frozen, causal procedure | Unexpected positive effects prompt a diagnostic investigation; **a positive control result is not by itself proof of a bug**, nor is its absence proof of no leakage. |
| No-information trigger | Trigger at a random price level drawn independently of future bars, with comparable risk/cost distribution | Detects apparent edge created by market drift, risk budget or simulation artifacts. |
| SPY reference | Buy-and-hold and intraday SPY over the same days | Economic context only, not a gate |

#### WP2.6 RNG-001 replay chain (engine validation)

Two independent evidence chains, as v0.4 requires:

1. **Old engine, old rules, rebuilt archive data** (IEX 5-minute bars). Reproduce the figures in `docs/implementation/evidence/range_rejection/range_evidence.json`: 102 trades, profit factor 1.271, bootstrap CI [−$19.74, +$57.53], and the walk-forward table. Use the existing scripts in `apps/backend/scripts/research/range/` read-only. Run through `results_guard` with partition `REPLAY_RNG001`.
2. **New engine correctness.** Hand-built edge-case fixtures with expected outputs computed independently (spreadsheet or a separate reference implementation). The new engine is **not** required to match RNG-001's old numbers. Any difference is explained line by line.

If chain 1 cannot reproduce the archived results, investigate and document the cause **before** any RANGE-002 result-bearing run (§9); only a written independent governance ruling may permit proceeding without byte/numerical reproduction. Do not adjust RNG-001 to fit the archive.

#### WP2.7 Required unit and property tests

- 09:59:59 / 10:00:00 boundary; normalize vendor start/end-stamped bars so an interval beginning at 10:00 cannot affect the OR, and a 09:59 interval cannot be used until delivered.
- DST days; half-days with an early flat.
- Gap-through on the trigger, gap-down through the stop; crossed-trigger before broker acknowledgement cannot be filled retroactively.
- Same-bar entry and stop; same-bar stop and target; target in the entry bar (not credited).
- R_fill ≤ 0 after an adverse fill.
- Participation cap binding; concurrency limit binding; daily loss limit hit mid-day.
- Split day, spinoff day, delisting mid-month, halt and resume.
- Duplicate trigger in the same day (must be ignored), and re-entry after a stop (must be ignored).
- Determinism (two runs give identical hashes); a random-entry draw below/equal to the OR-low stop is handled by the signed baseline policy and never generates invalid positive-risk fills.
- Property test: no entry precedes both bar availability and order acknowledgement; a regular executable session exits by the frozen cutoff. Halts/outages must create a retained-position incident, not an imaginary exit; validate the fall-back playbook.

#### WP2.7A Baseline construction and temporal-validity fixtures (v0.3)

**Why:** A random entry with the same OR-low stop is not always a valid economic comparator. A price below that stop gives `R_pre <= 0`, and using the day's successful breakout to choose random samples contaminates the control. The current implementation must not bury this asymmetry.

- Define the **eligible unit** before returns: security/session at 10:00, or a prospectively assigned entry opportunity based only on information available at decision time. Document which universe and orders are shared with RANGE-002.
- Implement an identical order state, sizing, portfolio clock, time cutoff, commissions and slippage contract for experimental and control orders. Require a valid positive pre-trade stop distance, or explicitly define a replacement stop mechanism **for both treatments** through research-design approval (never silently change the baseline after outcomes).
- Treat invalid control draws as `NOT_EXECUTABLE` and preserve the denominator; if a control redraws, the number of attempts and permitted redraw procedure must be frozen. Report comparison at portfolio/day level with a valid paired unit, not only trade-only means that select differing winners.
- Test the control with synthetic uptrend/downtrend and a simulated nonbreaking day: the control must not use a future cross of OR high to qualify an observation.
- **Acceptance:** `baseline_spec.yaml`, paired-unit explanation, exhaustive counts by draw status, and `baseline_validity_tests.json`. A statistical reviewer confirms estimand/comparability before P3. No gates change without explicit P0 decision.

#### WP2.8 Portfolio scheduler and realistic opportunity selection (NEW)

- Implement `engine/portfolio_clock.py` for a global event stream: OR freeze, signal eligibility, pending/partially filled orders, protective stop activation, exits, risk state and intraday equity updates.
- When multiple symbols trigger simultaneously, **pre-frozen** order priority (e.g., canonical security ID) and allocation policy determine which signals fit the risk/cash budget; this is **not** optimized by historical returns.
- Distinguish `signal_count`, `submitted_count`, `filled_count`, `blocked_count`, `cancelled_count`, `exit_count` and `missed_due_to_capital`. The funnel must reconcile exactly with the trial ledger.
- **Acceptance:** synthetic two-symbol timestamp collision causes identical allocations across reruns; shifting future prices does not change any order scheduled before the shift.

#### WP2.9 Causality/quote execution contract (NEW)

- Test bar-availability timestamps, delayed SIP feed, stop order becoming active after acknowledgment, quote gaps, price band tick validity, minimum increments and fill uncertainty with fixtures.
- A triggered OHLC price is not automatically marketable. If quote-level history is not available, use a documented conservative model with a sensitivity envelope and record `execution_model_uncertainty`; do **not** claim execution-ground truth.
- **Acceptance:** no order can be timestamped before its market data became available; entry/gap/stop/target and EOD-fill tests are hand-verified without reading future bars.

#### WP2.10 Execution state machine and restart safety (NEW)

- Enumerate client order IDs, state transitions, duplicate messages, partial fills, cancel/replace, residual exposures, stop attachment failures, late-day orders and broker disconnects. The order router must be the sole owner of auth and execution privileges.
- **Acceptance:** restart/retry fixtures submit no duplicate order, all filled positions get protective stops promptly, and reconciliation fail-closed blocks *new entries* while preserving exits and protective monitoring.

#### WP2.11 Market-data / broker timestamp interoperability (v0.3)

- Store exchange-event time, vendor publication time, local receive time, strategy decision time, router submission time, broker acknowledgement time and activation time (when available). **These are different clock domains; normalize to UTC for ordering and retain New York session labels.**
- Reconstruct the first 10:00 eligible decision using only delivered 09:30–09:59 intervals. Simulate missing late minute, clock skew and duplicated bars. Late data should reduce opportunity count, not permit retroactive participation.
- Pin a broker-specific order-type capability report: native stop-market vs stop-limit, accepted time-in-force, extended-hours flags, stop/target linkage, auto-cancellation, expiration and reject semantics. Do not infer support from an SDK method name.
- **Acceptance:** `data_to_order_latency_contract.md`, executable protocol fixtures and a signed order-capability check. If broker cannot support the chosen semantics, stop for owner decision rather than simulate a different strategy unnoticed.

**P2 exit gate.** All tests pass (WP2.1–WP2.11), chain 1 reproduces (or the cause is documented and approved by written governance ruling), and the synthetic and return-blind controls pass. Historical negative-control returns are computed only inside the guarded P3 run's sealed control stage (WP4.0), not as an earlier P2 preview. The engine version SHA is pinned in the signed execution manifest, which references the immutable P0 spec.

### WP3 — Statistics and diagnostics (built in P2, used in P3–P5)

| Module | Specification |
|---|---|
| `bootstrap.py` | **Day-clustered block bootstrap** (design reference only: `factor_data/evidence.py` circular-block/cluster functions and `services/market_projection/validate.py` stationary resampler; no existing implementation is claimed, and MR-002 is not a source). Resampling method, block length, repetitions, confidence level and hypothesis adjustment are open D06 owner decisions. All trades on one day form one cluster; blocks of consecutive trading days are drawn with the frozen mean block length. Repetitions, CI type and seed are in the spec (D06). Outputs: one-sided bootstrap p-value and lower bound for mean net R per trade, and the same for the paired G5 difference (WP3.3). |
| `multiplicity.py` | Holm adjustment over the family declared in `stats.hypothesis_family`. Also reports unadjusted values, clearly labelled. |
| `walk_forward.py` | Yearly windows. Profit factor, mean R and trade count per window. |
| `splits.py` | Time halves of the evaluation window. Market-regime split (D12 definition, e.g. SPY vs its 200-day average or intraday VWAP). Reports metrics per regime and the share of total P&L per regime. |
| `costs.py` | Base and stress cost application from itemized components. Both results are reported. |
| `redundancy.py` | Daily net-return correlation with each approved strategy. Above 0.85 is flagged as redundant. |
| `funnel.py` | New implementation of the CAP-025 charter (no existing wrapper or library module). Reports eligible days, trigger rate, the share of triggered days that hit the stop, hit the target (B), or were flat at end of day, and the share of trades that fell back inside the OR within N minutes. |
| Economics | Net P&L, maximum drawdown and its duration, capital use, turnover, tail losses (worst 1% of days), and concentration by year, sector and name. |

#### WP3.1 Opportunity-to-profit attribution (NEW)

Generate a deterministic **strategy performance funnel**, with stages:

`PIT symbol-days → complete OR → width eligible → signal-eligible → first trigger → order admissible → order submitted → order filled → protected → exited → net profitable/losing`.

For each stage report counts, losses/exclusions and root-cause codes; measure results by **actual risk-constrained filled trades**, not hypothetical best candidates. Include `net_R` and `net_PnL` *only* in authorized P3/P4/P5 audit packs. Return-blind P1 reports may include only data-coverage funnel portions.

Break down gross opportunity into: gross theoretical move (clearly non-tradable reference), allowed order fills, execution costs, stop losses, missed opportunities, exposure limits and portfolio net outcome. Quantify which component dominates **without changing the strategy specification**.

#### WP3.2 Market-path and payoff diagnostics (NEW)

Report OR width/price/volatility, trigger time, exit time, maximum favorable/adverse excursion (MFE/MAE) measured **after entry**, time to stop, time to 2R, entry-to-EOD available minutes, path ambiguity, adverse gaps, and positive/negative contribution by time/regime/security. **Do not use MFE/MAE to choose a new target on P4.**

Define a labeled diagnostic (`MFE_R`, `MAE_R`, `time_to_2R`, `OR_reentry_within_N`) with units, valid time boundaries and missing rules. For variant B, `2R` must use actual fill price and risk, not the trigger price. For variant A, do not backfill a hypothetical 2R exit into its performance.

#### WP3.3 Economic viability and statistical robustness (NEW)

Output per-account daily equity and buying-power series, geometric annualized return (when defined), dollar net P&L, PF, expectancy per trade/day, net R, max drawdown and duration, volatility, downside/tail losses, participation, slippage/fees decomposition, cost-stress breakeven and trade concentration. Compare portfolio performance to simple ORB and market exposure at comparable assumptions; comparator values remain diagnostic unless v0.4/P0 explicitly makes them binding.

For adjusted confidence intervals: specify the **actual** approved procedure. Do not call an unadjusted bootstrap CI “Holm-adjusted.” **Recommended default for D06 (owner to confirm):**

- **G4.** For each hypothesis in the P4 family, compute the one-sided bootstrap p-value `p = share of resampled means ≤ 0` for mean net R per trade. Apply Holm at α = 0.05 (one-sided). Report the matching adjusted lower bound: the hypothesis tested at step k uses the `1 − α/(m − k + 1)` lower quantile.
- **G5 estimand.** On each resample of trading days, compute `mean net R per RANGE-002 trade − mean net R per random-entry trade`, using only trades on the resampled days for both series. This pairs at the day level without requiring both to trade on the same symbol-day. Days with RANGE-002 trades but no valid random draw are counted and reported, not dropped silently.
- If D02 chooses a fixed-sequence (A then B) procedure instead of Holm, the gate function must implement that procedure exactly and label it so.

#### WP3.4 Diagnostic interpretation without overfitting (NEW)

`diagnosis_report.md` separates one of: `NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, or `UNCLASSIFIED`.

A label is **explanatory, not a license to override REJECT**. A distinct successor proposal may cite it in a future owner-approved research registration with independent validation data.

#### WP3.5 Success diagnostics that do not change the candidate (v0.3)

Return-bearing diagnostics run **only after P0/P2 authorization** and cannot be used to adjust RANGE-002 A/B and retest the holdout. Report, for both variants, separately:

1. **Signal mechanics:** number of eligible universe-days; complete ORs; pending-stop orders; actual stop crossings after arming; theoretical signals versus fillable signals.
2. **Edge at each stage:** mark-to-market edge before costs; fill-adjusted performance; after-cost performance; portfolio after capital and risk constraints. Negative net outcomes must remain visible.
3. **Stop/target geometry:** distribution of opening-range width, `R_pre`, `R_fill`, time remaining and realized MFE/MAE as *diagnostics*; no hindsight stop adjustment.
4. **Opportunity capture:** what fraction of signals is missed due to vendor latency, acknowledgement, buying power, participation, halt, order rejection or no quote.
5. **Fragility:** fraction of P&L from ambiguous bars, individual dates/tickers/sectors, one regime, unrealistic gap fills, and nonreproducible data paths.
6. **Economic significance:** profit in absolute dollars, R and percent of capital committed; time in market; drawdown duration; liquidity footprint. Statistical significance alone is insufficient.

Export one machine-generated `edge_attribution.json` per variant with counts and reconciled P&L waterfall. Label **observational explanations** clearly; any suggested new rule goes into an unexecutable successor backlog and needs a new approved registration and independent data.

### WP4 — Decisive runs (phases P3 and P4)

#### WP4.0 Two-stage sealed run (applies to P3 and P4)

1. **Stage 1 (controls).** `results_guard` authorizes the run. The engine computes RANGE-002 and all controls, but writes strategy outputs to a sealed store (encrypted or access-controlled; hash recorded). Only control outputs are readable: time-shuffle, no-information trigger, and engine sanity checks (no entry before 10:00, flat at close, ledger reconciliation).
2. **Control check.** If a control fails, the run verdict is `INCONCLUSIVE_ENGINE` and the sealed strategy outputs are **never opened** for this run. The defect goes through the defect-only rerun protocol.
3. **Stage 2 (unseal).** If the controls pass, the seal is opened, the hash is verified, and gates are evaluated. The unseal event is logged with timestamp and operator.

#### WP4.1 P3 development run (2016–2021)

- One governed P3 development-screen run for frozen variants A and B through `results_guard` (and only after P2 technical acceptance). This is **not** an open optimization loop. Produce WP3.1–3.4 diagnostics in its immutable audit pack.
- Outputs: the full audit pack (§7) plus the gate evaluation against the **P3 advance criteria frozen in D17**. `results_guard` refuses a P3 run while `p3.criteria` is null. Neither v0.4 nor earlier plans define these criteria; D17 lists the options.
- If neither variant meets the development criteria, record **STOP** for this registered candidate. Do not tune its parameters and rerun P3. A separate new hypothesis may be reviewed through §11, with all P3 exposure inherited and independent future validation required.
- **Defect-only reruns.** Allowed only for a bug in code or data. They need a defect record (symptom, root cause, fix commit, and why the fix does not encode knowledge of results) and owner approval. Each rerun is a ledger row.

#### WP4.2 P4 holdout run (2022–2025)

- Precondition: the exposure audit (WP0.6) confirms 2022–2025 is independent.
- `holdout_token.py` issues one token per spec hash. `run_p4.py` consumes it atomically, using a two-phase durable write (read intent, then read verified) so that a crash cannot silently allow a second opening.
- Only the variants that passed P3 are run. The strategy-definition, event-engine and statistics code hashes must match the approved P3 manifest; tooling/evidence-wrapper changes require a documented non-semantic review rather than silently changing the strategy. If v0.4 requires byte-identical overall code SHA, **that stricter requirement prevails**.
- The P4 multiplicity family is fixed by the rule frozen in D02 (for example, "all variants that advance from P3"), not chosen after P3.
- Output: the audit pack and a verdict from the closed enum in §5.2 (`PASS_HISTORICAL_PENDING_PROSPECTIVE`, `REJECT`, or an `INCONCLUSIVE_*` value).

### WP5 — Prospective paper trading (phase P5)

Starts only after a P4 `PASS_HISTORICAL_PENDING_PROSPECTIVE` verdict **and** written owner approval.

| ID | Task | Acceptance criteria |
|---|---|---|
| WP5.1 | Provision a **new** paper account for RANGE-002 (D07). It is not user 2 and not any existing strategy account. | The account ID is recorded in the signed execution manifest. A test asserts the executor refuses any other account. |
| WP5.2 | `executor.py`: builds the PIT universe daily, computes the OR at 10:00 from SIP, and places a buy-stop at OR high + 1 tick with a protective stop at OR low **only after the entry fill is acknowledged and sized**. Uses the identical frozen spec hash and does not reimplement the rules. Signal logic is imported from `engine/`; timestamps enforce data availability and brokerage latency. | A shared-code test shows the executor and the backtest generate identical signals on a replayed day. |
| WP5.3 | Orders go through the authenticated OrderRouter and risk engine. Each order carries an explicit reference price (the trigger price) so the notional gate prices it. Unpriced orders must fail closed. | An integration test on paper shows a stop order passes the notional gate with a reference price and is refused without one. |
| WP5.4 | Daily-flat watchdog: hard flat at the flat time. An independent check runs 2 minutes later and alerts if any position remains. | Alert on any residual position. Zero unplanned overnight positions **when the market remains executable**; a halt/market closure creates an explicit incident and retained-risk alert, never a fictitious fill. |
| WP5.5 | Reconciler: signal → order → fill → position → cash, end of day. | Daily reconciliation report. Any unexplained difference raises an alert and blocks the next day's entries until it is resolved. |
| WP5.6 | Fill-vs-model comparator: real paper execution shortfall versus consistently measured model costs on comparable orders. Model zero/negative/unknown denominators are `UNDEFINED`, not automatic pass/fail; those trades need an explicit fallback metric approved under D07. | Daily plus cumulative comparison, matched trade IDs, model/real components and exceptional denominators. The existing ≤1.5× threshold remains subject to D07's frozen calculation contract; an unresolvable undefined case blocks promotion. |
| WP5.7 | Observation-plane firewall: paper results may **not** feed back into the strategy spec. Any spec change ends this P5 run and requires a new registration. | Spec hash is checked at every executor start. |
| WP5.8 | Monitoring: SNS alarms for executor errors, data gaps at 10:00, rejected orders, the residual-position watchdog, and a daily-loss limit hit. | Alarm runbook committed. |
| WP5.9 | **Shadow-run before active paper submission (NEW).** Consume live SIP and generate intended orders, but send none to broker. Compare timestamps, active signal set and predicted order payloads against deterministic historical replay for sampled days. | Owner-approved dry-run report; no orphan signals, duplicate intents, or look-ahead discrepancies. **This is an operational dry-run, not an extra profitability screen.** |
| WP5.10 | **Order protection and outage drills (NEW).** Broker integration tests for delayed acknowledgments, stop attachment failure, partial fills, intraday halt and early close. | Order-state idempotence; no duplicate exposure; uncovered fill generates a critical alert and fail-closed new-entry policy, with protective action where possible. |
| WP5.11 | **Realized economics and operational quality (NEW).** Record fill-minus-assumed price, cost and opportunity attrition, order rejects, protection latency, residual exposure and trading-session availability. | Daily `paper_execution_quality.json`, reconciled to broker events, clear missing-data policy. No modifying frozen A/B logic. |
| WP5.12 | **Risk budget and release checklist (NEW).** Check who can pause, resume, inspect anomalies and authorize shutdown, and verify blocked account/user segregation. | Signed owner/independent-reviewer checklist, archived paper-account authorization, runbooks and alarms demonstrated in a controlled test. |

**P5 cost-quality calculation (v0.3 proposal; D07 approval required):** Define modeled execution cost and realized execution shortfall in the same units (currency/notional bps), same direction and matched order subset; distinguish brokerage paper-simulation artifacts from actual market fills. Agree whether to aggregate as `sum(realized_cost)/sum(modeled_cost)` over valid **positive** denominators or use a per-order alternative. Report nonpositive/missing denominators and their share separately, with a preapproved rule; **never** manufacture a `0/0 = 1` pass. Use the existing ≤1.5× threshold only after the denominator, exceptions and coverage are signed. Paper fills cannot prove live execution quality.

**P5 exit criteria (frozen in P0, D07).** At least 60 trading days **and** at least 100 trades. Realized cost ≤ 1.5× model. Degradation from the historical result within the pre-frozen tolerance. Drawdown and loss limits not breached. No unresolved operational defects. Reaching the minimum counts does not by itself mean there is enough evidence.

### WP6 — P6 decision pack

Assemble the P3, P4 and P5 audit packs, the redundancy analysis, the capacity estimate, the risk budget, the operational incident log, and the rollback plan. **No automatic promotion.** The named approver (D08) signs one of: restricted small live pilot, extend paper, or retire.

---

## 5. Gates (machine-checkable)

### 5.1 P4 holdout gates

All gates must pass. They are evaluated by `gates.py` from the audit pack, not by hand.

**Computation basis (D18).** Every gate is computed on one declared trade set. Recommended: the **portfolio-constrained filled trades** (what the account would actually have traded under the frozen risk limits), because that is the economic claim. The unconstrained signal-level set (every first trigger, sized independently) is reported as a diagnostic. G1 counts closed round-trips in the gate set; partial fills of one signal count as one trade.

| ID | Gate | Threshold | Status in v0.4 |
|---|---|---|---|
| G0 | Holdout independence | Exposure audit signed; no material contamination | Blocking |
| G1 | Sample | ≥ 300 trades in 2022–2025 | Required |
| G2 | Profit factor | ≥ 1.30 at base cost | Required |
| G3 | Stress cost | Mean net return > 0 at 15 bps per side | Required |
| G4 | Significance | Holm-adjusted one-sided test of mean net R > 0 passes at α = 0.05, day-clustered stationary bootstrap (WP3.3) | Required |
| G5 | Random baseline | Mean net R above random entry; adjusted lower CI bound of the paired difference > 0 | Required |
| G6 | Yearly consistency | ≥ 3 of 4 calendar years with profit factor > 1.0 | Proposed (D04) |
| G7 | Regime robustness | Profit does not come from a single regime or a single half; criterion set in P0 | Required (D12) |
| G8 | Max drawdown | No worse than the pre-registered comparator; comparator, equity sampling and account sizing require D10 sign-off | Platform gate (D10) |
| G9 | Data and engine reliability | Coverage, no look-ahead, stage-1 controls passed (WP4.0), engine validation passed | Required |
| G10 | Redundancy | Correlation with approved strategies ≤ 0.85, else flagged and not promotable | Promotion constraint |
| — | Win rate | **Platform > 50% gate applies until a formal D10 deviation is signed; display both evaluations** | Open (D10); owner ruling 2026-10-09 (C3) |

> **D10 governance alert.** The RNG-001 Rejection Summary Report (§3.5) records the owner's formal promotion gate (trades > 100, PF > 1.2, win rate > 50%, max drawdown no worse than baseline, positive expectancy, bootstrap CI > 0). Before P0 sign-off, the owner must determine in writing whether a deviation is approved, how the P4 ≥300 trades interacts with it, and the exact drawdown comparator. **Until resolved, both evaluations must be displayed and promotion must be blocked, not silently choose a developer default.** The v0.4/ADR interpretation is controlling.

### 5.1A Gate definition and economic quality checklist (NEW; proposed)

- `gates.py` must preserve existing G0–G10. Each must specify denominator, exact data partition, calculation function, comparison operator, units, missing-data handling, adjustment method and reference evidence. **Any requested gate modification goes back to the v0.4 owner**; v0.3 proposes no lowering of PF, cost, sample, significance or consistency thresholds.
- **PF treatment:** zero-loss denominator / no closed losers must return `UNDEFINED` and require review, not `+∞` automatic PASS. Include flat trades, full costs, same portfolio sizing and rejected signals under transparent accounting.
- **Year and regime consistency:** when a calendar year has too few trades for meaningful PF, report its count and P0-specified validity rule; do not count undefined years as passing.
- **Risk acceptance:** define a drawdown comparator using identical capital, costs, equity sampling and exposure; report gap losses and stress tail even if PF passes.
- **Net economic value:** don't claim a winning strategy solely because historical PF passes. P5 still requires prospective evidence and risk/operational controls. Report capacity/turnover and investor-relevant net return separately from gate status.
- **Statistical family:** freeze which A/B and paired comparisons count as confirmatory; report multiplicity-adjusted evidence. Distinguish confidence intervals and tests mathematically instead of tagging an arbitrary lower CI `Holm-adjusted`.

### 5.2 Verdict states (closed set)

```
UNTESTED → (P3) → STOP | ADVANCE_TO_P4 | INCONCLUSIVE_*
ADVANCE_TO_P4 → (P4) → PASS_HISTORICAL_PENDING_PROSPECTIVE | REJECT | INCONCLUSIVE_*
PASS_HISTORICAL_PENDING_PROSPECTIVE → (P5) → PAPER_PASS | PAPER_FAIL | PAPER_EXTEND | PAPER_HALTED_OPS
PAPER_PASS → (P6, human) → LIVE_PILOT_APPROVED | PAPER_EXTENDED | RETIRED
INCONCLUSIVE_* ∈ {INCONCLUSIVE_DATA, INCONCLUSIVE_HOLDOUT_CONTAMINATED, INCONCLUSIVE_ENGINE, INCONCLUSIVE_TECHNICAL}
```

| Enum | Research design v0.4 §6.1 state |
|---|---|
| `UNTESTED` | 待验证 |
| `PASS_HISTORICAL_PENDING_PROSPECTIVE` | 历史留出期通过 / 待前瞻确认 |
| `STOP`, `REJECT`, `PAPER_FAIL` | 否决 |
| `INCONCLUSIVE_*`, `PAPER_EXTEND` | 证据不足 / 技术阻断 |

- `REJECT` is terminal for this spec. It is archived as an evidenced rejection, the same way RNG-001 was.
- `INCONCLUSIVE` is not a soft pass. A repair and retest goes through a separate governance decision.
- No other strings are allowed. `gates.py` validates the enum.

---

## 6. Run protocol

1. `run_registry.open(phase, spec_sha, code_sha, data_manifest_sha, partition)` writes the ledger row **before** computing.
2. `results_guard.authorize(...)` checks every precondition (WP0.4); technical and governance privileges are verified in-process, not only by a developer-side import convention.
3. The computation runs with fixed seeds.
4. `audit_pack.write(...)` writes an immutable, hashed bundle containing the opportunity funnel, costs, event-quality, risk and diagnose-only analytics; the full raw trial ledger reference is embedded.
5. `run_registry.close(run_id, status, audit_pack_sha)`.
6. A crash between steps 1 and 5 leaves the row `ABORTED`. The run still counts in the ledger.

---

## 7. Audit pack (each P3, P4 and P5 run)

| File | Content |
|---|---|
| `research_manifest.yaml` | Run ID, phase, spec SHA, code SHA, engine SHA, data manifest SHA, partition, seeds, ledger row |
| `data_manifest.json` | Vendor, feed, adjustment, coverage summary, file hashes |
| `strategy_spec.yaml` | Copy of the frozen spec |
| `trades.csv` | One row per trade: symbol, permaticker, date, OR high/low, trigger, entry time and price, R_pre, R_fill, qty, exit time, price and reason, costs by component, net P&L, net R, `path_ambiguous`, variant |
| `orders.csv` | P3/P4: simulated orders; P5: intended vs submitted vs filled (owner ruling C9) |
| `risk_events.csv` | Limit bindings, adjustments, refusals |
| `controls/*.csv` | Random-entry, naive ORB, negative controls |
| `test_summary.json` | Every gate: value, threshold, pass/fail, CI, adjustment method |
| `diagnostics/` | Funnel, walk-forward, regime and half splits, cost stress, path-ambiguity sensitivity, concentration, redundancy |
| `validation_report.md` | Human-readable summary generated from the JSON (no hand-edited numbers) |
| `approval_log.md` | Sign-offs and defect records |
| `economic_thesis.md` | Pre-frozen claim, falsifiers, trading-expert review, allowed diagnostic questions |
| `candidate_events.parquet` | Chronological pre-trade opportunity events, risk/cash reservation and **rejected** candidate reasons |
| `order_event_log.parquet` | Simulated/live order lifecycle with market-data availability and broker acknowledgment timestamps |
| `opportunity_funnel.json` | Eligible → signal → order → fill → risk-protected → exit → net result, reconciled stage denominators |
| `economic_attribution.json` | Gross versus net edge, cost drag, missed opportunity, capital use, drawdown and tail risk |
| `diagnosis_report.md` | Evidence-based explanatory classification, **not** a new acceptance rule or retuning permission |
| `paper_execution_quality.json` | P5 only: actual observed slippage, reject rate, partial fills, stop-protection delay, service gaps |

---

## 8. PR sequence

Each PR has one purpose, carries its tests, and links its work-package ID.

| # | PR | Depends on | Phase |
|---|---|---|---|
| 1 | Recon doc (WP0.1) | — | P0 |
| 2 | Spec schema, hashing, freeze tool (WP0.2–0.3) | 1 | P0 |
| 3 | Results guard, run registry, exposure ledger, holdout token (WP0.4, 0.6, 0.7) | 2 | P0 |
| 4 | Non-equivalence check output + ORM-001 note (WP0.5) and AI provenance (WP0.8) | 2 | P0 |
| 4A | Signed economic thesis, return-blind feasibility, hypothesis lineage and order contract (WP0.9–0.12) | 1–4 | P0 |
| — | **Owner P0 sign-off. Spec frozen.** | 1–4, 4A | gate |
| 5 | ADR 0033 finding + chunked SIP loader + manifest (WP1.1–1.3) | gate | P1 |
| 6 | Calendar, PIT universe, corporate actions, anomaly flags (WP1.4–1.7) | 5 | P1 |
| 7 | Return-blind coverage report (WP1.8) | 6 | P1 |
| 8 | OR signal, fill model, risk sizer, position sim + tests (WP2.1–2.4, 2.7) | 7 | P2 |
| 9 | Controls (WP2.5) | 8 | P2 |
| 10 | RNG-001 replay chain + new-engine fixtures (WP2.6) | 8 | P2 |
| 11 | Stats and diagnostics modules (WP3) | 8 | P2 |
| 12 | Gates evaluator + verdict enum + audit-pack writer (§5–§7) | 11 | P2 |
| 12A | Portfolio chronological scheduler, baseline temporal-validity fixtures, market-data/order causality, and stop-order state machine (WP2.7A, WP2.8–2.11) | 8, 12 | P2 |
| 12B | Opportunity funnel, reconciled edge-attribution waterfall, path/payoff and fragility diagnostics (WP3.1–3.5) | 11, 12A | P2 |
| — | **P2 gate. Engine SHA pinned in the signed execution manifest referencing the frozen spec SHA; no mutation of the frozen research spec.** | 8–12, 12A, 12B | gate |
| 13 | P3 run + audit pack (results PR is docs/evidence only) | gate | P3 |
| 14 | P4 run + audit pack | 13 = ADVANCE | P4 |
| 15 | Executor, reconciler, watchdog, comparator, alarms (WP5) | 14 = PASS + approval | P5 |
| 15A | Shadow order audit, outage drills and execution-quality/owner controls (WP5.9–5.12) | 15 (before any paper order) | P5 |
| 16 | P6 decision pack | P5 complete | P6 |

**Definition of done (every PR).** CI is green, the new code has tests, no return computation exists outside `results_guard`, there are no hard-coded `P0:` values, and the docs are updated. Results PRs (13, 14) contain only generated evidence; the strategy/engine remains pinned to the approved SHAs. PR 15A's shadow-run, broker compatibility and operational tests **must pass before the first P5 paper order**; PR numbering describes dependency, not permission to activate. No `P0:` signature may be fabricated by a development agent.

---

## 9. Stop and escalate (do not work around)

Stop work and report to the owner with evidence if any of these occur:

1. The ADR 0037 check flags RANGE-002 as equivalent to a rejected pattern.
2. The exposure audit shows 2022–2025 was used for RANGE-002 ideation, parameter choice, engine tuning or comparison.
3. Licensed SIP history or delisted coverage does not reach the planned period, or coverage is below 98%.
4. The cache writer can still truncate silently and the monthly-chunk path is not approved.
5. The RNG-001 replay cannot reproduce the archived evidence.
6. A stage-1 control fails (WP4.0). The sealed strategy results stay sealed; investigate as a possible engine or data defect.
7. Any code path can compute returns without `results_guard`.
8. A requested change would alter a frozen spec value after results exist.
9. Any order path outside the authenticated OrderRouter, or any attempt to use user 2 or another strategy's account.
10. Any conflict between this plan and v0.4.
11. OR inputs are not finalized before the claimed signal timestamp, or a triggered minute bar cannot support the assumed causal fill.
12. Global event simulation can select a trade using future P&L or can overallocate cash/risk to simultaneous signals.
13. Paper account order type, stop protection or broker timestamps disagree with the frozen research semantics without a documented owner decision.
14. Agent attempts to redesign RANGE-002 after P3/P4 performance, or uses a supposedly new independent test containing previously examined outcomes.
15. Platform score or performance claims are generated from a return-blind gate, synthetic data, or an otherwise unauthorized research stage.
16. A P3 or P4 run is requested while D17 (P3 criteria) or D18 (gate basis) is unsigned.

---

## 10. Open owner decisions that block code

Code reads these from the frozen spec. **The agent must not choose them.**

| ID | Decision | Spec keys | Blocks |
|---|---|---|---|
| D01 | Register RANGE-002; sign the exposure conclusions and holdout applicability | `governance.exposure_signed` | P0 exit |
| D02 | Primary A / secondary B, test order, whether B can be promoted alone, Holm family; confirm PF ≥ 1.30 and stress > 0 | `variants.*`, `stats.hypothesis_family` | P3 |
| D03 | N (proposal 100), PIT timing, SIP vendor and licence, data budget | `universe.n`, `data.vendor` | P1 |
| D04 | Yearly gate (≥ 3 of 4 years with profit factor > 1.0) if 2022–2025 is used | `gates.yearly` | P4 |
| D05 | R_pre/R_fill rules, gap fills, same-bar order, tick size, half-day exit, halt rule | `fill.*`, `risk.*`, `exit.*` | P2 |
| D06 | Baselines, block bootstrap parameters, adjustment method, confidence level, seeds | `controls.*`, `stats.*` | P2 |
| D07 | New paper account; P5 slippage, drawdown and degradation tolerance; extension rules | `p5.*` | P5 |
| D08 | Research lead, trading-expert reviewer, independent validator, sole P6 approver | `governance.roles` | P0 |
| D09 | ADR 0037 statement; relationship to ORM-001 (merge / shared ledger and family / independent) | `governance.related_programs` | P0 |
| D10 | Win rate as diagnostic (deviation) or > 50% gate; drawdown comparator | `gates.win_rate`, `gates.max_dd` | P4 |
| D11 | Writer meets ADR 0033 points 1–3, or a new monthly-chunked, fail-closed RANGE-002 SIP loader is used; the shared `BarCache` is not modified (owner ruling 2026-10-09, C5) | `data.fetch_mode` | P1 |
| D12 | Regime definition and the single-regime-dependence criterion | `stats.regime.*` | P2 |
| D17 | **P3 advance criteria.** Options: (a) the same G1–G8 thresholds as P4, with G1 scaled to the longer window (for example ≥ 450 trades for six years); (b) a looser screen (for example PF ≥ 1.15, mean net R > 0, no significance gate), accepting more false advances in exchange for fewer false stops; (c) significance only. Recommended: (a), so P4 does not inherit a weaker screen. | `p3.criteria` | P3 |
| D18 | **Gate computation basis** (portfolio-constrained fills vs signal-level) and **trade definition** for G1 | `gates.basis`, `gates.trade_unit` | P3 |

### 10.1 Detailed decisions D13–D16 (within v0.4 scope; owner values required)

| ID | Decision (v0.4 parent) | Why it is needed | Spec keys / artifacts |
|---|---|---|---|
| D13 | Confirm economic thesis, competing baselines and which diagnostics are non-binding (v0.4 §10.3) | Make hypothesis value assessable independently of fitting returns | `governance.economic_thesis_sha`, `controls.naive_orb`, `diagnostics.*` |
| D14 | Freeze bar timestamp convention, vendor delay, decision/submit/ack latency, crossed-before-arm policy (WP2.1A), stop order type, order state machine, EOD lead time and same-time allocation priority (v0.4 decision 05) | Prevent OHLC wishful fills and portfolio hindsight allocation | `execution.*` |
| D15 | Approve cost accounting decomposition and whether base/stress bps are all-in or additive to fill-price slippage (v0.4 §4 cost row). Recommended: all-in bps applied as a P&L debit, with fills at the modeled price and no extra slippage, so nothing is charged twice; gap-through fills stay adverse because they are price events, not costs | Prevent both optimistic undercharging and double-charging | `costs.accounting_mode`, `costs.components` |
| D16 | Approve explanatory diagnosis taxonomy, P5 shadow verification and minimum broker execution-quality evidence (v0.4 decision 07) | Improve future strategy discovery while preserving frozen gates | `diagnostics.taxonomy`, `p5.shadow_acceptance` |

**Interpretation (v0.4).** The §0A reconciliation shows D13–D16 refine decisions v0.4 already requires (decisions 05–07 and the cost-itemization rule). No design addendum is needed. Each still needs an owner value before P0 exit, because D14 and D15 change simulated fills and costs. This document does **not** authorize a new strategy rule, an alternative holdout, or a revised acceptance threshold.

---

## 11. Controlled strategy enhancement after a disappointing outcome (NEW)

The development team's job is to maximize the chance of discovering a **real and repeatable edge** over multiple research cycles; it is **not** to manufacture a PASS for this frozen RANGE-002 candidate.

### 11.1 If P3 or P4 fails, produce an evidence-based attribution report

| Root cause | Evidence to investigate | Allowed action | Not allowed |
|---|---|---|---|
| No continuation effect | Net R vs causal random entry / naive ORB; path and MFE/MAE diagnostics | Close candidate; ask trading expert for independent economic hypothesis | Raise PF by adding filters to the exposed same test |
| Cost overwhelms weak gross effect | Fill-vs-trigger, spread, bps, capacity, adverse gaps | Improve **general engine truthfulness**; propose a separate strategy or order-policy study | Delete costly trades or replace costs post hoc |
| Stop too wide / 2R rarely accessible | Predeclared OR-width and post-entry payoff distribution | Draft successor stop/exit hypothesis with fresh evidence | Move stops or targets on RANGE-002 after results |
| Concentrated market regime | Per-year and preregistered regime attribution | Future independently registered conditional-strategy thesis | Invent a regime gate from the protected holdout |
| Data or engine defect | Reproducible failing fixture; manifest mismatch, silent truncation | Document defect and obtain governed defect-only rerun authorization | Redesign trading logic disguised as bug fix |
| Too few legitimate trades | Return-blind eligibility and governed event-funnel attrition | Mark insufficient evidence; plan independent larger prospective sample | Remove low-trade days or lower sample gate without sign-off |

### 11.2 Success-oriented iteration workflow

1. Produce the immutable P3/P4/P5 report (whatever the verdict); record all attempted hypotheses and variants.
2. Have a **trading expert** independently interpret the economic mechanism and failure modes. AI summarizes evidence and proposes *questions*, not optimizations on held-out data.
3. Convert a genuinely different idea into a documented new hypothesis: why it should work, what opposite result would falsify it, what earlier evidence exposed it, and what costs/capacity it introduces.
4. Register under a distinct program ID, apply platform's related-hypothesis / rejected-pattern and multiplicity rules, and secure genuinely **unexposed** decisive evidence. Reusing an exposed holdout under a new ID does not make it independent.
5. Implement under the same P0–P6 governance gates. Do not promote because results improved on a previously examined data window.

### 11.3 First 10 implementation-agent actions (read-only and non-return producing)

1. Inspect the repository and reconcile all module paths named in v0.1 (§3.2); record commit IDs.
2. Commit `RANGE-002_开盘区间突破延续策略_验证与实施方案_v0.4.docx` and the RNG-001 Rejection Summary Report to `docs/implementation/evidence/range_002/`. Extend the §0A matrix with the actual ADR 0014/0033/0037 texts. Stop on disagreements.
3. Audit exposure ledger and historical contact with 2022–2025, including AI-assisted analysis history; report unknown exposure rather than asserting independence.
4. Ask the trading expert for a **one-page economic-edge thesis** and the expected failure mechanisms.
5. Inventory SIP 1-minute and survivorship-free PIT coverage **without evaluating any returns**; prove cache paging cannot silently truncate.
6. Determine actual data timestamp conventions and the broker's supported stop-order/partial-fill semantics; define observed versus simulated capabilities.
7. Draft causality, simultaneous-signal, cost accounting and gap-risk fixtures for independent sign-off.
8. Prepare owner decision sheets for D13–D18 (with the recommended defaults marked as recommendations), retaining all existing v0.4 gates and A/B definitions.
9. Create/verify the guarded trial ledger, frozen-spec loader and authorization boundaries, with fail-closed negative tests.
10. Send owner a P0 **GO / HOLD** packet listing unresolved D01–D18, data budget, technical blockers and whether any P1 work may safely proceed. **Do not run returns or place orders.**

### 11.3A Implementation-agent handoff template (v0.3)

Use this exact **format**, adapted to actual repository findings, after each work package. Do not claim a command ran unless the agent actually ran it:

```markdown
Work package: WPx.y / PR link:
Code and files changed: [paths + commit SHAs]
Source-spec references: [v0.4 section / ADR / frozen spec hash]
Data accessed: [none | return-blind metadata | approved P3 | approved P4 | paper]
Governance authorization: [owner signer / token ID / timestamp]
Tests executed: [command, test counts, result]
Evidence artifacts: [paths + SHA256]
Risk/safety assessment: [broker credentials touched? account ID? new order capability?]
Open decisions or blockers: [D01–D18 etc.]
Recommended next action: [one bounded task]
```

**STOP criteria for the agent:** if the governing v0.4 cannot be located, evidence indicates contaminated holdout, a frozen spec is incomplete, an unexpected P&L is exposed, archived RNG-001 cannot be explained, or an order path risks an unintended account, report `BLOCKED` with exact evidence and request authorization. Do not proceed by selecting a plausible default or weakening a test.

### 11.4 Objective project measures (distinct from trading PASS)

- Research quality: reproducibility rate, exposure/ledger completeness, defect leakage, automated gate coverage and evidence turnaround.
- Development quality: deterministic replay, data-coverage accuracy, test completeness and order-state correctness.
- Economic quality (only after an authorized run): cost-adjusted expectancy, causal-baseline advantage, path fragility, drawdown, capital efficiency and regime robustness.
- Operational quality (P5): reconciled days, signal/order/fill mismatch rate, stop-protection latency, duplicate orders, paper slippage and unplanned residual risk.

**Final instruction to agents:** do not confuse platform success with passing every strategy. RANGE-002 is successful as a research project only if it produces a trustworthy outcome; it is successful as a trading candidate only if its predeclared tests demonstrate an economically useful, independently reproducible edge and forward operations corroborate it.

---

## Appendix A — Frozen spec skeleton

```yaml
program: RANGE-002
spec_version: 1
registration:
  trial_ledger_id: null          # set by run_registry
  related_programs: null         # P0: D09
universe:
  instrument_types: [common_stock]
  n: null                        # P0: D03
  min_price: 10.0
  adv_window_days: 20
  rebuild: monthly
  include_delisted: true
data:
  feed: sip                      # asserted
  vendor: null                   # P0: D03
  bar: 1min
  session: rth
  tz: America/New_York
  fetch_mode: null               # P0: D11
signal:
  missing_minute_classes: [NO_TRADE_MINUTE, DATA_GAP]   # only DATA_GAP counts against completeness
  or_start: "09:30:00"
  or_end: "09:59:59"
  or_completeness_rule: null     # P0: D05
  min_or_width_ticks: null       # P0: D05
  entry_window: ["10:00:00", "14:59:59"]
  tick_offset: 1
  max_entries_per_symbol_day: 1
variants:
  A: {target_r: null}
  B: {target_r: 2.0}
  order: null                    # P0: D02
exit:
  stop: or_low
  eod_flat: "15:55:00"
  halfday_offset_min: null       # P0: D05
fill:
  slippage_model: null           # P0: D05
  same_bar_policy: worst_case
  halt_policy: null              # P0: D05
costs:
  base_bps_per_side: 5
  stress_bps_per_side: 15
  accounting_mode: null          # P0: D15 (all_in | itemized_additive)
  components: null               # P0: itemized
risk:
  per_trade_pct: null            # P0 (proposal 0.25)
  per_name_cap: null
  gross_cap: null
  max_concurrent: null
  daily_loss_limit: null
  max_participation: null
  fill_risk_tolerance: null
partitions:
  development: ["2016-01-01", "2021-12-31"]
  holdout: ["2022-01-01", "2025-12-31"]
  exposed: [["2026-01-01", "2026-07-31"]]
controls:
  random_entry: {repetitions: null, seed: null, invalid_draw_policy: null}   # P0: D06
  naive_orb: {definition: null}
stats:
  bootstrap: {method: stationary_block, cluster: trading_day, mean_block_len: null, reps: null, seed: null}
  hypothesis_family: null        # P0: D02 (incl. P4 family rule)
  adjustment: holm               # or fixed_sequence per D02
  alpha_one_sided: 0.05          # P0: D06
  regime: {definition: null, criterion: null}     # P0: D12
execution:                       # P0: D14
  bar_timestamp_convention: null # start | end, verified against vendor docs
  vendor_delay_ms: null
  submit_latency_ms: null
  ack_latency_ms: null
  crossed_before_arm_policy: null   # SKIP | MARKET_AT_NEXT_ACTIVE_BAR_OPEN | REQUIRE_RETRACE
  order_type: null               # stop_market | stop_limit | emulated
  stop_protection_policy: null
  tie_break: null                # return-independent, e.g. permaticker ascending
  eod_lead_s: null
  order_reservation_policy: null
p3:
  criteria: null                 # P0: D17
gates:
  basis: null                    # P0: D18 (portfolio_constrained | signal_level)
  trade_unit: null               # P0: D18
  min_trades: 300
  pf_base: 1.30
  stress_mean_positive: true
  yearly: null                   # P0: D04
  win_rate: null                 # P0: D10
  max_dd: null                   # P0: D10
  redundancy_corr_max: 0.85
p5:
  account_id: null               # P0: D07
  min_days: 60
  min_trades: 100
  max_cost_ratio: 1.5
  degradation_tolerance: null
  cost_ratio_contract: null      # P0: D07 (denominator, aggregation, UNDEFINED handling)
  shadow_acceptance: null        # P0: D16
diagnostics:
  taxonomy: null                 # P0: D16 (explanatory only)
governance:
  economic_thesis_sha: null      # P0: D13
  roles: null                    # P0: D08
signoff:
  owner: null
  trading_expert: null
  independent_validator: null
  date: null
  spec_sha256: null
```

## Appendix B — Lessons from RNG-001 that this plan encodes

| RNG-001 lesson | Where it is enforced |
|---|---|
| Full-sample metrics produced a false positive (E-vwap+gate: profit factor 1.53 full sample, 0.68 in the first half) | G7, `splits.py`, holdout-only verdict |
| Six months of one regime could not separate a filter from noise | 2016–2025 partitions, G6 |
| Same-day trades share a regime, so per-trade significance was overstated | Day-clustered bootstrap (G4, G5) |
| An optimistic fill model inflated the edge | WP2.2 adverse fills, path-ambiguity reporting |
| A truncated cache produced a biased one-third sample | WP1.1 ADR 0033 pre-check, coverage gate |
| IEX quotes are not the consolidated market | R6, feed assertion |
| Retuning is data mining | R4, spec hash on every run, holdout token |
| The 49% "target hit before entry" finding gave rise to RANGE-002 | R2, exposure ledger |
