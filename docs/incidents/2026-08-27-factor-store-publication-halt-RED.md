# RED — Factor store publication halt, live SEP frozen at 2026-08-21

| Field | Value |
|---|---|
| Opened | 2026-08-27 |
| Severity | RED — the live factor store cannot publish; every factor book ranks on frozen data if activated |
| Status | **Administrative hold ACTIVE; mechanical interlock NOT YET DEPLOYED** |
| Systems | `workbench-factor-refresh.service` (06:00 ET weekdays), `workbench-factor-freshness.service` (07:00 ET weekdays), `factor_data.duckdb` on `ec2-paper` |
| Affected strategies | 7 (sector-rotation, acct 5), 8 (low-volatility, acct 6), 9 (combined-book) — all IDLE |
| Repair | ADR 0056; this document is the closure gate for that PR |

---

## Current exposure — stated precisely

**Administrative hold ACTIVE; mechanical interlock NOT YET DEPLOYED.**

Strategies 7/8/9 are presently IDLE, so no scheduled factor rebalance is executing. Until the
Tier-3 fail-closed interlock is deployed, prevention of `IDLE → PAPER/LIVE` activation depends
on observance of this governing hold.

That is the whole of the current protection, and it is worth being exact about why the word
"closed" does not apply. The hold is a *governing instruction*, not a code path. Nothing in the
deployed runtime refuses an activation today; the refusal exists in this PR and has not
shipped. A second operator, an automation, or a scheduler completing a `PENDING_LIVE` cooldown
would not encounter it.

Existing positions are untouched and are to remain so. RED blocks new activation, ranking and
rebalance; **it is not a liquidation trigger.** Account 6 (IDLE, 34 positions, ~$97K) is
investigate-only.

---

## What happened

`workbench-factor-refresh.service` has aborted on four consecutive mornings — 2026-08-25, 08-26,
08-27 and 08-28 — with:

```
VERIFY_FAILED: ... UNEXPLAINED: ['WBS']
```

Staging is fresh (`2026-08-27` as of the 08-28 run, 1254 tickers). The live store is not: it is
frozen at SEP `2026-08-21` — **five trading days stale**, the store file dated 2026-08-24. The abort is **correct behaviour**: verification is fail-closed and a bad refresh
must never reach the live book. Nothing executed incorrectly. What failed is that the condition
was unresolvable without a human, undiagnosable from the message, and on a fuse.

## Diagnosis

### ⛔ The first diagnosis was wrong, and the correction matters

The initial call was "the producer and the watchdog are two diverged implementations of the
same adjudication policy." **They are not.** Both already consume the shared
`apps/backend/scripts/factor_adjudication.py` (ADR 0051, merged and deployed):
`factor_refresh.py:512-545` imports it; `factor-freshness.sh:199` resolves and pipes its
source; `tests/deploy/test_factor_freshness_shared_adjudication.py` pins the arrangement.

The error came from grepping `factor-refresh.sh` for a Python import. The wrapper delegates to
`factor_refresh.py`, which imports the adjudicator and re-exports it — **a grep of the wrapper
could never have found it.** Acting on that diagnosis would have produced a PR that re-unified
two things already unified and repaired nothing.

### The producer and the watchdog disagreed — correctly

* producer (`factor_refresh.py verify`) → **staging** store, frontier `08-26` → WBS stale → `UNEXPLAINED`
* watchdog (`factor-freshness.sh:153` `STORE_PATH`) → **live** store, frontier `08-21` → WBS not stale → `unexplained_count: 0`

`classify_stale_symbol` is pure, with `cutoff = frontier - max_lag_days`. Different stores ⇒
different verdicts, **by design**. The readiness artifact's `unexplained_count: 0` is a true
statement about the frozen live store, not a contradiction. Nothing in either message said so,
which is why it read as one.

### The actual defect — the artifact had no writer

`_factor_exhaustion_evidence.json` is a **static, hand-built file**, generated
`2026-08-11T19:30:57Z`, holding 11 records (`DBC EA EEM EFA GLD IEF KMLM SATS SPY TLT UUP`).
`WBS` is absent. Re-verified independently against `origin/main`: `git grep` finds **no writer
anywhere** — `factor_adjudication.py`, `factor_refresh.py`, `factor-freshness.sh` and the tests
all only read it.

Any name going attributable-stale after 08-11 has no record, adjudicates
`FAILED_OR_UNEXPLAINED`, and halts publication until a human regenerates the file. `EA` is in
the artifact because a human added it on 2026-08-17. `WBS` is the next name. There will be
another.

### 🚨 The dated cliff — 2026-09-10

`MAX_EVIDENCE_AGE_DAYS = 30`, and all 11 records carry the **same** observation timestamp, so
they expire **together**. On 2026-09-10 the refresh begins failing on eleven names rather than
one. Any repair that does not regenerate evidence has a two-week fuse. Confirmed by running the
shared expiry function against the artifact's date: 14 days remaining as of 2026-08-27.

### The second defect — the veto is not armed

Separately, and not caused by the above: the factor-readiness interlock **never ran** for
strategies 7 and 8 in production. On 2026-08-10 both books logged
`strategy_factor_classification_unavailable` and dispatched 52 filled orders. AST introspection
of the loaded instance failed, so classification returned "not factor-consuming" and the gate
returned `True` before evaluating anything. CI was green because its safety-net test classified
template *files*, which parse fine.

⚠ This was **not re-verified** in this session. It is carried forward from the 2026-08-10
observation and is repaired on that basis; the repair does not depend on the defect still being
present, because declaring classification is correct either way.

---

## Repair — ADR 0056

1. **`scripts/factor_evidence.py`** — regenerates the artifact from observations on every
   refresh, between ingest and verify. Decides nothing; the verifier re-derives every verdict.
2. **Diagnosis in the shared module** — `diagnose_unexplained` and `evidence_expiry`, consumed
   by both the verifier and the watchdog, so one condition gets one vocabulary.
3. **`Strategy.requires_factor_readiness`** — declared classification; AST inference demoted to
   a fallback. Every shipped template declares.
4. **Activation interlock** — `engine.register` (IDLE → PAPER/LIVE) and
   `ActivationService.complete_pending` (PENDING_LIVE → LIVE) both refuse while readiness is
   not PASS. Entry only; no liquidation path.
5. **`check_no_factor_symbol_special_cases.py`** — CI invariant; no ticker literal in the path.
6. **Every execution seam gated, structurally.** Review challenged the claim that "an
   already-registered strategy short-circuits before the check" is sufficient. It was not.
   Enumerating the engine's seams from the AST found **two ungated `on_bar`-class paths**:
   `_fire_all_event_strategies` (the fallback tick for event-scheduled strategies, calling the
   same `on_bar` that computes the book) and `_on_signal_event`. Neither could dispatch a
   factor book *today* — all six books run on cron and implement only `on_bar` — so the
   invariant held because of what the STRATEGIES contain, not because of anything the ENGINE
   guarantees. Both are now gated. `on_fill` remains deliberately ungated with its reasoning
   recorded: it reports an order that has already filled, so blocking it prevents nothing and
   would desynchronise the strategy's book from the account.

   The pre-existing `test_gate_runs_at_every_dispatch_site` asserted a hardcoded count of
   **3** and a docstring stating "three dispatch paths exist". That number is what made the
   tree look complete. It is now derived from a named list, and `test_every_execution_seam_is_gated`
   enumerates seams from the AST so a newly-added hook fails the build until it is classified.

7. **Unloadable class fails CLOSED at the LIVE completion.** Review asked for proof that a
   strategy whose class cannot be loaded could not use `_factor_readiness_for`'s `None` return
   to transition state. **The proof failed.** `complete_pending` never consults the loader or
   the engine — it reads the row, checks the cooldown and the hold, and writes
   `StrategyStatus.LIVE` itself — so the "the engine will refuse it separately" justification
   did not apply to the one caller that mattered. An unloadable strategy took the "not a factor
   consumer" branch and promoted to LIVE with the interlock never evaluated.

   Exposure was bounded (an unloadable strategy cannot dispatch, so no factor book could be
   computed), but the safety rested on a refusal by a caller this path does not have.
   `_factor_readiness_for` now returns a distinct `CLASSIFICATION_UNAVAILABLE` sentinel — its
   own type, not `None` and not a string — and `complete_pending` refuses, leaving the strategy
   PENDING_LIVE. Two pre-existing fixtures used non-existent code paths (`x.py`, `s.py`) and
   were asserting a promotion production would now refuse; both point at a real loadable
   non-factor template.

### ⚠ What the repair does NOT do

**⛔ CORRECTED 2026-08-28 — this section previously said the repair "does not resolve `WBS`".**
That rested on the premise that `WBS` was a *coverage regression* — a name with provider history
still current at the alternate source. **Production evidence refutes the premise.** Record:
`docs/incidents/2026-08-28-WBS-disposition.md`.

`WBS` is an **exhaustion** case. Read-only from the live store and a live alternate-source probe on
2026-08-28: Sharadar and Alpaca both end at `2026-08-19`; the store's `actions` table carries
`delisted` and `acquisitionby` → `SAN` on that date; control `AAPL` and acquirer `SAN` are current
to `2026-08-27`; there is no holding, open order or registration. Webster Financial was acquired by
Banco Santander and ceased trading. Its production failure diagnosed **`EVIDENCE_ABSENT`** — no
record existed in the `2026-08-11` artifact at all — not `EVIDENCE_PRESENT_REFUSED`. Regeneration
**is** the governed convergence mechanism for `WBS`, and this PR supplies it.

**What the repair still does not do: it does not itself CLEAR `WBS` until regeneration runs in
production.** The classification is resolved; the operational gate is not.
`scripts/factor_evidence.py` is **not yet deployed**, so the production writer → artifact →
verifier path has never executed. Until it does, `WBS-DISPOSITION` remains a named precondition of
the closure gate below. The expected verdict — `PROVIDER_EXHAUSTED`, "ceased trading: provider last
2026-08-19, alpaca last 2026-08-19, control AAPL current to 2026-08-27" — has been reproduced by
running `classify_stale_symbol` against production-observed values, which is classification proof,
not operational closure proof.

The coverage-regression shape remains real: a name current at the alternate source is still refused
with "coverage regression, not exhaustion", and regeneration still would not clear it. It is
exercised by a synthetic name in the regression pack rather than by `WBS`.

The 2026-09-10 cliff is removed regardless of `WBS`.

---

## Closure gate

**⛔ A merge does not close this incident.** The PR remains **NOT DEPLOYMENT-CLOSED** until
production supplies the following evidence. Each item is observed from live state, not
inferred, and not pre-filled.

| # | Gate | Evidence required |
|---|---|---|
| 0A | `WBS` classification | **RESOLVED 2026-08-28 — `PROVIDER_EXHAUSTED`.** Production evidence establishes that `WBS` ceased trading on 2026-08-19 following acquisition by `SAN` and delisting. Provider and alternate source terminate at the same frontier; the controls remain current; there are no holdings, orders or registrations. Record: `docs/incidents/2026-08-28-WBS-disposition.md`. |
| 0B | Governed evidence convergence | **NOT YET OBSERVED IN PRODUCTION.** `scripts/factor_evidence.py` regenerates the missing record; the verifier must independently derive `PROVIDER_EXHAUSTED` from it. No ticker-specific exception is authorized. **A precondition of gates 1–6, not a product of this PR.** ⚠ This does not count regeneration as passed before deployment — the expected verdict has been reproduced against production-observed values, but the production writer → artifact → verifier path remains unexecuted. |
| 1 | Producer verification PASS | `VERIFY_OK` in `journalctl -u workbench-factor-refresh` |
| 2 | Successful atomic promotion | staging→live swap completed; `factor_data.prev.duckdb` retained; sealed artifact advanced |
| 3 | Live SEP advances | live `sep_max` moves from `2026-08-21` to the expected fresh date, read from the live store |
| 4 | Producer / watchdog agreement | both adjudicate **the same store** post-swap and report the same accepted and unexplained sets |
| 5 | `overall_readiness=PASS` | `_factor_readiness.json` published with `overall_readiness: "PASS"` |
| 6 | **One subsequent scheduled refresh succeeds unattended** | the *next* 06:00 ET timer-driven run passes with no operator intervention |

Gate 6 is the one that distinguishes a repaired production path from a one-off
operator-assisted success. Gates 1–5 can all be produced by a human standing at the console;
only gate 6 shows the scheduled path works on its own.

### Test execution status at time of PR

| Suite | Status |
|---|---|
| `tests/deploy/`, `tests/scripts/`, `tests/strategies/`, `tests/api/`, `tests/services/` | **RUN — PASS** |
| Mutation falsification of the new regression pack (6 mutations) | **RUN — all caught** |
| ruff check / ruff format (changed files) | **RUN — clean** |
| mypy (changed app modules) | **RUN — clean** |
| CI structural invariants (14 scripts incl. the new one) | **RUN — PASS** |
| Full backend pytest under CI's matrix | **RUN — PASS.** All 13 checks green on `c101cbf` (PR #698), including `Python FULL (backend)` and `Python (backend)` (the latter executing the new no-ticker invariant on Ubuntu; it had only been run on Windows locally). This item was NOT RUN at PR open and is now evidence rather than an inference. |
| Container / integration run of `factor_evidence.py` against a real store | **NOT RUN** — requires the box |
| Live `AlpacaBarsProbe` corroboration fetch | **CLASS NOT RUN** — it is not deployed; Norton SSL still blocks `data.alpaca.markets` on the laptop. An **equivalent read-only probe** (same endpoint, params and credential loader) was executed on the box on 2026-08-28 and returned `WBS` last bar `2026-08-19`, control `AAPL` `2026-08-27`, `SAN` `2026-08-27`. That evidences the *market fact*, not the class. |
| Production deployment and gates 0–6 above | **NOT RUN** |

Items marked NOT RUN are **not** inferred to pass. They are the next capable session's work.

⚠ **Green CI does not move the status.** It shows the control repair is internally sound. It says
nothing about `WBS`, nothing about the box, and nothing about gates 0–6. The factor store remains
**RED / publication blocked**, the administrative hold remains ACTIVE, and the mechanical
interlock remains **NOT YET DEPLOYED**.

---

## Related

* ADR 0051 — shared factor adjudication (the part that already worked)
* ADR 0056 — this repair
* `ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001` — governs the exhaustion evidence artifact
* 2026-08-17 — EA delisting / Sharadar `lastpricedate` retraction, repaired by one-row convergence
* 2026-08-11 — the divergence ADR 0051 closed
* 2026-08-10 — the fail-open classification observation
* 2026-08-03 — producer disabled; the incident that produced the watchdog
