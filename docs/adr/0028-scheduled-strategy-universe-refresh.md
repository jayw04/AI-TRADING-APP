# ADR 0028 — Scheduled Pre-Open Opportunity Assignment (Range Top-N)

*(formerly "Scheduled daily strategy-universe refresh"; renamed per owner review to match the
Candidate Engine / Discovery Lab framing — the Candidate Engine **assigns the day's opportunity
set** before the strategy starts.)*

| Field | Value |
|---|---|
| Date | 2026-06-26 |
| Status | **Accepted** (owner approved 2026-06-26, 9.7/10, `docs/review/comments.md`; small edits folded) |
| Phase | Range-trading research (P8 §5a/§7 follow-on) |
| Supersedes | — |
| Related | 0005 (24-hour activation cooldown — this carves a narrow exemption), 0002 (single OrderRouter — the job never submits orders), 0026 (research programs as configuration — this extends "selection is configuration"), 0019 (Research Engine subsystem), 0020 (daily gross-exposure overlay — strategy-level risk stays centralized) |

## Context

The Range Trader's edge depends heavily on *which* names it trades on a given day: a
fade-the-range strategy needs oscillating names, and a single fixed symbol goes dormant on a
trending day (the live NVDA sleeve recorded 0 trades over ~17 days, partly because NVDA
rarely returned to its opening-range low). The design (`Docs/design/RangeTrading_Logic_and_Research`,
§"Top 3–5 candidates") resolves this by having **one** Range Trader consume the Candidate
Engine's **Top-N candidates each morning**, so its universe changes daily — the only strategy
on the platform whose universe does.

But a running strategy's symbol set is **fixed at start**: `StrategyEngine.register()` reads
`symbols_json` once, and the `PUT /strategies/{id}` symbol-edit path is guarded to require
`IDLE`. There is no sanctioned runtime symbol-mutation API. So refreshing the universe of an
already-running strategy necessarily means stop → update symbols → start. That pattern brushes
against ADR 0005 (activation cooldown — "activation is the expensive direction") and the
general expectation that a strategy's configuration is stable over its run. We must decide
whether a strategy's universe may be reset automatically every day, by what mechanism, and
under what guardrails.

## Decision

1. A strategy may **opt in** to daily system-driven opportunity assignment by setting
   `params_json.auto_select_top_n` to an integer `> 0` (Range Trader template only). An
   optional `params_json.auto_select_universe` overrides the default candidate pool. A
   strategy without the marker is never touched.
2. A **pre-open scheduled job** (~09:00 ET, weekdays) selects today's Top-N candidates
   **evidence-first** (realized backtest win rate → Sharpe → structural Range Score) and
   re-points each opted-in strategy via **stop → set `symbols_json` → audit → start**.
3. **Frozen daily input.** The Top-N set is chosen once, pre-open, and is **immutable for the
   trading session** — no intraday replacement occurs even if a better candidate appears later.
   This keeps each day's paper-trial evidence reproducible. The job runs only **before RTH
   (09:30 ET)**; a run at/after the open is skipped.
4. **Pre-flight guards.** For a given strategy the stop → start runs only when **all** hold:
   it is **PAPER** (not LIVE), the time is **pre-RTH**, there is **no open position** in any
   symbol it currently trades, and there is **no working (non-terminal) order** from it. If any
   fails, the rotation is **skipped + WARN-logged** for that sleeve that day (never a partial
   stop/start).
5. This assignment is **exempt from the activation cooldown (ADR 0005)**, narrowly: the
   exemption applies **only to system-initiated, pre-open, same-strategy, PAPER-only universe
   reassignment with no open position and no pending order**. It is a same-status rotation, not
   an (re)activation, and resets no cooldown or activation timestamp.
6. LIVE strategies are explicitly **out of scope** and skipped (the stop→start cycle would
   downgrade LIVE→PAPER; rotating a live book daily needs its own ADR + stronger controls).
7. Every applied assignment is **audit-logged** (`STRATEGY_UPDATED`, actor `SYSTEM`,
   `payload.source = "daily_preopen_auto_select"`, carrying the previous and new symbol lists
   and `n`). The job is **idempotent** (a no-op when the selection equals the current universe),
   **fail-soft** per strategy, and touches **no order path**.

## Rationale

**Why an opt-in marker, not global behavior.** Daily universe mutation is surprising; it must
never happen to a strategy the user didn't enable. Gating on an explicit per-strategy param
means the blast radius is exactly the strategies the user marked, and the marker is visible in
the strategy's params.

**Why stop → start rather than runtime symbol mutation.** The engine deliberately fixes the
symbol set at `register()` and routes all symbol edits through the IDLE-guarded PUT path.
Adding a runtime "change symbols on a running strategy" API would be a materially larger and
riskier change — it touches bar subscription/dispatch, the in-flight-order reconciliation, and
would need its own audit story. The stop → update → start cycle instead **reuses already-audited,
already-tested paths** (`engine.unregister` / `engine.register`, the same IDLE-guarded symbol
write the PUT endpoint uses). Pre-open, before the strategy holds any intraday position, the
restart is clean.

**Why exempt from the activation cooldown.** ADR 0005's cooldown protects the IDLE→LIVE
transition — the moment real (or paper-as-real) capital is first committed to a *new*
strategy configuration. A daily universe rotation within an *already-running research book* is
not that transition: the strategy, its risk limits, its account, and its run intent are
unchanged; only the day's symbol list rotates. Applying a 24-hour cooldown per rotation would
make daily rotation impossible, defeating the design. The exemption is therefore narrow: it
covers same-status, system-initiated, audited universe rotation of an opted-in **paper**
strategy — nothing else.

**Why PAPER only, excluding LIVE.** Two reasons. (a) Mechanically, the stop→start cycle passes
through `IDLE`, and `register()` maps an `IDLE` row to `PAPER`; preserving `LIVE` across the
cycle needs extra handling that does not yet exist. (b) More importantly, silently re-pointing
a **live** book's holdings every morning is a far larger trust and risk decision than rotating
a research book — it warrants its own ADR with stronger controls (operator notification,
per-day turnover caps, an explicit live-rotation acknowledgment). Until that exists, the job
must refuse LIVE.

## Implementation notes

- **Opt-in**: `params_json.auto_select_top_n: int (>0)`; optional `auto_select_universe: list[str]`.
  These live in `params_json` and are intentionally **not** in the template's `params_schema`
  (they configure orchestration, not strategy behavior — the template's `on_bar` ignores them).
- **Service**: `app/services/range_auto_select.py`
  - `load_range_backtest_evidence(session, symbols)` — per-symbol realized win-rate/Sharpe/trade-count
    from the latest range `BacktestResult` (shared with the Range Candidates API).
  - `select_range_universe(session, *, bar_cache, n, universe, now)` — rank evidence-first, return Top-N.
  - `refresh_range_universe(session_factory, engine, bar_cache, *, strategy_id, n, universe, now)` —
    read row → select → (if running) `engine.unregister(reason="daily_range_autoselect")` →
    set `symbols_json` + `updated_at` → audit → (if it was running) `engine.register`. Idempotent
    on unchanged; an `IDLE` strategy is updated but **not** started (activation stays a user action).
  - `run_daily_range_universe(session_factory, engine, bar_cache, *, now)` — weekend-skip,
    **before-RTH gate** (`now_et.time() < 09:30` or skip), discover opted-in strategies via
    `find_autoselect_range_strategies`, apply each, per-strategy fail-soft.
  - `_preflight_blocker(session, row)` — returns `"pending_order"` (any non-terminal `Order` from
    this strategy) or `"open_position"` (a `Position` with `qty != 0` on the strategy's PAPER
    account in any symbol it currently trades), else `None`. `refresh_range_universe` calls it on
    the stop→start path and returns `skipped_pending_order` / `skipped_open_position` on a hit.
- **Guards implemented** (review #6): `skipped_live` (status LIVE), `skipped_after_open` (RTH gate),
  `skipped_open_position`, `skipped_pending_order` — each WARN-logged; no partial stop/start.
- **Schedule**: registered in `app/lifespan.py` as an APScheduler cron job, `day_of_week="mon-fri",
  hour=9, minute=0` (scheduler timezone is already ET), `max_instances=1`, `coalesce=True`. It is a
  **no-op until a strategy opts in**.
- **Minimum-quality gate** (review #4, implemented): an optional `params_json.auto_select_min_score`
  (default 0 = off) sets a structural Range-Score floor (`score = atr20_pct × oscillation`); a
  candidate must clear it to be eligible, so a weak day selects fewer than N — or zero, which skips
  the day for that sleeve — rather than filling slots with poor setups.
- **Selection evidence** (review #3, implemented): the audit payload carries a `selection` record —
  `ranking_version` ("evidence-first-v1"), `n_requested`, `min_score`, `universe_size`, the chosen
  names with `rank`/`score`/`win_rate`/`sharpe`/`backtested`, and the `excluded` names with reasons
  (`insufficient_data` / `not_range_bound` / `below_min_score` / `rank_beyond_n`) — making each daily
  pick a reproducible Evidence-Engineering artifact, not just a symbol diff.
- **Audit**: `AuditAction.STRATEGY_UPDATED`, `actor_type=SYSTEM`, `payload={"changed":{"symbols":…},
  "previous":…, "source":"daily_preopen_auto_select", "n":…}`. No new `AuditAction` value (keeps the
  on-call runbook unchanged); the `source` tag distinguishes a system rotation from a user edit.
- **No new CI invariant.** The job imports nothing from the order path (ADR 0002 / 0006 unaffected).

## Consequences

- **Positive**: range research observes more valid setups per day across a diversified, evidence-ranked
  universe; the "0 trades on a trending name" dormancy failure is mitigated; the daily selection and its
  inputs are auditable; the mechanism reuses existing engine + audit paths.
- **Negative**: a strategy's universe is **no longer stable day to day**, which complicates
  cross-day performance attribution (a name traded Monday may be gone Tuesday — analytics that
  assume a fixed universe must account for this). The daily stop→start adds engine churn and audit
  volume. An external scheduled job now **mutates strategy configuration**, a new write path that must
  be reasoned about alongside user edits. LIVE auto-rotation is unsupported — a deliberate gap.
- **Neutral**: introduces the `auto_select_top_n` params convention (orchestration config stored in
  `params_json`, outside `params_schema`); other strategy types could adopt the same marker later.

## Alternatives considered (not chosen)

- **Fixed large universe + internal Top-N gating** (register the strategy once with the full candidate
  pool; each morning the strategy itself trades only today's Top-N). Rejected: the engine would feed
  bars for the entire pool every day (wasteful), and the evidence-first ranking needs DB access that is
  not available inside `on_bar`. Reconsider if the engine gains cheap universe-wide bar provisioning and
  the ranker becomes callable from strategy context.
- **Runtime symbol-mutation API on the engine** (change `running.symbols` in place, no restart).
  Rejected: a much larger surface (subscription, dispatch, in-flight reconciliation) with no existing
  audit story, and it would erode the IDLE-only symbol-edit guard. Reconsider if such an API is built
  and audited for general use.
- **Recreate the strategy row each day** with the new universe. Rejected: loses strategy identity and
  history, multiplies audit/lineage churn, and orphans signals/backtests tied to the prior row.

## Re-evaluation triggers

- A desire to auto-rotate a **LIVE** range book → supersede this ADR with one that adds LIVE handling
  plus stronger controls (notification, turnover caps, explicit acknowledgment).
- The engine gains a sanctioned **runtime symbol-update** API → revisit the stop→start mechanism.
- Evidence that **daily universe churn harms research attribution** (cannot fairly compare results
  across days) → reconsider cadence (e.g. weekly rotation) or a freeze-after-N-days rule.
- **More than one strategy type** wants daily auto-select → generalize the opt-in marker and this ADR
  beyond the Range Trader.
