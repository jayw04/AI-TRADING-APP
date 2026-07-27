# ADR-0043 — account-3 scoped sync

**Tool:** `apps/backend/scripts/adr0043_scoped_sync.py`
**Purpose:** refresh account 3's `accounts_state` and `positions` rows from the broker, on the
Phase-0 validation host, without arming the global scheduler and without any code path that can
reach a second account.

This is not a general-purpose sync. It is a single-purpose governed instrument that refuses every
situation it was not built for.

---

## Why it exists

The validation host runs with `WORKBENCH_SCHEDULER_ENABLED=false`
(`ADR0043_VALIDATION_SCHEDULER_DISARMED`). That is intentional and stays that way: the flag is
global, so arming it syncs **every** local account — including account 1, whose ledger is evidence
for the 2026-07-13 risk-gate incident.

The two existing mechanisms cannot be narrowed by argument:

| mechanism | why it is unacceptable here |
|---|---|
| `AccountSyncService.sync_once` / `PositionSyncService.sync_once` | binds the *primary* adapter and resolves "the first alpaca account in the requested mode" — which account that is depends on row order, not on intent |
| `sync_all` (either service) | iterates every `accounts` row and syncs each from the broker registry |

Both are *configured* to be narrow at best. `ADR0043_RUNTIME_TARGET_BINDING_MISMATCH` is what
happens when a correct default meets a host whose environment silently overrides it.

---

## What it guarantees

Enforced in code, pinned by `apps/backend/tests/scripts/test_adr0043_scoped_sync.py`:

1. the target is **user 3 / account 3**, frozen as module constants — the module reads **no**
   environment variable, so there is nothing for a host to override;
2. the adapter is built from **user 3's** encrypted credentials and nothing else; `BrokerRegistry`
   is not imported, because its `load_all` decrypts every user's credentials in a loop;
3. the connected broker account must be **`PA34USW0Q8UO`**, verified *before* any write;
   **`PA3QRX9KSPXA`** (account 1) is refused **by name**;
4. account 1 is never queried, decrypted, or mutated;
5. there is no account loop;
6. no scheduler is constructed;
7. no mutating broker method is reachable — the adapter is wrapped in a read-only proxy that
   exposes exactly `get_account`, `get_positions`, `list_orders`;
8. every write statement binds `account_id = 3`, including the stale-position delete;
9. the run **REFUSES** unless the broker holds exactly **MSFT 19 LONG**, **0 open orders**, and the
   ledger holds **0 HELD reservations**.

### Clause 9 is a refusal, never a repair

If the broker disagrees with the frozen manifest, **something moved the account**, and the
interesting question is *what*. A sync would overwrite the local rows and erase the evidence. The
tool stops and says what it saw.

Do not "fix" a mismatch by re-running with different expectations. Investigate, record the finding,
and bring it to the owner.

---

## Running it

⚠ **Runtime is AWS.** This runs on the ADR-0043 validation host, inside the backend container, never
against the laptop's local stack. The canary box is **not** `ssh workbench` (that is production) —
see the Phase-0 runbook for the current address and the `hostname` confirmation step.

### 1. Dry run (always first)

```bash
python scripts/adr0043_scoped_sync.py \
  --evidence /app/data/adr0043_scoped_sync_dryrun.json
```

Performs every read and every check, writes nothing, and reports what it *would* write. Exit `0` =
all checks passed; exit `2` = refused (the reason is on stderr and in the evidence file).

### 2. Read the evidence before committing

The evidence JSON binds, in one document: the frozen target, the mode, each check with its verdict
and detail, the account-3 rows as they stood before, and the exact write that would be performed.

Confirm by eye:

- `target.user_id` = 3, `target.account_id` = 3;
- `checks[].result` — all three `PASS` (`account_row_binding`, `broker_identity`, `frozen_manifest`);
- `broker_identity` detail names `PA34USW0Q8UO`;
- `frozen_manifest` detail reads `MSFT 19 long, 0 open orders, 0 HELD reservations`.

### 3. Commit

```bash
python scripts/adr0043_scoped_sync.py --commit \
  --evidence /app/data/adr0043_scoped_sync_commit.json
```

The checks run again against a fresh broker read — the commit run does **not** trust the dry run's
observations. If anything moved between the two runs, the commit refuses.

### 4. Retain both evidence files

They are the pre/post halves of the governed mutation record.

---

## Failure modes and what they mean

| exit / message | meaning | action |
|---|---|---|
| `REFUSED: ... EXPLICITLY FORBIDDEN` | the credentials resolved to account 1's broker account | **stop.** The credential binding on the host is wrong. This is the `RUNTIME_TARGET_BINDING_MISMATCH` class of defect. |
| `REFUSED: connected broker account ... != expected` | user 3's credentials point somewhere unexpected | stop; verify the installed canary credentials |
| `REFUSED: ... does not match the frozen Phase-0 manifest` | the account moved | stop; investigate what moved it. Do **not** sync. |
| `REFUSED: account 3 belongs to user N` | the DB binding disagrees with the frozen target | stop; nothing was decrypted |
| `REFUSED: ... paper-only` | account 3 is marked live | stop |
| `ScopedSyncRefused: broker method ... is not reachable` | a code change tried to act through this tool | fix the code; this tool reads |

---

## Relationship to the rest of Phase 0

This tool refreshes risk inputs. It does **not** capture the authoritative baseline, and running it
is not a substitute for the baseline capture step, which remains **HELD**.

Order of operations on the host is governed by
`docs/runbook/ADR0043_Phase0_SameSession_Runbook_v1.0.md` and the frozen execution plan. The scoped
sync runs **after** the environment repair and container recreate, and **before** the read-only
reconciliations.
