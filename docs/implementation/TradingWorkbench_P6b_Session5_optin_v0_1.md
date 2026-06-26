# Trading Workbench — P6b §5: LLM-Driven Live Trading Opt-In

| Field | Value |
|---|---|
| Document version | v0.2 (review-driven scope-narrowing — see "Revision v0.2" below) |
| Date | 2026-06-18 |
| Phase | P6b — §5 (LLM-driven live trading opt-in, ADR 0006 v2) |
| Session | §5 of P6b (the late half; §4 shipped the paper eval harness) |
| Predecessor | `TradingWorkbench_P6b_Session4_eval_harness_v0_1.md` (tag `p6b-session4-eval-harness-complete`, `6f970e6`) |
| Successor | — (P6b complete after §5; then P7 NL→Python) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The ADR-0006-v2 user opt-in that lets a *single eligible strategy* route its **live** orders through an LLM act/skip gate — the only sanctioned LLM-in-order-path. Full-stack. |
| Estimated wall time | 7–9 hours (full-stack; relaxes invariant #11; touches the live order path + audit subsystem) |
| Tag on completion | `p6b-session5-optin-complete` |
| Out of scope | See §"What this session does NOT do" |

> **✓ UNBLOCKED (2026-06-05): P6b §4.5 shipped** (`p6b-session4-5-autodispatch-complete`, ADR 0015).
> The live path now exists — the engine resolves the dispatch account by status and a
> `LIVE` strategy auto-dispatches behind the `LIVE_AUTODISPATCH_ENABLED` master switch
> (the `make_live_autodispatch_submit_fn` wrap). §5.4 (below) is revised: the §5 LLM gate
> nests **inside** that wrap (master switch outermost → an off switch skips the LLM call
> and its cost entirely).
>
> **Budget default = $5/day** (`DEFAULT_LIVE_DAILY_CAP_CENTS = 500`), per the owner's
> 2026-06-05 instruction. ADR 0006 v2 line 100 was amended the same day from its
> original `$10/day` to this more conservative `$5/day` default (the cap remains
> user-configurable upward — the raise-cap endpoint is the deferred §5b piece), so the
> ADR and the implementation now agree.

> **Revision v0.2 (2026-06-18) — review-driven scope-narrowing.** A review of v0.1
> (`comments.md`) confirmed the design but asked for a **narrower, more test-heavy** §5
> given it relaxes invariant #11 on the live order path. Changes folded in:
> 1. **`$5/day` cap made consistent everywhere** (item #7, §5.1 model default, §5.3) — the
>    v0.1 text still said `$10` in places while the constant was `500`.
> 2. **`raise-cap` definitively deferred to §5b** (was "implementer's call") — the cap
>    *field* + enforcement ship; the endpoint, the `LLM_OPT_IN_CAP_RAISED` action, and the
>    raise-cap UI move to §5b, keeping §5 to **four** audit actions.
> 3. **Global kill-switch `LLM_LIVE_GATE_ENABLED`** (§5.4) — disables the feature even with
>    `active` opt-in rows present, no DB edit needed.
> 4. **Fail-safe test matrix made explicit** (§5.11) — the seven safety branches are pinned
>    by named tests; "garbage→skip vs error/missing-key→deterministic" asymmetry documented.
> 5. **Audit payload strengthened + size-guarded** (§5.6) — more fields, `prompt_hash` /
>    `response_hash`, and max-size truncation so audit rows can't grow unbounded.
> 6. **DB-level uniqueness defense** (§5.1) + a **UI warning** that the LLM can only suppress,
>    never create, trades (§5.10), and an **emergency rollback** runbook (§"Emergency rollback").

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
7. Per-user **$5/day** live LLM cap (`DEFAULT_LIVE_DAILY_CAP_CENTS = 500   # $5/day`), enforced as a hard pre-call check. Raising it is the deferred §5b piece (the cap *field* + enforcement ship here; the upward-config endpoint does not).
8. Endpoints: `POST /strategies/{id}/llm-opt-in`, `POST /strategies/{id}/llm-opt-out`, `GET /strategies/{id}/llm-opt-in`. *(raise-cap → §5b.)*
9. `${ROOT}/services/llm_live_gate` added to invariant #11 ALLOWED_DIRS; **new invariant #13** `check_llm_optin_bypass_gated.sh`. Global kill-switch env flag `LLM_LIVE_GATE_ENABLED` (default conservative).
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
    daily_cap_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=500)  # $5/day (DEFAULT_LIVE_DAILY_CAP_CENTS)
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
- Constants in the live-gate module: `LLM_OPT_IN_COOLDOWN_DAYS = 7`, `DEFAULT_LIVE_DAILY_CAP_CENTS = 500   # $5/day (ADR 0006 v2 amended 2026-06-05)`.
- **At most one non-terminal (`pending` | `active`) opt-in per strategy.** Primary enforcement is the service query guard (like §4's `find_active_harness`) — no DB partial index (SQLite friendliness, matches the codebase pattern). **Defense-in-depth (review v0.2):** the duplicate check runs *inside the same transaction* as the insert (re-`SELECT` the existing non-terminal row immediately before `INSERT`, with `... FOR UPDATE` where the backend supports it — Postgres in a future hosted mode; a no-op-but-harmless on SQLite, which serializes writers anyway). This closes the check-then-insert race a pure read-before-write guard leaves open under concurrency.

### §5.2 — The live LLM gate (`app/services/llm_live_gate/`)

A new package — **separate from `eval_harness`** so invariant #12 (harness-is-paper-only) is untouched. Added to the no-LLM `ALLOWED_DIRS`.

`gate.py`:

```python
GATE_MODEL = "claude-haiku-4-5-20251001"  # same tier as §4's gate
LLM_OPT_IN_COOLDOWN_DAYS = 7
DEFAULT_LIVE_DAILY_CAP_CENTS = 500   # $5/day (ADR 0006 v2 amended 2026-06-05)

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
      6. Audit-log LLM_LIVE_DECISION with the full §5.6 payload (baseline='act',
         llm_decision, fail_safe_reason, cost_cents, prompt_hash/response_hash,
         size-guarded prompt/response, order_id if acted else null).

    Every branch above (1–6) writes exactly one LLM_LIVE_DECISION audit row with a
    distinct `fail_safe_reason` so the safety path that fired is unambiguous in audit
    (none / over_budget / missing_key / llm_error / invalid_response / acted / suppressed)."""
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

# raise_cap(...) — DEFERRED to §5b (review v0.2). Not implemented this session.
```

> **`raise-cap` is deferred to §5b — decided, not optional (review v0.2).** §5 ships the
> `daily_cap_cents` field + hard enforcement + the `$X / $5.00 today` status display, and
> nothing more on the cap. The upward-config path — `POST /strategies/{id}/llm-opt-in/raise-cap`,
> the **5th** audit action `LLM_OPT_IN_CAP_RAISED` (and its runbook scenario), and the
> raise-cap UI — all move to §5b. Rationale: §5 already touches the live order path, audit,
> a cron, the frontend, the MCP, and two CI invariants; adding a second TOTP-gated,
> audit-logged security path (raising a spend ceiling on a live LLM) widens the blast radius
> of the single most invariant-sensitive session in the project. Keep §5 to **four** audit
> actions and ship raise-cap as a small, focused follow-on.

### §5.4 — Engine integration (`app/strategies/engine.py`)

**Revised to nest inside the §4.5 wrap.** §4.5 already wraps a `LIVE` strategy's submit with `make_live_autodispatch_submit_fn` (the master-switch suppressor). §5 inserts the LLM gate **between** the deterministic submit and the §4.5 wrap, so the master switch stays **outermost**:

```python
if row.status == StrategyStatus.LIVE:
    inner = submit_order_fn  # OrderRouter.submit (innermost)
    # P6b §5: an opted-in LIVE strategy routes its live orders through the LLM
    # gate (active opt-in + version match). The gate decides act/skip per intent.
    # Global kill-switch (review v0.2): LLM_LIVE_GATE_ENABLED=false disables the
    # feature for EVERYONE without touching any llm_opt_in row — the wrap is simply
    # never applied, so live trading continues deterministically and zero Anthropic
    # calls are made. Checked at register time (re-register to pick up a flag change).
    opt_in = await find_active_opt_in(session, row.id) if settings.LLM_LIVE_GATE_ENABLED else None
    if opt_in is not None:
        inner = make_live_llm_submit_fn(
            strategy_id=row.id, user_id=row.user_id,
            real_submit=inner, session_factory=self._session_factory,
        )
    # P6b §4.5: the master-switch suppressor is OUTERMOST — an off switch returns
    # before the LLM is ever consulted (no call, no cost).
    submit_order_fn = make_live_autodispatch_submit_fn(
        strategy_id=row.id, real_submit=inner, session_factory=self._session_factory,
    )
```

Call order per order intent: master-switch check → (if on) LLM act/skip → (if act) `OrderRouter.submit`. The wrap is applied at register time, so flipping pending→active (cron), opting out, or toggling `LLM_LIVE_GATE_ENABLED` all go through a strategy **re-register** to rebuild `submit_order_fn`. ADR 0002 stays intact — the wrapped fn still calls `OrderRouter.submit`; the gate only decides whether to call it.

**Config (review v0.2):** `LLM_LIVE_GATE_ENABLED: bool` is a new `Settings` field (env `LLM_LIVE_GATE_ENABLED`), default **`false`** — the feature ships dark and is turned on deliberately, consistent with "conservative defaults, configurable extremes." It is the per-feature kill-switch *inside* the per-account master switch (`LIVE_AUTODISPATCH_ENABLED`); both must be true for any live LLM call to occur.

### §5.5 — Cooldown completion cron (`app/jobs/llm_opt_in_completion.py`)

Mirrors `activation_completion.py`: collect `pending` opt-in ids in one session → fresh session per item → Python-side elapsed check (`initiated_at + LLM_OPT_IN_COOLDOWN_DAYS <= now`) → `complete_pending_opt_in`. Registered in `lifespan.py` (alpaca block) via `scheduler.scheduler.add_job(..., minutes=15, kwargs={session_factory, engine: strategy_engine})`.

### §5.6 — Audit actions + runbook

Add to `app/audit/logger.py`: `LLM_OPT_IN_INITIATED`, `LLM_OPT_IN_ACTIVATED`, `LLM_OPT_OUT`, `LLM_LIVE_DECISION` (**four** — `LLM_OPT_IN_CAP_RAISED` is §5b). **Each gets a runbook scenario** in `docs/runbook/agent.md` (CLAUDE.md "proven costly": a new AuditAction without a runbook scenario leaves an operator stranded).

**`LLM_LIVE_DECISION` payload schema (review v0.2 — strengthened + size-guarded):**

```jsonc
{
  "strategy_id": 123, "strategy_version": "4.2", "user_id": 1,
  "baseline_decision": "act",                 // the deterministic strategy always wanted to fire
  "llm_decision": "act" | "skip" | "error" | "budget_skip_fired_deterministic",
  "fail_safe_reason": null | "over_budget" | "missing_key" | "llm_error" | "invalid_response",
  "cost_cents": 0,                            // the per-user 24h budget sum reads THIS field
  "prompt_hash": "sha256:…", "response_hash": "sha256:…",   // fast forensic compare
  "prompt": "…", "response": "…",            // full text for reconstruction (ADR line 79)
  "prompt_truncated": false, "response_truncated": false,
  "order_id": 456 | null,                     // set iff acted; null on skip/fail-safe
  "timestamp": "2026-…Z"
}
```

**Size guard (review v0.2):** `prompt`/`response` are stored verbatim up to `_MAX_AUDIT_TEXT = 16_000` chars; beyond that they are truncated with the `*_truncated` flag set, while `prompt_hash`/`response_hash` are **always** computed over the *original full text* — so forensic comparison and dedup survive truncation and a runaway prompt can't bloat an audit row (which is hash-chained and immutable, so it can never be pruned later). The budget sum reads `cost_cents`; nothing else in the hot path depends on the full text.

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
- ~~`POST /strategies/{id}/llm-opt-in/raise-cap`~~ — **deferred to §5b** (review v0.2; not implemented this session).
- Register in `app/api/v1/__init__.py`.

### §5.9 — MCP read tool

`workbench_llm_opt_in_status(strategy_id)` → `GET /strategies/{id}/llm-opt-in` (read-only). Add to `_TOOLS` (20 → 21); `test_tools.py` count assertion; `apps/mcp-workbench/CLAUDE.md` decision-tree row. Promotion to LLM-driven live is **always user-gated** — the tool description says never suggest auto-enabling.

### §5.10 — Frontend (zero-dep, react-query v5)

- `src/api/llmOptIn.ts` — `status` / `optIn` / `optOut`.
- `components/strategies/LLMOptInCard.tsx` — renders only when the strategy is LIVE with an active eval harness. States:
  - **ineligible** — shows the `EligibilityVerdict` reasons (e.g. "32/50 Mode-B trades, 18/30 days"); no opt-in control.
  - **eligible (no opt-in)** — the §4 comparison metrics + a typed-ack input (must match `RISK_ACK_PHRASE`) + TOTP input + "Opt in to LLM-driven trading" button. A prominent risk disclosure.
  - **pending** — "LLM-driven trading activates in N days" + Opt-out.
  - **active** — "LLM-gating live · $X.XX / $5.00 today" + Opt-out.
  - **Mandatory capability disclaimer (review v0.2):** every state that shows the opt-in
    control renders a prominent, non-dismissible line — **"The LLM can only *allow or
    suppress* trades your deterministic strategy already generated. It cannot create new
    trades, change size, or pick symbols."** This directly counters the most likely (and
    most dangerous) user misconception — that opting in lets an AI trade *for* them.
  - Plain `useState/useEffect` (the strategy-detail page has no QueryClientProvider — DriftCard/VariantCard pattern).
- Mounted in `pages/Strategies/Detail.tsx` next to `VariantCard`.
- Tests (vitest): the four states render; the capability disclaimer renders in every opt-in-control state; opt-in disabled until ack matches + TOTP non-empty; opt-out calls the endpoint.

### §5.11 — Fail-safe test matrix (review v0.2 — the load-bearing tests)

This is a live-order-path relaxation, so the safety branches are pinned by **named, dedicated** tests, not left implicit. The rule being protected, stated once:

> **LLM unavailable / error / over-budget / no-key → the deterministic live order still submits.
> LLM says `skip` → the order is suppressed. LLM says `act` → the order submits.**
> The LLM can only ever *subtract* a trade the strategy already produced; it can never add one.

| # | Scenario | Expected | Asserts |
|---|---|---|---|
| 1 | no opt-in row | **zero** Anthropic calls; order submits | invariant #11 holds for non-opted-in strategies |
| 2 | `pending` opt-in (cooldown not elapsed) | zero LLM calls; order submits | gating switches on only at `active` |
| 3 | `active` opt-in but `strategy_version` mismatch | zero LLM calls; order submits | the version pin fails safe to deterministic |
| 4 | `active` + over daily cap | zero LLM calls; order submits; audit `fail_safe_reason="over_budget"` | budget never halts live trading, only the consultation |
| 5 | `active` + missing Anthropic key | zero LLM calls; order submits; `fail_safe_reason="missing_key"` | credential gap → deterministic |
| 6 | `active` + LLM raises an exception | order submits; `fail_safe_reason="llm_error"` | transport/API failure → deterministic |
| 7 | `active` + LLM returns a malformed/garbage response | order **suppressed**; `fail_safe_reason="invalid_response"` | **the one asymmetry — see below** |
| 8 | `active` + LLM `act` | order submits; audit row, `order_id` set | the happy path |
| 9 | `active` + LLM `skip` | order suppressed; audit row, `order_id=null` | suppression works |
| 10 | `LLM_LIVE_GATE_ENABLED=false` (even with an `active` row) | **zero** Anthropic calls; order submits | the global kill-switch (#10) — protects cost control |

**The deliberate asymmetry (documented, not accidental):** an *infrastructure* failure (no key, exception, over budget) fails safe to **deterministic submit** — the user is asking the LLM to optionally *veto* a strategy they already trust live, so an unavailable LLM means "no veto," i.e. trade as intended. A *garbage response*, by contrast, fails to **skip** (suppress) — a malformed answer from a reachable model is treated as "could not confirm act," and the conservative direction for an unconfirmed live order is not to fire. These two defaults differ on purpose; both are pinned by the tests above so the choice can't silently drift.

---

## Manual smoke

1. Seed (or reuse) a LIVE strategy with an `active` eval harness whose `EligibilityVerdict.eligible` is forced true (≥50 Mode-B trades, ≥30 days — or a test seam).
2. `GET /strategies/{id}/llm-opt-in` → `eligible: true`, `status: none`.
3. `POST /llm-opt-in` with the wrong phrase → 400 `acknowledgment_mismatch`. With the right phrase + bad TOTP → 400 `totp_invalid`. With both correct → `pending`.
4. `GET` → `status: pending`, `seconds_remaining` ≈ 7d.
5. Force the cron (or call `complete_pending_opt_in` directly with a back-dated `initiated_at`) → `active`; strategy re-registered.
6. Submit a strategy signal → confirm an `LLM_LIVE_DECISION` audit row with full prompt/response, and that a `skip` suppresses the live order while `act` lets it through (against the paper-broker smoke account, byte-identical structurally to the deterministic path).
7. `POST /llm-opt-out` → `opted_out`; strategy re-registered without the wrap; the next signal submits deterministically.
8. Set `LLM_LIVE_GATE_ENABLED=false`, re-register, submit a signal from the opted-in strategy → **zero** Anthropic calls, order submits deterministically (the global kill-switch, even with the `active` row present).
9. **Load-bearing assertion:** with no active opt-in (or with the kill-switch off), a live strategy's order path makes **zero** Anthropic calls (invariant #11 holds for everyone not opted in); with an active opt-in and the gate enabled, exactly one LLM call per order intent, fully audit-logged.

## Walk-away discipline

**≥ 2 hours** (touches the live order path *and* the audit subsystem — the session-doc skill's two triggers for the 2-hour minimum, and the most consequential single relaxation in the codebase). Honor it especially because the change feels gated enough to be safe.

## Emergency rollback (review v0.2)

Because §5 puts an LLM in the live order path, the runbook gets an explicit kill sequence. Any **one** of the first two steps fully disables LLM gating; the rest are cleanup/verification.

1. **Flip the global kill-switch:** `LLM_LIVE_GATE_ENABLED=false` and re-register live strategies (or restart the backend). The LLM wrap is no longer applied → live trading continues deterministically, zero Anthropic calls. *(Fastest; no DB edit.)*
2. **Or flip the outer master switch:** `LIVE_AUTODISPATCH_ENABLED=false` — stops *all* auto-dispatch (deterministic included), the heavier hammer if you want live strategies fully paused.
3. **Opt-out the affected rows if needed:** `POST /strategies/{id}/llm-opt-out` for each (or set `state="opted_out"` on the `active` rows) — frictionless, no cooldown; each writes an `LLM_OPT_OUT` audit row.
4. **Re-register the affected live strategies** so the engine rebuilds `submit_order_fn` without the LLM wrap (opt-out already does this; do it explicitly if you edited rows directly).
5. **Verify:** confirm **zero** `LLM_LIVE_DECISION` rows after the flip and no Anthropic calls in the logs; `GET /strategies/{id}/llm-opt-in` shows `none`/`opted_out`. The hash-chained audit log is the source of truth that the feature is dark.

This sequence is added to `docs/runbook/agent.md` alongside the four new audit-action scenarios.

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
