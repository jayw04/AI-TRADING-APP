# P6b Session 3b-promote — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — §3b-promote (promote/reject + cooldown cron + lockout + UI + MCP, ADR 0007) |
| Plan doc | `TradingWorkbench_P6b_Session3b_promote_v0_1.md` (+ the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session3a-gate-complete` (`d1ba2c4`) |
| Tags | `p6b-session3b-promote-complete` (`7435836`, §3b feat) → **`p6b-session3-promote-complete`** (`5213c69`, the §3 rollup) |
| Shipped as | PR **#62** — branch `feat/p6b-session3b-promotion`; merged `7435836` |
| Verdict | **GO. P6b §3 CLOSED** (rollup). Shipped offline-green AND — Norton disabled — the previously-blocked live `BarCache → Alpaca` equity-curve path verified. Full backend + frontend suites + mypy + ruff + tsc + eslint + coverage gates + invariants all green. No migration. |

## What shipped

- **`POST /proposals/{id}/promote`** — EVIDENCE_READY → PROMOTING; re-checks LIVE + not-in-lockout + bundle present; embeds the **evidence-bundle SHA-256 hash** in the audit payload (ADR 0007). Does **not** terminate the variant (A1 — kept alive through cooldown).
- **`POST /proposals/{id}/reject-promotion`** — one endpoint for "Reject evidence" (EVIDENCE_READY) and "Cancel cooldown" (PROMOTING); → REJECTED; terminates the variant (`terminate_for_parent`, terminate-first ordering).
- **`app/jobs/promotion_completion.py`** — 15-min sweep mirroring `activation_completion` (collect ids, fresh session per item, Python-side elapsed check on `transitioned_at`). Registered in `lifespan.py` (alpaca block) via `scheduler.scheduler.add_job` with `strategy_engine`.
- **`app/services/promotion.py`** — `PROMOTION_LOCKOUT_DAYS = 30`, `in_lockout` / `lockout_expires_at`, and `execute_mechanical_promote` (PROMOTING → PROMOTED: terminate variant, **`_apply_changes` merge** of the proposal's `changes`, set `last_promoted_at`, two-commit `STRATEGY_PROPOSAL_TRANSITIONED` + `STRATEGY_PROMOTED`, `SYSTEM` actor).
- **Lockout enforcement** — 409 on `POST /validate`; silent skip in `_maybe_auto_validate_proposal`. Does **not** block ACCEPT/propose.
- **`/variant-comparison` additive fields** — broadened the proposal lookup to `EVALUATING | EVIDENCE_READY | PROMOTING`; added `proposal_state`, `evidence_bundle`, `eligible_for_promotion`, `parent_last_promoted_at` (the last also on the `no_active_variant` branch). Flows through `workbench_paper_variant_metrics` unchanged (tool count stays 19).
- **VariantCard sub-renders** — EVIDENCE_READY (gate checklist + Promote + Reject), PROMOTING (Cancel + cooldown note), lockout-aware empty state (off `parent_last_promoted_at`). `variantsApi.promote` / `.rejectPromotion` added.
- **Tests** — 24 backend + 3 new frontend (incl. the `test_no_auto_promote_in_codebase` grep guard).

## Corrections applied vs the v0.1 plan

- **B1** `terminate_for_parent(parent_strategy_id, reason, user_id)` (not the wrong `terminate(variant_id=…)`).
- **B2** mechanical merge uses `_apply_changes` on `proposal_payload_json["changes"]` (not the nonexistent `proposal_payload["params"]`).
- **B3** terminate-first → one audit row per commit.
- **B4** cron registered via the in-scope `scheduler.scheduler` (not `app.state.scheduler`).
- **A1** variant terminated at **PROMOTED**, not PROMOTING — otherwise the variant-keyed endpoint goes dark during cooldown and the PROMOTING/PROMOTED UI has no data.
- **A2** broadened the proposal lookup to the three active-validation states.
- **A3** lockout-empty driven off the `parent_last_promoted_at` additive field (no frontend `Strategy.last_promoted_at`).
- **A4** **no migration** — reused `transitioned_at` as the cooldown anchor.
- Minors: no `with_for_update` (SQLite no-op); `SYSTEM` cron actor; `ACTIVATION_COOLDOWN_HOURS` import; the no-auto-promote guard is a pure-Python scan (Windows-portable).

## Verification

- `pytest` full suite green (0 failed, ~3 steady skips); mypy(165) + ruff clean; `vitest run` 122/122; tsc + eslint clean; 3 coverage gates (risk 0.904 / P2 / P3); invariants green (audit-immutability, no-LLM, workbench-mcp-readonly, agent-no-DB, strategy-isolation). **No migration; no new audit action** (STRATEGY_PROMOTED defined §3a); tool count 19; no order-path code.

## P6b §3 rollup (§3b-promote.14 cross-session verification) — 2026-06-04

Run after §3b merged + post-merge CI green. **Jay chose "Tag now" (AskUserQuestion).** Tag **`p6b-session3-promote-complete`** at `5213c69`. Confirms §3a (gate) + §3b (promote/cooldown/lockout/UI/MCP) cohere.

**Verified GREEN (offline battery):**

| Gate | Result |
|---|---|
| 8 shell CI invariants | all pass |
| 3 coverage gates | risk branch 0.904 / P2 / P3 ✓ |
| Full backend suite | exit 0, **0 failures** (all §3a + §3b tests) |
| Agent / mcp-workbench | exit 0 / exit 0 (mcp via the mcp-server venv, `PYTHONPATH=src`) |
| Frontend vitest | 122/122 |

**Verified LIVE (Norton disabled — the previously-blocked path):**

- Python `certifi` probe → `data.alpaca.markets` + `paper-api.alpaca.markets` returned **HTTP 401** (handshake clean — the Norton MITM is gone).
- **`BarCache.get_bars("AAPL","1Day")` fetched 13 real daily bars** (last close $311.21, 2026-06-04), written to parquet.
- **`reconstruct_equity_curve`** marked an open 10-share AAPL position (bought @ $297.85) at each day's **real close** → equity $100,000 → **$100,133.60** (= 10 × ($311.21 − $297.85)). This is the open-position-with-live-closes path **deferred since §2b** — the substrate the §3a promotion gate evaluates. **Now verified live.**
- **Caveat — intermittent SSL.** One mid-run `SSLCertVerificationError: unable to get local issuer certificate` at the alpaca SDK's `requests` layer among successes (Norton / an SSL inspector re-engaging). Mitigation: a persistent BarCache cache dir + a small retry loop. So "works when Norton is fully off," not rock-solid.

**Deferred (interactive / DB-faked — NOT run; low marginal value):**

- [ ] Full `docker compose up` + auth + a real EVIDENCE_READY → promote → 24h-cooldown → PROMOTED end-to-end + the 15-min cron firing on a real boot.
- [ ] Browser UI smoke of the four VariantCard sub-renders.

§3's promote/cooldown/lockout flow is **pure DB (no Alpaca)** and exhaustively unit-covered (33 §3a + 24 §3b tests + offline battery); a live boot would only additionally confirm the cron registers/fires. Jay's dev DB was left untouched (no faked EVIDENCE_READY proposal). **Unlike §2, §3 has no remaining Norton-gated piece** — its one market-data dependency is now verified live.

## Next

**P6b §3 closes here.** Next is the committed P6b-late split: **§4 (Mode-B LLM eval harness)** + **§5 (LLM-driven live opt-in)** — §5 is the only session touching the order-path LLM allowlist (ADR 0006 v2), so it needs the invariant update + its own decision turn first (like §3b's 11-question turn). Draft fresh v0.1s post-§3 (Rec #10). The ADR "extended evaluation" (STRATEGY_PROPOSAL_EXTENDED) feature + full strategy-version archiving remain explicitly deferred. Also now-feasible with Norton off, if wanted: `§1b.12 → p6-session1-complete` + the §2-variant live smoke.
