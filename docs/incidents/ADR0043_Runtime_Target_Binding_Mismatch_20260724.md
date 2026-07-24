# Defect record — ADR0043_RUNTIME_TARGET_BINDING_MISMATCH

- **Date:** 2026-07-24
- **Severity:** **PRE-SUBMISSION CRITICAL BLOCKER**
- **Component:** `/opt/workbench/.env` on the validation host vs the Frozen Execution Plan §3
- **Status:** OPEN — correction authorized, not yet applied

## Summary

The deployed runtime binds the ADR-0043 harness to the **wrong local user and account**.

| | user | account |
|---|---|---|
| Frozen Execution Plan §3 | **3** | **3** |
| `/opt/workbench/.env` (deployed) | **1** | **1** |

`scripts/adr0043_canary_lib.py` resolves these from the process environment:

```python
USER = int(os.environ.get("ADR0043_USER", "3"))
ACCT = int(os.environ.get("ADR0043_ACCOUNT", "3"))
```

The defaults are correct. The deployed environment **silently overrides them**, and the runbook's
documented invocation passes `--env-file /opt/workbench/.env` without re-asserting the frozen values.

## Impact

A formal canary launched per the runbook would bind to user 1 / account 1 — including
`credentials_for_mode("paper", USER, sf)`, so it would load **user 1's credentials** — while every
gate, position expectation and identity assertion in the plan is written about account 3 and broker
account `PA34USW0Q8UO`.

**No baseline, preflight, Phase-0 or canary evidence produced under this container environment is
admissible.**

This morning's Step-A read was unaffected only by accident: the staged `adr0043_session_open.py`
hardcodes `USER_ID = 3` / `ACCOUNT_ID = 3` and ignores the environment entirely. The frozen harness
does not.

It also changes the reading of the missing `accounts_state` row for account 3. With `ACCT=1` the
harness's `ACCOUNT_STATE_ROW_MISSING` refusal would never have fired — it would have found account
1's row and proceeded against the wrong account. The refusal is correct; on this host it would have
been evaluated against the wrong target.

`ADR0043_PROTECTED=MSFT` and `ADR0043_LEGS=MSFT:19` do match. `ADR0043_CHURN` is **absent**; the
library default `IEUS,KOKU` happens to equal the frozen value, but §3 requires it set explicitly
rather than defaulted.

## Correction (authorized, applied separately)

`.env` must carry the frozen identity:

```
ADR0043_USER=3
ADR0043_ACCOUNT=3
ADR0043_PROTECTED=MSFT
ADR0043_LEGS=MSFT:19
ADR0043_CHURN=IEUS,KOKU
```

**`.env` alone is not sufficient.** The governed invocation must re-assert every value with explicit
`-e` overrides so the run cannot inherit a wrong binding from a file, and the harness must print and
verify user/account 3/3, credential prefix `PKZYTY…`, broker `PA34USW0Q8UO`, `!= PA3QRX9KSPXA`,
protected, legs and churn **before** loading credentials or constructing an order path. A mismatch is
a pre-submission refusal.
