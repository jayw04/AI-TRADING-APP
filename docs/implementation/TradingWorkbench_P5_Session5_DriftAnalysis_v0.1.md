# P5 Session 5 — Drift Analysis (pre-v1.0 reconciliation)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-31 |
| Purpose | Identify drift between `TradingWorkbench_P5_Session5_v0.1.md` (dated 2026-05-23, 2,484 lines) and the codebase state actually shipped by Sessions 1, 2, 3, 4 — before committing to a Session 5 v1.0 promotion. |
| Sources read | Session 5 v0.1 (selected sections — header, §5.1, §5.2 open, §5.4 BuyingPowerChecker, §5.5 RiskEngine integration), Session 2 v1.0, Session Zero Results, Session 2 Results, Session 3 Results, Session 4 Results (updated; Session 4 shipped at `b5b37da` tag `p5-session4-complete`), ADRs 0006v2 / 0007 / 0008, Session 4 v1.0 (for promotion-format reference) |
| Audience | Pre-execution review. Output of this doc determines whether Session 5 needs a small promotion (matching Session 4's pattern) or substantive rework. |
| Recommendation | **Small promotion with two design decisions folded into Notes & Gotchas.** v0.1 is largely sound; the drift is mostly path/tooling corrections plus three naming-level integration items that would prevent the v0.1 code from compiling against current `main`, plus two real design decisions worth being explicit about. No fundamental design rethink needed. |

---

## What Session 5 v0.1 plans to do

In one paragraph: live-mode risk hardening. New schema (`accounts.circuit_breaker_tripped_at`, `risk_limits.max_orders_per_day`, `StrategyStatus.HALTED`). Three new services: `CircuitBreakerService` (daily-loss hard halt per ADR 0004), `PdtAnalyzer` (day-trade counting for the PDT warning surface), `BuyingPowerChecker` (pre-trade buying-power check for LIVE only, via adapter `get_account()`). RiskEngine extended with the three new gates plus a per-day order cap. Four new endpoints under `/api/v1/accounts/{id}/risk-state`, `.../risk/reset-circuit-breaker`, `/api/v1/risk-limits` GET and PUT. Three new audit actions. Frontend: PDT warning banner, circuit breaker state indicator, Risk Limits page, reset modal with typed account-name confirmation. ADR 0004 written. Manual smoke covers paper byte-identical chain + new error paths. Single PR ending at `git tag p5-session5-complete`.

Scope is well-defined: 13 subsections (§5.1 through §5.13), ~2,484 lines of plan, multiple new modules + extensive frontend work.

**Load-bearing assertion** (v0.1's own framing): paper smoke from P1-§4 still produces byte-identical order chains. New code paths fire only under conditions paper accounts don't reach (LIVE-scoped limits, circuit breaker in live mode, buying-power check skipped for paper).

---

## Verified-still-true (no change needed)

These are facts the v0.1 assumes that Sessions 1, 2, 3, 4 confirmed remain accurate:

1. **`risk_limits` table exists with mode-scoped rows.** Per P1 §5 (shipped, Session 1 of P5 may have extended it). v0.1's §5.1.2 adding `max_orders_per_day` is an additive column change.

2. **`accounts` table has a `mode` column.** Session 2 v1.0 confirms — used as `account.mode` for adapter selection (the enum value is `AccountMode.paper` or `AccountMode.live`).

3. **`audit_log` accepts new action enum values without schema change.** Per P1 design, AuditAction is a string column with non-native enum. v0.1's three new actions (`CIRCUIT_BREAKER_TRIPPED`, `CIRCUIT_BREAKER_RESET`, `RISK_LIMITS_UPDATED`) require no DDL.

4. **`StrategyStatus` is a string column with non-native enum.** v0.1 §5.1.3 correctly notes this — adding `HALTED` requires no migration. (See drift item below about the StrEnum convention.)

5. **`RiskEngine` is the central pre-submission gate.** Session 4 Results confirms the order path is unchanged from Session 2's structure — risk engine called between credential resolution and broker submission. v0.1 §5.5's integration approach is sound.

6. **`BrokerRegistry.get(account_id)` returns an adapter or None.** Session 2 v1.0 §2.4 establishes this exactly. v0.1 §5.4's `BuyingPowerChecker` correctly handles the None case (fail-open with "no broker adapter" reason).

7. **Audit logging follows the established pattern.** `AuditLogger` is the API; new action values fit cleanly. v0.1 §5.7's audit additions match the convention.

8. **`AuditAction` and `AuditActorType` enums.** v0.1 §5.2 imports these correctly. Already present per P1 / P5 §1.

9. **The ADR 0004 framing is sound.** v0.1 §5.10's "daily-loss circuit breaker as hard halt" rationale is consistent with the trust architecture in the product overview (Section 11) and ADR 0002's "single gate, no bypass" pattern. ADR can be written without revision.

10. **Threat model is consistent.** v0.1's "Real-money posture (recap)" — "failure modes that could cost money default to halting" — is the same posture the rest of the platform commits to. No change needed.

---

## Verified-different (corrections needed in v1.0)

These are facts that drifted between when v0.1 was drafted (2026-05-23) and what Sessions 1, 2, 3, 4 actually shipped:

### Drift 1 — Predecessor reference is stale

v0.1 says "Predecessor: *TradingWorkbench_P5_Session4_v0.1.md*". Session 4 was followed against v1.0 (`TradingWorkbench_P5_Session4_v1.0.md`), shipped as PR #40 / `b5b37da` / tag `p5-session4-complete`. Session 5 v1.0 should reference the v1.0 doc as predecessor, plus the Session 4 Results document for the deliberate-deviations context.

### Drift 2 — Path corrections from Session Zero Results

v0.1 uses Linux paths consistently (`cd ~/code/AI-TRADING-APP`). Windows environment is `C:\LLM-RAG-APP\ai-trading-app`. Session 2 v1.0 and Session 4 v1.0 already use the Windows paths. Session 5 v1.0 needs the same correction throughout, primarily in Prerequisites Check, §5.4 testing procedures, §5.11 manual smoke, and §5.13 commit/PR/tag commands.

### Drift 3 — Tooling: `uv run` → venv python

v0.1 uses `uv run pytest`, `uv run alembic`, `uv run --directory apps/backend python scripts/check_*` consistently. Session 2 v1.0's "Why v0.2" note #7 established the correction: `uv` is not on PATH; use `apps\backend\.venv\Scripts\python.exe`. Pytest needs `--cov-branch` or the risk gate falsely reports 0.000.

Session 5's coverage gates (§5.9 explicitly runs `check_risk_coverage.py`) need the `--cov-branch` flag.

### Drift 4 — `check_adr0002.sh` referenced in Prerequisites

v0.1 §"Prerequisites Check" includes `bash apps/backend/scripts/check_adr0002.sh` in the eight-invariant list. Session Zero Results corrected this: **`check_adr0002.sh` does not exist**. ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + the `_router_token` tripwire (Session 2 v1.0).

The accurate eight-invariant inventory after Session 4 ships:
- `check_strategy_isolation.sh`
- `check_mcp_readonly.sh`
- `check_no_llm_in_order_path.sh`
- `check_risk_coverage.py`
- `check_p2_coverage.py`
- `check_p3_coverage.py`
- `check_broker_isolation.sh` (Session 2 §2.6)
- `check_no_env_credentials.sh` (Session 4 §4.12)

Plus `tests/test_adr_0002_invariant.py` as a separate pytest invariant. Session 5 does not add a new CI invariant; the count stays at eight.

### Drift 5 — `BrokerMode` enum does not exist; use `AccountMode`

This is the most consequential naming drift. v0.1 imports `from app.db.enums import BrokerMode` in `app/risk/buying_power.py` (§5.4) and `app/risk/engine.py` (§5.5). Session Zero Results §3 confirmed: **`BrokerMode` is absent** (P5 §1 didn't introduce it; the existing enum is `AccountMode`).

Specific corrections needed in Session 5 v1.0:
- `from app.db.enums import BrokerMode` → `from app.db.enums import AccountMode`
- `account.mode == BrokerMode.LIVE` → `account.mode == AccountMode.live`
- All similar comparison sites in §5.4 `BuyingPowerChecker.check()`
- All similar comparison sites in §5.5 RiskEngine integration
- Test files in §5.9 that mock or assert on `BrokerMode.LIVE` / `BrokerMode.PAPER`

This is roughly a dozen sites across the session. Mechanical correction, but cannot be skipped — the v0.1 code does not compile against current `main`.

### Drift 6 — `BrokerAccountSnapshot` does not exist; adapter returns `dict[str, Any]`

v0.1 §5.4 has `from app.brokers.base import BrokerAccountSnapshot` and treats the return of `adapter.get_account()` as a typed object with `snap.buying_power`.

Session 2 v1.0 §2.0 explicitly rejected the typed-DTO Protocol approach and shipped the adapter with `get_account() -> dict[str, Any]` (sync, dict return, no DTOs). The Session 2 Results confirms this in the as-built section.

Specific corrections in Session 5 v1.0 §5.4:
- Drop the `BrokerAccountSnapshot` import
- `snap.buying_power` → `Decimal(str(snap.get("buying_power", "0")))` or similar dict access. Account data shape from Alpaca adapter has `buying_power` as a string field that needs coercion.
- Verify what other fields `BuyingPowerChecker` reads — `account_equity`, `cash`, or other — and access them the same way

Worth a note in the v1.0 doc: if the day comes when the platform wants a typed account snapshot, the right path is a follow-up PR with its own byte-identical proof (mirroring Session 2's reasoning) — not bundled into Session 5.

### Drift 7 — `adapter.get_account()` is sync, not async

Same root cause as Drift 6. v0.1 §5.4 writes `snap = await adapter.get_account()`. Session 2 v1.0 shipped the adapter as sync.

Correction: drop the `await` on `get_account()`. The `BuyingPowerChecker.check()` method itself can stay async (it does async work elsewhere, e.g. interacting with `session_factory`), but the specific call to the adapter is synchronous.

Same correction applies anywhere else in Session 5 that calls a broker adapter read method (`get_positions`, etc.). Mutator calls (`submit_order`, `cancel_order`, `replace_order`) are sync too, but they require `_router_token` — and Session 5 should not be calling them in any case (see Drift 9).

### Drift 8 — `BrokerRegistry.refresh` is now async (Session 4 effect)

Session 4 v1.0 §4.6 made `BrokerRegistry._construct/_try_construct/load_all/refresh` all async (because `credentials_for_mode()` became async). Session 5 v0.1's §5.6 "POST `/api/v1/risk/reset-circuit-breaker`" endpoint may call `broker_registry.refresh(account.id)` if circuit-breaker reset should also refresh the adapter — but actually, on reflection, reset doesn't change credentials, so there's no need to refresh.

The actual integration point: v0.1's §5.2 `CircuitBreakerService.trip()` HALTS strategies. It does **not** modify adapter state. Per Session 4's pattern, the adapter is constructed at boot and only refreshed on credential changes or account creation. Session 5 doesn't need to touch `BrokerRegistry.refresh()`.

Worth a one-paragraph note in Session 5 v1.0: explicitly confirm that circuit-breaker trip/reset does NOT call `broker_registry.refresh()` — the adapter is fine to remain constructed; what changes is whether the OrderRouter forwards orders to it. The `RiskEngine` is the gate, not the adapter.

### Drift 9 — `_router_token` discipline must not be weakened

Session 2 v1.0's load-bearing invariant: broker mutators (`submit_order` / `cancel_order` / `replace_order`) are gated by `_router_token`, only `OrderRouter` passes it.

Session 5 §5.4 `BuyingPowerChecker` calls `adapter.get_account()` — a *read*, not a mutator. No `_router_token` required for reads. This is in-policy.

Session 5 §5.2 `CircuitBreakerService.trip()` halts strategies and rejects pending orders — it does NOT call adapter methods directly. The order rejection happens by raising `CircuitBreakerError` from `RiskEngine.check()` *before* the router calls the adapter. In-policy.

But: v1.0 should add a one-paragraph note in the Real-money posture section explicitly confirming that the new risk gates only call read methods on the adapter, never mutators. Matches Session 4 v1.0's pattern (Notes & Gotchas #15).

### Drift 10 — SQLite datetime coercion needed in multiple sites

This is the most consequential architectural drift. Session 3 added `_aware()` to `stub.py`; Session 4 added `_ensure_aware()` to `credential_store.py`. Both for the same reason: **SQLite returns timezone-aware datetimes as naive**, breaking comparisons against `datetime.now(timezone.utc)`.

Session 5 has heavy datetime work across three modules:

- **§5.2 `CircuitBreakerService`**: compares `accounts.circuit_breaker_tripped_at` against `now()` in `check()`. Computes `realized_pnl_today` from fills where `created_at >= market_open_today` — the cutoff is computed in Python (aware) but the fill rows return naive datetimes from SQLite.
- **§5.3 `PdtAnalyzer`**: queries fills for the last 5 trading days in US/Eastern time. Heavy datetime arithmetic, all subject to the same gotcha.
- **§5.5 RiskEngine integration**: per-day order cap filters orders where `Order.created_at >= cutoff`. SQLite-side filtering by naive datetime works (SQLite ignores tzinfo), but if any logic on the Python side compares the returned row's `created_at` against `now()`, the comparison breaks.

**Real risk**: a circuit-breaker check that should trip doesn't trip, because the date-window filter returned no fills due to a tz-comparison mismatch. This is a silent-correctness bug, not a crash. **Worth catching in v1.0.**

Two options for how to address this in v1.0:

- **(a) Inline coercion in each module** — copy the `_ensure_aware()` pattern from `credential_store.py` into `circuit_breaker.py`, `pdt_analyzer.py`, and the relevant function in `engine.py`. Modest duplication (~15 lines per copy).
- **(b) Extract a shared helper** — create `app/utils/time.py::ensure_aware(dt)` and have all four sites (auth/stub.py, credential_store.py, circuit_breaker.py, pdt_analyzer.py, engine.py — five sites total) call it.

Option (b) is the right answer if Session 5 is the third site to need this helper. With three sites now (and Session 6+ likely to hit it again), extraction is justified. **Worth being explicit about as a design decision** (see "Open question" below).

### Drift 11 — Migration pattern: acquire required state before DDL

Session 4 Results documents a deliberate deviation from the v1.0 sketch: "Migration acquires the master key *before* any DDL. The v1.0 sketch created the table first, then checked the key. Moving `_fernet()` to the top of `upgrade()`/`downgrade()` means a missing key aborts with **zero schema changes** — eliminating the half-migrated-DB risk Gotcha #2 warns about."

Session 5 §5.1.4 has its own migration: adds `circuit_breaker_tripped_at` and `max_orders_per_day` columns, then **runs a data migration to seed the LIVE risk_limits row** for user_id=1. v0.1's sketch shows the data migration after the column adds.

Session 5 v1.0 should follow Session 4's better pattern: any precondition checks (does user_id=1 exist? does a LIVE risk_limits row already exist?) happen *before* DDL. If a precondition fails, the migration aborts with no schema changes.

For Session 5 specifically, the precondition is mild — `user_id=1` either exists (P5 §3 created it) or doesn't (fresh install). Both branches are fine; the data migration just becomes a no-op if user_id=1 isn't there. But the pattern matters.

### Drift 12 — Frontend wiring: `apiFetch` + React Query, router via `app/api/v1/__init__.py`

Session 4 Results documents two frontend/router pattern corrections:
- "Credentials router wired via the central `app/api/v1/__init__.py`" (not `main.py`)
- "Frontend uses `apiFetch` + React Query, not the doc's `apiClient.get/put` sketch"

Session 5 v0.1's §5.6 adds four new endpoints (`GET /accounts/{id}/risk-state`, `POST /accounts/{id}/risk/reset-circuit-breaker`, `GET /risk-limits`, `PUT /risk-limits/{id}`) and §5.8 adds frontend components. Same corrections apply: wire the new router through `app/api/v1/__init__.py`; frontend uses `apiFetch` + React Query.

This is a stylistic correction. The functional behavior is the same; the code shape needs to match what's actually in the codebase.

### Drift 13 — `StrategyStatus` follows StrEnum convention

Session 4 Results documents: "`CredentialKind` is a `StrEnum`, not `(str, Enum)`. Matches the project's `AccountMode` convention and satisfies ruff `UP042`."

Session 5 §5.1.3 adds `StrategyStatus.HALTED` to an existing `StrategyStatus` enum. If `StrategyStatus` is currently declared as `class StrategyStatus(str, Enum)`, v1.0 should follow the project convention and migrate it to `class StrategyStatus(StrEnum)` — or leave the existing declaration alone and just add the new value (matching whatever the file currently does).

Worth a verification step: read `app/db/enums.py` to see what convention `StrategyStatus` currently follows, then match. Don't change the convention if not necessary; do follow it for any *new* enums added.

---

## Items needing verification against current code

These are things I can't confirm without reading `main`. Listed here so the v1.0 promotion can verify each:

1. **Does `app/db/enums.py` currently declare `StrategyStatus` as `(str, Enum)` or `StrEnum`?** Affects Drift 13.

2. **Does `risk_limits` table currently have any LIVE-scoped rows?** Affects Drift 11. If the column data migration needs to insert vs upsert, the SQL changes.

3. **What does `BrokerAdapter.get_account()` actually return in dict form?** The keys (`buying_power`, `cash`, `account_equity`, etc.) need to match what the Alpaca adapter actually produces. Session 2 v1.0 confirms `dict[str, Any]` return type but doesn't enumerate keys. Verify-during-execution.

4. **Are there any callers of `BrokerMode.LIVE` or `BrokerMode.PAPER` elsewhere in the codebase that the v1.0 promotion needs to update?** Drift 5 fixes the Session 5 v0.1 references; if other shipped code uses `BrokerMode`, those need fixing too. Quick grep before execution: `grep -RE "BrokerMode" apps/backend/app`.

5. **Does the `bar_cache` reference in §5.4's `BuyingPowerChecker.__init__(*, broker_registry, bar_cache=None)` correspond to anything that exists?** P2/P3 may have shipped a bar cache; verify the import path. If absent, the parameter can be removed entirely (Session 5 §5.4's `_estimate_worst_case_notional` is the only caller, and it's a price-estimation utility).

6. **Is the existing `RiskEngine.__init__` signature compatible with the `(*, session_factory, broker_registry, bar_cache=None, **kwargs)` shape v0.1 §5.5 uses?** If not, the integration is a small refactor of the existing class rather than an extension.

7. **What audit-log payload shape is conventional?** v0.1 §5.7 documents new action values but doesn't pin the payload schema. Verify against existing audit calls in `app/services/audit_log.py`.

8. **Does `app/api/v1/__init__.py` exist as the central router registry?** Per Session 4 Results — but worth confirming the actual file path before §5.6 reorganizes.

---

## ADR considerations

Three ADRs landed after Session 5 v0.1 was drafted. Quick check on each:

**ADR 0004 (daily-loss circuit breaker):** Written *by* Session 5 §5.10. Not "applies to" — Session 5 is the source. No drift.

**ADR 0005 (24-hour activation cooldown):** Session 5 doesn't activate strategies; it halts them. The cooldown is for going LIVE (P5 §7), not for going IDLE → HALTED. Not applicable.

**ADR 0006 v2 (LLM in order path gated):** Not applicable. Session 5 doesn't touch the LLM path. The new risk gates are deterministic.

**ADR 0007 (Auto-promotion of LLM-proposed strategy updates):** Not applicable. Session 5 doesn't touch strategy auto-promotion.

**ADR 0008 (Flexibility principle for AI tooling absorption):** Mildly applicable. The new `risk_limits` columns and the new `accounts.circuit_breaker_tripped_at` column are additive; future risk-related capabilities (e.g., per-strategy gross exposure caps mentioned in v0.1's "Out of scope") can add columns without rework. Worth one sentence in Notes & Gotchas to acknowledge.

---

## Recommendation

**Small promotion to v1.0 with two design decisions folded into Notes & Gotchas. Not substantive rework.**

Reasoning:
- The core design (three new risk services + RiskEngine integration + schema additions + ADR 0004) is sound and matches the trust architecture the platform commits to.
- The 13 drift items above are mostly path/tooling corrections (Drifts 1-4) plus naming-level corrections that would prevent compilation against current `main` (Drifts 5, 6, 7) plus integration-with-shipped-Sessions clarifications (Drifts 8, 9, 11, 12, 13) plus the one architecturally meaningful item (Drift 10 — SQLite datetime coercion).
- None of these invalidate the design. They're calibrations against what Sessions 1-4 actually shipped.
- Drift 10 (datetime coercion) deserves a design decision: extract a shared helper to `app/utils/time.py` vs inline copies in three modules. **Recommend extraction** — Session 5 is the third site to need this; the duplication cost across five sites total (stub.py, credential_store.py, circuit_breaker.py, pdt_analyzer.py, engine.py) outweighs the cost of a shared file.

**Estimated v1.0 size: 1,600-1,800 lines.**

For comparison:
- Session 5 v0.1 is 2,484 lines (about 30% larger than Session 4 v0.1 was)
- Session 4 v0.1 → v1.0 was 82 KB → 71 KB (13% reduction)
- Same ratio applied to Session 5: ~2,150 lines, but Session 5 has more new substance (three services + ADR 0004 inline + more frontend), so 1,600-1,800 is realistic if v1.0 tightens speculation similarly

**Sections needing real attention during v1.0 promotion:**
- Header table (predecessor reference; scope wording for `_router_token` non-modification)
- New "Why v1.0" section near the top documenting the 13 drift items
- Prerequisites Check (path corrections, tooling, invariant count)
- §5.1 Schema Changes (StrEnum convention check; migration pattern per Drift 11)
- §5.2 CircuitBreakerService (datetime coercion via shared helper)
- §5.3 PdtAnalyzer (datetime coercion via shared helper)
- §5.4 BuyingPowerChecker (the big one — `BrokerMode` → `AccountMode`, drop `BrokerAccountSnapshot` import, dict access for adapter return, drop `await` on `get_account()`, possibly drop `bar_cache` parameter)
- §5.5 RiskEngine Integration (`BrokerMode` → `AccountMode`, datetime coercion for the order-count cutoff)
- §5.6 Endpoints (router wired through `app/api/v1/__init__.py`)
- §5.8 Frontend (`apiFetch` + React Query, not `apiClient`)
- §5.9 Tests (`BrokerMode` → `AccountMode` everywhere, coverage runs use venv python + `--cov-branch`)
- §5.10 ADR 0004 (no change needed — Session 5 is the source)
- §5.11 Manual Smoke (live runtime gates deferred per Norton/Docker pattern)
- §5.13 Commit list (Windows paths, no `uv run`)
- Notes & Gotchas section (add the two design-decision items: shared `ensure_aware()` helper, circuit-breaker doesn't touch adapter state)

**Sections that need minimal touch:**
- §5.7 Audit Actions + WS Routing (additive enum values, fits established pattern)
- §5.10 ADR 0004 (written here for the first time; nothing to reconcile)
- §5.12 Runbook (writing a new runbook section; nothing prior to reconcile)

---

## Open question for the v1.0 author

**Should the v1.0 design decisions be a §5.0 section, or folded into Notes & Gotchas?**

Two real decisions exist:

- **Decision 1: Shared `ensure_aware()` helper at `app/utils/time.py`** vs inline copies in `circuit_breaker.py`, `pdt_analyzer.py`, `engine.py`. The shared-helper choice means refactoring `stub.py::_aware()` and `credential_store.py::_ensure_aware()` to import from the new location — a small but real cross-file change. Could be deferred to a future hygiene PR if Session 5 wants to stay focused; my recommendation is to do it in Session 5 because there's already 3-4 sites needing the helper and adding the centralized version is small.

- **Decision 2: BuyingPowerChecker behavior when adapter credentials have been revoked between adapter construction and check time.** Three options: (a) fail-open (proceed without check, log warning) — matches Session 5 v0.1's "broker unreachable" handling; (b) fail-closed (reject the order) — safer but unfamiliar; (c) trip the circuit breaker — escalates to the operator. v0.1 implicitly chose (a) via the generic exception handler. Worth being explicit.

Both decisions are smaller than Session 2's "reject async DTOs entirely" decision. Neither rises to needing its own §5.0 design section.

**Recommendation: fold both into Notes & Gotchas**, matching Session 4 v1.0's pattern. Decision 1 becomes Notes & Gotchas #N: "Datetime coercion lives in `app/utils/time.py::ensure_aware()`, shared across stub.py, credential_store.py, circuit_breaker.py, pdt_analyzer.py, engine.py." Decision 2 becomes Notes & Gotchas #M: "BuyingPowerChecker fails open on adapter errors (matches v0.1 §5.4's generic exception handling). A future hardening pass could escalate to fail-closed or breaker-trip; out of §5 scope."

---

## What changes if Session 4 turns out to need rework

Worth flagging: Session 4 was merged "without the ≥1h walk-away" per its Results punch list. The post-merge CI confirmation on `b5b37da` is still pending. If CI surfaced something that requires a Session 4 patch-forward (or unlikely but possible revert), Session 5's foundation moves slightly.

For now, assume Session 4 holds. If a Session 4 patch lands before Session 5 begins, the v1.0 promotion picks up any final adjustments at that time. No reason to delay the drift analysis on that risk.

---

## Summary

Session 5 v0.1 is mostly right. The core design — three new risk services, RiskEngine integration, schema additions, ADR 0004 — holds up against what Sessions 1, 2, 3, 4 actually shipped. The 13 drift items are calibrations, not redesigns. The most consequential ones are the `BrokerMode` → `AccountMode` rename, the `BrokerAccountSnapshot` removal + sync `get_account()` (a single root cause: Session 2 rejected async DTOs), and the SQLite datetime coercion that affects three of the new modules.

Two real design decisions worth being explicit about in v1.0:
1. Shared `ensure_aware()` helper at `app/utils/time.py` (extract the pattern that now appears in three sites)
2. BuyingPowerChecker fail-open posture on adapter errors

Both can fold into Notes & Gotchas. Neither warrants a §5.0 design decision section.

**Recommendation: proceed with v1.0 promotion.** Estimated 1,600-1,800 lines, similar size to Session 4 v1.0 (1,481) but larger because Session 5 has more substance (three new services + ADR 0004 inline + more frontend work). The v0.1 → v1.0 transformation tightens speculation and applies the 13 drift corrections; the architectural design is preserved.

*End of P5 Session 5 drift analysis v0.1. Output of this document informs whether to proceed with v1.0 promotion (recommended) or revisit the design.*
