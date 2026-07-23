# §0 Owner Countersignature and Forward-Window Opening — v1.0

**Owner:** Jay Wang
**Authorized operator:** Jay Wang
**Countersignature date:** 2026-07-23
**Countersignature timestamp — America/Chicago:** 2026-07-23T06:44:08-05:00
**Countersignature timestamp — UTC:** 2026-07-23T11:44:08Z

## Owner adjudication

I confirm the result recorded in `Section7A_EquivalenceGate_Result_v1.0.md` and commit
`d05c29f1401beb99c72319fabd92ef9b9bc44e9b`.

The production-faithful validation instrument reproduced the countersigned §8 census seams exactly,
and all six preregistered §7 A construct/equivalence counts are zero.

**§7 A CONSTRUCT / EQUIVALENCE GATE: PASS**

This finding establishes **construct validity** of the frozen validation instrument. It does **not**
establish performance validity, activation readiness, or authorization to change Account 4.

## Frozen run-start bindings

| binding | value |
|---|---|
| Production strategy commit | `b0058bf335628f8dbde09a93915314f3a1f7743b` |
| Validation measurement-code commit | `764883b58cb96936f23e49182dd02b70d969501b` |
| §7 A evidence commit | `d05c29f1401beb99c72319fabd92ef9b9bc44e9b` |
| Primary benchmark implementation | `539cf6e` (`PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED`) |
| Academic 12-1 momentum benchmark implementation | `4675073` (`ACADEMIC_12_1_MOMENTUM_FACTOR`) |
| Cash / T-bill benchmark implementation | `b055b1c` (`CASH_OR_TBILL_RETURN`) |
| DGS3MO snapshot SHA-256 | `87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1` |
| DGS3MO observation cutoff | `2026-07-21` |
| Trial ledger SHA-256 | `b7d9d71591cc449a1768f33a3f3f5e0dcdf8ae518710ecec13422f0a0a98eb6d` |
| Effective DSR trial count | `45` |
| Forward validation start | `2026-07-24` |
| Governing timezone (market-session determination) | America/New_York |
| Countersignature timezone | America/Chicago |

## Forward-window authorization

The forward-only validation window is authorized to open on the **first eligible market session dated
2026-07-24**. Setting the start to July 24 (not July 23) avoids retroactively admitting any July 23
session activity after the gate result and countersignature were produced; the validation clock begins
only when the instrument processes the July 24 session under the fully frozen configuration.

The validation must run **exclusively** through the frozen shadow ledger or a separate governed
paper-validation account. Account 4 capital, positions, baseline, and the retired baseline `84466.41`
**must not** be used as the research ledger.

The window remains governed by all preregistered requirements, including: minimum 252 completed
trading sessions; minimum 40 rebalances; minimum one completed year; the sealed no-peeking rules;
preregistered integrity-stop conditions only; **no** parameter/benchmark/threshold/cost/universe/
trigger/regime/methodology changes after opening; and **no** extension after a performance failure.

## Operational state

This countersignature authorizes **only** the forward validation window. It does **not** authorize:
clearing the Account 4 hold; starting cooldown; activating Account 4; changing Account 4 capital or
positions; reusing the retired `84466.41` baseline; or treating interim performance as an activation
decision.

Account 4 remains: **PAUSED · hold ACTIVE · reason `AWAITING_PRODUCTION_SIZING_VALIDATION` · cooldown
NOT STARTED.**

A completed result of `PASS_ACTIVATION_READINESS` will authorize a **separate** operational
adjudication. It will **not** activate Account 4 automatically.

**Countersigned: Jay Wang**
**Signature:** recorded via governed commit under owner directive 2026-07-23 (this file's commit SHA
is the formal electronic countersignature record).

---

*After this block is committed, its commit SHA is the formal window-opening artifact. The first
July 24 evaluation must verify the exact bound code, benchmark, data, and ledger digests before
writing any observation.*
