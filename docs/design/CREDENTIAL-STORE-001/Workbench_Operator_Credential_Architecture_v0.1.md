# CREDENTIAL-STORE-001 — Workbench operator credential architecture (v0.1)

| Field | Value |
|---|---|
| Status | **DESIGN APPROVED CONCEPTUALLY (owner rulings 2026-09-02) — no implementation, no credential migration, no bulk rotation** |
| Date | 2026-09-01 (drafted) · 2026-09-02 (rulings incorporated) |
| Finding remediated | `WORKBENCH-PLAINTEXT-CREDENTIAL-STORE-001` — seven current live Workbench passwords stored in plaintext on the developer laptop (`certs/workbench_logins.md`, gitignored, never in Git) |
| Owner direction (Ruling 10, reaffirmed 2026-09-01 and 2026-09-02) | **C first** — eliminate the need for seven recoverable local passwords. **A second** — OS-native secret storage (Credential Manager / DPAPI) only for residual secrets that genuinely remain. Do not build a better bulk-secret vault for a workflow that should no longer need seven passwords. |
| Companion finding | `CREDENTIAL-ROTATION-TOOL-CUSTODY-001` (§7) — the proven hash-only rotation tool exists only untracked on the laptop |
| Separate and prior | The Account 6 credential incident (2026-09-01) is **NOT CONTAINED** and does not wait for this design (§8). |
| Authority granted | **None.** |

---

## 1. Why the store exists — four root causes, not one file

The plaintext file is a symptom. Six exposures in nine weeks (07-28, 08-03, 08-19, 08-24, 08-26, 09-01)
came through three different channels — agent renders, a human editor selection, and a chat paste —
which is the evidence that fixing agent behaviour or encrypting the file does not close the class.
The file exists because four properties of the platform force a human to hold seven recoverable
passwords (owner, 2026-09-02: this framing is accepted):

| # | Root cause | Measured in code |
|---|---|---|
| R1 | **Account identity doubles as human identity.** Every per-user surface is scoped by `current_user.id` (positions, orders, strategies, discovery). There is no role, admin, or delegation concept (`User` has `email`, `password_hash`, `totp_verified_at`; no role column; no `is_admin` anywhere in `app/`). To operate account N, the operator must *be* user N. | `app/auth/stub.py::get_current_user`; `app/db/models/user.py`; `accounts.user_id`, `strategies.user_id` |
| R2 | **Automation authenticates with human passwords.** The Strategy-9 transition executor reads a box-local password file; `range-healthcheck.sh` reads a root-only password file to log in as the range user; `paper_activate_momentum.py` and `provision_momentum_daily.py` take `--password` on argv (one docstring embeds an example password). | `deploy/aws/range-healthcheck.sh:14,43`; `apps/backend/scripts/paper_activate_momentum.py:20,96,150`; `provision_momentum_daily.py:93,126`; `ops/acct7/user7_password.txt` |
| R3 | **No first-class rotation endpoint.** `auth.py` exposes login / logout / me / totp setup+verify / session revoke only. Rotation is a direct write to `users.password_hash` from a script; `create_user.py` prints the generated password and can silently re-seed TOTP. The proven hash-only tool (`scripts/rotate_user_passwords.py`) is **untracked** (§7). | `app/api/v1/auth.py`; `scripts/create_user.py:169` |
| R4 | **No safe out-of-band secret retrieval.** A secret that lives only on the box, with no password-manager entry, is always retrieved *through the agent* and therefore lands in a transcript (2026-07-31, user 7). Rotation resets the clock; it does not change the topology. | memory record `security-shared-password-compromise-2026-07-28` |

Two further facts shape the design:

- **Login TOTP is disabled** (`WORKBENCH_LOGIN_TOTP_REQUIRED=false` on the box; the UI hard-codes
  `LOGIN_TOTP_DISABLED = true`). Passwords are currently the *only* login factor. Step-up TOTP on
  consequential actions is unaffected and stays.
- **No audit row exists for any credential event.** `AuditAction` has no LOGIN / PASSWORD /
  CREDENTIAL / SESSION value; auth events exist only as structlog on container stdout, bounded by
  container lifetime. Four rotations have happened with no hash-chain record.

---

## 2. The three options compared (owner asked for A / B / C)

### A. Windows Credential Manager / DPAPI for local operator credentials

| | |
|---|---|
| What it gives | Per-entry storage; at-rest encryption bound to the Windows user; no *bulk* file to render; standard tooling (`cmdkey`, PowerShell `CredentialManager` module, Python `keyring`). |
| What it does **not** give | Protection from the operator's own session. DPAPI user-scope decrypts for **any process running as that Windows user** — including the agent's Bash/PowerShell tools. `Get-StoredCredential` from an agent session would put the plaintext into the transcript exactly as `cat` does today. Enumeration is one command. |
| Fit | Correct for **residual** secrets a human genuinely must type (the operator's *own* password, an AWS profile, short-lived break-glass material). Wrong as a home for seven per-account passwords: it changes the file format of the failure, not the failure. |
| Verdict (ruled) | **A — residual only.** No bulk-read verb. No plaintext export. Pair with a Bash/PowerShell permission rule that denies credential-manager read verbs to agent sessions — a control, not a structure, so it cannot be the primary mechanism. |

### B. An existing server-side encrypted/managed-secret mechanism compatible with Workbench

| | |
|---|---|
| Already present | `user_credentials` — Fernet-encrypted per-user store (ADR 0003) keyed by `CredentialKind`, with `revoked_at` and `updated_at`, already holding Alpaca keys, TOTP seeds, Pine webhook secrets and **two bearer-token kinds** (`WORKBENCH_MCP_KEY`, `AGENT_API_KEY`) that `get_current_user` resolves to a user with constant-time matching. AWS SSM Parameter Store / Secrets Manager on the box. |
| What it gives | Machine identities can authenticate **without a password**: a per-user bearer credential is minted server-side, stored encrypted, revocable by row, and never needs to exist on the laptop. |
| What it does **not** give | It does not remove the *human* login problem. A server-side vault still requires the operator to retrieve a value to type into a login page — R4 again. |
| Verdict (ruled) | **B — the mechanism for R2 (automation).** Reuse of the existing `CredentialKind` resolver is acceptable **if the semantics and revocation model are appropriate** — §3 states them. Not a solution for R1/R4 on its own. |

### C. Is any local password storage actually necessary once operator workflows are improved?

| Sub-option | Mechanism | Removes |
|---|---|---|
| **C1 — automation identity** | New `CredentialKind.OPERATOR_AUTOMATION_KEY` (per user, encrypted, revocable, `updated_at`), **scoped to the required function** (a `scope` field, e.g. `transition-executor`, `healthcheck-rearm`), issued by a governed box-side script that **writes the token straight into the consuming 0600 file and prints nothing**. Executor, healthcheck and provisioning scripts authenticate with `Authorization: Bearer`, which `_resolve_from_bearer_token` already supports once the kind is added to `_BEARER_KINDS`. Human passwords are never reused for automation. | R2 entirely: no password on the box, no `--password` argv, no password in any script docstring |
| **C2 — first-class, audited rotation** | `POST /auth/password/rotate` (current password + step-up TOTP → new hash), and a governed **reset** path for the operator-side case (the custodied hash-only tool, §7). New `AuditAction` values with playbook scenarios. | R3; a rotation leaves a hash-chain record for the first time |
| **C3 — assume-account capability** | The operator authenticates once as their own principal (user 1, TOTP). A governed `POST /auth/assume/{user_id}` — allowed only for principals listed in an `operator_grants` table, step-up TOTP, mints a **scoped session** for user N whose row records `assumed_by = 1`, short TTL, audit-logged as `SESSION_ASSUMED` with **operator identity → target account → action → reason/context → timestamp/result**. The operator manages the account **without learning its password**. Every per-user surface keeps scoping by `current_user.id`; nothing else in the app changes. | R1 for the human: one password (their own) plus TOTP; users 2–7 need no human-typed password |
| **C4 — password elimination for users 2–7** | Once C1 + C3 exist, users 2–7 have no human login path that needs a memorized or stored password **where the business workflow does not genuinely require one**. Their `password_hash` is set to a random value that is **never recorded anywhere**. Break-glass = the governed reset script (C2), which mints a fresh hash on demand and writes it into Credential Manager (A) only for the duration of the incident. | R4: there is nothing to retrieve, so nothing to leak. "Do not merely rotate seven passwords forever." |

**Verdict (ruled): C is the design.** After C1–C4, "local password storage" reduces to the operator's
own password (memorized or in Credential Manager) — one entry, one human, one factor plus TOTP.

---

## 3. Target operating model (approved conceptually 2026-09-02)

```
HUMAN / OPERATOR IDENTITY   one principal authenticates as a human (user 1 · own password + TOTP)
                            authorization decides which strategy/account operations it may perform
                            → assume account N (step-up TOTP, short TTL, audited)                   [C3]

AUTOMATION IDENTITY         non-human, function-scoped bearer credential per user in user_credentials
                            (encrypted, revocable, updated_at); presented from a 0600 box file written
                            by the issuer script, never printed; never a human password              [C1]

USERS 2-7                   no recoverable operator-facing password; hash of a discarded secret       [C4]
BREAK-GLASS                 governed reset mints a fresh hash on demand; hash-only transport;
                            any temporary plaintext lives in Credential Manager (A) and is revoked after   [C2/A]
TOTP                        seeds stay Fernet-encrypted in user_credentials; never in any local file
ROTATION                    one account at a time; no argv secrets; no stdout secrets; audit row per event  [C2]
RESIDUAL SECRETS            Credential Manager / DPAPI only: operator's own credential, short-lived
                            break-glass material, other irreducible local secrets; no bulk-read verb,
                            no plaintext export                                                          [A]
```

**Bearer-credential semantics required for the `CredentialKind` reuse to be acceptable (B):**
function scope enforced at the endpoint layer (an automation key cannot mint a session cookie or
call `/auth/assume`); revocation by `revoked_at` bites on the next request (auth resolves against the
DB every call — already true for sessions); issuance/revocation audited; a revoked or expired key can
never be re-enabled, only re-issued.

---

## 4. Migration sequence (one account at a time; Account 6 first because it is already the incident)

| Step | Action | Plaintext handling | Verification |
|---|---|---|---|
| 0 | **Account 6 containment** (operator, now, independent of this design) — §8 | Operator only; the agent never sees the value | Agent: stored hash ≠ old; sessions census = 0 live; file line absent; repo clean — fingerprints only |
| 1 | Custody the hash-only rotation/verification tooling (§7) — its own security PR | None | Tests prove no secret output |
| 2 | Land C1 (bearer kind + issuer script) and C2 (rotation endpoint + audit actions) — Tier 3 (auth + audit + migration) | None | Issuer prints nothing (capsys); token resolves to the intended user and scope; revoked token 401s; audit rows present |
| 3 | Switch each automation consumer to bearer: transition executor (acct 7), `range-healthcheck.sh` (acct 2), provisioning scripts | Issuer writes the box file directly | Login probe returns the intended `user_id`; old password file deleted; `rule-credential-rotation-resync-local-files` acceptance = login-tested |
| 4 | Land C3 (`operator_grants`, assume endpoint, scoped sessions) — Tier 3 | None | Assume without TOTP fails; assumed session is scoped to N; `SESSION_ASSUMED` audit present with all five fields; TTL enforced |
| 5 | For each of users 2–7: rotate to a discarded secret (C4), revoke sessions, **delete the line** from `certs/workbench_logins.md` | Never generated into any file | Hash changed; no live sessions; line absent |
| 6 | When the file has no lines left, delete it; purge the stale `User Information.txt` lines and the plaintext TOTP seed noted in the SEC-001 memory | — | `certs/` contains no credential material |
| 7 | Owner decision: re-enable login TOTP for the single remaining human login | — | — |

Each step is its own PR or its own operator action; none is combined with SIP, Strategy 8, Strategy 9,
B3, or Mechanism C work.

---

## 5. Explicitly rejected

- **Encrypting `certs/workbench_logins.md` in place.** Preserves the bulk-read operation and the
  seven-secret topology; the decrypt step is exactly where the next exposure happens.
- **A bulk vault with a "list all" verb** as the primary store. Same objection.
- **Rotating all seven now and writing seven fresh values back into the same file.** Resets the clock,
  preserves the failure mode (owner ruling, 2026-09-01).
- **Automating the rotation from an agent session.** The agent has no compliant transport for a secret
  laptop→box (`read -rs` needs a human TTY); relaxing that so an agent can rewrite the file recreates
  the exposure class. **Owner ruling 2026-09-02: do not modify permission rules to let an agent rewrite
  the plaintext credential file automatically.**

---

## 6. Rulings received 2026-09-02

| Item | Ruling |
|---|---|
| Direction | C then A — accepted |
| Root-cause framing (R1–R4) | Accepted as stated |
| Human/operator identity | One human principal; authorization determines permitted account operations; no per-strategy recoverable password merely to act administratively |
| Automation identity | Non-human, function-scoped tokens; never human passwords; `CredentialKind` reuse acceptable with appropriate semantics and revocation (§3) |
| Assume-account | Audited action under authorization, without learning the account's password; audit fields as in C3 |
| Password elimination | Users 2–7: no recoverable operator-facing password where the workflow does not genuinely require one |
| Residual secrets | Credential Manager / DPAPI for the operator's own credential, short-lived break-glass, other irreducible local secrets; no bulk-read verb, no plaintext export |

Still open for the implementation PRs: the operator principal is user 1 (assumed here); `operator_grants`
seeded by a governed script; the exact `AuditAction` set (`CREDENTIAL_ROTATED`, `SESSION_REVOKED`,
`SESSION_ASSUMED`, `AUTOMATION_KEY_ISSUED`, `AUTOMATION_KEY_REVOKED`) with playbook scenarios; step 7.

---

## 7. `CREDENTIAL-ROTATION-TOOL-CUSTODY-001`

```
= IDENTIFIED
= PROVEN TOOL EXISTS ONLY UNTRACKED ON LAPTOP
= CUSTODY REQUIRED BEFORE IT BECOMES GOVERNED REMEDIATION TOOLING
```

`scripts/rotate_user_passwords.py` (hash-only rotation, 2026-08-19 and 2026-08-24 rotations) is not
in Git. It must not be used as though it were governed production tooling because it worked before.
A **separate, narrowly scoped security PR** — not folded into B3 or Mechanism C — will custody:

- the hash-only rotation tooling and the read-only verification tooling, **as separate commands**
  (rotation action vs verification never share an entry point);
- tests, including explicit **no-secret-output guarantees** (capsys/caplog assert nothing
  secret-shaped is emitted), **no argv plaintext** (secrets are generated in-process or read from a
  0600 file, never from the command line), and **no log lines containing secret material**;
- a documented operator procedure (runbook `docs/runbook/credentials.md` section), including the
  hash-only laptop→box transport and the "login-tested, not file-updated" acceptance rule.

---

## 8. Account 6

```
ACCOUNT-6 CREDENTIAL INCIDENT = NOT CONTAINED
```

No further plaintext inspection. The untracked rotation script's existence does not change containment
status. Containment is operator work, in order: secure rotation → authoritative hash update → revoke
existing sessions → eliminate or securely resync the local secret representation → **then** the
agent's hash/fingerprint-only verification. Until rotation occurs, the exposed password is treated as
live-compromised.
