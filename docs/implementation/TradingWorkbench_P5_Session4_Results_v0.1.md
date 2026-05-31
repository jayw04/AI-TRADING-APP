# P5 Session 4 — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-31 |
| Phase | P5 §4 — Credential Encryption (companion to `TradingWorkbench_P5_Session4_v1.0.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#NN** — branch `feat/p5-session4-credentials`; tag **`p5-session4-complete`** |
| Built against | `main` at `p5-session3-complete` (`66c19b0`) |
| Verdict | **GO.** All §4 sections implemented and **executed** locally: crypto + store + migration round-trip, the four swaps (broker / agent / webhook / auth), the credentials API + UI, the eighth CI invariant, and 29 new tests. Full backend suite green (419 passed, 9 skipped); all eight invariants pass; ADR 0002 invariant test still green; frontend `tsc --noEmit` + ESLint clean. Live-runtime smoke (§4.14) is deferred to WSL/CI per the standing Norton + no-Docker posture. |
| Method | **Executed** (not static): pytest with `--cov-branch`, the migration upgrade/downgrade/upgrade round-trip against a copy of the dev DB, the CI invariant positive+negative, ruff, and the frontend typecheck/lint were all run on the dev box. |

> **Doc-version note.** Implementation followed the **v1.0** session doc
> (`TradingWorkbench_P5_Session4_v1.0.md`), which had already reconciled the
> eleven v0.1 drifts against the shipped Sessions 1–3. The gates below are
> scored against what v1.0 required.

---

## Statically- and dynamically-verified gates — PASS

| § | Gate | Result |
|---|---|---|
| 4.1 | `scripts/generate_master_key.py` + key in `.env` | ✅ Python script (Fernet); 44-char key generated and appended to the git-ignored root `.env` |
| 4.2 | `app/security/crypto.py` — `encrypt`/`decrypt`/`verify_master_key` | ✅ cached Fernet, clear errors for missing/invalid key; `_reset_cache_for_tests` for the suite |
| 4.3 | `app/security/credential_store.py` — get/set/revoke/list/hard_delete_revoked | ✅ `CredentialKind` (StrEnum), `CredentialMetadata` (no plaintext), `_ensure_aware` SQLite coercion; reads touch `last_used_at` |
| 4.4 | `user_credentials` table + data migration | ✅ model + migration `b7e3c1a9f5d2`; **upgrade/downgrade/upgrade round-trip verified on a copy of the real dev DB**, encrypt-on-move + plaintext-restore both confirmed |
| 4.5 | Boot refuses without master key | ✅ `verify_master_key()` runs first in `lifespan` (before broker registry); `sys.exit(1)` on `MasterKeyMissingError` |
| 4.6 | `credentials_for_mode()` async + store-backed | ✅ now `async (mode, user_id, session_factory)`; `BrokerRegistry._construct/_try_construct/load_all/refresh` propagate `await`; router→adapter call path untouched |
| 4.7 | AgentRuntime per-user Anthropic key from store | ✅ `_get_anthropic_key(user_id)`; `start_session` validates, `_do_turn` reads per turn; no process-global key |
| 4.8 | TV webhook constant-time match vs store | ✅ `_authenticate_webhook` decrypts each active user's secret, `hmac.compare_digest`; `users.py` rotate/get swapped to the store too |
| 4.9 | Auth/login + TOTP setup/verify + `create_user.py` via store | ✅ all read/write `CredentialKind.TOTP_SECRET`; `totp_verified_at` stays on `users` as a status flag |
| 4.10 | `/api/v1/users/me/credentials/` (GET/PUT/DELETE) | ✅ TOTP excluded from PUT/DELETE; broker-kind PUT refreshes the registry; plaintext never in GET |
| 4.11 | Settings → Credentials page | ✅ `api/credentials.ts` + `pages/Settings/Credentials.tsx` (card per kind, set/rotate/revoke, password field cleared after submit); route behind the existing `RequireAuth` wrapper; Settings index links to it |
| 4.12 | `check_no_env_credentials.sh` (eighth invariant) | ✅ created, positive + negative tested, wired into `ci.yml` after broker isolation |
| 4.13 | New tests + suite + invariants | ✅ 29 new tests; **419 passed / 9 skipped**; risk branch-rate 0.905 (≥0.85); P2/P3 gates OK; eight invariants OK; ADR 0002 test green |
| — | `app/auth/future.py` deleted (S3 close-out) | ✅ `git rm`; stale coverage `omit` entry removed from `pyproject.toml` |
| — | Dep added | ✅ `cryptography>=42,<46` in `pyproject.toml`; installed `45.0.7` in the venv |

---

### Deliberate deviations (as-built vs the v1.0 plan)

Sensible deviations, not gaps:

- **`CredentialKind` is a `StrEnum`, not `(str, Enum)`.** Matches the project's
  `AccountMode` convention and satisfies ruff `UP042`. `.value` is used at every
  call/DB site, so behavior is identical.
- **Migration acquires the master key *before* any DDL.** The v1.0 sketch
  created the table first, then checked the key. Moving `_fernet()` to the top
  of `upgrade()`/`downgrade()` means a missing key aborts with **zero schema
  changes** — eliminating the half-migrated-DB risk Gotcha #2 warns about.
  Verified: with no key, the migration raises and `user_credentials` is not
  created.
- **Credentials router wired via the central `app/api/v1/__init__.py`** (the
  codebase's actual pattern), not `main.py` as the v1.0 sketch showed. Full
  path is `/api/v1/users/me/credentials/` either way.
- **Frontend uses `apiFetch` + React Query**, not the doc's `apiClient.get/put`
  sketch (which doesn't exist in this codebase). The whole app already sits
  behind `RequireAuth` in `main.tsx`, so the new route needs no extra guard.
- **`users.py` (Pine secret rotate/get) was also swapped** to the store. The
  v1.0 §4.8 named only `alerts.py`, but the write side lives in `users.py`; both
  had to move for "no code reads `users.pine_webhook_secret`" to hold.
- **`load_credentials()` and `config.py` left as-is.** Only `credentials_for_mode`
  was the §4 swap-point. The startup bootstrap adapter still loads paper creds
  from env via `load_credentials()`; the CI invariant only forbids
  `os.environ.get(<credential-name>)` reads (none exist), so this is in-policy.

---

## Findings / punch list

- [ ] **§4.14 live-runtime smoke — deferred (no committed evidence).** The four
  load-bearing flows (login, paper order, agent live call, Pine webhook) have
  **in-suite** coverage exercising the credential-store path, but the live
  curl/diff against a running stack was not run here (Norton SSL blocks
  `data.alpaca.markets`; no local Docker). **Action:** run §4.14 in WSL/CI before
  promoting the tag to a release.
- [ ] **Operational note: `WORKBENCH_MASTER_KEY` must be in the process env**,
  not just `.env`. The backend, the migration, and `create_user.py` all read it
  via `os.environ` directly (by design, per §4.2). docker-compose `env_file`
  handles this; local runs must export it. Documented in
  `docs/runbook/credentials.md`.
- [ ] **`scripts/rotate_master_key.py` is documented but not shipped** (P5+
  polish, explicitly out of §4 scope). Rotation is currently a careful manual
  operation against a backed-up DB.

---

## Deferred gates — require a live stack (run in a working / non-Norton env)

- [ ] **§4.14** login + paper order + agent + webhook end-to-end against a
  running backend, post-§4.
- [ ] **Migration on the real production DB** — `alembic upgrade head` with the
  master key exported (verified here only against a *copy* of the dev DB).
- [ ] **Eight CI invariants green on CI** (they pass locally; confirm on the PR run).
- [ ] **Frontend `vite build`** — `tsc --noEmit` + ESLint pass locally; the full
  production build wasn't run (no behavioral change expected).

---

## To close Session 4 cleanly (Jay, in a working env)

1. Run §4.14; note the results (login cookie, paper order routes, agent live
   call, webhook authenticates) — even a short runbook note.
2. Run the migration against the real DB with `WORKBENCH_MASTER_KEY` exported;
   confirm the env broker/Anthropic keys land in `user_credentials` for user 1
   and that the agent/broker still work reading from the store.
3. Confirm the PR's CI run is green including the new credential env-isolation
   invariant.

The code is merged and tagged (`p5-session4-complete`); these are close-out
items, not blockers. Next up per the P5 plan: **§5 — live-mode risk gates.**

---

*P5 Session 4 results v0.1 — recorded 2026-05-31.*
