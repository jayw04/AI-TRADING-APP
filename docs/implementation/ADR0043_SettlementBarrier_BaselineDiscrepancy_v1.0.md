# ADR-0043 settlement barrier — known baseline discrepancy

**Status:** OPEN, declared. NOT waived.
**Applies to:** branch `feat/adr0043-settlement-barrier` (off `80a6c043`, the clean lineage that
excludes ADR-0044 #457/#459).
**Recorded:** 2026-07-22, developer laptop (Windows 11, Python 3.13.14, `apps/backend/.venv`).

## The full-suite result, stated exactly

The backend suite was run in two halves (the whole run exceeds the session's background-command
budget). Combined: **3051 passed, 6 failed**.

The suite is **not** "green" in this environment, and the PR must not claim it is. All six failures
are pre-existing at the clean baseline, in two unrelated groups:

**Group A — ADR-0042 reservation capacity (1 test)**

```
tests/orders/test_adr0042_end_to_end.py::test_reductions_cannot_be_stacked_past_the_position
```

Asserts that three concurrent SELL 200 reductions against a long of 500 do not all pass; the second
is observed as `REJECTED` (`EXCEEDS_REDUCIBLE_CAPACITY`) where the test expects `SUBMITTED`. That is
ADR-0042 reservation-capacity behaviour, not settlement behaviour.

**Group B — missing optional dependency (5 tests)**

```
tests/services/market_projection/test_train_attribution.py  (5 tests)
```

All five fail with `ModuleNotFoundError: No module named 'sklearn'` at
`app/services/market_projection/train.py:154`. This is a local environment gap (MKT-PROJ / P10
work), entirely outside this branch's blast radius.

## Proof that all six are pre-existing and unrelated

| Check | Result |
| --- | --- |
| All 6 run at the clean baseline `80a6c04` (detached worktree, same interpreter) | **6 failed, 8 passed** — identical failures, identical causes |
| Same 6 on `feat/adr0043-settlement-barrier` | **6 failed** — same |
| Half 1 (`alerts…llm`) | **957 passed**, 0 failed |
| Half 2 (`market…strategies`) | **2094 passed, 6 failed** — exactly the six above |
| Settlement-targeted suite `tests/orders/test_settlement.py` | **28 passed**, `app/orders/settlement.py` **100%** coverage |
| Canary-harness suite `tests/risk/test_adr0043_canary_harness.py` | **84 passed** |
| Churn-driver suite `tests/risk/test_adr0043_churn_driver.py` | **43 passed** |
| `ruff` over `app`, `scripts`, `tests` | clean |
| `mypy app` | **Success — 384 source files** |
| Behavioural overlap between the changed files and the failing assertions | **none** — see below |

### Overlap analysis

Files changed by this branch:

- `apps/backend/app/orders/settlement.py` (new)
- `apps/backend/scripts/reconcile_stuck_orders.py` (refactored onto the shared resolver)
- `apps/backend/scripts/adr0043_canary_lib.py`, `adr0043_canary_run.py`, `adr0043_churn_driver.py`
- `apps/backend/tests/orders/test_settlement.py`, `tests/risk/test_adr0043_canary_harness.py`,
  `tests/risk/test_adr0043_churn_driver.py`

`app/orders/settlement.py` has exactly three importers in the tree — the two ADR-0043 scripts and
their tests. **No order-path module imports it**: not `OrderRouter`, not the risk engine, not
`RiskDecisionService`, which are the modules Group A exercises. The dependency runs the other way
(settlement imports `TradeUpdateConsumer`), so nothing this branch adds can reach the code under
test. Group B fails at import time on a missing third-party package and touches none of these files
at all.

## What is NOT claimed

That any of the six is wrong, or that any may be skipped.

For Group A, memory from earlier sessions records the same test failing on clean `ec23656` while
passing in CI, which points at an environment-specific cause (SQLite concurrency / event-loop
ordering on Windows) rather than a product defect — but that is a hypothesis, not a finding, and no
work on this branch investigated it.

For Group B the cause is known and mundane (`sklearn` absent from the local venv), but whether it
*should* be a hard dependency, an extra, or a skip-if-missing is an MKT-PROJ decision, not one this
branch gets to make by installing a package.

## Required of the PR

1. CI must run the full backend suite and the result recorded on the PR.
2. The PR states **3051 passed / 6 failed locally**, not "full suite green".
3. If CI is **green**, the environment-specific hypothesis holds for both groups; the discrepancy
   stays open and laptop-local, and this file is the record of it.
4. If CI is **red**, the failures are real and pre-existing on `80a6c043`. They are then their own
   defects with their own fixes — they do **not** get folded into this PR, and they do **not** block
   it beyond the reviewer's judgement, because the baseline comparison above shows the branch
   neither caused nor worsened them.

Either way the discrepancy is declared on the PR, not silently absorbed into a "known flaky" bucket.
