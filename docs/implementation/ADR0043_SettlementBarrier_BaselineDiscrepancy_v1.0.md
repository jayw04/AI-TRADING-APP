# ADR-0043 settlement barrier — known baseline discrepancy

**Status:** OPEN, declared. NOT waived.
**Applies to:** branch `feat/adr0043-settlement-barrier` (off `80a6c043`, the clean lineage that
excludes ADR-0044 #457/#459).
**Recorded:** 2026-07-22, developer laptop (Windows 11, Python 3.13.14, `apps/backend/.venv`).

## The discrepancy

One test in the full backend suite fails locally and is **not** caused by this branch:

```
tests/orders/test_adr0042_end_to_end.py::test_reductions_cannot_be_stacked_past_the_position
```

It asserts that three concurrent SELL 200 reductions against a long of 500 do not all pass; the
second one is observed as `REJECTED` (`EXCEEDS_REDUCIBLE_CAPACITY`) where the test expects
`SUBMITTED`. This is ADR-0042 reservation-capacity behaviour, not settlement behaviour.

## Proof that it is pre-existing and unrelated

| Check | Result |
| --- | --- |
| Fails at the clean baseline `80a6c04` (detached worktree, same interpreter) | **FAIL** — identical assertion, identical reject reason |
| Fails identically on `feat/adr0043-settlement-barrier` | **FAIL** — same |
| Settlement-targeted suite `tests/orders/test_settlement.py` | **28 passed**, `app/orders/settlement.py` **100%** coverage |
| Canary-harness suite `tests/risk/test_adr0043_canary_harness.py` | **82 passed** |
| Rest of `tests/orders` | green |
| Behavioural overlap between the changed files and the failing assertion | **none** — see below |

### Overlap analysis

Files changed by this branch:

- `apps/backend/app/orders/settlement.py` (new)
- `apps/backend/scripts/reconcile_stuck_orders.py` (refactored onto the shared resolver)
- `apps/backend/scripts/adr0043_canary_lib.py`, `adr0043_canary_run.py`
- `apps/backend/tests/orders/test_settlement.py`, `tests/risk/test_adr0043_canary_harness.py`

`app/orders/settlement.py` has exactly two importers in the tree — `scripts/adr0043_canary_run.py`
and its tests. **No order-path module imports it**: not `OrderRouter`, not the risk engine, not
`RiskDecisionService`, which are the modules the failing assertion exercises. The dependency runs the
other way (settlement imports `TradeUpdateConsumer`), so nothing this branch adds can reach the code
under test.

## What is NOT claimed

That the test is wrong, or that it may be skipped. Memory from earlier sessions records the same
test failing on clean `ec23656` while passing in CI, which points at an environment-specific cause
(SQLite concurrency / event-loop ordering on Windows) rather than a product defect — but that is a
hypothesis, not a finding, and no work on this branch investigated it.

## Required of the PR

1. CI must run the full backend suite and the result recorded on the PR.
2. If CI is **green**, the environment-specific hypothesis still holds; the discrepancy stays open
   and laptop-local, and this file is the record of it.
3. If CI is **red**, the failure is real and pre-existing on `80a6c043`. It is then its own defect
   with its own fix — it does **not** get folded into this PR, and it does **not** block this PR
   beyond the reviewer's judgement, because the baseline comparison above shows the branch neither
   caused nor worsened it.

Either way the discrepancy is declared on the PR, not silently absorbed into a "known flaky" bucket.
