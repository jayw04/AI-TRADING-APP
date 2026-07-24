# Defect record — ACCOUNT1_BROKER_ACCOUNT_NUMBER_STALE

- **Date:** 2026-07-23
- **Severity:** Low (local metadata defect; no trading impact observed)
- **Component:** DB `accounts_state` for account 1 (momentum)
- **Status:** OPEN — reconciliation HELD by owner (do not modify account 1 yet)

## Summary

DB account 1 (momentum) stores a broker `account_number` that does **not** match the account its
credential actually authenticates into.

| Field | Value |
|---|---|
| `stored` (DB account 1 `accounts_state.account_number`) | `PA34USW0Q8UO` |
| `credential-confirmed actual` (PKOJTY / `ALPACA_PAPER` → `get_account()`) | `PA3QRX9KSPXA` |
| `trading impact` | none observed — execution uses the credential (`PKOJTY → PA3QRX9KSPXA`), not the stored display number |
| `reconciliation required` | **before momentum reactivation** |

`PA34USW0Q8UO` is in fact the **canary** account (PKZYTY / `ALPACA_PAPER_2`, DB account 3). At some
point account 1's `accounts_state` was synced against the canary's Alpaca account, leaving account 1's
stored number pointing at the canary's number.

## Evidence

Read-only `get_account()` on both keys (2026-07-23), DB SHA unchanged pre==post:

```
PKOJTY (ALPACA_PAPER, acct 1, momentum) -> PA3QRX9KSPXA  ACTIVE
PKZYTY (ALPACA_PAPER_2, acct 3, canary) -> PA34USW0Q8UO  ACTIVE
separate_accounts = true
```

## Ruling (owner, 2026-07-23)

- Account-1 `account_number` correction: **HOLD** (do not modify account 1 yet).
- Reconciliation is **required before momentum reactivation**.
- This is a local metadata defect, **separate** from the ADR-0043 canary discovery.
