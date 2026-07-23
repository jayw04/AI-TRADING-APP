# Runbook — ADR-0043 Canary Scaffold (user 3 + account 3)

**Purpose.** Create the isolated ADR-0043 canary identity — **and only that** — on the validation
host: `user_id=3` and `account_id=3` (`broker=alpaca`, `mode=paper`, `label="ADR-0043 canary"`). The
momentum user 1 / account 1 and every credential are left byte-identical. No positions, orders,
reservations, loss-control/breaker events, strategies, or risk-limit rows are created.

This scaffold does **not** install broker credentials (that is the separate Gate-B step:
`store.set(3, ALPACA_PAPER_KEY/SECRET, …)`) and does **not** require a backend restart — it only
inserts two DB rows plus SQLite id-sequence repair.

## Preconditions (the tool enforces these; it fails closed if any is false)
- user 1 exists; account 1 exists (momentum, untouched)
- user 2 / account 2 existence is reported (not required either way)
- user 3 does not exist; account 3 does not exist; user 3 has no credentials
- 0 open orders; 0 HELD reservations
- On a rerun: user 3 + account 3 must match the frozen canary identity **exactly**, else it stops
  with a specific error — it never edits rows into conformance.

Keep `WORKBENCH_ALPACA_STARTUP_ENABLED=false`, scheduler and live trading disabled.

## Procedure (on the validation host `i-01527ac7b7c7efa35`)

1. **Back up the DB first** (whole-file, the authorized recovery point):
   ```
   sudo bash /home/ubuntu/adr0043_db_backup_restore.sh backup \
     /opt/workbench/data/workbench.sqlite /home/ubuntu/adr0043_preflight_backup
   ```
2. **Record the DB SHA-256 before**:
   ```
   sudo sha256sum /opt/workbench/data/workbench.sqlite
   ```
3. **Dry run** (writes nothing — runs the full checked flow then rolls back). Confirm the evidence
   shows `mode: created`, `created: ["user:3","account:3"]`, `protected_unchanged: true`, and
   `counts_after` still `open_orders:0 / held_reservations:0 / integrity:ok`:
   ```
   sudo docker exec workbench-backend python -m scripts.adr0043_canary_scaffold
   ```
4. **Apply** (single transaction; commits only if every invariant holds):
   ```
   sudo docker exec workbench-backend python -m scripts.adr0043_canary_scaffold --apply
   ```
5. **Record the DB SHA-256 after** (it WILL change — two rows added; the protected user-1 / account-1
   / credential digests in the evidence must be unchanged):
   ```
   sudo sha256sum /opt/workbench/data/workbench.sqlite
   ```
6. **Verify**:
   ```
   sudo python3 - <<'PY'
   import sqlite3; c=sqlite3.connect("file:/opt/workbench/data/workbench.sqlite?mode=ro",uri=True)
   print("users:", c.execute("SELECT id,email,display_name FROM users ORDER BY id").fetchall())
   print("accounts:", c.execute("SELECT id,user_id,broker,mode,label FROM accounts ORDER BY id").fetchall())
   print("acct1 unchanged (momentum):", c.execute("SELECT label FROM accounts WHERE id=1").fetchone())
   print("integrity:", c.execute("PRAGMA integrity_check").fetchone())
   PY
   ```
   Expect user 3 (`adr0043-canary@localhost`, "ADR-0043 Canary") + account 3 (user_id 3, alpaca,
   paper, "ADR-0043 canary"); account 1 still `Alpaca Paper`; integrity ok.

## Rollback

Nothing else references the two new rows yet (no credentials, positions, or orders). Rollback is
either:

- **Whole-file restore** (preferred, from step 1's backup):
  ```
  sudo bash /home/ubuntu/adr0043_db_backup_restore.sh restore \
    <backup>.bak /opt/workbench/data/workbench.sqlite
  ```
- **Targeted delete** (only the two canary rows; verify user 1 / account 1 first):
  ```
  sudo python3 - <<'PY'
  import sqlite3; c=sqlite3.connect("/opt/workbench/data/workbench.sqlite")
  c.execute("DELETE FROM accounts WHERE id=3 AND user_id=3 AND label='ADR-0043 canary'")
  c.execute("DELETE FROM users WHERE id=3 AND email='adr0043-canary@localhost'")
  c.commit(); print("deleted; users:", c.execute("SELECT id FROM users ORDER BY id").fetchall())
  PY
  ```

## After the scaffold
Proceed to the separately-authorized Gate-B credential install for **user 3** (canary `PKZYTY…`
paper key/secret, supplied via a root-only `0600` file), then the one-shot read-only Alpaca discovery
(`GET account`/`positions`/`open orders`, bound to `ADR0043_USER=3 ADR0043_ACCOUNT=3`). Local
positions/risk reconciliation and a new canary baseline remain separately gated.
