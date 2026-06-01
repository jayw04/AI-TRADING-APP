# P5 Session 8 — Results (go / no-go record) · **closes P5**

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-01 |
| Phase | P5 §8 — Production Hardening (companion to `TradingWorkbench_P5_Session8_v0.2.md`); **final P5 session** |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#46** — branch `feat/p5-session8-production-hardening`; tags **`p5-session8-complete`** + **`p5-complete`** |
| Built against | `main` at `p5-session7-complete` (`6a3a10e`) |
| Verdict | **GO — P5 is closed.** Immutable hash-chained audit log (DB triggers + per-user SHA-256 chain + integrity verifier + CI invariant), subsystem-aware `/healthz`, Prometheus `/metrics` (12 metrics + 30s snapshot job), structured-log credential redaction, daily SQLite backup + restore, and the deployment + on-call runbooks are all implemented and **executed**. Backend **568 passed / 9 skipped**; risk 0.904 / p2 / p3 gates; mypy clean (142); ruff clean; **6 shell invariants** (incl. the new `check_audit_immutability`) + ADR 0002 green. Migration `f2a7c1d9e4b6` backfill + down/up round-trip + integrity verify all clean on an isolated DB. **§8.9 manual smoke + §8.10 live cross-session verification deferred** (Norton + no Docker); the in-suite equivalents stand in. |
| Method | **Executed** (not static): full pytest, the migration backfill/round-trip on a stamped isolated DB, `verify_audit_integrity.py` against migrated data, `backup_db.sh` against a dev-DB copy, the 6 shell invariants + ADR 0002, mypy, ruff. `prometheus_client` installed from PyPI (not Norton-blocked) and added to `pyproject.toml`. |
| `p5-complete` basis | Per the developer's explicit decision, `p5-complete` is tagged on the **in-suite stand-in** (full suite + 6 shell invariants + ADR 0002 + audit-immutability tests + 3 coverage gates, all green). The live Docker §8.10 walkthrough is recorded as carry-forward. |

> **The v0.2 doc was candid that §8 had the largest drift surface of any P5
> session and listed the verifications to run first.** It was right. The
> deviations below are the reconciliation — the most consequential being that
> `AuditLogger` is async-ORM (not the doc's sync raw-SQL) and the `audit_log`
> columns are `ts`/`payload_json` (not `created_at`/`payload`).

---

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 8.1 | Immutable audit log | ✅ `row_hash`/`prev_hash` columns; per-user SHA-256 chain populated by a **`before_insert` mapper event** (not a `write()` rewrite); `audit_log_no_update`/`audit_log_no_delete` triggers via **`after_create` DDL** (so `create_all` in tests AND the migration both install them); migration `f2a7c1d9e4b6` backfills + round-trips; `verify_audit_integrity.py`; `check_audit_immutability.sh` (6th shell invariant). |
| 8.2 | `/healthz` | ✅ 5 subsystem checks (database, master_key, broker_registry, scheduler, circuit_breakers_clear); `fail`→503, `degraded`/`ok`→200; legacy `db` key preserved; intentionally-off subsystems (alpaca disabled) report `disabled` (non-degrading). |
| 8.3 | `/metrics` | ✅ 12 Prometheus metrics; order counter + duration histogram via a thin `submit` wrapper (logic untouched); LIVE counter; auth-failure + broker-error counters; `metrics_snapshot` job (30s) populates gauges. |
| 8.4 | Log redaction | ✅ `redact_processor` (5 pattern families) wired into `configure_logging` before the JSON renderer. |
| 8.5 | Daily backup | ✅ `scripts/backup_db.sh` (SQLite `.backup`, integrity check, 30-day prune) + `scripts/restore_db.sh` (refuses while backend up); scheduled 02:00 (scheduler tz). |
| 8.6 | Deployment runbook | ✅ `docs/runbook/deployment.md` (clone → first paper order; reverse-proxy note). |
| 8.7 | On-call playbook | ✅ `docs/runbook/on-call.md` (the dozen §1–§8 failure modes, skim format). |
| 8.8 | Tests | ✅ **20 new tests** (6 audit-immutability + 4 healthz + 2 metrics + 8 redaction); existing `test_health.py` updated to the §8 `fail`-on-db-down contract. |
| — | CI invariants | ✅ 6 shell (new `check_audit_immutability.sh` wired into `ci.yml`) + ADR 0002 pytest + 3 coverage gates. |

---

## Deliberate deviations (as-built vs the v0.2 plan)

The v0.2 §8.1/§8.3 were sketches against an imagined shape; reconciled to live
code and **executed**:

- **`AuditLogger.write` is async-ORM, not sync raw-SQL.** It takes an
  `AsyncSession` and does `session.add(row)`; the columns are **`ts`** (not
  `created_at`) and **`payload_json`** (not `payload`), with a stringified
  `target_id` and an `ip` column the doc didn't mention. The §8.1.3/§8.1.4 hash
  module + write rewrite were rebuilt to this shape.
- **Hash chain via a `before_insert` mapper event, not a `write()` rewrite.**
  This keeps every `AuditLogger.write` call site a plain `session.add` (zero
  churn, paper path untouched) and sets `row_hash` BEFORE the INSERT so the
  no_update trigger never fires. **`id` is excluded from the hash** (it's a
  post-INSERT autoincrement; `prev_hash` already detects reordering/deletion) —
  so the doc's `MAX(id)+1` atomic-insert dance is unnecessary.
- **Chain ordering invariant: rows link in COMMIT order.** Every write call site
  commits one row at a time, so `prev_hash` reads the last committed row. (A
  batch of audit writes for one user in a *single* flush would be unchained —
  the ORM batches those INSERTs; no code path does this. Documented in the model
  and enforced-by-convention.)
- **Triggers installed via `after_create` DDL**, so they exist for both
  `Base.metadata.create_all` (tests use create_all, NOT migrations) and the
  migration's `op.execute` (prod). `IF NOT EXISTS` keeps the two paths from
  colliding. The doc's §8.1.5 "wipe audit_log" fixture is **unnecessary** —
  every test gets a fresh in-memory DB.
- **No pre-existing audit-immutability pytest.** The doc assumed Session 7 left
  one; it didn't (the `-k immutab` match was the ADR-0002 test's `adr0002`
  alternation). §8.1's tests are net-new — no conflict, no duplication.
- **`/healthz` already existed** (a basic inline probe in `main.py`); §8.2
  replaces it with the router version, **preserving the legacy `db` key** and
  treating intentionally-off subsystems (`alpaca_startup_enabled` false) as
  `disabled` so the test harness stays `ok`. The existing `test_health.py`
  db-down case was updated from `degraded` to the §8 `fail` semantics.
- **Order metrics via a `submit` → `_submit_inner` wrapper**, not hooks threaded
  through the submission body — the ADR-0002 path is byte-identical; metric
  failures are swallowed. Account mode for the label is read with one extra
  indexed PK get rather than threading it out of the logic.
- **`prometheus_client` was absent** (the doc guessed it might be present);
  installed from PyPI and added to `pyproject.toml`.
- **Dev DB journal mode is `delete`, not WAL.** The hash insert's atomicity
  relies on SQLite being single-writer (true in either mode), so this is
  immaterial to correctness; the runbook still recommends WAL for production.
- **Order-path tests are router-level** (the order_router isn't on `app.state`
  under the test harness) — same pattern as §6/§7.

---

## Findings / punch list

- [ ] **§8.9 manual smoke + §8.10 live cross-session verification — deferred.**
  The healthz/metrics/backup/audit-immutability surfaces have in-suite coverage,
  but the live `docker compose down -v / up` + curl walkthrough (and the
  byte-identical paper-order smoke) were not run: no Docker + Norton blocks
  Alpaca. **Action:** run §8.9/§8.10 in WSL/CI before promoting to a release.
- [ ] **`broker_api_errors_total` covers 5 adapter methods** (submit/cancel/
  replace/get_account/get_positions); other read methods (list_assets/get_order/
  list_orders) are not yet counted. Low value; add if needed.
- [ ] **Scheduler jobs (metrics_snapshot, daily_backup) run only when
  `alpaca_startup_enabled`** (they're wired in that lifespan block, alongside
  activation_completion). In a no-broker diagnostics boot they won't run. Matches
  the existing job-wiring convention; revisit if a broker-less prod mode appears.
- [ ] **`p5-complete` tagged on the in-suite stand-in** (developer's decision),
  not the live §8.10 walkthrough. The phase is closed in code; the live
  walkthrough remains the one outstanding confidence step.

---

## Deferred gates — require a live stack (run in a working / non-Norton env)

- [ ] §8.9 manual smoke; §8.10 full cross-session §1–§8 verification + paper
  byte-identical smoke.
- [ ] Migration on the **real** prod DB (verified here on an isolated stamped DB;
  note the real dev DB is itself stale at `8c1e26e3d0a6` — migrations were never
  run against it across §4–§8, a pre-existing carry-forward).
- [ ] 6 CI invariants + ADR 0002 + audit-immutability green on CI for the merge commit.
- [ ] Frontend `vite build` (no §8 frontend changes; last green at §7).

---

## To close P5 cleanly (Jay, in a working env)

1. Run §8.9 + §8.10 in WSL/CI (paper-as-live), including the byte-identical
   paper smoke.
2. Run the migration against the real DB (and catch it up through §4–§8).
3. Confirm the post-merge CI run is green.

**P5 is complete.** Next phase: **P6 — agent intelligence layer** (review /
propose / drift / NL→Python, all advisory; gated behind P5 + P5.5). Do not start
P6 work without an explicit go.

---

*P5 Session 8 results v0.1 — recorded 2026-06-01. Closes Phase 5.*
