# Trading Workbench — TODO

> Single source of truth for "what's done, what's next" across sessions. Update at the end of each working session. For frozen versioned plans, see `docs/implementation/` and `docs/design/`.

Last updated: 2026-06-04 · branch: `main` · latest tag: **`p6b-session2b-variant-complete`** (`12da27e`) — **P6b §2b-variant merged via PR #59** (squash `12da27e`): variant-vs-live **comparison metrics** + read endpoint + MCP tool + D5/D8 hooks. New **`app/services/equity_curve.py`** — `reconstruct_equity_curve(...)`: daily NYSE-business-day EOD marks (`E = capital_base + realized + unrealized_at_close`), closes via the injected **`BarCache.get_bars(ticker,"1Day",…)`** (`_close_on_day`), missing-close days skipped, curated-holiday calendar fallback (`pandas_market_calendars` not a dep / Norton-blocked install → fallback is the live path). `paper_variant.py` +`VariantSideMetrics`/`VariantComparison`/`find_in_flight_variant`/`compare_variant_to_parent` — both sides share **ONE `capital_base`** + window `[variant.created_at, now]`; metrics from the §1a-drift FUNCTIONS (`win_rate`/`avg_return_per_trade`/`sharpe_ratio`/`max_drawdown` — NO `compute_metrics`/`BacktestMetrics`; capital base = `BacktestResult.metrics_json.starting_equity` or $100k). `GET /strategies/{id}/variant-comparison` (read-only; `no_active_variant`|`variant_active`). **MCP `workbench_paper_variant_metrics` (18→19)**, positional, `_TOOLS` list literal. **D5 auto-spawn** on proposal ACCEPT when `agent_envelope_json.auto_validate_proposals` set + parent LIVE (best-effort; swallows `spawn`'s plain `ValueError`). **D8 invalidation** — terminate the in-flight variant when a parent leaves `ACTIVE_STRATEGY_STATUSES` (`stop_strategy`/`deactivate_strategy` endpoints) + on `apply_proposal`, via `terminate_for_parent` (no-op if none). **DEVIATIONS:** D8 hook lives at the **ENDPOINT layer** (engine handle is there, not on `ActivationService`); two **SQLite naive→aware** datetime coercions (fill-walk EOD compare + comparison window); **fill horizon = end-day EOD** not the mid-day `end` instant (each day marked at EOD); `find_in_flight_variant` promoted to module-level; `request:Request` added to `patch_proposal`+`apply_proposal`. **No migration; no new audit action; no new lifecycle states; no order-path code.** 35 new tests; full backend suite green; ruff+mypy clean; no-LLM/workbench-MCP-readonly/agent-no-DB/audit-immutability invariants green; all PR CI green; merged on Jay's "merge now" (CI-green-verified). **Norton-deferred:** live `BarCache→data.alpaca.markets` close path + open-position equity curves against a real broker. Session doc + Results: `..._P6b_Session2b_variant_v0_1.md` / `..._Session2b_variant_Results_v0.1.md`. · **Next: P6b §3** — EVIDENCE_READY/PROMOTING/PROMOTED lifecycle + **4-criterion promotion gate** (≥30d-or-50-trades, ≥5% Sharpe margin, positive absolute return, no 7-day worst-case divergence beyond 20% of live max-dd) + evidence bundle + promotion-with-P5§7-cooldown + STRATEGY_PROMOTED + 30-day post-promotion lockout; the equity-curve primitive is now ready for the gate. Then **§2c** variant UI surfaces (card / overview / comparison viz — draft against the §2b Results, Rec #10). Still pending (live, non-Norton stack): **§1b.12 → `p6-session1-complete`** + §2b-variant live equity-curve re-confirmation. · prior tags `p6b-session2a-variant-complete` (`7ee5186`), `p6b-session1b-drift-complete` (`377617a`), `p6b-session1a-drift-complete` (`fe2d3ab`), `p5.5-complete` (`878b9f8`)

**P6b §2a-variant (PR #58, `7ee5186`, tag `p6b-session2a-variant-complete`):** **paper-variant model + spawn + lifecycle** — the auto-validation paper-variant runner FOUNDATION (ADR 0007). When an ACCEPTED proposal on a **LIVE** strategy is validated, the platform **clones the strategy** as a new `PAPER_VARIANT` row (`parent_strategy_id` FK + variant params) that runs forward on the user's paper account in parallel with the live strategy. **Migration `c5e1a2b3f4d6`** (`strategies.parent_strategy_id` nullable self-FK; round-tripped up/down/up on a fresh DB). **Enums:** `StrategyStatus.PAPER_VARIANT`, `ProposalState.EVALUATING`, new **`ENGINE_RUNNABLE_STATUSES` = ACTIVE ∪ {PAPER_VARIANT}** (engine runs+resumes variants but they stay OUT of `ACTIVE_STRATEGY_STATUSES` → `_is_active`/cadence/morning-brief skip them; strategies-list + cadence add `parent_strategy_id IS NULL`). `PaperVariantService`: spawn (clone→register→ACCEPTED→EVALUATING), terminate (unregister→EVALUATING→REJECTED), 90-day expiry sweep; **one-row-per-txn audits**. Engine: register() sets PAPER_VARIANT for clones; **unregister() reset widened to ENGINE_RUNNABLE_STATUSES** (else a terminated variant re-runs on boot) — status bookkeeping only, NO order-path change. Endpoints `POST /proposals/{id}/validate` + `/stop-validation`. 2 new audit actions **PAPER_VARIANT_SPAWNED/_TERMINATED (6→8)**. Reconciles ADR 0007 onto the shipped Decision-3 lifecycle (ADR 0007's EVALUATING…PROMOTED states were superseded; this LAYERS paper-validation on). **DEVIATIONS (IDLE-guard reality):** PUT/apply both require IDLE → a LIVE parent's params can't change mid-eval, so the **auto-spawn-on-ACCEPT envelope flag + the apply/deactivation invalidation hook DEFER to §2b** (90-day expiry covers orphans); §2a = manual spawn + stop + concurrency(1/parent→409) + expiry. 21 backend tests; full suite under --cov 0 failed; mypy(160) + ruff + migration round-trip + all 8 shell invariants + audit-immutability + 3 coverage gates green; all 10 PR CI green first try; merged on Jay's "merge it" (informed ≥1h walk-away override). No metrics/UI (§2b); no evidence/gate/promotion (§3); no order-path code. Session doc + Results: `TradingWorkbench_P6b_Session2a_variant_v0_1.md` / `..._Session2a_variant_Results_v0.1.md`. · **Next: P6b §2b-variant** — variant-vs-live **comparison metrics** (incl. the **live equity-curve Sharpe/max-dd reconstruction §1a deferred** — the §3 4-criterion gate needs it) + `workbench_paper_variant_metrics` MCP tool (18→19) + variant UI + the deferred auto-spawn/invalidation hooks; draft `..._P6b_Session2b_variant_v0.1.md` against the §2a Results (NOT speculatively, Rec #10). Then **§3** (EVIDENCE_READY/PROMOTING/PROMOTED + 4-criterion gate + evidence bundle + promotion-with-P5§7-cooldown + STRATEGY_PROMOTED + 30-day post-promotion lockout). Still pending (live, non-Norton stack): **§1b.12 → `p6-session1-complete`** + §2b live re-confirmation. · prior tags `p6b-session1b-drift-complete` (`377617a`), `p6b-session1a-drift-complete` (`fe2d3ab`), `p6-session2b-complete`, `p5.5-complete` (`878b9f8`)

**P6b §1b-drift (PR #57, `377617a`, tag `p6b-session1b-drift-complete`):** drift read surfaces — CLOSED P6b §1. Audit-log-backed (no migration). `POST /strategies/{id}/drift-check` + `GET /strategies/{id}/drift-status` (on `proposals.py::strategies_router`) + user-level `GET /drift-findings` (new `app/api/v1/drift.py`); `workbench_drift_findings` MCP tool (17→18). Frontend `DriftCard` (plain useState/useEffect — strategy-detail page has NO QueryClientProvider, cf. CooldownIndicator) + drift section on Dashboard `MorningBriefCard` (react-query). Hybrid read shape (per Jay) + 3 corrections vs an alternate draft (`str(target_id)`, `datetime.now(UTC)`, real MCP `_get`/`_TOOLS`). 16 backend + 5 frontend + 1 MCP tests; all green. · prior tags `p6b-session1a-drift-complete` (`fe2d3ab`), `p6-session2b-complete`, `p5.5-complete` (`878b9f8`)

**P6b §1a-drift (PR #56, `fe2d3ab`):** strategy drift detection + shared metrics — the detection foundation. Advisory-only; runs on the morning-brief cadence (Mon-Fri 09:00 ET), compares a live strategy's recent behavior to its backtest baseline, writes `STRATEGY_DRIFT_DETECTED` audit (6th P6-era action) — takes no action. New `app/strategies/metrics.py` extracts the formula FUNCTIONS so the backtester + drift detector share bit-identical math (`BacktestMetrics` stays in `backtest_models.py` — "extract functions, keep the dataclass"). `drift_detection.py`: fill-level FIFO round-trip reconstruction (`Fill→Order→Symbol`; Order has no fill aggregates), params-matched baseline from `BacktestResult.trades_json`, sizing-invariant compare on win_rate + avg_return_per_trade. Thresholds in `agent_envelope_json.drift_thresholds`. **Audit-only, NO migration** (`morning_briefs` has no `report_json` column); one-row-per-txn commits; `_canonical_params` is a recursive leaf-stringify (`json.dumps(default=str)` doesn't normalize int-vs-str). 32 tests; all green; merged on Jay's "merge it". · prior tags `p6-session2b-complete`, `p6-session2b-review-complete` (`2ee3c93`), `p6-session2b-backtest-complete` (`267b666`), `p5.5-complete` (`878b9f8`)

**P6 §2b-review (PR #55, `2ee3c93`, tags `p6-session2b-review-complete` + `p6-session2b-complete`):** 10% human-review sampling + review UI, closing Decision 8 + **P6 §2**. Singleton weekly cron (Mon 09:00 ET, lifespan 10h) samples 10% of each user's past-7-days terminal-state proposals — two non-negotiables (de-dup vs already-sampled; merge-not-overwrite of `evaluation_results_json`). `POST /proposals/{id}/review` (sampled+not-yet-rated → merge-write `human_review` + `PROPOSAL_REVIEW_RECORDED` audit, 5th action); `GET /proposals?awaiting_review=true`; additive eval-summary counts; `ReviewQueue` page + badges. No migration/MCP/ADRs; no order-path. Key drift: lifespan `app.state.scheduler` unset at registration → in-scope locals; react-query v5; `EvalPanel` prop `ev`. `p6-session2b-complete` tagged on the in-suite stand-in. · **P6b** is the next phase (four Direction-v0.2 deferred capabilities — drift [§1, shipped], auto-validation paper runner + evidence-bundle flow [§2-§3, ADR 0007], Mode-B + LLM-driven live [§4-§5, ADR 0006 v2]; committed split early §1-§3 / late §4-§5; charter = Part D of `..._P6_Closure_Observation_Plan_v0_1.md`). · prior tags `p6-session2b-backtest-complete` (`267b666`), `p6-cleanup-1-complete` (`6fb0f9f`), `p5.5-complete` (`878b9f8`)

**P6 §2b-backtest (PR #54, `267b666`):** backtest eval pipeline. On DRAFT→REVIEWING the PATCH endpoint enqueues two `BacktestJob` rows (baseline current params + variant merged with the proposal's `changes`, 90-day window) via a service-layer direct insert (sidesteps the HTTP single-flight 409); a 60s reconcile cron (`proposal_evaluation_reconcile`, inside the alpaca block) detects completion via `BacktestJob.result_id` and writes Decision 8's verdict (`sharpe ≥ baseline AND drawdown ≥ max(baseline−0.05, −0.20)`) into `evaluation_results_json`. Non-PYTHON/zero-symbol strategies skip with a reason; eval is judgment fuel, not a gate. `GET /strategies/{id}/proposal-eval-summary` + `workbench_proposal_eval_summary` MCP tool (16→17) + frontend eval badge/`EvalPanel`. No new migration/audit/ADRs (ADR-0014 already Accepted); no order-path code. All 10 PR CI checks green first try. **Deferred** (Norton + no Docker): real Anthropic proposal + live worker run. · prior tags `p6-cleanup-1-complete` (`6fb0f9f`), `p6-session2a-complete` (`d0f709e`), `p5.5-complete` (`878b9f8`)

**P6 cleanup-1 (PR #53, `6fb0f9f`):** renamed backend `app/agent/` → `app/llm/` (5 LLM modules + `tests/agent/`→`tests/llm/` + all `app.agent` imports; the **two load-bearing invariants** updated to match — `check_no_llm_in_order_path.sh` allowlist `agent`→`llm`, `check_p3_coverage.py` suffixes `agent/*`→`llm/*`; P3 chat router `app/api/v1/agent.py` NOT renamed) and removed the dead `_resolve_from_mcp_token` bearer shim. No behavior change; no new migration/audit/ADRs; no order-path code. All 10 PR CI checks green (one transient Docker-Hub-timeout rerun). **Next: P6 §2b** (backtest eval + human-review sampling — Decision 8 / ADR-0014; draft `..._P6_Session2b_v0.1.md` against §2a Results + this cleanup). Still pending: **§1b.12 cross-session live verification → `p6-session1-complete` tag** on a non-Norton stack. · prior tags `p6-session2a-complete` (`d0f709e`), `p6-session1b-complete` (`16855f9`), `p5.5-complete` (`878b9f8`)

**P6 §2a (PR #52, `d0f709e`):** opt-in **scheduled proposal cadence**. `agent_envelope_json.proposal_cadence` (off|weekday_market_open|daily|weekly|monthly_first; default off) drives an APScheduler cron per user (registered at startup + reconciled on profile update) that iterates the user's strategies, budget-pre-checks, and invokes the existing `POST /strategies/{id}/propose` with `trigger="cadence"` using the user's `AGENT_API_KEY`. New `AGENT_CADENCE_FIRED` audit action (one row per strategy per fire). `ProposeRequest.trigger` attributes cadence fires to actor_type=AGENT. Frontend cadence dropdown + no-key warning. No new migration/MCP tools/ADRs; no order-path code. All 10 PR CI checks green (after a ruff-F401 fix on a test file). **Deferred** (Norton + no Docker): live cron fire, real Anthropic call, `docker compose` run. · **next: cleanup PR** (`app/agent/`→`app/llm/` + bearer-resolver dedup) → tag `p6-cleanup-1-complete`, **then P6 §2b** (backtest eval + human-review sampling). Also still pending: **§1b.12 cross-session live verification → `p6-session1-complete` tag** on a non-Norton stack. · prior tags `p6-session1b-complete` (`16855f9`), `p5.5-complete` (`878b9f8`)

---

## ✅ P0 — Scaffolding (complete)

Tag `p0-complete` → `6e66ad9`. (Original 10-group breakdown lives in the v0.1 of this file in git history.)

---

## ✅ P1 — Manual Trading MVP (complete)

Tag `p1-session4-complete` → `48ea67d`. Sessions 1–4 all merged. Trader can place/modify/cancel paper orders against Alpaca from the UI; OrderRouter is the single dispatch path (ADR 0002); risk engine + trade-update consumer + position recompute all live; full REST surface; WS topic publishing; live-mode gates.

| Session | Scope | PR |
|---|---|---|
| **S1** | Alpaca read-only adapter + creds | #1 |
| **S2** | Account/position polling + scheduler + lifespan | #2 |
| **S3** | Trade-updates WS lifecycle | #3 |
| **S4** | Trading DB schema | #4, #5 |
| **S5** | RiskEngine + OrderRouter + trade-update consumer + drift detector | #6 |
| **S5/6** | Full REST + WS topic publishing | #7 |
| **S6 frontend** | Order ticket, orders + positions pages, typed API client | #8 |
| **S6 frontend** | Charts page, real dashboard, live-mode UX gates | #9 |
| **S6 tests** | Coverage gates, REST + e2e tests, runbooks, exit gate | #10 |

---

## 🚧 P2 — Strategy MVP (in progress)

Goal per Design Doc §13: *"One reference systematic strategy runs end-to-end on paper, with backtest harness + deploy."*

Master plan: [`docs/implementation/TradingWorkbench_P2_Checklist_v0.1.md`](../docs/implementation/TradingWorkbench_P2_Checklist_v0.1.md). Session docs alongside it.

| Session | Scope | Status |
|---|---|---|
| **S1** | Bar cache + IndicatorComputer | ✅ #11 |
| **S2** | Strategies framework skeleton (schema, base/context/engine/loader, fixtures) | ✅ #12 |
| **S3** | Reference RSI strategy + backtest harness | ✅ #13 tag `p2-session3-complete` |
| **S4** | Strategies + signals REST surface + WS topic routing | ✅ #16 tag `p2-session4-complete` |
| **S5** | Frontend Strategies pages (CRUD, signals view, backtest modal) | ✅ #18 tag `p2-session5-complete` |
| **S6** | Tests + smoke matrix + runbooks + P2 exit gate | 🚧 PR open: coverage gates + backfill tests + runbooks + README done; smoke matrix + branch-protection promotion + `p2-complete` tag are manual steps after merge |

### P2 known blockers
- AAPL fixture parquets for `tests/strategies/test_backtest_reproducibility.py` and the live smoke step — Norton SSL inspection on Jay's dev machine blocks `data.alpaca.markets`. Generating from any other env (WSL, CI, a non-Norton machine) populates the three parquets and flips two skipped tests to required.
- Live smoke step in P2 S3 / P2 S4 docs is still pending behind that same SSL blocker.

---

## ⏳ P4 — Polish & extend (partially started, out of stated order)

We ran ahead of the doc order on P4 items because they unblock UI work later. Items are independently mergeable.

| Item | Scope | Status |
|---|---|---|
| **§1** | TradingView Pine webhook receiver | ✅ #14 tag `p4-tv-webhooks-complete` |
| **§2 Part A** | Async backtest job queue (backend) | ✅ #17 tag `p4-async-backtest-backend-complete` |
| **§2 Part B** | Async backtest progress UI (frontend) | ✅ #20 tag `p4-async-backtest-complete` |
| **§5** | Backend `source_type` / `source_id` filter on orders + frontend scoped queries | ✅ #22 tag `p4-order-source-filter-complete` |
| **§7** | Typed Params tab form derived from `Strategy.params_schema` | ✅ #23 tag `p4-param-form-complete` |
| **§6** | Backtest charting: drawdown sub-chart + trade markers + Equity/Returns toggle + stats panel | ✅ #24 tag `p4-backtest-charting-complete` |
| **§4** | Strategy hot-reload: file watcher + reload endpoint + UI banner | ✅ #25 tag `p4-strategy-hot-reload-complete` |
| **§3** | Opportunities page: six cross-cutting widgets + aggregator endpoint | ✅ #26 tag `p4-opportunities-page-complete` |
| **§8** | WS bar dispatch: BarStreamService + diff-based subscriptions + cron fallback | ✅ #27 tag `p4-ws-bar-dispatch-complete` |

### P4 §2 ship sequence — DONE 2026-05-26
1. P2 S5 landed the Strategies UI scaffolding (PR #18).
2. P4 §2 Part B layered the WS-driven progress bar + cancel button on top (PR #20).
3. Tag `p4-async-backtest-complete` pushed; both halves shipped.

> Side fix in PR #20: the P2 S5 frontend `BacktestJobStatus` type alias claimed `"done"` but the backend enum serializes `"completed"`. The old modal's success-path check never matched a real backtest — users saw "Running…" forever until dismissing. Type + check both corrected.

---

## 🧱 Cross-cutting work that landed alongside

- **`app/audit/` module** (#15 — `feat(audit): typed AuditLogger`) — introduced `AuditLogger` + `AuditAction` + `AuditActorType` enums. P2 S4 needed them and they weren't built earlier despite the P1.C checkbox above implying they were. Refactored `OrderRouter`, `StrategyEngine`, `TradeUpdateConsumer` to use the typed helper. Cleanup, not new feature.
- **Alembic template fix** (in #14 and re-tweaked in #17) — `script.py.mako` now produces ruff-clean imports on autogenerate; future `alembic revision --autogenerate` calls don't need a manual fixup pass.

---

## ✅ P3 — Agent MVP (B1+B2) — code complete

Six sessions merged; `p3-complete` tag held pending Jay's manual smoke walkthrough (same pattern as P2's open close-out — `p3-session6-complete` ships now; `p3-complete` lands after the smoke log at `docs/runbook/p3-smoke-log.md` records a clean run).

Session docs live under uppercase `Docs/implementation/` (still untracked; six P3 + nine P5 + the P4 checklist are pending an inventory commit).

| Session | Scope | Status |
|---|---|---|
| **S1** | Agent schema (3 tables, 3 enums) + Alembic + pricing helper + DailyBudgetResolver + settings | ✅ #28 tag `p3-session1-complete` |
| **S2** | MCP server read-only tool expansion: 12 new tools + tripwire + runbook (`docs/runbook/mcp-tools.md`) | ✅ #29 tag `p3-session2-complete` |
| **S3** | Agent runtime: Anthropic client + system prompt + session lifecycle + tool-use loop + bilateral cost cap. Constrained by [ADR 0006](../docs/adr/0006-llm-not-in-order-path.md); B3_AUTONOMOUS paused indefinitely. | ✅ #31 tag `p3-session3-complete` |
| **S4** | REST + WS surface: 6 endpoints under `/api/v1/agent` + `agent` WS topic (5 bus events + 128-event replay) | ✅ #32 tag `p3-session4-complete` |
| **S5** | Frontend chat panel at `/agent`: SessionList + ChatPanel + MessageList (role-based + tool cards + suggestion extraction) + CostMeter + WS-driven re-fetches | ✅ #33 tag `p3-session5-complete` |
| **S6** | Tests (E2E + P3 coverage gate) + runbooks (`docs/runbook/agent.md`, `docs/runbook/p3-smoke-log.md`) + README Agent subsection + exit gate prep | ✅ this PR tag `p3-session6-complete` |

### P3 manual steps remaining before `p3-complete` tag
1. Walk `docs/runbook/p3-smoke-log.md` against the live `/agent` page with `ANTHROPIC_API_KEY` configured; commit the filled log.
2. Tag `p3-complete` after the smoke log lands clean.

Step 5 of the smoke (force cost cap) makes a temporary `.env` edit — restore `AGENT_DAILY_BUDGET_USD=2.0` before signing off or the next session opens directly in CAPPED.

### P3 architectural commitment
[ADR 0006 — LLM not in the order path](../docs/adr/0006-llm-not-in-order-path.md) (merged via #30) constrains every future agent-related PR. The CI invariant `apps/backend/scripts/check_no_llm_in_order_path.sh` enforces it: Anthropic SDK use is allowed in `app/agent/`, `app/services/morning_brief.py` (P5.5 §2, future), `app/services/strategy_review.py` (P6, future), `app/services/drift_detection.py` (P6, future) — never in `app/orders/router.py`, `app/risk/`, `app/brokers/`, or strategy execution. **B3 (autonomous order submission) is paused indefinitely** — the `AgentSessionMode.B3_AUTONOMOUS` enum value stays reserved but the runtime rejects sessions started in that mode.

### P3 settled decisions
- **Modes:** B1 (read-only) + B2 (interactive) ship in P3; B3 (autonomous order submission) is paused indefinitely per ADR 0006 (not just deferred — paused).
- **Cost cap:** $2/day per user across all sessions; configurable via `AGENT_DAILY_BUDGET_USD`.
- **Default model:** Haiku 4.5 (`claude-haiku-4-5-20251001`).
- **Anthropic key handling:** env var `ANTHROPIC_API_KEY` only for MVP; per-user encrypted in `system_config` is a P5+ enhancement. Empty key disables agent with a clear runtime error (Session 3).
- **Chat panel placement:** top-level page at `/agent` (settled in Session 5).

### P3 deferred to later phases
- **B3 autonomous trading** — paused indefinitely per ADR 0006.
- **Per-user encrypted API keys** — P5 alongside multi-user auth.
- **Streaming text deltas** — `stream_message` exists but unused; P4+ polish.
- **Multi-session concurrency** — one ACTIVE session per user; multi-session UX is P4+ if it ever becomes a real ask.
- **Tool result expand-to-modal** — replaces the 4000-char truncation; P4+ polish.

## 🚧 P5 — Live trading (in progress)

Master plan: per-session docs under uppercase `Docs/implementation/` (`TradingWorkbench_P5_Session*_v0.1.md`). Session Zero complete (conditional GO, commit `82c1d2c`).

| Session | Scope | Status |
|---|---|---|
| **S0** | Session Zero: static/pytest/live-schema baseline | ✅ `82c1d2c` |
| **S1** | Foundations — LIVE/PAPER distinction: `accounts.broker_mode_locked_at`, `risk_limits.broker_mode` (engine resolves limits scoped by mode), OrderRouter refuses LIVE with `BrokerModeError` before the risk engine, `POST/GET /api/v1/accounts` (live create → 400), red LIVE banner for any live account, Order Ticket disabled-submit for live, `docs/runbook/live-mode.md` | ✅ #37 tag `p5-session1-complete` |

| **S2** | Per-account broker registry — `BrokerAdapter` Protocol (`app/brokers/base.py`, satisfied by existing `AlpacaAdapter` unchanged), `BrokerRegistry` (one adapter per account by `AccountMode`; network-free construct; reuses connected startup paper adapter), OrderRouter resolves per-account after the §1 LIVE guard (fallback keeps paper byte-identical), `credentials_for_mode()` helper, new `check_broker_isolation.sh` CI invariant (trading SDK only; `alpaca.data.*` exempt). Session doc frozen v1.0. | ✅ #38 tag `p5-session2-complete` |

| **S3** | Multi-user auth — replaces the P0 stub: `users.password_hash`(bcrypt 12)/`totp_secret`/`totp_verified_at` + new `sessions` table (SHA-256 token hash, rolling 14-day TTL, revocation); `app/auth/{passwords,tokens,totp}.py`; `stub.py` body replaced (name/exports kept); 6 `/api/v1/auth/*` endpoints + IP rate-limit (5/15min→60min cooldown); WS `/ws` requires cookie → close 4401; `scripts/create_user.py` CLI bootstrap (no web self-signup); frontend `/login`+`RequireAuth`+logout+Vite proxy; `docs/runbook/authentication.md`. | ✅ #39 tag `p5-session3-complete` |

| **S4** | Credential encryption — Fernet store for all per-user secrets at rest. `WORKBENCH_MASTER_KEY` (env) + `app/security/{crypto,credential_store}.py`; new `user_credentials(user_id,kind,ciphertext,…)` table + data migration (`totp_secret`/`pine_webhook_secret` columns dropped, env broker/Anthropic keys captured for user 1); `credentials_for_mode()` → async + store-backed (registry propagates `await`); agent/webhook/auth/`create_user.py` swapped to the store; `/api/v1/users/me/credentials/` (GET/PUT/DELETE, TOTP excluded) + Settings→Credentials page; eighth CI invariant `check_no_env_credentials.sh`; `docs/runbook/credentials.md`; `app/auth/future.py` deleted (S3 close-out). Session doc frozen v1.0. | ✅ #40 tag `p5-session4-complete` |

| **S5** | Live-mode risk gates — account-scoped circuit breaker (hard halt, ADR 0004), per-day order cap, PDT warning, pre-trade buying power (LIVE-only, dormant until §7). New `accounts.circuit_breaker_tripped_at` + `risk_limits.max_orders_per_day`; migration seeds a LIVE GLOBAL risk_limits row + backfills PAPER cap=200. `app/risk/{circuit_breaker,pdt_analyzer,buying_power}.py` + RiskEngine integration; `/api/v1/risk-limits` (list/update) + `/accounts/{id}/risk-state` + `/risk/reset-circuit-breaker` (typed-label); 3 audit actions; `system.circuit_breaker` WS; RiskStateBanner + Settings→RiskLimits UI; shared `app/utils/time.ensure_aware`; ADR 0004 + `docs/runbook/risk-gates.md`. Session doc frozen v0.2. | ✅ #43 tag `p5-session5-complete` |

| **S6** | Live order safety — two friction layers wired in the OrderRouter (ADR-0002 choke point), dormant until §7. Typed-ticker confirmation for MANUAL+LIVE (server-enforced, case-insensitive/whitespace-stripped; CONFIRMATION_REQUIRED/MISMATCH); 60s per-strategy cooldown after failed STRATEGY submissions (each failure resets; self-clears; STRATEGY_COOLDOWN). New `strategies.cooldown_until`; `StrategyCooldownService`; `confirmation_text` on OrderRequest/OrderCreateRequest; LIVE_ORDER_SUBMITTED audit on every reachable live attempt; GET/POST `/strategies/{id}/cooldown[/clear]`; 2 audit actions; LiveOrderConfirmModal (ready, not wired — ticket disables live) + CooldownIndicator on strategy detail; `docs/runbook/live-order-safety.md`. Session doc frozen v0.2. | ✅ #44 tag `p5-session6-complete` |

| **S7** | **Activation Wizard & Live Path Open** — lifts §1's blanket `BrokerModeError`. New `StrategyStatus.PENDING_LIVE` (excluded from `ACTIVE_STRATEGY_STATUSES`) + `strategies.live_activation_initiated_at` (migration `e1f6b4c9a8d3`). `ActivationService`: 6 prerequisites (live account, live creds, TOTP enrolled, recent `BacktestResult` ≤7d, LIVE risk_limits, breaker clear), `initiate` (typed name + TOTP + prereqs → PENDING_LIVE), frictionless `cancel`, idempotent `complete_pending` (24h, ADR 0005), `deactivate` (optional liquidation via MANUAL closing orders). OrderRouter guard lifted → `_live_guard_reject_reason`: MANUAL ok; STRATEGY ok iff status LIVE; AGENT→AGENT_LIVE_DISABLED; returns typed REJECTED (no raise); LIVE_ORDER_SUBMITTED on every reachable path. LIVE account creation TOTP-gated; POST /orders extended (optional account_id/source/strategy_id). 4 activation endpoints; APScheduler `activation_completion` job (60s, idempotent); 5 audit actions + 5 reason codes; ActivationWizard/Countdown/DeactivationModal + Settings→Accounts; ADR 0005 + `docs/runbook/activation.md`. Session doc v0.2. | ✅ #45 tag `p5-session7-complete` |

### P5 §7 deviations from the v0.2 doc (verified against live code)
- **No `backtests` table** → "recent backtest" prereq checks for a `BacktestResult` row ≤7d (engagement, not quality). **Strategies have no `account_id`** → live account resolved by `user_id`+mode (`_resolve_strategy_account`).
- **`OrderStatus` has no `ACCEPTED`; no `OrderSubmissionResult`/`BrokerPosition`** → router returns `Order`; guard returns ephemeral REJECTED via `_ephemeral_rejected_order_with_reason`.
- **Lifted guard REJECTS, not raises** → §1/§2/§6 BrokerModeError tests repurposed: AGENT+LIVE→REJECTED/AGENT_LIVE_DISABLED; STRATEGY+PAPER-status→STRATEGY_NOT_LIVE.
- **Liquidation uses MANUAL + auto `confirmation_text=symbol`** (not STRATEGY) → works for LIVE+HALTED, bypasses the §7 status guard + §6 cooldown, still full-risk-gated + audited.
- **Live-path tests router-level** (`app.state.order_router` is None under the `client` fixture); one API test covers LIVE-account-TOTP. **TOTP re-verified on initiate** (14-day cookie ≫ 30s code; session-hijack defense). Audit UPPER; reason codes typed.
- Suite **548 passed / 9 skipped**; risk 0.904/p2/p3/mypy/ruff/5-shell-invariants/ADR-0002/audit-immutability green; frontend tsc/eslint/77 vitest green. **Live runtime smoke deferred** (Norton + no-Docker; and §8 hardening lands before any real activation).

| **S8** | **Production Hardening — closes P5.** Immutable hash-chained audit log: `audit_log.row_hash`/`prev_hash` (migration `f2a7c1d9e4b6`, per-user SHA-256 chain via a `before_insert` mapper event; `id` excluded), `audit_log_no_update`/`no_delete` triggers via `after_create` DDL (so create_all in tests + migration in prod both install them), `verify_audit_integrity.py`, `check_audit_immutability.sh` (6th shell invariant). Subsystem `/healthz` (database/master_key/broker_registry/scheduler/circuit_breakers_clear; fail→503, degraded/ok→200; legacy `db` key kept; off-when-alpaca-disabled→`disabled`). Prometheus `/metrics`: 12 metrics + 30s `metrics_snapshot` job; order counter+histogram via a `submit`→`_submit_inner` wrapper (logic byte-identical), auth-failure + broker-error counters. structlog `redact_processor` (5 credential families). `scripts/backup_db.sh` (.backup, 30d retention) + `restore_db.sh` + daily 02:00 job. `docs/runbook/{deployment,on-call}.md`. 20 new tests. Session doc v0.2. | ✅ #46 tags `p5-session8-complete` + `p5-complete` |

### P5 §8 deviations from the v0.2 doc (verified against live code)
- **`AuditLogger.write` is async-ORM, not sync raw-SQL**; columns are `ts`/`payload_json` (NOT `created_at`/`payload`), `target_id` stringified, plus an `ip` column. Hash module/integration rebuilt to this shape.
- **Hash chain via `before_insert` mapper event** (keeps `write()` a plain `session.add`, zero call-site churn; sets row_hash pre-INSERT so the trigger never fires). **`id` excluded from the hash** (post-INSERT autoincrement; `prev_hash` already detects reorder/delete) → no `MAX(id)+1` dance. **Chain links in COMMIT order** (every call site commits one row; batched same-flush writes would be unchained — no code path does that).
- **Triggers via `after_create` DDL** (tests use `create_all`, NOT migrations) with `IF NOT EXISTS`; doc's §8.1.5 wipe-fixture unnecessary (fresh in-memory DB per test). **No pre-existing audit-immutability pytest** (doc was wrong; `-k immutab` matched the ADR-0002 test) → §8.1 tests net-new.
- **`/healthz` already existed** (basic inline); replaced by router, preserving legacy `db` key + treating alpaca-disabled subsystems as `disabled`; existing db-down test updated `degraded`→`fail`. **Order metrics via wrapper** (ADR-0002 path untouched). **`prometheus_client` was absent** → added to pyproject. **Dev DB is `delete` journal mode** (not WAL; immaterial — SQLite is single-writer).
- Suite **568 passed / 9 skipped**; risk 0.904/p2/p3/mypy(142)/ruff/**6**-shell-invariants/ADR-0002 green; migration backfill+round-trip+integrity verified on isolated DB; backup script smoke-tested. **`p5-complete` tagged on the in-suite stand-in** (Jay's call); **§8.9/§8.10 live Docker smoke deferred** (Norton + no-Docker). No frontend changes (last green at §7). **P5 CLOSED.**

### P5 §6 deviations from the v0.2 doc (verified against live code)
- **POST /orders hardcodes the paper account** (no account_id, extra=forbid) → manual LIVE orders UNREACHABLE via the API until §7; §6 logic lives in the OrderRouter and is **tested at the router level** (the doc's HTTP §6.8 tests are impossible).
- Real router: `submit(req: OrderRequest)->Order`, rejections carry `rejection_reason` (not `reason_code`), risk is `evaluate()`; no `_reject`/`_record_*` helpers. Added `_confirmation_reject_reason`/`_strategy_id_from_source`/`_ephemeral_rejected_order_with_reason`/`_maybe_set_cooldown`/`_audit_live_submission`.
- **Confirmation runs BEFORE the §1 BrokerModeError** (which RAISES→400); the two existing §1 live-refusal tests updated to pass matching `confirmation_text`.
- `strategy_id` derived from `source_id` (str(strategy_id)); audit values UPPER (`LIVE_ORDER_SUBMITTED`/`STRATEGY_COOLDOWN_CLEARED`); §6 reason codes typed in `ReasonCode`.
- `LiveOrderConfirmModal` ships ready but NOT wired (ticket disables live submit — §7 wires); `CooldownIndicator` uses plain useEffect (detail page has no QueryClientProvider).
- Paper byte-identical preserved (existing order/risk suite green). §6.9 live smoke deferred. Suite 512 passed; mypy/ruff/8-invariants/ADR-0002 green; frontend 77 vitest green.

### P5 §5 deviations from the v0.2 doc (verified against live code; confirmed with Jay)
- **strategies has no `account_id`** (deferred to §7) → breaker HALTs strategies via `user_id`+status↔mode (PAPER-status→paper acct, LIVE→live).
- **`Fill` has no `signed_direction`** → realized PnL joins `Fill→Order`, signs by `Order.side`; **unrealized PnL** summed from local `positions.unrealized_pl` (no broker call — engine stays DB-bound).
- **`SQLEnum` persists the enum NAME** (`'GLOBAL'`/`'PAPER'`/`'BUY'`) → migration raw-SQL seed uses `scope_type='GLOBAL'` (lowercase would orphan the LIVE row); all ORM compares use enum members, never `.value`.
- **`AuditLogger` is in `app.audit`, `.write()` is sync** (not `app.db.enums`, not awaited).
- **`StrategyStatus.HALTED` already existed**; **existing global daily-loss halt** (`app/risk/halt.py` step 9) is **kept** — the account breaker composes with it (per risk-engine skill; ADR 0004 notes consolidation as future work).
- Endpoints wired via `app/api/v1/__init__.py` (no double prefix); buying-power gate dormant in §5 (router `BrokerModeError` short-circuits LIVE before the engine; `bar_cache` wired in §7).
- §5.11 live trip/reset + paper-baseline smoke deferred to WSL/CI. Suite green; new risk modules ≥0.96 branch.

### P5 §4 deviations from the v1.0 doc (verified against live code)
- **`CredentialKind` is a `StrEnum`** (matches `AccountMode`, satisfies ruff `UP042`); `.value` used at every DB/call site.
- **Migration acquires the master key before any DDL** — a missing key aborts with zero schema changes (eliminates the half-migrated-DB risk of Gotcha #2). Verified on a copy of the dev DB: upgrade/downgrade/upgrade round-trip + encrypt-on-move + plaintext-restore.
- **`users.py` (Pine secret rotate/get) also swapped** to the store — the v1.0 §4.8 named only `alerts.py`, but the write side lives in `users.py`.
- **Credentials router wired via `app/api/v1/__init__.py`** (codebase pattern), not `main.py`; **frontend uses `apiFetch` + React Query** behind the existing `main.tsx` `RequireAuth`.
- **`load_credentials()`/`config.py` left as-is** — only `credentials_for_mode` was the §4 swap-point; the CI invariant forbids only `os.environ.get(<credential-name>)` (none exist).
- §4.14 live-runtime smoke deferred to WSL/CI (Norton + no Docker); in-suite tests are the stand-in. Full suite **419 passed / 9 skipped**; eight invariants + ADR 0002 test green.

### P5 §3 deviations from the v0.1 doc (verified against live code)
- **Test auth**: one autouse `get_current_user` dependency-override in `tests/conftest.py` + a `real_auth` opt-out marker authenticates the whole pre-auth suite as user 1 — **zero per-file edits** (every test client builder imports `create_app` lazily, so patching the factory reaches them all), instead of the doc's "edit ~30 fixtures."
- **CLI**: Docker-free `scripts/create_user.py` (getpass, cross-platform) instead of the doc's `docker compose exec` bash script — the dev box runs without Docker.
- **Cookie transport**: Vite proxy (`/api`,`/ws` → backend) makes the cookie same-origin; `RequireAuth` placed in `main.tsx` so `App`/`App.test` stay unchanged; `apiFetch` defaults to a relative base + `credentials:"include"`; WS bases derive from the page origin.
- Added `email-validator` dep (required by `EmailStr`); test emails use `example.com` (`.local` is rejected by email-validator). `_aware()` UTC coercion in `stub.py` fixes SQLite naive-datetime comparisons. `.gitignore totp_*.png` (QR embeds the secret).
- **Auth-event audit-logging deferred to P5 §8** (structured logs only here, mirrors §1's refusal-audit deferral). TOTP secret stays plaintext until **P5 §4** wraps it in Fernet. §3.10 manual smoke + live paper-order-post-auth unrun (no Docker / Norton).

### P5 §2 deviations from the v0.1 doc (verified against live code; full rationale in the v1.0 session doc §2.0)
- v0.1 wanted a *literal extraction* + async/DTO `BrokerAdapter` rewrite. The Alpaca order logic was **already** extracted (`app/brokers/alpaca/adapter.py`, sync, dict-returning, tested), so v1.0 keeps it untouched and defines the Protocol to match the real surface — the only new capability is **per-account selection** (registry), which is wiring, not an interface rewrite.
- No `app/brokers/{base,alpaca_paper,alpaca_live}.py` split and no `BrokerMode` enum — reused `AccountMode`; the single `AlpacaAdapter` serves paper or live via `paper=` credentials.
- ADR 0002 enforced by `tests/test_adr_0002_invariant.py` + `_router_token` (no `check_adr0002.sh`); all adapter calls stay in `router.py`, so the invariant test needed no edit.
- §2.9 live paper-smoke byte-identical diff deferred to WSL/CI (Norton blocks `data.alpaca.markets`); in-suite routing test is the stand-in.

### P5 §1 deviations from the v0.1 doc (verified against the live codebase)
- `AccountMode{paper,live}` already existed and already typed `accounts.mode`; reused it. No `BrokerMode` enum, no string→enum migration (both already done).
- OrderRouter lives at `app/orders/router.py`; there is no `app/risk/resolver.py` — GLOBAL limits resolve inline in `RiskEngine._load_global_limits`, where the `broker_mode` filter was added.
- Strategy-detail red border / list badge / `StrategyResponse.account_broker_mode` deferred to P5 §7: `strategies` has no `account_id` and no strategy can be LIVE yet.
- Refusal audit-logging deferred to P5 §8 (audit_log is a §8 concern); the refusal is structured-logged via `order_router_refused_live`.

## ✅ P5.5 — Trader preferences / Morning brief / Workbench MCP (complete)

Tag **`p5.5-complete`** → `878b9f8` (in-suite stand-in; live §3.13 cross-session smoke deferred — Norton/Docker). All three sessions merged: §1 #47, §2 #48, §3 #49.

Master plan: `Docs/implementation/TradingWorkbench_P5.5_ImplementationPlan_v0.1.md`. Per-session docs drift against the prior session's Results doc (Retrospective Rec #10): §1 = `TradingWorkbench_P5_5_Session1_v0_2.md`; §2 drift = `TradingWorkbench_P5_5_Session2_v0_2.md`.

| Session | Scope | Status |
|---|---|---|
| **S1** | **Trading profile foundation.** `trading_profiles` table (1/user, 5 JSON sections: watchlist, bias_criteria, bias_thresholds, session_preferences, risk_preferences) + migration `9d2e7b3a1f5c` (backfills an empty profile per user). `TradingProfileService` (async get/update, single-commit audited old/new diff, race-safe `get()` via IntegrityError→re-select). `GET/PUT /api/v1/users/me/trading-profile` mounted via `app/api/v1/__init__.py`. `AuditAction.TRADING_PROFILE_UPDATED`. Settings→Trading Profile page (5-section form + JSON power-user mode). No reader yet — §2 (morning brief) is first. Session doc v0.2. | ✅ #47 tag `p5.5-session1-complete` |
| **S2** | **Morning brief.** `morning_briefs` table (1/user/day, UPSERT) + migration `b3f8c2d1e9a7` (down-rev `9d2e7b3a1f5c`). `MorningBriefService` (bias labeling off the EXISTING `BarCache.get_bars`+`IndicatorComputer.compute` path; single-commit audited save). Optional Haiku 4.5 narration reusing `app/agent/{anthropic_client,pricing}`, key-gated + failure-degrading, **cost (model/tokens/cents) in the `MORNING_BRIEF_GENERATED` audit payload**. Scheduled `run_morning_brief_generation` in `lifespan.py` (mon-fri 09:00 ET, idempotent per (user,date), verified-users-only). 4 endpoints `/api/v1/morning-brief/*`. `today_eastern()` (ZoneInfo) added to `app/utils/time.py`. **EMA20/EMA50 added to `IndicatorComputer`** (so bias_thresholds `20>50` maps to real EMAs). Dashboard `MorningBriefCard`. Session doc v0.2. | ✅ #48 tag `p5.5-session2-complete` |
| **S3** | **Workbench-MCP + bearer auth + audit endpoint (closes P5.5).** New `apps/mcp-workbench/` packaged FastMCP server, **SSE on 127.0.0.1:8766** (12 read-only tools, thin HTTP adapters). Per-user bearer auth: `CredentialKind.WORKBENCH_MCP_KEY` (StrEnum); `get_current_user` gained a `Header` param + `_resolve_from_mcp_token` (constant-time; cookie path untouched). New `GET /api/v1/audit` (user-scoped paged read — did not exist). `check_workbench_mcp_readonly.sh` (**12th** invariant) wired into ci.yml; `mcp-workbench` added to the Python-test + build-image matrices. Agent guide at `apps/mcp-workbench/CLAUDE.md` (root CLAUDE.md preserved, 1 line updated); docker-compose service + `.env.example`. Session doc v0.3 (post-review). | ✅ #49 tag `p5.5-session3-complete` |

### P5.5 §3 deviations from the v0.2/v0.3 doc (verified against live code)
- **Transport is SSE on a PORT (8766), NOT stdio** — reading P3's real `apps/mcp-server/server.py` (`run(transport="sse")`, EXPOSE 8765) reversed the doc's "stdio" correction; the root CLAUDE.md already said 8766. Built packaged like P3 (`config`/`client`/`server`).
- **P3's chart-MCP catalog is effectively unauthenticated vs the P5 backend** (its per-user tools send no auth → would 401; P3 predates P5 cookie auth, `p3-complete` never tagged). Validates §3's per-user bearer design; **P3 alignment is a future follow-up.**
- **Root `CLAUDE.md` already existed** (PR #35 dev-conventions doc) → agent guide shipped at `apps/mcp-workbench/CLAUDE.md`, NOT root (root would have been overwritten). **`/api/v1/audit` had to be CREATED** (absent). `CredentialKind` is `StrEnum`; `user_credentials.kind` is plain `String(64)` storing `.value`. `get_current_user` got a `Header` param (not a `request: Request` rewrite).
- **CI caught 2 real regressions post-open** (fixed in `3ea23a6`): credentials list is now **8** kinds not 7 (WORKBENCH_MCP_KEY is correctly manageable via Settings→Credentials) → `test_p5_credentials_endpoint` updated; `pytest-cov` was missing from `apps/mcp-workbench` dev deps (CI runs `pytest --cov`). **Lesson:** `pytest > file; echo "exit=$?"` makes the task-notification exit code meaningless (echo's exit) — run pytest as the sole command for a reliable code.
- 10 backend tests (6 bearer + 4 audit) + 17 workbench-mcp tests. **Squash `aa4928c`; all 8 CI jobs green** (incl. the new `Python (mcp-workbench)` + `Build image (workbench-mcp)`). Jay merged inside the ≥1h walk-away (informed override, CI green). **DEFERRED → `p5.5-complete` HELD:** live SSE handshake + real Claude-Code tool calls + §3.13 cross-session verification (Norton + no local Docker).

### P5.5 §2 deviations from the v0.2 doc (verified against live code)
- **Bar cache is `BarCache.get_bars(symbol, timeframe, start, end) → DataFrame[t,o,h,l,c,v]`** (async), NOT the doc's `get_recent_bars(symbol, limit)` with close/high/low/volume; bias computed via the existing `IndicatorComputer.compute(...)` path (same as `/api/v1/indicators`), no pandas_ta inline.
- **EMA20/EMA50 added to `IndicatorComputer`** (CORE_INDICATORS + dispatch) — the computer previously had only EMA9/EMA21 + SMA20/50/200, so a user's `ema_relationship: "20>50"` had no real EMAs to compare. +2 indicator tests; `check_p2_coverage` stays green. Benefits charts too.
- **LLM narration reuses `app/agent/anthropic_client.create_message` + `app/agent/pricing.estimate_cost`** (no second SDK wrapper); cost recorded in the `MORNING_BRIEF_GENERATED` audit payload (CLAUDE.md "Audit-logging the AI"). `morning_brief.py` was **already** on the no-LLM allowlist → zero CI change.
- **Scheduler:** coroutine-fn + `kwargs={session_factory, bar_cache, indicator_computer}` (NOT lambda), inside the alpaca-enabled block; `get_sessionmaker()` (no `app.state.session_factory`). **`today_eastern()` uses `ZoneInfo`** (DST-correct), not the doc's fixed −5h. **Positions deferred** (indicator-only, broker-independent job). Decisions (EMA-extend / cost-in-payload / positions-defer) confirmed with Jay via AskUserQuestion.
- Full suite green under `--cov` (mypy 149/ruff/6-shell-invariants/ADR-0002/3-coverage-gates); frontend tsc+eslint+**87 vitest**; 29 backend + 5 frontend new tests; migration round-trip on a DB copy. **Squash `224efc6`; merge-commit CI confirm pending.** Jay merged ~54 min into the ≥1h walk-away (informed override, CI green). **Live + Haiku narration smoke deferred** (Norton). **Pre-existing flake:** `test_full_pipeline_paper_buy` (async order pipeline) intermittently fails only under non-CI `-p no:cacheprovider` ordering — not a §2 regression; flagged for a separate order-independence fix.

### P5.5 §1 deviations from the v0.2 doc (verified against live code)
- **Audit imports from `app.audit`** (re-exports `AuditAction`/`AuditActorType`/`AuditLogger`), NOT `app.db.enums`; `write()` sync, caller commits. `AuditAction` is `StrEnum`, value==name UPPER → `TRADING_PROFILE_UPDATED`; stored action string is the UPPER name.
- **v0.2 correction #3 mis-described §5**: the live `risk.py` actually TWO-commits (mutate→commit→audit→commit). Both are valid for the §8 hash chain (one audit row per commit); the service uses single-commit.
- **Router object is `api_router`** (not `api_v1_router`); included with no extra prefix. **Frontend `apiFetch` body must be `JSON.stringify(...)`**; routes register in `App.tsx`, nav link in `Settings/index.tsx`.
- **`user_id unique=True, index=True` → one unique index** `ix_trading_profiles_user_id` (no separate UNIQUE constraint); the migration mirrors `create_all`. **No `tests/migrations/` harness** → migration verified by a manual up/down/up round-trip on a DB copy + ORM read (repo norm). `TradingProfile` re-exported in `models/__init__.py` (drives `create_all`).
- 19 backend (11 service + 8 API) + 5 frontend vitest. Suite green; mypy(145)/ruff/6-shell-invariants/ADR-0002/3-coverage-gates green; frontend tsc+eslint+82 vitest green. **Squash `5919a66`**; pre-merge CI all 6 jobs green. Jay authorized the merge ~16 min before the ≥1h walk-away cleared (informed override, CI green). §1.8 live curl smoke + migration-vs-real-prod-DB deferred (Norton). Results: `TradingWorkbench_P5_5_Session1_Results_v0.1.md`.

## 🚧 P6 — Strategy intelligence layer (in progress)

Goal: advisory agent that reviews strategies, proposes parameter changes, and (later) drafts strategies — all routed through the existing activation flow before anything goes live; constrained by ADR 0006 v2 (B3_AUTONOMOUS paused). The 8 architectural questions are settled in `Docs/implementation/TradingWorkbench_P6_Architectural_Decisions_v0_1.md` (Decisions 1–8). Per-session docs drift against the prior session's Results (Rec #10).

| Session | Scope | Status |
|---|---|---|
| **S1a** | **Agent infrastructure (skeleton + schema + cost envelope).** New `apps/agent/` packaged consumer service (config + budget client + LLM-call wrapper; reads via workbench-mcp, writes via backend HTTP, **never touches the DB**; `python -m agent` is a stub until §1b). `strategy_proposals` table + `ProposalState` (composite-unique per `(strategy_id, generated_at→minute)` via a `strftime` functional index). `trading_profiles.agent_envelope_json` (Decision 4) wired through the service dataclass + trading-profile API. **`GET /api/v1/agent/cost-envelope`** (Decision 6 hard pre-call cap, default $2.00, `AGENT_BUDGET_REJECTED` audit row; renamed from `/agent/budget` — P3 owns that). `CredentialKind.AGENT_API_KEY` + generalized bearer auth (`AGENT_API_KEY` then `WORKBENCH_MCP_KEY`; MCP path byte-identical). 3 audit actions. **13th CI invariant** `check_agent_no_db_access.sh`; `apps/agent` added to the python-checks + build-image matrices. Migration `a3d9f1c4b7e2` (down-rev `b3f8c2d1e9a7`). Session doc + Results: `TradingWorkbench_P6_Session1a_v0_1.md` / `..._Session1a_Results_v0.1.md`. | ✅ #50 tag `p6-session1a-complete` |
| **S1b** | **Agent invocation path + MCP tools + proposals UI (closes the §1 build-out).** `apps/agent/` FastAPI control-plane (`POST :8767/generate-proposal`), real **MCP-over-SSE** read client (`mcp` SDK; injectable for tests), backend write client, proposal-generation flow (reads context → budget-checked Sonnet call → writes DRAFT→REVIEWING). Backend: `POST /strategies/{id}/propose` (sync agent invoke; cleans up DRAFT on failure), `PATCH /proposals/{id}` (REVIEWING/ACCEPTED/REJECTED), `GET /proposals`, `POST /proposals/{id}/apply` (merges `params_json`, IDLE guard), `GET /strategies/{id}/history` (**in proposals.py** to keep strategies.py P2-gate stable). 4 new workbench-mcp GET tools (12→16). Frontend Proposals page + RecentProposalsCard + envelope editor (6th profile section) + `/proposals` route. **ADRs 0009-0014.** No new migration/audit actions; no order-path code. Session doc + Results: `TradingWorkbench_P6_Session1b_v0_1.md` / `..._Session1b_Results_v0.1.md`. | ✅ #51 tag `p6-session1b-complete` |

### P6 §1b deviations from the v0.1 doc (verified against live code)
- **Agent reads via a real MCP-over-SSE client** (`mcp` SDK `sse_client` + `ClientSession.call_tool`) — FastMCP has no `POST /tools/{name}` surface. Injectable so unit tests mock it; live SSE handshake Norton/Docker-deferred.
- **APPLIED merges into `params_json` with an IDLE guard** (mirrors `PUT /strategies/{id}`); params aren't top-level columns, no `description` column, no `MUTABLE_PARAMS` whitelist. Orders filtered via `source_type=strategy`+`source_id` (no `strategy_id` param). Package is `mcp_workbench` (not `workbench_mcp`).
- **`call_with_budget` gained a `system=` param** (Anthropic takes the system prompt separately). A fresh `apps/agent/.venv` was created (PyPI reachable for `mcp`/`fastapi`/`anthropic`) so the agent suite runs locally as CI does.
- **Two CI catches my narrow local checks missed** (fixed before merge): (1) the new `/strategies/{id}/history` endpoint dropped `api/v1/strategies.py` branch-rate to 0.097 (<0.10 P2 gate; CI computes ~0.003 below local) → **moved the endpoint to proposals.py's strategies_router**, reverting strategies.py to byte-identical §1a state; (2) `RecentProposalsCard`'s empty-state link was named "Proposals", colliding with the sidebar nav link in `App.test` → renamed "Proposals page". **Lesson: run the FULL `pnpm test` (vitest) + the coverage gate locally, not just targeted file checks.** `test_full_pipeline_paper_buy` flaked under the new collection order (passes in isolation; pre-existing).
- 17 backend (15 proposals + 2 history; +5 strategies read-path tests for gate margin) + 22 agent + 91 frontend vitest. **Squash `16855f9`; all 10 PR CI jobs green.** Merged on Jay's "merge and tag when green". **Deferred** (Norton + no Docker): real Anthropic call, `docker compose` run, **§1b.12 cross-session verification → `p6-session1-complete` tag**.
- **Next:** run §1b.12 on a non-Norton stack → tag `p6-session1-complete`; then **P6 §2** (scheduled cadence + backtest eval — Decision 8 / ADR-0014). Do NOT speculate against §2 before `p6-session1-complete` (Rec #10).

| **S2a** | **Opt-in scheduled cadence.** `agent_envelope_json.proposal_cadence` enum (off|weekday_market_open|daily|weekly|monthly_first; default off) → `app/services/proposal_cadence.py` registers one APScheduler cron per user (startup `register_all_cadence_jobs` inside the alpaca block; `reconcile_cadence_for_user` on profile update). Each fire iterates the user's strategies, budget-pre-checks via `/agent/cost-envelope`, invokes existing `POST /strategies/{id}/propose` with `trigger="cadence"` (user's `AGENT_API_KEY` bearer). New `AGENT_CADENCE_FIRED` audit action (1 row/strategy/fire; outcomes generated/budget_skipped/propose_failed/no_api_key). `ProposeRequest.trigger` → cadence fires audit as actor_type=AGENT/cron_scheduler. Frontend cadence dropdown + no-`AGENT_API_KEY` warning. No new migration/MCP/ADRs. Session doc + Results: `TradingWorkbench_P6_Session2a_v0_1.md` / `..._Session2a_Results_v0.1.md`. | ✅ #52 tag `p6-session2a-complete` |
| **cleanup-1** | **Rename `app/agent/`→`app/llm/` + bearer-resolver dedup.** 5 LLM modules + `tests/agent/`→`tests/llm/` + all `app.agent` imports. Invariants updated: `check_no_llm_in_order_path.sh` allowlist + `check_p3_coverage.py` suffixes (`agent/*`→`llm/*`; gate re-matches `llm/pricing.py` 1.000 / `system_prompt` 0.900 / `runtime` 0.542 / `anthropic_client` 0.312). P3 chat router `app/api/v1/agent.py` unchanged. Removed dead `_resolve_from_mcp_token` shim. No behavior change. No session doc (cleanup PR). | ✅ #53 tag `p6-cleanup-1-complete` |
| **S2b-backtest** | **Backtest eval pipeline.** `app/services/proposal_evaluation.py`: `enqueue_eval_for_proposal` (service-layer baseline+variant `BacktestJob` insert, bypasses the single-flight 409; `config_json` matches `_config_from_dict`; params flow → baseline vs variant differ), `compute_verdict` (Decision 8: sharpe ≥ baseline AND drawdown ≥ max(baseline−0.05, −0.20); ties pass), `reconcile_pending_evals` (60s cron, reads completion via `BacktestJob.result_id`, writes `evaluation_results_json`). PATCH DRAFT→REVIEWING enqueues atomically (non-fatal; audit `eval_status`). Non-PYTHON/no-symbols skip. `GET /strategies/{id}/proposal-eval-summary` + `workbench_proposal_eval_summary` MCP tool (16→17) + frontend eval badge/`EvalPanel`. No migration/audit/ADRs. Session doc + Results: `TradingWorkbench_P6_Session2b_backtest_v0_1.md` / `..._Session2b_backtest_Results_v0.1.md`. | ✅ #54 tag `p6-session2b-backtest-complete` |

### P6 §2b-backtest deviations from the v0.1 doc (verified against live code)
- **`BacktestJob` requires `user_id` + `submitted_at`; NO `created_at`/`updated_at` columns** (the sketch would have crashed). Read results via `BacktestJob.result_id` (worker-set on COMPLETED), fail via `error_text`; status values lowercase.
- **`strategy.symbols_json`** (not `strategy.symbols` — the sketch would skip every eval as `no_symbols`). `config_json` matches `_config_from_dict`/`submit_backtest`: `timeframe="1Min"`, `commission=0.0`, `initial_equity="100000"` (str). Params verified to flow (`strategy_class(ctx, params={**default_params, **config.params})`).
- Eval-summary endpoint on `proposals.py::strategies_router` (§1b coverage-gate lesson); reconcile in-flight query uses `func.json_extract` Core. ADR-0014 already Accepted (no flip).
- 21 backend + 6 frontend + 1 MCP tests. **Squash `267b666`; all 10 PR CI jobs green first try.** Merged on Jay's "merge and tag when green". Deferred: real Anthropic proposal + live backtest-worker run.
- **Next: §2b-review** (10% human-review sampling cron + review UI), drafted against the §2b-backtest Results.

### P6 §2a deviations from the v0.1 doc (verified against live code)
- **Scheduler is `WorkbenchScheduler`** → jobs register via `scheduler.scheduler.add_job(...)` (`CronTrigger`, `America/New_York`). The scheduler + `app.state.scheduler` **only exist in alpaca-enabled boots** → `register_all_cadence_jobs` runs inside that block; the profile-update reconcile hook `getattr(app.state, "scheduler", None)` → no-op when absent (tests/data-only stay green). **No `app.state.session_factory`** → `get_sessionmaker()`. (The doc's sketches were wrong on all three.)
- `run_proposal_cadence` accepts an injectable `client` → unit tests drive the cost-envelope + propose HTTP via `MockTransport`. The trading-profile `PUT` gained a `request: Request`; reconcile wrapped in try/except so it never fails the profile update.
- **CI ruff catch** (fix `0e2cfd2`): unused `pytest` import in a new test file — CI's `ruff check .` covers `tests/` but my local pre-push ruff only checked `app/`. **Lesson: run the whole-package linters (`ruff check .`, full `eslint`), not just changed files.**
- 15 backend (12 service + 3 propose-trigger) + 4 frontend tests. **Squash `d0f709e`; all 10 PR CI jobs green.** Merged on Jay's "merge and tag when green". **Deferred** (Norton + no Docker): live cron fire, real Anthropic call, `docker compose` run.
- **Next: cleanup PR** (`app/agent/`→`app/llm/` rename + bearer-token resolver dedup) → tag `p6-cleanup-1-complete`; then **§2b** (backtest eval + human-review sampling — Decision 8) drafted against §2a Results + the cleanup PR.

### P6 §1a deviations from the v0.1 doc (verified against live code)
- **Audit columns are `ts`/`payload_json`** (not `created_at`/`payload`); `AuditLogger.write` is a sync staticmethod. **`cost_cents` is fractional cents** (USD×100, stringified Decimal, e.g. `"0.0800"`) → summed as `Decimal` and rounded UP once; the doc's per-row `int(Decimal(...))` truncation would have zeroed every sub-cent cost.
- **24h spend query built with SQLAlchemy Core** (mapped `AuditLog.ts` + `func.json_extract`), not raw `text()` — a raw `ts >= :iso_string` compares SQLite's stored `"YYYY-MM-DD HH:MM:SS.ffffff"` against an isoformat `"...T...+00:00"` lexicographically and silently excludes every row.
- **Functional unique index uses `sa.text("strftime('%Y-%m-%d %H:%M', generated_at)")`** — passing the bare string `"generated_at"` to `func.strftime` would index a constant. Verified empirically (create_all + migrated-copy SQL).
- **Route collision:** P3's `agent` router already owns `GET /agent/budget` (chat-session USD budget) → renamed the P6 endpoint to `/agent/cost-envelope`.
- **`TradingProfileService` returns a dataclass** → extended the dataclass + `_to_data` + `_new_row` + `PROFILE_FIELDS` + the trading-profile API request/response (doc only named `PROFILE_FIELDS`). **`AuditActorType.AGENT`** used for the rejection row.
- **CI mypy caught a real type error** the local run missed (local venv lacks `anthropic` → `ignore_missing_imports` masked it): `messages.create(messages=list[dict])` vs `Iterable[MessageParam]` → targeted `# type: ignore[arg-type]` (fix commit `3824831`). **Lesson:** the agent's mypy needs `anthropic` installed to be meaningful; trust CI's `Python (agent)` job.
- 15 backend (9 cost-envelope + 6 schema) + 12 agent unit tests. **Squash `b95395a`; all 10 PR CI jobs green** (incl. new `Python (agent)` + `Build image (agent)`). Merged on Jay's explicit "PR and tag" (informed override of the ≥1h walk-away, CI green). **Deferred** (Norton + no Docker): real Anthropic call (no caller until §1b), `docker compose` run, migration on the real dev DB (verified on a copy). Credentials list is now **9** kinds (`test_p5_credentials_endpoint` updated 8→9).
- **Next: P6 §1b** — agent invocation path + MCP read tools for proposal context + frontend (envelope editor + proposals UI). Draft `TradingWorkbench_P6_Session1b_v0.1.md` against the §1a Results doc (NOT speculatively).

## 🗺️ P5 + P5.5 + P6 + P7 — Roadmap

Captured for orientation; plans land when their turn comes. P5 + P5.5 + P6 + P7 per-session docs are already drafted under uppercase `Docs/implementation/`.

| Phase | Theme | Headline outcome |
|---|---|---|
| **P5** | Live trading toggle | Live creds, live-mode UI, hard gates, reconciliation, audit trail with hash chain. Per-user encrypted Anthropic key lands here. |
| **P5.5** | Morning brief + trading profile + workbench-mcp polish | Scheduled advisory narration; trader profile/preferences; MCP server tightening. The `morning_brief.py` allowlist entry in ADR 0006 anticipates this work. |
| **P6** | Strategy intelligence layer | Periodic strategy review, parameter tuning proposals, drift detection, optional NL → Python exploration. All advisory; all routed through the existing activation flow before anything goes live. Constrained by ADR 0006. |
| **P7** | NL → Python strategy authoring (standalone if not in P6) | "Draft strategy with Claude" UI button; backend generates the strategy file. |

---

## How to use this file

- After each working session, update the top section (Last updated / branch / latest tag) and the relevant phase table.
- When a session lands, link the merging PR + tag in the table; don't expand the row into a checklist.
- Frozen versioned plans live in `docs/implementation/`. This file is the index, not the spec.
