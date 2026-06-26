# ADR 0020 — Daily Gross-Exposure Overlay as a Separate Layer

| Field | Value |
|---|---|
| Date | 2026-06-19 |
| Status | Accepted (frozen architectural baseline 2026-06-19; future changes via a new incremental ADR, not by editing this one) |
| Phase | P10 §2 |
| Supersedes | — |
| Related | 0002 (single OrderRouter — the overlay never submits orders directly), 0004 (circuit breaker — the overlay is risk-reducing, never risk-adding), 0005 (activation cooldown — the overlay rides the strategy it scales), 0014 (backtests as eval ground truth — the overlay is validated by backtest before live), 0019 (Research Engine — the overlay's gross-scale logic is the same one walk-forward-validated there) |

## Context

`momentum-portfolio` selects names **weekly** (a single cron, `0 14 * * <day>`) and
no-ops on every other tick. Its single biggest residual risk (per the owner's two
reviews) is **intra-week momentum-crash risk**: a violent vol spike or regime turn
between Monday rebalances that the weekly cadence cannot react to. P10 §1 built an
EWMA vol-target gross-exposure scale (`_gross_scale`) and walk-forward-validated it
across regimes (GFC, COVID, 2022) — it is a proven *drawdown* tool — but today it is
applied only inside the backtester's return series (`_vol_target_overlay`), not in the
live deployment loop. To act intra-week, the live book needs a **daily** gross-exposure
adjustment that does **not** re-select names.

The question is architectural, and the two owner reviews point in tension:

- The pre-v2 roadmap (§2) recommended **(A)** a second daily schedule *on the strategy
  itself*.
- Review v2 (now authoritative) warned **"do NOT build dual-cadence inside one
  strategy"** and called for a **separate overlay engine** as the first step of an
  alpha / portfolio-construction / overlay / execution / risk **layer separation**,
  with a formal action boundary (roadmap §9.2).

We must decide *where the daily overlay lives* and *what it is allowed to do* — without
breaking the single-OrderRouter invariant (ADR 0002) or the
one-strategy-owns-its-symbols model that keeps position ownership and audit
attribution unambiguous.

## Decision

**Component classification (at a glance):**

| Attribute | Value |
|---|---|
| Overlay type | Risk overlay (exposure de-risking) |
| Frequency | Daily |
| Input | Market state (proxy returns) only |
| Output | A **scalar** `desired_gross ∈ [0, 1]` (never weights, never orders) |
| Statefulness | **Stateless** — a pure function of (market state, params) |
| Determinism | Deterministic — identical (positions, prices, params, date) → identical `desired_gross` (replayable) |

Introduce the daily gross-exposure overlay as a **distinct, independently-testable
Overlay layer with a hard action boundary**, driven by an **optional bounded daily
cadence the owning strategy may declare** — not as a competing companion strategy, and
not as logic buried inside the selection code.

1. **Action boundary (the invariant).** The Overlay layer may compute and apply **only
   a target gross-exposure multiplier in `[0, 1]` (and, later, per-bucket caps)**. It
   **never** selects or ranks symbols, **never** emits orders directly, and **never**
   overrides the alpha engine's name choices. Selection ownership stays with the alpha
   (momentum) engine; the overlay scales the book the alpha produced.
2. **Boundaries it must honor.** The overlay is **risk-reducing only** — it can scale
   gross *down* (cap at 1.0 = never adds leverage), consistent with §1. Every order it
   induces routes through `OrderRouter.submit()` (ADR 0002) and passes the full risk
   engine; the overlay itself touches no broker adapter.
3. **Compute / Validate / Execute separation.** The overlay layer **only computes
   desired state** — a **scalar `desired_gross ∈ [0, 1]`** (and, later, per-bucket
   caps). It does **not** think in terms of orders. A distinct execution step
   *validates* the target, *diffs* it against the held book, and routes any deltas
   through `OrderRouter.submit()` (ADR 0002). The overlay emits a scalar gross, **never
   `desired_weights`** — emitting weights would let it alter intra-book composition,
   violating its own boundary (point 1). The existing book weights are preserved; only
   gross is scaled.
4. **Mechanism.** The overlay is a **separate module** (a pure computation over market
   state → `desired_gross`). To act daily, a strategy may declare an **optional
   secondary daily cadence** (`daily_overlay_schedule`); on a daily (non-rebalance)
   tick the compute→validate→execute path scales the *existing* book **without
   re-selecting names**. The strategy continues to own its positions. The daily tick is
   **idempotent** — a same-day re-fire that finds the book already at the target is a
   no-op (no duplicate re-sizing).
5. **Default OFF.** The overlay is opt-in per strategy (conservative default); off
   reproduces today's weekly-only behavior byte-for-byte, and is inert for the live
   paper book (id=2) until a deliberate, backtested param change enables it.

### Overlay invariants (the forbidden list)

The overlay layer, by construction:

| The overlay NEVER… | The overlay ONLY… |
|---|---|
| selects or ranks symbols | scales **gross exposure** (a scalar in `[0, 1]`) |
| changes factor scores or the alpha ranking | reads market state + the held book (no writes of its own) |
| changes sector / bucket caps (those are §3/§3C, at construction) | reduces exposure when it has a valid signal |
| emits orders itself (a separate execute step does, via OrderRouter) | fails **open** (gross = 1.0) on missing/!valid data |
| leverages (gross is capped at 1.0) | preserves the alpha engine's intra-book weights |
| overrides the alpha engine's name choices | — |

Additionally, the overlay is **deterministic**: identical `(positions, prices, params,
date)` must yield identical `desired_gross` — which is what makes an overlay run
replayable from its audit fingerprint. A code reviewer can check any overlay change
against this table; a violation is a stop-the-PR event.

## Rationale

**Why a separate layer (not logic inside `_select_targets`).** Review v2's strongest
guardrail is "freeze the core momentum logic — no signal/overlay creep inside it."
Extracting the overlay as its own module makes its one job and its boundary explicit,
lets it be unit-tested in isolation, and makes the §1 vol-scale and (future) §3-style
caps **instances of one pattern** rather than ad-hoc strategy code. It is the first
concrete step of the alpha/portfolio/overlay/execution/risk layer separation the
reviews want.

**Why an optional secondary cadence on the owning strategy (A′), not a companion
overlay strategy (B).** A companion strategy that scales the same book introduces
**cross-strategy position ownership**: two strategies acting on one set of positions
breaks the one-strategy-owns-its-symbols model, muddies audit attribution (which
strategy "owns" a de-risking sell?), and would need new reconciliation machinery.
Keeping the daily tick on the *owning* strategy preserves single ownership and clean
audit, while the **separate overlay module** still delivers Review v2's layer
separation. This reconciles the two reviews: the *computation/responsibility* is a
separate layer (v2), but the *position ownership and trigger* stay with one strategy
(avoiding B's coordination cost).

**Why risk-reducing only.** A gross multiplier capped at 1.0 can only shrink exposure,
so the overlay can never manufacture risk the risk engine then has to catch — it is
defense-in-depth-aligned with ADR 0004. An overlay that could *add* exposure would be a
fundamentally different, higher-stakes decision.

**Why default off.** Enabling the overlay changes the deployed book's risk profile and
must be backtested first (ADR 0014). "Conservative defaults, configurable extremes" —
the protective behavior is opt-in and deliberate, never a silent default flip.

## Implementation notes

- **Overlay module:** a new `app/strategies/overlay/` (pure function: `(market_state,
  params) -> desired_gross ∈ [0,1]`), reusing the `_gross_scale` EWMA-vol logic already
  validated in §1. Returns a **scalar**, not weights. No broker import; no DB writes of
  its own; no order concepts.
- **Execute step (separate):** validate → diff held book vs. `desired_gross × book ×
  weights` → route deltas through `OrderRouter.submit()`. A **drift threshold** skips
  re-sizing when `|Δgross|` is below a small epsilon (execution hygiene; distinct from
  §4 smoothing). **Idempotent:** if the book already matches the target for the day, the
  step is a no-op (`max_instances=1` + `coalesce` on the scheduler job, like the §6
  breaker job, plus a same-day already-applied guard).
- **Audit fingerprint:** each overlay run logs a structured payload — `overlay_version`,
  `date`, `gross_target`, `proxy_vol`, `reason`, `strategy_version` — so an overlay
  re-size is replayable and distinguishable from a weekly rebalance.
- **Framework addition (the "small" part):** the strategy base + engine/scheduler gain
  support for an **optional secondary daily cadence** (e.g. a `daily_overlay_schedule`
  cron field, default `None`). The engine registers it alongside the existing weekly
  `schedule`; on a daily tick the strategy runs an overlay-only path that re-sizes the
  held book toward the gross target and routes any deltas through `OrderRouter.submit()`.
- **Fail open / fail safe:** if the market proxy/vol estimate is unavailable, the
  overlay returns gross = 1.0 (no scaling) and logs — matching §1 and the
  reviewed-and-praised "fail open for market regime" posture. It must never fail
  *closed* into a forced liquidation.
- **Audit:** overlay-induced orders are audit-logged like any order (through the router)
  and tagged so an overlay re-size is distinguishable from a weekly rebalance.
- **Defaults:** `use_daily_overlay: bool = False`; reuse `vol_target_annual` /
  `vol_ewma_span` from §1 so a single set of params governs both the backtest overlay
  and the live overlay.
- **CI:** no new invariant required; the overlay is covered by the existing
  `check_adr0002.sh` (it must not call a broker adapter) and the risk-coverage gate for
  any code that touches sizing/risk.

## Consequences

- **Positive.** Intra-week crash de-risking reaches the *live* loop, not just the
  backtest. The overlay is a reusable, isolated, testable layer with a formal boundary.
  Selection vs. sizing become cleanly separable in the audit trail. Single-OrderRouter
  and one-strategy-owns-its-symbols are preserved. The §1 vol-scale math is reused, not
  reinvented.
- **Negative.** It is a **real framework change** — the engine/scheduler must now
  support a per-strategy secondary daily cadence, which adds surface area to the most
  safety-critical part of the system (the live execution loop). Daily re-sizing adds
  turnover and cost (mitigated by §4 exposure smoothing, and by the cap-at-1.0
  no-leverage rule). More moving parts in the live path means more to test and monitor.
- **Neutral.** `momentum-portfolio` gains an optional second schedule; its weekly
  selection behavior is unchanged when the overlay is off. The vol-scale logic shifts
  from a backtest-only return overlay to a live-callable module (same math, new call
  site).

## Alternatives considered (not chosen)

- **(B) Companion overlay strategy.** A separate strategy that scales gross on the book
  another strategy selected. *Rejected:* cross-strategy position ownership conflicts
  with one-strategy-owns-its-symbols and the single OrderRouter; unclear audit
  attribution and new reconciliation cost. *Reconsider if* multiple alpha strategies
  ever need to share one overlay — at which point extracting the overlay into a true
  standalone engine/service (owning its own scaling orders under a defined ownership
  protocol) becomes worth the coordination cost.
- **(A) Dual-cadence logic inside the strategy with no separate module.** *Rejected:*
  Review v2 explicitly warns against burying dual-cadence logic in the selection code;
  yields no reusable, isolated overlay and is hard to test independently.
- **Full portfolio-engine rewrite now** (formal alpha/portfolio/overlay/execution/risk
  services). *Rejected:* over-scoped for one strategy and one overlay; YAGNI. This ADR
  is the *first* step toward that separation, taken at bounded cost.
- **Intraday / sub-daily overlay.** *Rejected (out of scope):* daily is the cadence the
  reviews call for; sub-daily adds data and execution complexity without evidence it is
  needed.

## Re-evaluation triggers

- **Turnover/cost erosion:** if daily re-sizing's added turnover materially erodes
  net returns in backtest or paper beyond what §4 smoothing contains, revisit the
  cadence (e.g. act only on threshold moves) or the mechanism.
- **Second consumer:** if a second alpha strategy needs the same overlay, revisit (B) —
  a shared standalone overlay engine may then justify its coordination cost.
- **Execution-Engine extraction:** §2 implements the compute/validate/execute split as a
  boundary *within* the overlay path (compute step + execute step that calls
  `OrderRouter`), not a standalone Execution Engine. When a second consumer needs order
  diffing/batching/retry/partial-fill handling, extract that execute step into a real
  Execution Engine (the next layer in the alpha/portfolio/overlay/execution/risk
  separation).
- **Framework leakage:** if the optional-secondary-cadence addition proves leaky or
  complicates the engine's scheduling guarantees, reconsider whether the overlay belongs
  in the engine at all.
- **Leverage need:** if a future strategy genuinely needs gross > 1.0, the
  risk-reducing-only constraint must be revisited as a separate, higher-stakes decision.
