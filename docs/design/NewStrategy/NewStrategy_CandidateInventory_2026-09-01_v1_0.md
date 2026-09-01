# New-strategy opportunity inventory and top-three selection

| Field | Value |
|---|---|
| Status | **READ-ONLY DISCOVERY + RESEARCH DESIGN.** No implementation, no activation, no orders. |
| Question | Which hypotheses deserve **research capital**? |
| Method | Evidence-ranked from the platform's own registered verdicts, not idea-ranked |

---

# 0. Lane 1 — Strategy 7 retirement closeout: **BLOCKED, unchanged**

⛔ **Still not executable.** Lane 1 instructs *"mark Strategy 7 RETIRED through the normal governed
mechanism."* No such mechanism exists:

| surface | state |
|---|---|
| `StrategyStatus` enum | **no `RETIRED` value** |
| research registry `deployment_state=RETIRED` | exists in code; **`/app/data/research.duckdb` absent in production** |
| `[ARCHIVED …]` name prefix | **`name` not in `StrategyUpdateRequest`** (`extra="forbid"`) — unsettable via API |

⇒ Awaiting the owner's choice between documentary retirement, building the control, or a one-off
governed DB mutation. ⛔ No mutation attempted.

**Executable and current** (measured 2026-09-01): Account 5 `PA3DBWDGOING` / fp `5115fc74f097` ·
**0 positions, 0 position rows** · **0 open orders** · equity **99,260.28** = cash · breaker clear ·
no armed scheduler job (0 log hits/24h) · last run 765 closed 2026-08-22.
⚠ 130 `strategy_runs` rows have `ended_at IS NULL` — the **known stale-open-run defect**, *not*
evidence strategy 7 is running.

⛔ Credential untouched. `SEC-001 V3 = OFFLINE RESEARCH OPTION PRESERVED / NO ACTIVATION OR PAPER
AUTHORITY`.

---

# 1. The honest starting position

The platform has **already rejected most of its own hypotheses**, with pre-registered designs. That
is the most important input to this exercise:

| verdict | programs |
|---|---|
| **rejected (7)** | RNG-001 · MOM-002 · TV-001 · **INSIDER-001 · GOVCONTRACT-001 · CONGRESS-001 · LOBBY-001** |
| **validated (3)** | MOM-001 (strategy) · SCAN-001 (*capability*, not a trading light) · PORT-001 (*construction engine*; stock-selection alpha **REFUTED** under PIT) |
| **inconclusive (6)** | MF-001 · SEC-001 · LOW-001 · TREND-001 · TREND-002 · FI-001 |
| **research (3)** | DISC-001 (display only) · GAPPER-001 · MKT-PROJ-001 (display-only forever) |
| **planned (2)** | FI-002 (**reserved — do not start**) · **FI-003 (charter frozen, never run)** |

⭐⭐ **The event-driven / alt-data family is exhausted.** Four consecutive matched-control rejections
— insider buys, government contracts, congressional purchases, lobbying spikes — all *beta not
alpha*. ⛔ A fifth alt-data event study is the **worst** available use of research capital.

⭐⭐ **MOM-002's load-bearing lesson governs this selection:** *"widening the SAME factor does NOT
create independent evidence"* (Top-5↔Top-20 monthly corr **0.90**). *"Diversify by combining
INDEPENDENT FACTORS."*

---

# 2. Candidate inventory

| # | candidate | driver | evidence FOR | evidence AGAINST | PIT-safe | deployability | verdict |
|---|---|---|---|---|---|---|---|
| C1 | **FI-003 / CAP-022 crash-insurance overlay** | tail hedge (not selection) | 200d-trend gross de-risk **reproducibly cut COVID + 2022 DD ~13–15pp**; charter **frozen**; FI-001 Phase-4 regime overlay best DD-managed book (Sharpe 1.17, maxDD −24% vs mom −38%) | rejected as a *Calmar/Sharpe* improver; cost-of-carry in calm markets; needs a book to overlay | ✅ deepened survivorship-free store | overlay on an existing book | **RESEARCH** |
| C2 | **MF-001 V2 value + quality** | fundamentals | **most independent factor measured — corr −0.09 / −0.005**; DD −51% → −40% | ΔSharpe **+0.04** CI [−0.35, +0.48]; SF1 PIT floor **`datekey` ≥ 2016-01-29** limits history | ✅ survivorship-free SF1 | reuses ranked-book framework | **RESEARCH** |
| C3 | **LOW-002 broader-universe low-vol** | defensive anomaly | platform's **closest near-miss**: H1 **+0.24 CI [−0.029, +0.53]**; best risk-adjusted book (Sharpe **0.59**, maxDD **−39%** = half momentum's −76.4%, Calmar 0.20); corr **−0.15**; cost-robust to 50bps; program names this exact next step | ⚠ **same factor as Strategy 8** → adds standalone-alpha evidence, *not* diversification (MOM-002 lesson) | ✅ factor store | strategy-8 framework reusable | **RESEARCH** |
| C4 | TREND-003 wide-universe trend | TSMOM | two power failures ≠ hypothesis failure; maxDD **−11.3% vs −30.5%** (62.9% cut); TREND-002 found edge **thinner on narrow** universe (+0.02 vs +0.18) → go wider | ⚠ **FI-001 measured MOM↔TREND corr ≈ 0.90 — redundant with momentum**; ΔSharpe CI spans zero twice | ✅ ETF prices | multi-asset ETF book | **HOLD** |
| C5 | GAPPER-001 intraday gap | intraday continuation | frozen-blind v0.2 design; forward pipeline live | ⛔ early read **implied breakeven ~11bps/side vs a ≥20bps bar**; program itself says *"expect Rejected or Inconclusive"*; owner: do not promote/tune | ⚠ 20 valid dates | intraday execution burden | **REJECT for now** |
| C6 | SCAN-001 → tradable | discovery | capability validated, regime-robust | ⛔ **gate accrues `edge_E ≡ 0.0` by construction** (candidates == eligible on 32/32 days) — a day-40 verdict would be a **funnel artifact** | — | — | ⛔ **BLOCKED (defect)** |
| C7 | MKT-PROJ-001 → strategy | market projection | move-risk calibrated, Brier CI excludes zero | **display-only forever** absent a separate MKT-PROJ-STRAT-001; direction NOT validated | — | — | ⛔ out of scope |
| C8 | 5th alt-data event study | event drift | reusable Event-Study stack | ⛔ **4/4 rejected**; strong prior | — | — | ⛔ **do not fund** |
| C9 | SEC-001 V3 breadth floor | sector RS | derived `N_min=4` | construction **ARCHIVED** by pre-registered stopping rule; V2 proved *construction is not the limiter*; needs a **fundamentally different hypothesis** | ✅ | — | ⛔ **not now** |
| C10 | Re-widen momentum | momentum | — | ⛔ **MOM-002 rejected exactly this** | — | — | ⛔ **do not fund** |

---

# 3. Top three — selected

```
#1  FI-003 / CAP-022  CRASH-INSURANCE TAIL HEDGE
#2  MF-001 V2         VALUE + QUALITY
#3  LOW-002           BROADER-UNIVERSE LOW VOLATILITY
```

**Three economically distinct drivers within the set:** a *tail hedge overlay*, a *fundamentals
factor*, and a *defensive volatility anomaly*. None is a variant of another.

⚠ **Stated plainly:** C3 **is** a same-factor variant of the currently-armed Strategy 8. It earns its
place because it attacks the platform's **closest near-miss standalone edge** — not because it adds
diversification, which MOM-002 says it will not. If you would rather all three be independent of
existing books, **swap C3 for C4 (TREND-003)** and accept its corr-0.90 redundancy with momentum
instead. I would keep C3, because a near-miss on the platform's best risk-adjusted book is the most
likely place a *real* standalone edge is hiding.

**Why not TREND-003 in the top three:** two consecutive pre-registered power failures, and FI-001
measured MOM↔TREND ≈ 0.90. It is a *redundant* diversifier candidate. Held, not rejected.

---

# 4. Frozen research specifications (pre-registration drafts)

⛔ Each must be frozen **before** its decisive test. Pass/revise/reject thresholds are stated up
front; post-result modification is limited to the listed sensitivities.

## C1 — FI-003 / CAP-022 crash insurance

- **Hypothesis:** the 200d-trend gross de-risk overlay is worthwhile **as insurance**, not as a
  Calmar/Sharpe improver.
- **Universe/data:** deepened survivorship-free store; reuses `scripts/cap020_regime_validation.py`.
- **Signal:** existing CAP-020 mechanism, **unchanged** — no re-tuning of the trend window.
- **Benchmark:** the un-overlaid book.
- **Primary metrics:** stress-regime (2020, 2022) **MaxDD reduction**; **CVaR / worst-month**;
  calm/bull **CAGR drag** (cost-of-carry); regime-timing false-pos/neg.
- **PASS:** materially cuts stress-regime DD **and** improves worst-month/CVaR **and** bounded calm
  carry **and** robust across sweeps **and** no curve-fit timing.
- **REJECT:** carry exceeds tail benefit, or timing is fit-sensitive.
- ⛔ **Calmar/Sharpe are NOT the acceptance criteria** — that is the error FI-001 already made.

## C2 — MF-001 V2 value + quality

- **Hypothesis:** a value+quality book is an *independent* return source worth its own sleeve.
- **Universe/data:** survivorship-free SF1. ⚠ **PIT floor `datekey` ≥ 2016-01-29** — a hard boundary.
  ⛔ `calendardate` is the fiscal period end and is NOT the observable date.
- **Structure:** train / validation / OOS split inside the available window; walk-forward.
- **Primary metrics:** ΔSharpe vs momentum **and** vs equal-weight, with CI; correlation to
  **Strategy 8 (low-vol)** and to Range Trader; incremental portfolio effect.
- **PASS:** ΔSharpe CI excludes zero **or** decisive diversification (DD reduction + corr < 0.3 with
  CI-separated portfolio improvement).
- **REJECT:** repeats the +0.04 result with a CI spanning zero and no portfolio benefit.
- **History boundary (v1.2 R2 — supersedes the v1.0 STOP clause, which as written fired
  unconditionally):** the pre-2016 era is **not PIT-satisfiable in SF1 and is permanently out of
  scope**. ⛔ Do not extend the window backward; ⛔ do not reconstruct or backfill pre-2016
  fundamentals from later-known data. The shorter history is a **limitation to report, not a defect
  to hide and not a STOP trigger**. STOP applies only if the *in-window* data proves PIT-unsafe
  (e.g. a discovered `datekey` integrity defect) — a dataset defect record under §0.5.3.

## C3 — LOW-002 broader-universe low volatility

- **Hypothesis:** LOW-001's near-miss standalone edge (+0.24, CI [−0.029, +0.53]) becomes decisive on
  a materially wider universe.
- **Universe:** materially wider than LOW-001's; frozen **before** any result is seen.
- **Signal:** LOW-001's frozen definition — ⛔ **no re-tuning of lookback or quantile.**
- **Primary metrics:** H1 standalone ΔSharpe vs equal-weight with CI; maxDD; Calmar; cost sweep to
  50bps; **correlation and overlap vs Strategy 8's current book.**
- **PASS:** H1 CI **excludes zero** while preserving the DD advantage.
- **REVISE** — CI still spans zero but the DD advantage strengthens on the wider universe.
  **REJECT** — CI spans zero and the DD advantage does not improve.
- **Pre-registered falsifier (v1.2, two limbs):**

  ```
  IF correlation with Strategy 8 EXCEEDS 0.85            -> RETURN-REDUNDANCY
  IF mean holdings-weight-overlap with Strategy 8 > 0.85 -> HOLDINGS-REDUNDANCY
  IF EITHER is true -> MOM-002-style SAME-FACTOR REDUNDANCY
                       and NO INDEPENDENT-DIVERSIFICATION CLAIM
                       and do NOT tune around it
  ```

- ⭐ **Falsification built in:** either limb can refute the diversification claim even if the
  standalone edge improves. A redundancy finding alongside a passing standalone result is a
  legitimate recorded outcome; its disposition is a **Lane-7 owner question**, ⛔ not something this
  research may argue for.

---

# 5. What can start immediately

| candidate | startable now? | why |
|---|---|---|
| **C1** | ✅ **yes** | charter frozen; primitives + store exist; historical research needs no live account. The CAP-020 data-gate applied to *live* validation only. |
| **C2** | ✅ **yes** | survivorship-free SF1 in place; PIT boundary known and declarable. |
| **C3** | ✅ **yes** | factor store live and GREEN; LOW-001 definition already frozen. |

⭐ **None depends on the SIP cache, on ADR-0055 trusted-price propagation, or on #719.** All three are
historical research over existing PIT data. ⛔ No reason to wait on Developer 2's lane.

---

# 6. Blockers

**Authority:** Lane 1 retirement (§0). Not a research blocker.

**Data:** C2's SF1 PIT floor — **`datekey` ≥ 2016-01-29**, ~10.4 years — is a genuine constraint. Declare
it; do not paper over it. ⛔ It is a **limitation to report, not a STOP trigger** (v1.2 R2).

⛔ **Not blockers, and must not become ones:** Account 5's availability (capacity, not a reason to
choose a candidate), Strategy 8's canary, and the SIP lane.

---

# 7. What is NOT proposed

⛔ No implementation, prototype trading code, account binding, activation, scheduler change, order,
or deployment. ⛔ No candidate chosen for PAPER — that is Lane 7, after research.
