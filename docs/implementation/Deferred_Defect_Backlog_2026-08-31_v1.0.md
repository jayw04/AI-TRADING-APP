# Deferred defect backlog — recorded 2026-08-31

⛔ **RECORD ONLY. No implementation this cycle.** Every entry is non-blocking for the adjudications
closed on 2026-08-31 (Lane C factor acceptance, G4b operational reachability, TRACK-B-2026-08-31).
Recording them here is what allows those adjudications to close without carrying hidden debt.

---

## `DEPLOY-SRC-SHA-LIFECYCLE-001` — IDENTIFIED / NON-BLOCKING / FUTURE TOOLING FIX

`/opt/workbench/app/.deploy_src_sha` is **absent** after the `b94838b6…` deployment. No provisioner
writes it; it is a hand-maintained operator file and is not in the deploy archive.

⛔ **The fix is NOT "make the provisioner write it and keep treating it as an identity leg"** — that
recreates the writable-assertion weakness the repo's own falsification suite exists to reject. A
writable declaration is not identity evidence. Either emit it as an explicitly **non-authoritative
compatibility marker**, or **remove downstream dependence** in favour of manifest + runtime-derived
identity. ⛔ Never hand-write the file. ⛔ Never retroactively call Gate 1 "3/3 PASS".

## `FACTOR-POSTSWAP-HEALTH-GATE-001` — IDENTIFIED / FAIL-OPEN HEALTH CLASSIFICATION / REPAIR REQUIRED

`deploy/aws/factor-refresh.sh` probes `curl /healthz` **20 s** after restarting the backend; on failure
it logs `WARN: backend not healthy yet after refresh` and the producer **still exits 0**.

⛔⛔ **The defect is NOT "20 seconds is too short," and raising the timeout alone would not close it.**
The defect is that **terminal health failure is indistinguishable from a warm-up delay and carries no
operational consequence**. A genuine, permanent health failure produces the same WARN and the same
exit 0.

**Required shape of any future repair:** bounded warm-up/readiness semantics (poll to a deadline),
followed by a **distinguishable and operationally meaningful failure** if health never arrives — not a
longer silent wait.

⭐ Observed 2026-08-31 06:07:55. Independent later evidence shows *this* backend became healthy
(`RestartCount=0`, `Health=healthy`, `healthz 200`, successful 07:00 watchdog run), so today's producer
execution stands. ⛔ **Do not generalize that eventual health into proof that the health gate works.**

## `FACTOR-COVERAGE-ADJUDICATION-EXPIRY-001` — PASS CURRENTLY / SUPPORT EXPIRES 2026-09-30

Factor readiness PASSes on `gating_coverage = covered/assessable = 499/499 = 1.0000`. `raw_coverage`
is **0.9784**, below the 0.98 floor; it is **observability-only under the governing semantics and no
gate may threshold it**. The PASS is therefore load-bearing on **11 provider-exhausted adjudications**
whose supporting evidence **expires 2026-09-30**.

⛔ **Do not change today's PASS because of a future expiration.**

**Operational deadline — regenerate the adjudication evidence on or before 2026-09-19**, leaving ~11
days of margin before expiry. Missing the expiry silently changes what the coverage gate means.

## `FACTOR-INTERLOCK-TEST-SEMANTICS-001` — IDENTIFIED / TEST NAME OVERSTATES COVERAGE / NON-BLOCKING

`tests/strategies/test_factor_activation_interlock.py::test_register_refuses_a_factor_book_when_readiness_fails`
**never calls `engine.register`**. Its docstring claims it is *"driven through the real method with a
stub `self`"*, but it closes with:

```python
with pytest.raises(FactorReadinessNotMet):
    raise FactorReadinessNotMet(7, verdict.reason)
```

— asserting that raising an exception raises that exception.

⭐ **It earned no credit in the 2026-08-31 interlock ruling**, which rested on the *structural* tests
(interlock ordering before `StrategyStatus.PAPER` / `add_job` / `_running[id]=`, and seam coverage).
This is therefore **not a retroactive defect in the interlock proof**.

**Future repair:** make the test actually invoke the `register` seam with a controlled failing
readiness verdict.

---

## G4b probe defects (2026-08-31) — tooling/observer errors, not system defects

Recorded because each nearly became a **false finding about production**.

1. ⭐⭐ **A freshly constructed `BrokerRegistry` returns `None` from `get()` until `load_all()` runs.**
   A probe reported `broker_registry.get(6) -> None`, which reads exactly like a G4b failure. It is a
   **probe artifact** and says nothing about the live app's registry, which is populated at boot.
   After `load_all()`: `AlpacaAdapter`, accounts `[1..7]`.
2. **`positions` has no `symbol` column** — it is `symbol_id → symbols.ticker`. A query against the
   guessed column raised, and an earlier variant silently returned empty source text, producing a
   spurious `requires_factor_readiness=NOT FOUND` for strategies 7/8/9.
3. **`BrokerRegistry` lives in `app.brokers.registry`, not `app.brokers.factory`**; and strategy
   `code_path` values (`templates/<x>.py`) resolve under `/app/strategies_user/`, not `/app`.

⭐ Common lesson: **a negative result from a probe whose path, schema, or initialization was never
verified is not evidence about the system.** Confirm the probe would have produced a true positive
before reporting an absence.
