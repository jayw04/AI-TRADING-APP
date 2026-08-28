# ADR 0056 — Observed exhaustion evidence, and the factor-readiness activation interlock

| Field | Value |
|---|---|
| Date | 2026-08-27 |
| Status | Proposed — becomes Accepted on owner approval of this PR |
| Phase | Cross-phase (factor-data readiness; gates dispatch **and activation** for every factor book) |
| Supersedes | — |
| Extends | 0051 (shared factor adjudication and the readiness coverage gate) |
| Related | 0005 (activation cooldowns), 0032 (AWS EC2 paper stack), 0043 (`ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001` governs the exhaustion evidence), 0044 (operational holds) |

## Context

ADR 0051 established one adjudication authority. `apps/backend/scripts/factor_adjudication.py`
is imported by the refresh verifier and its source is piped into the readiness watchdog, and
`tests/deploy/test_factor_freshness_shared_adjudication.py` pins that arrangement. **That part
works and this ADR does not revisit it.**

Two defects survived it. Neither is a divergence between the two validators, and diagnosing
them as one would have produced a PR that changed nothing.

### Defect 1 — the evidence artifact had no writer

`_factor_exhaustion_evidence.json` is an input to the shared rule: it supplies the two facts
adjudication cannot observe for itself (the per-symbol provider request outcome, and an
independent lifecycle signal). Every component in the repository **reads** it. As of
`origin/main` at 1545656, nothing **writes** it.

The production artifact was hand-built once, on `2026-08-11T19:30:57Z`, holding eleven records
(`DBC EA EEM EFA GLD IEF KMLM SATS SPY TLT UUP`). Two consequences reached the live book:

* **A name that goes attributable-stale after the artifact was written has no record.** It
  therefore adjudicates `FAILED_OR_UNEXPLAINED`, and the staging→live swap aborts. `EA` needed
  a human to add a record on 2026-08-17. `WBS` was the next name: it aborted the 06:00 ET
  refresh on 2026-08-25, 08-26, 08-27 and 08-28, freezing the live store at SEP `2026-08-21`
  while staging advanced to `2026-08-27`. There would have been another name after `WBS`.
* **Every attribution expires simultaneously.** `MAX_EVIDENCE_AGE_DAYS = 30`, and all eleven
  records carry the same observation timestamp, so on `2026-09-10` the refresh begins failing
  on eleven names rather than one. Nothing measured or reported the distance to that date.

A control whose input is refreshed by remembering to refresh it puts a human in the hot path of
every market day, and its failure mode is a cliff.

### Defect 2 — the readiness veto was not armed, and did not cover activation

Two distinct gaps:

**Classification failed open.** The engine classified a strategy as factor-consuming by
AST-parsing its source. On 2026-08-10 — the first live factor-consuming dispatch after the veto
shipped — both production factor books logged `strategy_factor_classification_unavailable`:
`inspect.getsource` and the `sys.modules[...].__file__` fallback both failed on the **loaded
instance**. Inference returned "not factor-consuming", `_factor_readiness_ok` returned `True`
before evaluating anything, and 52 orders filled against factor data nothing had verified. CI
was green throughout, because its safety-net test classified template **files on disk**, which
parse perfectly — an assertion against an object the production path never touches.

**Activation was never gated.** The veto refuses to *enter* a book at dispatch. It does not
refuse to *activate* one. An activation during a factor-store outage registers the strategy,
starts its schedule, flips its status to PAPER/LIVE, and leaves it to discover at each tick
that it may not run — while an operator reading the status sees "running". The
scheduler-driven `PENDING_LIVE → LIVE` completion in `ActivationService.complete_pending`
never consults the engine at all, so a book whose 24h cooldown elapsed during an outage would
complete into LIVE with the store frozen.

The owner's 2026-08-27 interlock is explicit that while factor readiness is FAIL, no
factor-dependent strategy may transition `IDLE → PAPER/LIVE`, generate a new factor-ranked
book, or execute a scheduled factor-driven rebalance — and that **existing positions remain
untouched**.

## Decision

### 1. Exhaustion evidence is GENERATED FROM OBSERVATIONS, on every refresh

`apps/backend/scripts/factor_evidence.py` writes the artifact from what the run measured:

| Field | Where it comes from |
|---|---|
| `requested` | membership of the universe file handed to `ingest_sharadar.py --tickers-file` |
| `request_status` | the exit condition of that ingest |
| `provider_rows_after_live_frontier` | counted in the STAGING store the provider just filled |
| `corroboration.last_date` | a live probe of an independent source (Alpaca daily bars) |
| `corroboration.control_last_date` | the same probe, same call, for a control symbol |
| `adjudicated_at_utc` | the instant of that probe |

It runs between ingest and verify, and writes atomically.

**It decides nothing.** The classification it records is computed by calling
`classify_stale_symbol` — the same function, with the same recomputed operational facts, that
the verifier runs again over the same record moments later. The recorded claim is redundant
rather than authoritative, and `test_generator_claim_never_changes_the_verifier_verdict`
proves it by forging every claim to the most permissive value and asserting that no verdict
moves.

**Why this is not "generate the exemptions automatically".** The properties that bound
attribution are unchanged, and they are the ones that matter:

1. Classification is still **derived, never declared** (ADR 0051 asymmetry 1).
2. The **exemption ceiling** still voids the whole run's attribution above 5% of the pool. A
   provider outage still looks like, and is treated as, an outage.
3. **Corroboration requires a current control.** A stale control means the alternate source was
   broken when observed, and the rule then refuses every attribution resting on it — so an
   outage of the corroborating source cannot manufacture exemptions.
4. **Operational facts are recomputed** from the app DB. A held or registered name cannot be
   written off.

What changes is only *who supplies the observations*: a measurement on the day, instead of a
recollection from three weeks earlier.

### 2. `factor_adjudication.py` gains the DIAGNOSTIC surface, and keeps it

`UNEXPLAINED: ['WBS']` is the same string whether nobody ever wrote a record for the name or
the rule read a current record and refused it. Those need opposite operator responses.
`diagnose_unexplained` labels each unexplained name `EVIDENCE_ABSENT`,
`EVIDENCE_NOT_CLAIMABLE`, `EVIDENCE_EXPIRED` or `EVIDENCE_PRESENT_REFUSED`, and
`evidence_expiry` reports the artifact's distance from its cliff. Both live in the **shared
module** and are consumed by the verifier and the watchdog alike, for the same reason every
other figure does: two components describing one state in two vocabularies is how an operator
comes to believe they are two states.

These are reporting, not policy. They cannot change a verdict.

### 3. Factor consumption is DECLARED

`Strategy.requires_factor_readiness: ClassVar[bool | None]`. A class attribute cannot fail to
introspect. `app/strategies/factor_classification.py` resolves declaration first, AST inference
second; a declaration of `False` contradicted by source that reads `ctx.factors` **gates
anyway** and logs the contradiction — a declaration states intent, it is not a one-line opt-out
from an interlock whose subject the code demonstrably touches.

Undeclared **and** uninspectable remains ungated, deliberately and per the owner's standing
instruction: gating everything unclassifiable turns a linecache quirk into a trading halt,
which is worse than the failure prevented. Making classification *reliable* is the fix; flipping
the default is not. That branch is now unreachable for any shipped strategy — every template
declares, and `test_every_shipped_template_declares` fails the build if one stops.

### 4. Readiness gates ACTIVATION, not only dispatch

* `StrategyEngine.register` — the seam every `IDLE → PAPER/LIVE` activation crosses — raises
  `FactorReadinessNotMet` for a factor-consuming strategy when readiness is not PASS. The API
  maps it to **409**, like an operational hold: a conflicting state the caller resolves by
  restoring readiness.
* `ActivationService.complete_pending` refuses the `PENDING_LIVE → LIVE` completion and leaves
  the strategy **PENDING_LIVE**, so a later pass completes it once the store recovers. The
  cooldown is not what is in question; the data is.

Registration is not the boundary, and saying so was the flaw review caught. The rule is that
**no seam capable of computing or applying a new factor-derived book may be reached while
readiness is FAIL**, whatever it is called. Enumerating the engine's seams from the AST found
two that were not gated: `_fire_all_event_strategies` (a fallback tick calling the same
`on_bar` that computes the book) and `_on_signal_event`. Neither could dispatch a factor book
today — every book runs on cron and implements only `on_bar` — so the invariant held because of
what the *strategies* contain, not because of anything the *engine* guarantees. Both are now
gated, and `test_every_execution_seam_is_gated` enumerates seams from the AST so a new hook
fails the build until it is classified.

`on_fill` is a reasoned exemption, on the record: it reports an order that has ALREADY filled.
Blocking it prevents nothing and denies the strategy news of its own fill, desynchronising its
book from the account — a gate refusing to deliver a fact, to no benefit.

**The boundary, stated as a rule: this refuses ENTRY only.** It marks nothing ERROR, cancels
nothing, submits no order, and touches no held position. An already-registered strategy
short-circuits before the check, so the interlock cannot reach into a running book. Factor RED
blocks new activation, ranking and rebalance; **it is not a liquidation trigger.**

### 5. No ticker may be special-cased — enforced, not merely stated

New CI invariant `check_no_factor_symbol_special_cases.py`: no short uppercase string literal
may appear in the executable lines of the five files that make up the factor refresh /
readiness path. `SPY` is allowlisted with its reason — it is the corroboration *control*, whose
staleness makes the rule refuse attributions, so naming it can only tighten the gate.

Twice the cheapest apparent repair has been to name a symbol. It would also have left an
exemption the 5% ceiling cannot see, no report counts, and no operator can audit.

## Consequences

**Accepted.** The evidence artifact becomes machine-written rather than human-curated. This is
a real reduction in human review of what gets excused, and it is the point: the human review
was not happening on a cadence, it was happening after each outage. The bounding properties
(ceiling, derived classification, live control, recomputed operational facts) are what make the
trade sound, and every one of them is tested.

**Accepted.** A factor-store outage now blocks activation of factor books. That is the intended
behaviour and it is a real reduction in availability: a book that could previously be activated
into a frozen store now cannot be. Non-factor strategies are unaffected.

**⚠ Explicitly NOT claimed — the design must serve both branches, and neither is assumed.** A
stale name resolves to an *attributable* verdict (`PROVIDER_EXHAUSTED` / `PROVIDER_NOT_COVERED`)
or to a *refusal* (`FAILED_OR_UNEXPLAINED`), and the two need opposite operator responses:
regenerate the artifact, or investigate the symbol. This ADR claims only that the rule draws that
line from evidence, without symbol-specific logic, and that the abort now names which side a
symbol fell on. It does **not** claim in advance which side any particular name is on — that is an
observation, never an inference.

Both branches are exercised by synthetic names in
`tests/deploy/test_factor_adjudication_equivalence.py`, so neither rests on a real ticker.

**Production evidence for the exhaustion branch — `WBS`, observed 2026-08-28.** Read-only from the
live store and a live alternate-source probe: Sharadar and Alpaca both end at `2026-08-19`; the
store's `actions` table carries `delisted` and `acquisitionby` → `SAN` on that date; the control
`AAPL` and the acquirer `SAN` are current to `2026-08-27`; there is no holding, open order or
registration. Webster Financial was acquired by Banco Santander and ceased trading. WBS is
therefore an **exhaustion** case, and its production failure diagnosed `EVIDENCE_ABSENT` — no
record existed in the hand-built `2026-08-11` artifact — which is exactly the class the writer
introduced here addresses.

⚠ **This does not make regeneration a passed gate.** The expected verdict has been reproduced by
running `classify_stale_symbol` against production-observed values, but `scripts/factor_evidence.py`
is not yet deployed and the production writer → artifact → verifier path remains unexecuted.
`WBS-DISPOSITION` stays a named precondition of the closure gate. The 2026-09-10 cliff is removed
regardless.

⛔ **Review correction, 2026-08-28.** The first candidate of this writer (`ce38edd4`) dated its own
run by the **staging store frontier** rather than by the schedule, while stamping
`adjudicated_at_utc` with the current instant. Because the refresh runs 06:00 ET the frontier is
always the prior trading day, so every record it wrote claimed to be observed *after* its own run
date — refused by `classify_stale_symbol`, then dropped by `load_evidence_records`. **The writer
refused everything it produced, and Gate 0B was unreachable.** Two things are now part of this
decision:

* **The run date is a clock; the frontier is data.** `schedule_today` and `DEFAULT_SCHEDULE_TZ` live
  in `factor_adjudication.py` — the module the verifier, the watchdog and now the generator already
  share — so one artifact ages against one calendar. The generator reaches that clock **without
  importing the verifier**.
* **The invariant is enforced, not assumed.** `generate()` raises when the observation date exceeds
  the run date, because a document that refutes itself record by record reads to an operator as
  "nothing is attributable" rather than as "the writer is misconfigured".

The regression pinning this crosses the `generate()` seam end to end. The prior suite could not: it
called `build_evidence_document` directly and pinned `as_of` to the frontier *and* the observation
to that same day — precisely the arrangement in which the defect is invisible.

**Rejected — special-casing a ticker.** Restores publication the same morning; leaves an
exemption nothing measures. Now blocked by CI.

**Rejected — relaxing `MAX_EVIDENCE_AGE_DAYS` or `FRESH_MIN_COVERAGE`.** Both move the cliff
rather than removing it, and both weaken a gate to avoid regenerating an input.

**Rejected — gating every unclassifiable strategy.** Turns a linecache quirk into a trading
halt. See §3.

## Compliance

* `tests/deploy/test_factor_adjudication_equivalence.py` — the producer and readiness paths
  co-executed over one staged fixture (`EA`, `WBS`, and synthetic names), plus the negative
  cases: adjudicator unavailable, malformed output, unexplained ticker present, expired
  evidence, and a successful adjudication followed by publication.
* `tests/strategies/test_factor_activation_interlock.py` — the classification fail-open, the
  activation interlock at both seams, and the positions-untouched boundary.
* `check_no_factor_symbol_special_cases.py` — wired into `python-checks` in `ci.yml`.

**This ADR is not closed by merging.** Production must supply the evidence listed in
`docs/incidents/2026-08-27-factor-store-publication-halt-RED.md` §Closure gate before the
factor system may be called GREEN.
