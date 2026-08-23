# ADR 0051 — Shared factor adjudication and the readiness coverage gate

| Field | Value |
|---|---|
| Date | 2026-08-11 |
| Status | Draft — becomes Accepted on owner approval of this PR |
| Phase | Cross-phase (factor-data readiness; gates strategy dispatch for every factor book) |
| Supersedes | — |
| Related | 0025 (pending-aware exposure gates), 0032 (AWS EC2 paper stack), 0038 (reducing exits exempt from the gross-exposure gate), 0040 (valuing market orders in exposure gates), 0043 (loss-control architecture; `ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001` governs the exhaustion evidence), 0049 (Strategy 9 v1.3/C40 construction) |

## Context

Two components read the same governed artifact, `_factor_exhaustion_evidence.json`, and
until 2026-08-11 reached *different verdicts from it*.

`apps/backend/scripts/factor_refresh.py` gates the staging→live swap of the factor store.
It **derives** each symbol's classification from live facts — frontiers, an independent
price source, a liveness control, and recomputed holdings/registration — and refuses
evidence it cannot corroborate. `deploy/aws/factor-freshness.sh` publishes
`_factor_readiness.json`, the artifact that vetoes dispatch for every factor-consuming
strategy. It **trusted** the `expected_classification` string written in the file.

On 2026-08-11 the divergence became visible and expensive. From the same store, the same
510-name universe and the same evidence file, the watchdog published
`data_freshness=PASS` at `coverage=1.0000`, while the refresh aborted with
`coverage=0.9784` and left the live store frozen at `sep_max=2026-08-07`. Nine
cross-asset ETFs (SPY, EFA, EEM, TLT, IEF, GLD, DBC, UUP, KMLM) are absent from the
Sharadar Core US Equities subscription entirely; EA and SATS had genuinely ceased
trading. The refresh's own classifier would have attributed all eleven correctly — but
the coverage threshold it gated on was computed *before* classification ran and never
saw the result. Adjudication that does not reach the gate it exists to inform is
decoration.

Three separate asymmetries were in play, not one: **who decides** a classification
(derived vs declared), **what the gate measures** (`covered/universe` vs
`covered/assessable`), and **whether attribution is bounded** (the watchdog capped
exemptions at 5% of the pool; the verifier had no ceiling at all).

## Decision

1. **One implementation.** `apps/backend/scripts/factor_adjudication.py` is the single
   source of truth for staleness adjudication. Both the refresh verifier and the
   readiness watchdog consume it. Neither may carry its own reading of the evidence
   artifact.

2. **The watchdog receives that implementation as host-sourced text, never as an import.**
   The file is resolved relative to the watchdog's own checkout, read once, hashed, and
   the same bytes piped into the container ahead of the driver. There is deliberately no
   image-import fallback.

3. **`gating_coverage` is the only figure any gate compares against a threshold**, and it
   is `covered / assessable` where `assessable = universe − attributed`. An attributed
   name leaves the denominator: it neither counts against the pool nor pads it. The
   `0.98` threshold is unchanged.

4. **The exemption ceiling is part of the same contract**, not an independent control.
   Attribution above `max(5, 5% of universe)` voids attribution *entirely* for that run.

5. **Effective freshness is `min(sep_max, tickers.lastpricedate)`.** A name with current
   prices but a lagging `lastpricedate` is not fresh for gating purposes.

6. **Classification is derived, never declared.** `expected_classification` selects which
   records are adjudicable; the verdict is recomputed from frontiers, corroboration, a
   liveness control, and holdings/registration read from the app database.

7. **Provenance is recorded and absence fails closed.** The published readiness artifact
   carries the SHA-256 of the exact `factor_adjudication.py` bytes the watchdog executed.
   If the helper is missing, unreadable, or its operational inputs cannot be read,
   `data_freshness` is FAIL — a verdict with no named implementation behind it is never a
   PASS, and there is no fallback to stale or duplicated logic.

8. **Raw coverage is observability only.** It must continue to be reported on every run,
   and no dispatch or refresh gate may threshold it.

9. **Attribution is fail-closed.** Evidence that is missing, malformed, expired,
   frontier-mismatched, operationally inconsistent, or otherwise invalid leaves a symbol
   un-attributed and therefore *assessable* — it stays in the denominator and counts
   against the gate.

10. **Operational facts are adjudication semantics, not a local concern.** Held,
    registered and open-order conditions are evaluated identically by both components, from
    the app database, and are recomputed rather than read from the evidence artifact.

11. **The `0.98` threshold is unchanged.** This decision changes *which population* the
    existing threshold legitimately measures. It is not a threshold relaxation, and it must
    not be cited as precedent for one.

> **An attributed symbol is not considered "fresh."** It is removed from the assessable
> population because the provider has been governably determined unable or inapplicable to
> supply the required observation. `gating_coverage = 1.0000` therefore never means "all
> 510 names are current" — it means every name the provider *can* be expected to deliver is
> current. Read it with `attributed_count` and `raw_coverage` beside it; the published
> artifact carries all three for exactly this reason.

**Non-goal.** Ranking-pool hygiene — dead names accumulating in
`components.ranking_pool` and consuming freshness capacity — is separate work. This
decision does not redefine ranking-pool membership, and must not be read as having done so.

## Rationale

**Why one implementation rather than two kept in step by tests.** A conformance fixture
comparing two implementations catches drift only when CI runs. The watchdog's verdict is
a live trading veto evaluated every morning against production data; a divergence that
appears between CI runs is a divergence in production. Only a single implementation makes
the two structurally incapable of disagreeing.

**Why host-sourced rather than imported.** The existing code carried an explicit warning
against importing `factor_refresh.py` into the watchdog: the module is baked into the
backend image, the deployed image routinely predates the host tree, and a readiness
watchdog must never become the reason to deploy. That reasoning is correct and applies
identically to a new shared module. But a watchdog that adjudicates by *older* rules than
the verifier is the same class of defect this ADR exists to remove — it would simply move
the divergence from "different code" to "different vintage of the same code". Piping the
source satisfies both constraints at once: one implementation, and no dependency on image
contents. The cost is a coupling to the host tree's layout, which is why it is asserted by
test rather than left implicit.

**Why `covered / assessable`.** Three candidate denominators were available. Counting an
attributed name as *uncovered* — the verifier's prior behaviour — asks a symbol to satisfy
a threshold it can never satisfy; nine permanently-uncovered ETFs consumed 88% of a 2%
budget and froze the store. Counting it as *covered* (a `(fresh + attributed) / universe`
form the verifier already computed but never gated on) would let a growing exemption list
manufacture a passing grade. Removing it from the measurement entirely is the honest
reading: the store is being asked how much of what it *can* deliver is current.

**Why the ceiling is coupled to the denominator, and not tunable on its own.** Removing
names from the denominator is only safe while the number removed stays small. Without a
bound, systemic deterioration — a provider outage affecting hundreds of names — would
present as a shrinking denominator with perfect coverage, which is precisely the shape of
a suppressed check. The ceiling is what makes `covered / assessable` a measurement rather
than a loophole, so the two must move together or not at all. Raising the ceiling without
re-examining the coverage rule, or vice versa, is a change to the same control.

**Why voiding attribution is all-or-nothing.** Trimming to the ceiling would attribute
some arbitrary subset chosen by sort order. The condition being detected is "this artifact
is excusing too much of the pool", not "these particular names are wrong", so the response
is to trust none of it.

**Why effective freshness is the stricter reading.** `dollar_volume_universe` filters on
`lastpricedate`, so a name whose `lastpricedate` lags is dropped from the ranking pool
outright — strictly worse than being ranked on old data, and invisible to any check
looking only at `sep`. A gate that reports such a name as healthy is measuring something
other than what the books consume.

## Implementation notes

- **`apps/backend/scripts/factor_adjudication.py`** — standard library only. It must not
  import the `app` package or `duckdb`: the verifier runs in a minimal one-off container
  against raw stores, and the watchdog's copy is executed inside whatever backend image is
  deployed. Public surface: `classify_stale_symbol`, `load_evidence` (returns
  `(by_symbol, note, status)`), `operational_facts`, `adjudicate`, `gating_coverage`,
  `exemption_ceiling`, and the verdict constants.
- `factor_refresh.py` re-exports those names (PEP 484 `X as X` form) so existing callers
  and tests are unaffected, and now adjudicates *before* gating.
- **`deploy/aws/factor-freshness.sh`** — `ADJUDICATION_PATH` defaults to
  `$WATCHDOG_DIR/../../apps/backend/scripts/factor_adjudication.py`, overridable via
  `FACTOR_ADJUDICATION_PATH` for tests. The file is read once into `ADJUDICATION_SRC`;
  the hash and the pipe both use that variable through the same `<<<` construct, so the
  bytes hashed are the bytes executed.
- The watchdog now reads the app database (`WORKBENCH_CONTAINER_APP_DB`, default
  `/app/data/workbench.sqlite`) to recompute holdings and registration. It previously did
  not, which is why it could attribute a name the verifier refused. An unreadable app DB
  is `DATA_OPERATIONAL_FACTS_UNAVAILABLE` and fails closed — an empty result would be
  *laxer* than the verifier.
- The in-container block gains an `ET_TODAY` clock seam mirroring the shell's existing
  `WATCHDOG_NOW_EPOCH`. Without it the block read the wall clock while its tests pinned a
  frontier, so three of them began failing on 2026-08-11 purely because calendar time
  advanced. **This is a testability repair only: with `ET_TODAY` unset — which is every
  production invocation — behaviour is byte-for-byte what it was.** It carries no freshness
  policy and is not part of the decision above; it is included here only because the
  component it lives in is being rewritten and would otherwise be untestable.
- The readiness artifact gains a `coverage` object carrying `gating_coverage`,
  `raw_coverage`, `universe_count`, `assessable_count`, `attributed_count`,
  `covered_count` and `unexplained_count`, each with its definition alongside. The figures
  are parsed from the values the run actually used, never recomputed — a second calculation
  could disagree with the one that decided the verdict.
- Readiness artifact gains an `adjudication` object: `implementation`, `sha256`,
  `sourced_from`, `image_import: false`. The two contract fields the application reads
  (`evaluated_at_utc`, `overall_readiness`) are unchanged.
- No threshold, tolerance or schedule value changes.

## Consequences

**Positive.** The two components cannot disagree; the divergence class is removed rather
than patched. A structurally uncovered instrument no longer freezes the store forever. Any
published verdict names the implementation that produced it, so a PASS can be audited
after the fact. The watchdog now applies the verifier's operational checks, closing the
gap where it could excuse a held or registered dead name.

**Negative.** The gate is *stricter* in one respect — a lagging `lastpricedate` now counts
against it — so runs that previously passed on a technicality will fail. The watchdog is
newly coupled to the host tree's directory layout and to the app database; both are new
failure modes, both fail closed, and both are asserted by test, but they are new. The
shell is harder to read: the freshness block is no longer a self-contained heredoc, and a
reader must know the helper arrives over the same stdin. And a repository-level constraint
now exists that is easy to violate by accident — the helper must stay standard-library
only, or the watchdog breaks inside an image that lacks the dependency.

**Neutral.** The evidence artifact's schema is unchanged; `expected_classification` is
still read, but demoted from verdict to filter. The raw evidence-blind coverage figure is
still computed and reported on every run, so attribution can never hide how much the
provider actually delivered — it simply no longer decides the run.

## Alternatives considered (not chosen)

- **Make the watchdog match the verifier by copying its rules.** Rejected: two copies of a
  fail-closed classifier drift, and the drift is invisible until the day they disagree in
  production — which is the incident being recorded here.
- **Have the watchdog import the shared module from the image.** Rejected: the deployed
  image predates the host tree by design, so the watchdog would adjudicate by stale rules,
  or crash and publish nothing. Reconsider if the watchdog ever moves inside the deployment
  unit it observes, at which point "predates" stops being true.
- **Gate on `(fresh + attributed) / universe`.** Rejected: it counts attributed names as
  covered, so a growing exemption list raises the score. Numerically close to the chosen
  rule in healthy states and materially wrong in exactly the unhealthy ones.
- **Lower the 0.98 threshold.** Rejected explicitly. The threshold was never the defect;
  what counted toward it was. Lowering it would have unblocked 2026-08-11 while leaving
  every future structurally-uncovered name to consume the same budget.
- **Remove the nine ETFs from the refresh universe.** Rejected as a fix for *this* defect —
  they are legitimately in the universe because strategies hold and reference them. The
  related but separate question of dead names accumulating in `components.ranking_pool` is
  a universe-quality defect and is tracked on its own; folding it in would widen a
  correctness PR into a data-hygiene one.

## Re-evaluation triggers

- Attribution approaches the `max(5, 5%)` ceiling in normal operation. That is the signal
  that the subscription no longer covers the universe the books rank over, and the answer
  is a data-sourcing decision, not a larger ceiling.
- The provider begins supplying prices for the cross-asset ETFs (an entitlement change,
  e.g. adding the fund-price dataset). The nine `PROVIDER_NOT_COVERED` attributions should
  then disappear on their own; if they do not, the derivation is wrong.
- A `PROVIDER_NOT_COVERED` or `PROVIDER_EXHAUSTED` verdict is ever traced to a name that
  was in fact obtainable — attribution would then be masking an ingestion defect, and the
  corroboration requirements need strengthening.
- The watchdog moves into the deployment unit it observes, or the backend image begins
  being built from the same commit that ships the watchdog. The host-sourcing decision
  (item 2) exists only because those are false today.
- Any proposal to change the coverage denominator or the exemption ceiling independently
  of the other. By this ADR they are one control.
