# Proposal Generation, Baseline Eval, and Range Trader AAPL — Findings (Review Draft)

> **v0.2 — owner review folded** (`docs/review/comments.md`, 9.8/10). Added: the **immutable = historical
> experiment / reproducibility** framing (§4.5); the **Evidence Sufficiency Rule** as a platform invariant
> (§4.6, elevated from a §8 recommendation); the **priority-by-platform-risk** summary (§8.0); and the
> **four-evidence-types** placement — this document produces **Proposal Evidence** (`EvidenceEngineering_Methodology` §7a).

| Field | Value |
|---|---|
| Document version | v0.2 (review draft) |
| Date | 2026-06-24 (v0.2 fold 2026-06-25) |
| Author | Cursor session (Jay review) |
| Scope | Findings from live debugging of Proposals page, agent service, and backtest eval for **Range Trader AAPL** (strategy #3, user `range@local.dev`) |
| Related ADRs | [0014](../adr/0014-backtests-primary-eval-ground-truth.md) (backtests as eval ground truth), [0010](../adr/0010-agent-separate-process-mcp-reads-api-writes.md) (agent architecture) |
| Live DB snapshot | `data/workbench.sqlite` as of 2026-06-24 ~18:55 UTC |

---

## 1. Executive summary

We exercised the full **Generate proposal → backtest eval → Accept → Apply** path for **Range Trader AAPL**. Proposal generation and apply **work end-to-end** after several infrastructure and code fixes. The **baseline backtest eval** also runs, but for Range Trader AAPL it currently produces **zero trades** in both baseline and variant runs, so verdicts are **mechanical ties** (“above baseline”) rather than evidence of edge.

This document captures:

1. What broke during testing and what was fixed (may be **uncommitted** in the working tree — see §7).
2. How the **baseline** is defined and when it updates (answer: **once per proposal**, not daily).
3. Observed results for proposal **#7** (applied) and earlier failed proposals **#5–#6**.
4. **Recommended product/engineering changes** for Jay to accept, defer, or reject.

---

## 2. System under test

| Item | Value |
|---|---|
| Strategy | Range Trader AAPL (`strategies.id = 3`) |
| Owner | `range@local.dev` (user_id = 2) — per [app login info](../app%20login%20info.txt) |
| Strategy status (after testing) | **IDLE** (params updated; not paper/live) |
| Symbol | AAPL |
| Eval window | **90 days** (default; user has no `eval_window_days` override in agent envelope) |

**Important:** Each strategy user is isolated. Proposal generation requires that user’s **Agent API Key** in the credential store. The docker `agent` service holds `ANTHROPIC_API_KEY` for LLM calls; per-user **agent keys** are passed from the backend at invoke time (see §4.1).

---

## 3. Timeline of issues and resolutions

### 3.1 “Generation failed or was budget-rejected” (not budget)

The UI message is generic for **any** propose failure (`apps/frontend/src/pages/Proposals/index.tsx`).

| Root cause | Symptom | Resolution |
|---|---|---|
| Missing `AGENT_API_KEY` in `.env` / agent container | Agent 500 before generation | Registered key for dev user; added to `.env`; recreated agent |
| Missing `ANTHROPIC_API_KEY` | LLM step fails | User added key to `.env`; synced via `rebootstrap_credentials.py` |
| LLM returned JSON inside markdown fences | `LLM output not valid JSON` | Agent now strips fences (`_extract_json` in `proposal_generation.py`) |
| **User mismatch** — agent used user 1’s bearer token for user 2’s proposal | `404 Not Found` on `GET /proposals/{id}` | Backend passes **proposing user’s** `AGENT_API_KEY` to agent; evidence reads use backend HTTP with that key (not shared workbench-mcp bearer) |
| User 2 had no `AGENT_API_KEY` in credential store | Same as above for `range@local.dev` | Registered per-user agent key for user 2 |

### 3.2 “Eval failed” on proposals #5 and #6

| Root cause | Symptom | Resolution |
|---|---|---|
| `BacktestContext` missing `get_account_equity()` | `baseline_failed: 'BacktestContext' object has no attribute 'get_account_equity'` | Added method to `apps/backend/app/strategies/backtest_context.py`; backend rebuilt |

Proposals **#5** and **#6** remain **REJECTED** with **failed** eval snapshots from before the fix. They were not automatically re-run.

### 3.3 UI showed “Backtest pending” after eval completed

For proposal **#7**, DB had `evaluation_results.status = complete` while the UI still showed **Backtest pending** until refresh. Likely **stale React Query cache** / no auto-poll while eval runs (~1 minute).

### 3.4 Recurring dev-environment gotchas (not proposal-specific)

| Issue | Impact |
|---|---|
| `vite.config.ts` proxy hardcoded to `127.0.0.1:8000` inside Docker frontend | Login page shows TOTP (login-config fetch fails); fixed via `VITE_PROXY_TARGET=http://backend:8000` |
| `start-claude.bat` reverted to `npx` | Norton SSL blocks npm; batch file fixed to prefer native `claude.exe` |

---

## 4. How the baseline is set (canonical behavior)

Per **ADR 0014** and `apps/backend/app/services/proposal_evaluation.py`:

### 4.1 Trigger

Baseline eval is enqueued **once**, atomically when a proposal transitions **DRAFT → REVIEWING** (after the agent PATCHes the proposal with payload + evidence). See `apps/backend/app/api/v1/proposals.py` (PATCH handler).

There is **no** daily cron that refreshes baselines for existing proposals.

### 4.2 Baseline definition

At enqueue time:

```text
baseline_params = copy(strategy.params_json)     # snapshot at proposal time
variant_params  = apply(proposal.changes, baseline_params)
window_start    = now - eval_window_days
window_end      = now
symbols         = strategy.symbols_json
initial_equity  = 100000   # fixed in _build_config_json today
```

Two `BacktestJob` rows are inserted:

- `proposal_{id}_baseline` — current params  
- `proposal_{id}_variant` — proposed params  

A ~60s cron (`reconcile_pending_evals`) **only completes in-flight jobs**; it does not re-baseline.

### 4.3 Verdict rule (Decision 8)

From `compute_verdict()`:

- Variant Sharpe ≥ baseline Sharpe **and**
- Variant max drawdown ≥ max(baseline max DD − 0.05, −0.20)

**Ties count as above baseline** (variant equals baseline → pass).

### 4.4 Configurable knobs (per user)

| Knob | Location | Default | Notes |
|---|---|---|---|
| `eval_window_days` | Trading profile → `agent_envelope_json` | **90** | Must be 7–365 if set |
| `initial_equity` | Hardcoded in `_build_config_json` | **100000** | Not tied to live account equity today |
| Backtest bar timeframe in eval jobs | `_build_config_json` | **1Min** | Strategy param `timeframe` may differ (e.g. 5Min) |

### 4.5 Does the baseline update daily?

**No.** For a given proposal row, `evaluation_results_json` is **immutable** after the eval completes (success or failure).

A **new** baseline appears only when:

- User clicks **Generate proposal** again (new proposal id, new snapshot of `params_json`, new `[now - window, now]` dates), or
- Future feature explicitly re-enqueues eval (not implemented today).

Applying a proposal **does not** re-run eval on prior proposals.

> **Why frozen (Evidence Engineering).** Proposal evaluations are **historical experiments**: their
> purpose is **reproducibility**, not continuous optimization. A frozen baseline + frozen variant +
> immutable verdict is what makes a proposal's evidence auditable forever — the same discipline ADR 0014
> applies to research backtests. This is **Proposal Evidence** in the four-evidence-types taxonomy
> (`EvidenceEngineering_Methodology` §7a): the proof that a *change* beats the current baseline. The
> verdict it produces is stored in the Evidence Registry and referenced by the Capability Registry.

### 4.6 The Evidence Sufficiency Rule (platform invariant, not a recommendation)

The zero-trade case (§5.4) is not a tuning preference — it is a **platform invariant**, ratified in
ADR 0014 v1.1 and Evidence Engineering Principle 0 (*absence of evidence is not evidence of success*):

> **Evidence Sufficiency Rule.** No proposal may receive **PASS** (`above_baseline`) or **FAIL**
> (`below_baseline`) without sufficient observations. An evaluation that produces no trades / no
> observations is **`INSUFFICIENT_EVIDENCE`**, never a tie-pass.

This is implemented in `proposal_evaluation.compute_verdict` (review E4) and is why E4 is **Critical**
in §8 below: a zero-trade tie that reads as `above_baseline` is a *false* evidence claim, the one
failure mode Principle 0 exists to forbid.

---

## 5. Case study: Range Trader AAPL, proposal #7 (APPLIED)

### 5.1 Proposal

| Field | Value |
|---|---|
| State | **APPLIED** (2026-06-24 ~18:54 UTC) |
| Change | `max_trades_per_day`: **4 → 3** |
| Confidence | LOW |
| Rationale | Conservative cap with no empirical trade history |

### 5.2 Backtest window

- **90 days:** 2026-03-26 → 2026-06-24 UTC  
- Symbol: AAPL  

### 5.3 Baseline vs variant params (from backtest job configs)

| Param | Baseline | Variant |
|---|---|---|
| `max_trades_per_day` | 4 | 3 |
| `no_trade_open_minutes` | 5 | 5 |
| `hard_exit_before_close_minutes` | `'15'` (string) | `'15'` (string) |
| `entry_price` / `exit_price` / `stop_price` | 290.76 / 291.23 / 280.71 | same |

### 5.4 Metrics (both runs identical)

| Metric | Baseline | Variant |
|---|---|---|
| trade_count | **0** | **0** |
| total_return | 0.0 | 0.0 |
| sharpe_ratio | 0.0 | 0.0 |
| max_drawdown | 0.0 | 0.0 |
| ending_equity | 100,000 | 100,000 |

**Verdict:** `above_baseline` (tie passes).

### 5.5 Why zero trades?

Range Trader uses **fixed** entry/exit/stop prices in `params_json`. If AAPL did not interact with those levels during the 90-day window, the backtest produces **no fills**. This is expected for this strategy shape—not necessarily a platform bug.

**Separate issue:** `hard_exit_before_close_minutes` is stored as string `'15'` not int `15`. Proposal #6 (rejected) targeted that type mismatch; it was not applied.

### 5.6 Strategy state after apply

| Field | Value |
|---|---|
| `max_trades_per_day` | **3** (applied) |
| `hard_exit_before_close_minutes` | `'15'` (still string) |
| Strategy status | **IDLE** — apply updates params only; does not activate paper/live |

---

## 6. Proposal inventory (strategy #3, snapshot)

| id | state | eval | summary (short) |
|---|---|---|---|
| 7 | **APPLIED** | complete, above_baseline | max_trades 4→3 |
| 6 | REJECTED | failed (pre-fix BacktestContext) | string→int hard_exit |
| 5 | REJECTED | failed (pre-fix BacktestContext) | widen no-trade buffers |
| 3 | APPLIED | complete | hard_exit 5→15 (earlier session) |
| 2 | REVIEWING | complete | no_trade_open 5→15 |
| 1 | DRAFT | — | orphan from failed debug run |

---

## 7. Code changes made during investigation

The following were changed in the working tree during debugging. **Verify git status before merge** — some fixes may overlap with other local edits (vite proxy, `start-claude.bat`).

| Area | File(s) | Change |
|---|---|---|
| Multi-user agent auth | `apps/backend/app/api/v1/proposals.py` | Pass proposing user’s `AGENT_API_KEY` to agent |
| Agent invoke | `apps/agent/src/agent/server.py`, `config.py` | Accept per-request `agent_api_key` |
| Evidence reads | `apps/agent/src/agent/backend_client.py`, `proposal_generation.py` | Read profile/history/orders via backend bearer (user-scoped) |
| LLM JSON parse | `apps/agent/src/agent/proposal_generation.py` | `_extract_json()` for markdown fences |
| Backtest eval | `apps/backend/app/strategies/backtest_context.py` | `get_account_equity()` for range_trader |
| Tests | `apps/agent/tests/…`, `apps/backend/tests/factor_data/test_context_factors.py` | Updated/added coverage |
| Ops | `.env`, credential store | `AGENT_API_KEY`, `ANTHROPIC_API_KEY`, user 2 agent key |

---

## 8. Recommended changes (for review)

Jay: mark each **Accept / Defer / Reject** after review.

### 8.0 Priority summary (by platform risk, owner review)

The recommendations below are grouped by *subsystem* (Product / Eval / Ops). Read by **platform risk**,
the priority order is:

| Priority | Items | Why |
|---|---|---|
| **Critical** | **E4** (zero-trade → INSUFFICIENT_EVIDENCE), **P3** (re-run a failed eval), **P1** (show real error text) | E4 prevents a *false* evidence claim (the Evidence Sufficiency Rule, §4.6); P3/P1 are the difference between a debuggable and an opaque pipeline. |
| **High** | **E5** (dynamic levels for fixed-price evals), **E6** (param-type normalization on apply), **O1** (per-owner agent keys) | Make evals *meaningful* and multi-user setup *repeatable*. |
| **Medium** | everything else (P2/P4/P5, E1/E2/E3, O2/O3) | Quality-of-life and policy decisions; no correctness risk. |

(E4/E5/E6/P3 are already addressed in code — PRs #260–#263; this table records the *risk ranking*
the owner asked for.)

### 8.1 Product / UX (high impact)

| # | Recommendation | Rationale |
|---|---|---|
| P1 | **Show real error text** on Generate failure (not only “budget-rejected”) | Every failure class looked identical; debugging cost hours |
| P2 | **Poll or websocket** proposal eval status while `pending`/`running` | UI showed “Backtest pending” after completion until manual refresh |
| P3 | **“Re-run evaluation”** action on REVIEWING proposals with `failed` eval | #5/#6 stuck after bug fix; today only option is reject + regenerate |
| P4 | **Eval panel on APPLIED proposals** should show final metrics prominently | Applied card still emphasized pending state in testing |
| P5 | Document in UI that **Apply ≠ Activate** | User asked if strategy was “running”; IDLE after apply confused expectation |

### 8.2 Baseline / eval engine (medium impact)

| # | Recommendation | Rationale |
|---|---|---|
| E1 | **Rolling baseline policy** — decide explicitly: keep per-proposal snapshot (current) vs daily refresh vs regenerate on param change | User asked if baseline updates daily; today it does not |
| E2 | Use **`initial_equity_estimate` from strategy params** (or live equity) instead of hardcoded 100k | Eval may not match user’s sizing assumptions |
| E3 | Align eval job **`timeframe`** with strategy param (5Min vs 1Min mismatch today) | May affect bar granularity and fill simulation |
| E4 | **Fail or warn** when baseline and variant both have **zero trades** | Tie verdict passes but provides no information (AAPL #7) |
| E5 | For fixed-price strategies, **require** or backtest with **dynamic levels** (opening range mode) for eval to be meaningful | Otherwise eval is structurally empty |
| E6 | Normalize param types on **Apply** (int vs string) | `hard_exit_before_close_minutes` still `'15'` string |

### 8.3 Multi-user / ops (medium impact)

| # | Recommendation | Rationale |
|---|---|---|
| O1 | **Register `AGENT_API_KEY` for all strategy owners** (users 2–6) or document as setup step | Each isolated user needs their own key |
| O2 | Add `AGENT_API_KEY` to `rebootstrap_credentials.py` map | Today only partial `.env` → store sync |
| O3 | Pin **docker frontend proxy** + `start-claude.bat` in repo or CI check | Both reverted repeatedly during session |

### 8.4 Out of scope (unless explicitly desired)

- Changing ADR 0014 verdict formula  
- Auto-apply proposals on above_baseline  
- Daily scheduled proposal generation for Range Trader (different from eval baseline)  
- Live/paper activation workflow changes  

---

## 9. Open questions for Jay

1. **Should baseline eval re-run** when strategy params change outside the proposal flow (manual edit, apply of a different proposal)?  
2. **Is zero-trade backtest a pass or “insufficient data”?** Today it passes via tie rule.  
3. **Should Range Trader eval use opening-range dynamic levels** instead of stale fixed prices in `params_json`?  
4. **Should eval window roll forward** (e.g. always “last 90 calendar days” on each new proposal only — current — vs also on a schedule)?  
5. **Commit strategy:** merge investigation fixes as one PR or split (multi-user agent / BacktestContext / UX)?  

---

## 10. Manual verification checklist (post-merge)

Run as `range@local.dev` on strategy #3:

1. Login at http://127.0.0.1:5173 (no TOTP if proxy configured).  
2. Proposals → Range Trader AAPL → **Generate proposal** → expect **REVIEWING** within ~30s.  
3. Wait ~1–2 min → refresh → eval **complete** (or failed with readable reason).  
4. Accept → Apply → confirm `max_trades_per_day` (or proposed param) updated in Strategies page.  
5. Confirm strategy remains **IDLE** until explicit paper/live activation.  

---

## 11. References

- Eval pipeline: `apps/backend/app/services/proposal_evaluation.py`  
- Propose endpoint: `apps/backend/app/api/v1/proposals.py`  
- Agent generation: `apps/agent/src/agent/proposal_generation.py`  
- Range strategy: `apps/backend/strategies_user/templates/range_trader.py`  
- UI: `apps/frontend/src/pages/Proposals/index.tsx`, `apps/frontend/src/components/proposals/EvalPanel.tsx`  
- Credentials runbook: `Docs/runbook/credentials.md`  

---

*End of review draft v0.1 — intended for Jay’s accept/defer/reject on §8 and answers to §9.*
