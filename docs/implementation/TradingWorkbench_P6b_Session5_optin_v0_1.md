# Trading Workbench — P6b §5: LLM-Driven Live Trading Opt-In

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-05 |
| Phase | P6b — §5 (LLM-driven live trading opt-in, ADR 0006 v2) |
| Session | §5 of P6b (the late half; §4 shipped the paper eval harness) |
| Predecessor | `TradingWorkbench_P6b_Session4_eval_harness_v0_1.md` (tag `p6b-session4-eval-harness-complete`, `6f970e6`) |
| Successor | — (P6b complete after §5; then P7 NL→Python) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The ADR-0006-v2 user opt-in that lets a *single eligible strategy* route its **live** orders through an LLM act/skip gate — the only sanctioned LLM-in-order-path. Full-stack. |
| Estimated wall time | 7–9 hours (full-stack; relaxes invariant #11; touches the live order path + audit subsystem) |
| Tag on completion | `p6b-session5-optin-complete` |
| Out of scope | See §"What this session does NOT do" |

> **⚠ BLOCKED (2026-06-05): depends on P6b §4.5 — live strategy auto-dispatch.**
> Implementation surfaced that the strategy engine hardcodes the *paper* account for
> every strategy (`engine.py:189-197`, no `status==LIVE` branch), and the activation
> completion cron flips `PENDING_LIVE→LIVE` without registering the strategy for
> dispatch. So a LIVE strategy's automatic orders go to paper (or don't dispatch at
> all) — live strategy auto-dispatch was deferred and never wired. §5's "LLM-gate the
> strategy's *live* orders" presupposes that path. Jay's call: do **P6b §4.5 (live
> strategy auto-dispatch, with its own ADR)** first, then revise §5's engine-integration
> section (§5.4) to wrap the now-real live path. The rest of §5 (opt-in lifecycle, gate,
> invariant #13, audit, budget, cooldown, UI) is unaffected and stands.

---

## Why this session exists

ADR 0006 v2 ends "paused indefinitely" and replaces it with "available behind a defined evaluation framework and a user opt-in." §4 built the evaluation framework — the paper-only A/B harness (Mode A deterministic vs Mode B LLM-gated) and the `EligibilityVerdict` double-floor (≥50 Mode-B trades **AND** ≥30 days). §5 builds the *second half*: the opt-in itself.

After a strategy is eligible, the user may opt in. Opting in does exactly one consequential thing — it lets that strategy's **live** orders pass through an LLM act/skip gate before reaching the broker. This is the single, deliberate relaxation of the no-LLM-in-order-path invariant the entire ADR is built to make safe: gated by eligibility, a typed acknowledgment, a TOTP re-entry, a 7-day cooldown, a per-user dollar cap, full forensic audit logging, and a one-click frictionless opt-out.

This is the most invariant-sensitive session in the project. Every gate below exists because an LLM in the live order path is exactly the capability the platform spent its whole trust story being careful about. The friction is the feature.

## The invariant relaxation (stated up front)

§5 adds the **per-(user, strategy, version) runtime bypass** of `check_no_llm_in_order_path.sh` (invariant #11) that ADR 0006 v2 line 107 sanctions. The bypass is **not** a code allowance — it is a `llm_opt_in` row in state `active`, whose creation is audit-logged, whose version is pinned, and which a new CI invariant (#13) forces the live gate to honor. This is the **second** invariant change of the ADR (§4 was the first — the paper harness allowlist entry). It is intentional and ADR-authorized.

## What this session ships

1. `llm_opt_in` table (version-pinned per (user, strategy)) + Alembic migration.
2. `app/services/llm_live_gate/` — a **new allowlisted module** (distinct from §4's `eval_harness`, so invariant #12 stays intact) holding the live LLM act/skip gate that wraps an opted-in strategy's `submit_order_fn`.
3. `LLMOptInService` — initiate (typed-ack + TOTP) / opt-out (frictionless) / status, mirroring `ActivationService`.
4. A 7-day cooldown completion cron (`app/jobs/llm_opt_in_completion.py`) mirroring `activation_completion.py`.
5. Engine integration — `register()` wraps the live parent's submit when an `active` opt-in (matching the strategy's current version) exists.
6. Four new audit actions (`LLM_OPT_IN_INITIATED`, `LLM_OPT_IN_ACTIVATED`, `LLM_OPT_OUT`, `LLM_LIVE_DECISION`) — every live LLM decision audit-logged with full prompt + response + baseline decision + outcome (ADR line 79).
7. Per-user **$10/day** live LLM cap (`DEFAULT_LIVE_DAILY_CAP_CENTS = 1000`), user-configurable upward behind a confirmation gate.
8. Endpoints: `POST /strategies/{id}/llm-opt-in`, `POST /strategies/{id}/llm-opt-out`, `GET /strategies/{id}/llm-opt-in`, `POST /strategies/{id}/llm-opt-in/raise-cap`.
9. `${ROOT}/services/llm_live_gate` added to invariant #11 ALLOWED_DIRS; **new invariant #13** `check_llm_optin_bypass_gated.sh`.
10. MCP read tool `workbench_llm_opt_in_status` (20 → 21 tools).
11. Frontend: eligibility-gated opt-in dialog (metrics + typed-ack + TOTP), opted-in badge, opt-out button — zero-dep (Norton).

## Prerequisites

- `p6b-session4-eval-harness-complete` (`6f970e6`) merged: the `EvalHarness` model, `check_eligibility`, and the `GET /strategies/{id}/eval-harness` endpoint exist.
- The strategy being opted in is `LIVE`, has an `active` eval harness, and that harness's `EligibilityVerdict.eligible` is `True`.
- The user has a TOTP secret (P5 §7 — required for live activation, reused here).

---

## Detailed work

### §5.1 — Schema: the `llm_opt_in` table

`app/db/models/llm_opt_in.py` (new). Mirrors the `EvalHarness` shape; **version-pinned** so a parameter tweak (which bumps `strategies.version`) invalidates the opt-in automatically (ADR line 66/78: "that specific strategy version").

```python
# State constants (small closed set, stored as plain strings).
OPT_IN_PENDING = "pending"        # 7-day cooldown running; live still deterministic
OPT_IN_ACTIVE = "active"          # cooldown elapsed; live orders are LLM-gated
OPT_IN_OPTED_OUT = "opted_out"    # terminal; frictionless exit

class LLMOptIn(Base):
    __tablename__ = "llm_opt_in"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False)
    # Pin: the opt-in applies only while strategies.version still equals this.
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    acknowledgment_text: Mapped[str] = mapped_column(Text, nullable=False)  # the typed phrase, recorded
    daily_cap_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)  # $10/day
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 7-day anchor
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opted_out_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at / updated_at

    __table_args__ = (
        Index("ix_llm_opt_in_strategy_id", "strategy_id"),
        Index("ix_llm_opt_in_user_id", "user_id"),
    )
```

- Add to `app/db/models/__init__.py` + `__all__`.
- Alembic migration (new revision, down-rev = `e9a3c7f1d2b4` the §4 head). `create_table` + indexes. Round-trip up/down/up.
- Constants in the live-gate module: `LLM_OPT_IN_COOLDOWN_DAYS = 7`, `DEFAULT_LIVE_DAILY_CAP_CENTS = 1000`.
- **At most one non-terminal (`pending` | `active`) opt-in per strategy** — enforced in the service (a query guard, like §4's `find_active_harness`), not a DB partial index (SQLite friendliness, matches the codebase pattern).

### §5.2 — The live LLM gate (`app/services/llm_live_gate/`)

A new package — **separate from `eval_harness`** so invariant #12 (harness-is-paper-only) is untouched. Added to the no-LLM `ALLOWED_DIRS`.

`gate.py`:

```python
GATE_MODEL = "claude-haiku-4-5-20251001"  # same tier as §4's gate
LLM_OPT_IN_COOLDOWN_DAYS = 7
DEFAULT_LIVE_DAILY_CAP_CENTS = 1000

async def find_active_opt_in(session, strategy_id) -> LLMOptIn | None:
    """The OPT_IN_ACTIVE row for a strategy whose strategy_version still matches
    the live strategy's version. Returns None if pending / opted-out / version-stale."""

async def _user_live_spend_today_cents(session, user_id, now) -> Decimal:
    """Per-USER (not per-strategy) sum of LLM_LIVE_DECISION cost over 24h, from the
    audit log (json_extract on payload_json.cost_cents). Low volume — one opted-in
    strategy's live signals — so the hash chain is the single source of truth."""

async def query_live_llm_decision(api_key, payload) -> (action, rationale, prompt, response, cost_cents):
    """Same structured-only signal + act/skip contract as §4, but ALSO returns the
    full prompt + raw response text for the forensic audit (ADR line 79). Defaults
    to 'skip' on a garbage response (conservative — suppress, don't fire)."""

def make_live_llm_submit_fn(*, strategy_id, user_id, real_submit, session_factory) -> SubmitFn:
    """Wrap a LIVE strategy's submit_order_fn. Per order intent (the deterministic
    strategy already decided to fire → baseline == 'act'):
      1. Re-read the active opt-in (version match). None/stale → submit deterministically
         (passthrough — opt-in invalidated mid-run, e.g. param tweak).
      2. Per-user budget check. Over the daily cap → FAIL SAFE: submit deterministically
         (the LLM simply isn't consulted; live trading continues as the original strategy
         intended). Audit a LLM_LIVE_DECISION with decision='budget_skip_fired_deterministic'.
      3. Resolve the user's ANTHROPIC key (CredentialStore). Missing → submit deterministically.
      4. query_live_llm_decision(...). On exception → submit deterministically (best-effort;
         the deterministic baseline is always the safe fallback).
      5. action == 'act'  → submit the live order via real_submit.
         action == 'skip' → SUPPRESS the order (the LLM declined to fire).
      6. Audit-log LLM_LIVE_DECISION with: full prompt, full response, baseline='act',
         llm_decision, cost_cents, order_id (if acted) / null (if skipped)."""
```

**Why fail-safe = deterministic, not order-suppression:** the user opted into *LLM assistance on a deterministic strategy*, not into "no trading when the LLM is unavailable." When the LLM can't be consulted (budget, key, error), the conservative direction is the strategy the user already trusted enough to run live — i.e., submit as the deterministic code intended. The LLM can only *suppress* orders the strategy wanted (it never invents new ones), so a fail-safe to deterministic is strictly the less-surprising direction. (Mirrors §4 Mode A always acting.)

### §5.3 — `LLMOptInService` (`app/services/llm_live_gate/service.py`)

Mirrors `ActivationService`.

```python
RISK_ACK_PHRASE = (
    "I understand LLM-driven trading is non-deterministic and I accept the risk"
)  # the exact typed phrase (case-insensitive, whitespace-stripped compare, like the typed-symbol confirmation)

async def initiate_opt_in(session, *, strategy_id, user_id, acknowledgment_text, totp_code, engine=None) -> LLMOptIn:
    # Guards (each a distinct ValueError → mapped to 4xx):
    #   strategy_not_found / not the user's
    #   parent_not_live              (strategy.status != LIVE)
    #   no_eligible_harness          (no active EvalHarness, or check_eligibility().eligible is False)
    #   opt_in_already_active        (a pending|active row exists)
    #   acknowledgment_mismatch      (typed phrase != RISK_ACK_PHRASE, normalized)
    #   totp_invalid                 (verify_code against the user's TOTP secret — same as activation.py:278)
    # Create LLMOptIn(state=pending, strategy_version=strategy.version, initiated_at=now,
    #   acknowledgment_text=<recorded>, daily_cap_cents=DEFAULT_LIVE_DAILY_CAP_CENTS).
    # Audit LLM_OPT_IN_INITIATED. Commit. (No engine change yet — gating switches on at activation.)

async def opt_out(session, *, strategy_id, user_id, engine=None, reason="user_opted_out") -> None:
    # pending|active → opted_out (+ opted_out_at/reason). Audit LLM_OPT_OUT. Commit.
    # If it was ACTIVE: re-register the strategy so the engine rebuilds submit_order_fn WITHOUT the wrap
    #   (the deterministic strategy resumes live duty — ADR line 81). Frictionless, no cooldown.

async def complete_pending_opt_in(session, *, opt_in_id, engine=None) -> bool:
    # Called by the cron. pending + initiated_at + 7d elapsed + still version-matched + strategy still LIVE
    #   → active (+ activated_at=now). Audit LLM_OPT_IN_ACTIVATED. Commit.
    #   Re-register the strategy so register() now applies the live LLM wrap.
    # If the version drifted or the strategy left LIVE during the window → opt_out(reason="invalidated").

async def raise_cap(session, *, strategy_id, user_id, new_cap_cents, totp_code) -> LLMOptIn:
    # The "user-configurable upward with an additional confirmation gate" (ADR line 100).
    # Requires TOTP; new_cap_cents > current; audit LLM_OPT_IN_CAP_RAISED (a 5th action — see note).
```

> **Note on action count:** if `raise-cap` ships this session it adds a 5th audit action (`LLM_OPT_IN_CAP_RAISED`). If we keep §5 to the four core actions, `raise-cap` defers to §5b. *Open for the implementer to confirm at build time; default = ship the cap field + enforcement, defer the raise-cap endpoint+action to avoid a 5th runbook scenario this session.* (Surfaced here rather than buried.)

### §5.4 — Engine integration (`app/strategies/engine.py`)

In `register()`, after the §4 `harness_role == "mode_a"` block, add a sibling check:

```python
# P6b §5: an opted-in LIVE strategy routes its live orders through the LLM gate.
if row.status == StrategyStatus.LIVE:
    opt_in = await find_active_opt_in(session, row.id)   # active + version match
    if opt_in is not None:
        submit_order_fn = make_live_llm_submit_fn(
            strategy_id=row.id, user_id=row.user_id,
            real_submit=submit_order_fn, session_factory=session_factory,
        )
```

The wrap is applied at register time, so flipping pending→active (cron) or opting out both go through a strategy **re-register** to rebuild `submit_order_fn`. ADR 0002 stays intact — the wrapped fn still calls `OrderRouter.submit`; the gate only decides whether to call it.

### §5.5 — Cooldown completion cron (`app/jobs/llm_opt_in_completion.py`)

Mirrors `activation_completion.py`: collect `pending` opt-in ids in one session → fresh session per item → Python-side elapsed check (`initiated_at + LLM_OPT_IN_COOLDOWN_DAYS <= now`) → `complete_pending_opt_in`. Registered in `lifespan.py` (alpaca block) via `scheduler.scheduler.add_job(..., minutes=15, kwargs={session_factory, engine: strategy_engine})`.

### §5.6 — Audit actions + runbook

Add to `app/audit/logger.py`: `LLM_OPT_IN_INITIATED`, `LLM_OPT_IN_ACTIVATED`, `LLM_OPT_OUT`, `LLM_LIVE_DECISION`. **Each gets a runbook scenario** in `docs/runbook/agent.md` (CLAUDE.md "proven costly": a new AuditAction without a runbook scenario leaves an operator stranded). The `LLM_LIVE_DECISION` payload carries `{prompt, response, baseline_decision, llm_decision, cost_cents, order_id}` (the ADR-line-79 forensic record); the budget sum reads `cost_cents` from it.

### §5.7 — Invariants

- **#11** (`check_no_llm_in_order_path.sh`): add `${ROOT}/services/llm_live_gate` to `ALLOWED_DIRS` (replacing the §5 placeholder comment). This is the ADR-sanctioned live bypass entry.
- **#13** (new, `check_llm_optin_bypass_gated.sh`): assert the bypass cannot fire without the DB flag. Static checks on `app/services/llm_live_gate/`:
  1. `gate.py` references `find_active_opt_in` (the active-row lookup) — the LLM is never called without it.
  2. `gate.py` references `strategy_version` (the version pin) and `daily_cap_cents` (the per-user cap).
  3. The wrapper's fail-safe path submits deterministically (grep for the passthrough `real_submit` call on the None/over-cap branches).
  4. No `StrategyStatus.LIVE` assignment in the package (the gate decides *whether to fire*, it does not change strategy state).
  Wire into `ci.yml` after #12. Update CLAUDE.md (twelve → **thirteen** invariants).

### §5.8 — Endpoints (`app/api/v1/llm_opt_in.py`, new — off the P2 gate, like §4)

- `POST /strategies/{id}/llm-opt-in` — body `{acknowledgment_text, totp_code}`; ValueError → `_OPT_IN_ERROR_CODES` (404/409/400). Returns `{status: "pending", opt_in_id, initiated_at, activates_at}`.
- `POST /strategies/{id}/llm-opt-out` — frictionless; `{status: "opted_out"}`.
- `GET /strategies/{id}/llm-opt-in` — `{status: none|pending|active, seconds_remaining?, daily_cap_cents, spend_today_cents, eligibility: <§4 verdict>}`.
- `POST /strategies/{id}/llm-opt-in/raise-cap` — *(see §5.3 note; default-deferred to §5b)*.
- Register in `app/api/v1/__init__.py`.

### §5.9 — MCP read tool

`workbench_llm_opt_in_status(strategy_id)` → `GET /strategies/{id}/llm-opt-in` (read-only). Add to `_TOOLS` (20 → 21); `test_tools.py` count assertion; `apps/mcp-workbench/CLAUDE.md` decision-tree row. Promotion to LLM-driven live is **always user-gated** — the tool description says never suggest auto-enabling.

### §5.10 — Frontend (zero-dep, react-query v5)

- `src/api/llmOptIn.ts` — `status` / `optIn` / `optOut`.
- `components/strategies/LLMOptInCard.tsx` — renders only when the strategy is LIVE with an active eval harness. States:
  - **ineligible** — shows the `EligibilityVerdict` reasons (e.g. "32/50 Mode-B trades, 18/30 days"); no opt-in control.
  - **eligible (no opt-in)** — the §4 comparison metrics + a typed-ack input (must match `RISK_ACK_PHRASE`) + TOTP input + "Opt in to LLM-driven trading" button. A prominent risk disclosure.
  - **pending** — "LLM-driven trading activates in N days" + Opt-out.
  - **active** — "LLM-gating live · $X.XX / $10.00 today" + Opt-out.
  - Plain `useState/useEffect` (the strategy-detail page has no QueryClientProvider — DriftCard/VariantCard pattern).
- Mounted in `pages/Strategies/Detail.tsx` next to `VariantCard`.
- Tests (vitest): the four states render; opt-in disabled until ack matches + TOTP non-empty; opt-out calls the endpoint.

---

## Manual smoke

1. Seed (or reuse) a LIVE strategy with an `active` eval harness whose `EligibilityVerdict.eligible` is forced true (≥50 Mode-B trades, ≥30 days — or a test seam).
2. `GET /strategies/{id}/llm-opt-in` → `eligible: true`, `status: none`.
3. `POST /llm-opt-in` with the wrong phrase → 400 `acknowledgment_mismatch`. With the right phrase + bad TOTP → 400 `totp_invalid`. With both correct → `pending`.
4. `GET` → `status: pending`, `seconds_remaining` ≈ 7d.
5. Force the cron (or call `complete_pending_opt_in` directly with a back-dated `initiated_at`) → `active`; strategy re-registered.
6. Submit a strategy signal → confirm an `LLM_LIVE_DECISION` audit row with full prompt/response, and that a `skip` suppresses the live order while `act` lets it through (against the paper-broker smoke account, byte-identical structurally to the deterministic path).
7. `POST /llm-opt-out` → `opted_out`; strategy re-registered without the wrap; the next signal submits deterministically.
8. **Load-bearing assertion:** with no active opt-in, a live strategy's order path makes **zero** Anthropic calls (invariant #11 holds for everyone not opted in); with an active opt-in, exactly one LLM call per order intent, fully audit-logged.

## Walk-away discipline

**≥ 2 hours** (touches the live order path *and* the audit subsystem — the session-doc skill's two triggers for the 2-hour minimum, and the most consequential single relaxation in the codebase). Honor it especially because the change feels gated enough to be safe.

## What this session does NOT do

- **No auto-enable.** The platform never opts a user in or recommends it (ADR line 70). The metrics inform; the user decides.
- **No Mode-C swap to a separate live clone** — the deterministic strategy stays the one live row; the opt-in toggles an LLM wrap on its submit (decision A).
- **No new `StrategyStatus`** — the opt-in lifecycle lives in the `llm_opt_in` table (decision B).
- **No change to §4's harness** — invariant #12 (harness-is-paper-only) is untouched; the live gate is a separate module.
- **No LLM-authored orders** — the gate can only *suppress* orders the deterministic strategy already produced; it never invents trades (the social-engineering surface stays minimal, ADR line 98).
- **No multi-strategy opt-in batch UI** — one strategy at a time.
- **No raise-cap endpoint by default** (the cap *field* + enforcement ship; the upward-config endpoint + its 5th audit action default to §5b — see §5.3 note).
- **No removal of the §4 eligibility floor** — opt-in is hard-gated on it server-side.

## Notes & gotchas

1. **The version pin is the modification-floor.** ADR line 66: "a parameter tweak resets the clock." We get this free — `strategies.version` bumps on edit, and `find_active_opt_in` requires `opt_in.strategy_version == strategy.version`, so a tweak silently invalidates the opt-in (the wrap falls back to deterministic). The cron's `complete_pending_opt_in` also re-checks the version and opts out if it drifted.
2. **Budget is per-USER, not per-strategy** (ADR line 100), and fail-safe is *deterministic*, not no-trade. Don't copy §4's per-harness pause semantics — over-budget here must not halt live trading, only the LLM consultation.
3. **Re-register, don't hot-patch.** Flipping the wrap on/off goes through engine unregister+register (rebuild `submit_order_fn`), not by mutating a live closure. Same discipline as §4's "register Mode A after commit."
4. **Audit one row per commit** (the hash-chain contract). The opt-in transitions and each `LLM_LIVE_DECISION` write their audit row in their own transaction.
5. **TOTP is reused from activation** (`app.auth.totp.verify_code`, `CredentialKind.TOTP_SECRET`) — don't invent a new secret store.
6. **Norton:** frontend is zero-dep (no `pnpm add`); mirror the inline-SVG / plain-hooks patterns from VariantCard/DriftCard.
7. **The §4 `query_llm_decision` is close but not reused verbatim** — the live gate needs the *full prompt + raw response* returned for the forensic audit, which §4's signature doesn't surface. Define a sibling `query_live_llm_decision`; do not weaken §4's gate to share it.
8. **`raise-cap` decision** (§5.3 note) should be settled before the audit-action enum is edited, so the runbook scenario count is right the first time.
