# ADR-0043 — Repair B: the minimum evidence package

**Scope:** correct the validation host's runtime target binding
(`ADR0043_RUNTIME_TARGET_BINDING_MISMATCH`) and recreate the backend so the process environment
reflects it.

This is the **reduced** package, authorized 2026-07-27. The earlier package was overly broad; it is
superseded by exactly what is listed here. Nothing below re-proves a historical deployment artifact.

**Repair B is ONE indivisible governed mutation.** Do not start it without enough time and context
to finish it and capture the after-restart evidence.

---

## Preconditions

- #495, #498 and #499 are **merged and deployed**. Repair B runs after that, not before.
- You are on the **validation host**, not production. `ssh workbench` is the **production** paper
  stack — the wrong host here points canary tooling at the live book. Use the canary key/address
  from `ADR0043_Phase0_SameSession_Runbook_v1.0.md` and confirm `hostname` = `ip-172-31-6-164`.
  ⚠ The canary box's IP changes across stop/start.

### What Repair B does NOT change

| flag | stays | why |
|---|---|---|
| `WORKBENCH_SCHEDULER_ENABLED` | `false` | it is global — arming it syncs **every** local account, including account 1 |
| `WORKBENCH_LIVE_TRADING_ALLOWED` | `false` | Phase 0 is paper-only |

The account-3 refresh is the scoped sync (`ADR0043_Account3_Scoped_Sync.md`), not the scheduler.
There is no step in this procedure that enables either flag.

---

## 1. Before restart — capture

Capture all eight into the pre-repair evidence file. If any capture fails, **stop**: an
un-captured baseline cannot be compared afterwards, which is the entire point of the package.

| # | item | note |
|---|---|---|
| 1 | `.env` SHA-256 | of `/opt/workbench/.env`, the file being changed |
| 2 | current `ADR0043_USER` / `ADR0043_ACCOUNT` | the **defect itself**, recorded before it is corrected |
| 3 | container ID and image digest | the digest must be **unchanged** afterwards — Repair B changes configuration, never the image |
| 4 | DB backup + integrity check | `deploy/aws/adr0043_db_backup_restore.sh`; a backup that is not integrity-checked is not a backup |
| 5 | account-1 row digest | account 1 is 2026-07-13 incident evidence and must be provably untouched |
| 6 | user-1 credential ciphertext digests | proves no credential was decrypted or rewritten |
| 7 | open orders count | |
| 8 | HELD reservation count | |

⚠ **On a live DB, `SHA before == after` is NOT a valid no-write proof** — concurrent application
writes move the file. State items 5–6 as **operator-read-only**: read-only mount (`mode=ro`),
`SELECT` only, digests over the specific rows, not the file.

---

## 2. Apply Repair B

Edit `/opt/workbench/.env`:

```
ADR0043_USER=3
ADR0043_ACCOUNT=3
ADR0043_PROTECTED=MSFT
ADR0043_LEGS=MSFT:19
ADR0043_CHURN=IEUS,KOKU
```

Then **recreate the backend** so the process environment reflects the file. An edited `.env` alone
changes nothing about a running container.

⚠ **`--env-file` alone is never sufficient.** The governed invocation must re-assert every value
with explicit `-e` overrides, and the harness must print and verify identity **before** loading
credentials. That ordering is not cosmetic: the whole defect was an environment that silently
overrode a correct default, and an identity printed after a credential load is printed too late.

---

## 3. After restart — verify

Ten items. Nothing else.

| # | verify | expected |
|---|---|---|
| 1 | effective binding | `ADR0043_USER=3`, `ADR0043_ACCOUNT=3` **in the running process**, not just in the file |
| 2 | broker account | `PA34USW0Q8UO` |
| 3 | forbidden account | **not** `PA3QRX9KSPXA` |
| 4 | `WORKBENCH_SCHEDULER_ENABLED` | `false` |
| 5 | `WORKBENCH_LIVE_TRADING_ALLOWED` | `false` |
| 6 | loss-control mode | `ENFORCE` |
| 7 | image digest | **identical** to item 3 of the pre-capture |
| 8 | account-1 row digest + user-1 credential digests | **unchanged** from items 5–6 |
| 9 | open orders | `0` |
| 10 | HELD reservations | `0` |

Item 1 is the one that actually closes the defect: the file was never the problem, the *process
environment* was. Read it from the running process.

Any mismatch → **stop and report**. Do not re-run Repair B to "make it take."

---

## 4. Then, and only then

1. One sanctioned **scoped sync** for account 3 — dry run, read the evidence, then `--commit`.
   See `ADR0043_Account3_Scoped_Sync.md`.
2. **One** read-only reconciliation. If clean, proceed.

Three consecutive consistency observations are **no longer required** (superseded 2026-07-27):
after broker identity is confirmed, DB and broker positions match, open orders and HELD
reservations are zero, and account 1 is unchanged, repetition adds no evidence.

---

## Boundary

Repair B and the scoped sync produce a correctly-bound host with refreshed account-3 risk inputs.
They do **not** capture the authoritative baseline and do **not** authorize any Phase-0 broker
submission. Baseline capture happens in the next eligible session, and Phase-0 authorization is a
separate final GO.
