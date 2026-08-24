# Incident — credential exposure via conversation transcript (Workbench login passwords)

**Date:** 2026-08-24 · **Severity:** High (live paper-account credentials)
**Status:** **REMEDIATED** — 7/7 passwords rotated, all sessions revoked, verified. Pending only S3 seal + operator deletion of the exposing JSONL.
**Channel:** Claude Code conversation transcript (local JSONL) · **Repository exposure:** none

> **Sanitization rule for this document.** No password, TOTP seed, session token, command line
> containing a secret, or copy of the exposing transcript appears here or in any artifact it
> references. Counts, hashes, timestamps and attribution only.

---

## 1. One-line finding

While extracting a single credential field for an approved operational task, the agent rendered the
contents of `certs/workbench_logins.md` into the conversation transcript behind a masking filter that
failed, exposing **all seven Workbench account passwords in cleartext**.

## 2. What was exposed

| | |
|---|---|
| Fields rendered | `user id` · `email` · `password` |
| Accounts affected | **7** (users 1–7) |
| TOTP seeds | **NOT exposed** — the file has no TOTP column |
| Alpaca / broker credentials | **NOT exposed** |
| `WORKBENCH_MASTER_KEY`, AWS keys, GitHub credentials | **NOT exposed** |
| Repository exposure | **none** — `certs/` is gitignored (`.gitignore:74`); nothing reached Git |
| Exposure channel | conversation transcript, persisted to a local JSONL file |

⭐ **TOTP is independently out of scope**, verified two ways: the rendered table had only three
columns, and the database holds **no TOTP secret at all** — `users` carries only `totp_verified_at`,
while the seeds live encrypted in `user_credentials` (kind `totp_secret`). A copied-seed attack is
therefore not live from this incident. Scope was deliberately **not** widened to unrelated
infrastructure secrets, which were not present in the rendered material.

## 3. Root cause

The agent needed exactly one field from one line. Instead of extracting it in-process with no output,
it printed the file through a regular-expression masking filter. The filter keyed on characters the
passwords did not contain, so every value passed through unmasked.

Two aggravating factors, both recorded rather than excused:

1. The file's own header says never to paste its contents into a chat transcript, and records that
   these values were rotated on **2026-08-19 because of a prior transcript exposure**. This incident
   reproduces the one the file was rotated for.
2. The agent had itself raised transcript-exposure risk two messages earlier, then chose a display
   path whose safety depended entirely on the filter being correct.

**Correct method, now standing:** read a named field programmatically and print nothing. Never render
a credential file in order to verify a mask.

## 4. Authentication review — instrument and window

⚠ **Logins are not audit-logged.** No `LOGIN`/`AUTH`/`TOTP`/`SESSION` action exists in the
`AuditAction` enum, so the hash-chained `audit_log` is **not** the instrument here. Auth events are
emitted only to structlog on container stdout (`auth_login_success`, `auth_login_bad_password`,
`auth_login_bad_totp`). The reviewable window is therefore bounded by container lifetime.

**Window:** container created `2026-08-23T20:17:44.634887882Z` → capture. This fully covers the
exposure, which occurred on 2026-08-24.

| Event | Count in window |
|---|---|
| `auth_login_success` | **2** |
| `auth_login_bad_password` | **0** |
| `auth_login_bad_totp` | **0** |

⭐ **Amendment to the original "zero authentication attempts" formulation.** A pre-flatten capture at
`13:33:13Z` recorded 0/0/0, true as of that timestamp. The approved SEC-001 C5b flatten then executed
and produced two logins. The accurate claim is therefore **not** "zero attempts" but the stronger
**"every authentication event in the window is attributable, and failed attempts are zero"**:

```
user_id 5  ip 172.18.0.1  2026-08-24T13:37:52.801716Z   <- C5b dry run      (agent, approved)
user_id 5  ip 172.18.0.1  2026-08-24T13:38:28.953698Z   <- C5b live submit  (agent, approved)
```

`172.18.0.1` is the Docker bridge, consistent with the operator-side SSM port-forward. **No
unattributed login, and no failed authentication attempt of any kind, occurred in the window.**

**Final in-window totals after remediation** (see §7.3): `auth_login_success` **9** — the 2 above plus
7 from the post-rotation credential verification, every one agent-attributable —
`auth_login_bad_password` **0**, `auth_login_bad_totp` **0**. The invariant that matters holds
throughout: **zero failed authentication attempts, and zero logins not accounted for by an approved
action.**

## 5. Preserved evidence (no secret values)

Both artifacts live on the host volume, so they survive container restart — which matters because a
container recreate destroys the structlog window that constitutes the evidence.

| Artifact | SHA-256 | Bytes | Captured |
|---|---|---|---|
| `credexposure_auth_evidence_20260824T133313Z.json` | `4501d6ea615b63e14f138dbccb1e45e81e36768d417ea4115ec1044c14634631` | 1447 | 13:33:13Z (pre-flatten) |
| `credexposure_auth_evidence_final_20260824T134932Z.json` | `e4c53611be78b0eea3c5299178f492c60765425658d93d581ab0d0b62fa9803c` | 1710 | 13:49:32Z (final) |

Path: `/opt/workbench/data/` on `i-084f47fe4e69192e9`.

## 6. Live-session census before revocation

Sessions that are **unrevoked AND unexpired** — the 213 "unrevoked" figure is misleading because it
counts expired rows.

| user | live sessions | note |
|---|---|---|
| 3 | 2 | |
| **5** | **3** | was 1; +2 minted by the approved C5b flatten |
| 7 | 12 | |
| 1, 2, 4, 6 | **0** | nothing to revoke |
| **total** | **17** | |

`max(last_used_at)` before the flatten was `2026-08-23 02:50:18.026966Z` — no pre-existing session had
been used since well before the exposure.

This census was **re-taken immediately after the seventh rotation** and was still 17; that re-taken
figure, not an earlier one, is what was revoked (§7.2). **Post-remediation live count: 0.**

## 7. Remediation status

| # | Action | State |
|---|---|---|
| 1 | Re-census live sessions after the flatten | ✅ **DONE** (§6) |
| 2 | Preserve auth evidence before any restart | ✅ **DONE** (§5) |
| 3 | Rotate all **seven** exposed passwords | ✅ **DONE 13:56Z** (§7.1) |
| 4 | Revoke all live sessions for affected users | ✅ **DONE 13:57:54Z** — 17 revoked (§7.2) |
| 5 | Verify new credentials authenticate; live-session count = 0 | ✅ **DONE** — 7/7 PASS, live = 0 (§7.3) |
| 6 | Seal this closeout under the credential-exposure S3 prefix | ✅ **DONE 14:00Z** (§8.1) |
| 7 | Delete the local JSONL containing the plaintext exposure | ⬜ **OPEN** — operator action, now unblocked |

⭐ Ordering was honoured: **all seven rotations completed before any revocation**, so a revoked
session could not be re-established with a still-valid old password.

### 7.1 Rotation — method and proof

⛔ **`create_user.py` was rejected as the rotation path**, on inspection rather than on its name. It
*conditionally* mutates MFA:

```python
elif args.rotate_totp or not already_verified:
    secret = <fresh>;  await store.set(user.id, CredentialKind.TOTP_SECRET, secret)
```

`already_verified` depends on a successful decrypt-read of the existing seed. Any failure of that
read silently installs a **new** TOTP seed, breaking the authenticator. It also prints the seed to
stdout. Not a password-rotation tool.

⛔ **No password-change or admin-reset endpoint exists** anywhere in the API (searched
`apps/backend/app/api/v1/`), so the application-service route was unavailable.

✅ **Method used:** a purpose-built, password-only rotation reusing the application's own
`app.auth.passwords.hash_password` (bcrypt, `BCRYPT_COST = 12`, 72-byte limit).

- Seven **independent** 32-character secrets generated with `secrets.token_urlsafe(24)`; distinctness
  and length asserted.
- Generated **and hashed on the operator machine**; each hash self-verified with `verify_password`
  before transit. **Only the one-way bcrypt hashes crossed to the host** — no plaintext ever entered
  an SSM command body, instance command history, or OS argv.
- The update statement touched **`users.password_hash` only**, with `rowcount == 1` asserted per user
  inside a single `BEGIN IMMEDIATE` transaction. The transit hash file was deleted from the container
  afterwards.

**Identity invariant — `user_id + email + display_name + created_at + totp_verified_at + totp_secret_rows`:**

```
IDENTITY_DIGEST before : 3cbb1379bd289cf6a6d126883912d6b544472b5b40e2497da3d814150ee0f4f5
IDENTITY_DIGEST after  : 3cbb1379bd289cf6a6d126883912d6b544472b5b40e2497da3d814150ee0f4f5
                         ^ byte-identical
```

All 7 password hashes changed; `totp_verified_at` unchanged for all 7; `totp_secret_rows` remained
exactly 1 for all 7. **Direct proof that rotation neither re-enrolled MFA nor altered account
identity.**

### 7.2 Session revocation

Final census taken **immediately after the seventh rotation** (not the earlier figure): 17 live —
user 3 = 2, user 5 = 3, user 7 = 12. All **17 revoked** at `2026-08-24T13:57:54Z`; post-revocation
live count **0**.

Revocation set `sessions.revoked_at`, the identical mutation performed by `/auth/logout` and
`/auth/sessions/{id}/revoke`. Auth resolves the session token against the database on every request,
so revocation takes effect immediately with no cache to invalidate. (198 rows remain `revoked_at IS
NULL` but are **already expired** and cannot authenticate; the meaningful metric is
unrevoked **and** unexpired = 0.)

### 7.3 Verification

New credentials, one account at a time through the authenticated login endpoint:

```
user 1..7  ->  HTTP 200   (7/7 PASS)
```

The 7 sessions minted by that check were themselves revoked immediately afterwards; **final live
session count is 0** and the post-rotation identity digest still matches `3cbb1379…`.

⭐ **Old-credential rejection is established cryptographically, not by replay.** Every stored hash is
now a bcrypt digest of a different, independently generated 32-character secret (distinctness
asserted), so `checkpw(old_password, new_hash)` cannot succeed. Replaying an exposed password to
"prove" it fails would have re-entered the secret into tooling for no evidentiary gain — the hash
change is the stronger proof.

Login events across the whole container window afterwards: `auth_login_success` **9**
(2 × approved C5b + 7 × this verification, all agent-attributable), `auth_login_bad_password` **0**,
`auth_login_bad_totp` **0**.

⚠ **Known gap, unchanged by this incident:** a credential rotation still produces **no audit-log
row**. This is the fourth recorded instance. The rotation above is evidenced by this document and the
identity digests, not by the hash chain.

## 8. Custody — deliberately separate from SEC-001

This closeout and its artifacts seal under

```
s3://workbench-evidence-incidents-219024422756/credential-exposure/2026-08-24/
```

**not** `sec001/…`. The bucket is Object Lock **COMPLIANCE** — every write is permanent for seven
years and cannot be deleted by anyone, including root. Filing a credential incident inside the
SEC-001 evidence prefix would conflate two unrelated incidents **irreversibly**, so the evidentiary
distinction is enforced by prefix.

⛔ **Never** place in S3 evidence: plaintext password values, command lines containing them, or the
exposing JSONL itself. ⛔ **Never** place a write probe inside an evidence prefix (see the SEC-001
incident §8.1 for the seven-year cost of that mistake).

### 8.1 Sealed custody — 2026-08-24 14:00Z

Bucket `workbench-evidence-incidents-219024422756`, prefix `credential-exposure/2026-08-24/`.
Object Lock **COMPLIANCE**, retain-until **2033-08-22**. Every S3 checksum was decoded and compared
against the locally computed SHA-256: **all three MATCH**.

| Object | SHA-256 | Bytes | VersionId |
|---|---|---|---|
| `closeout_2026-08-24_credential-exposure.md` | `7cf1793da28261ffa8ba8f4b661bbe736f269414d9156113b1415f9a896f7ed9` | 13064 | `VZeR6KXqXR8R.1aed9kWVy31x8Z2E4ne` |
| `credexposure_auth_evidence_20260824T133313Z.json` | `4501d6ea615b63e14f138dbccb1e45e81e36768d417ea4115ec1044c14634631` | 1447 | `ZgYFMmzRT4SfMKPggDZkIitY.DwnSqbz` |
| `credexposure_auth_evidence_final_20260824T134932Z.json` | `e4c53611be78b0eea3c5299178f492c60765425658d93d581ab0d0b62fa9803c` | 1710 | `Pc.gEcv877.RTEKfzYN3W5ciG6kC_Po1` |

A prefix listing confirms **exactly these three objects and nothing else** — no write probe was placed
inside the evidence prefix.

⭐ The sealed copy of this document is the state as of 14:00Z, which still lists step 6 as open (it
could not describe its own sealing). This Git working copy is the live record; the S3 object is the
point-in-time seal. Both were verified secret-free by an automated scan against the *current*
credential file immediately before upload: 0 passwords, 0 bcrypt hashes, 0 base32 blobs.

## 9. The exposing artifact

```
C:\Users\jayw0_ithkvux\.claude\projects\C--LLM-RAG-APP-ai-trading-app\
    33cfe675-e23a-4084-a13c-745d77be056c.jsonl
```

Local, plaintext, operator-controlled. ⭐ There is **no ChatGPT conversation and no OpenAI retention
path** — deleting one would remove nothing. Deleting this file is the equivalent action. It also
destroys `/resume` continuity for the session, so this closeout must carry everything needed for
continuity before deletion (step 7).

## 10. Related, but out of scope for today

The **user-5 TOTP seed stored in plaintext** in the agent memory file `sec001_production_started.md`
was **not** exposed by this incident, and the encrypted store already holds that seed. Owner ruling:
treat as a standing **credential-hygiene defect**, not part of this incident — after containment
closes, re-enroll that TOTP seed and replace the memory-file text with a non-secret statement such as
*"TOTP configured; secret stored in approved credential store."* A long-lived plaintext MFA seed
defeats much of the value of MFA even when unexposed.

## 11. Unaffected

SEC-001 containment is **closed and unaffected**: C5b and C6 both PASS, account 5 is flat
($99,262.44, all cash), strategy 7 remains `IDLE`, and that incident's evidence is sealed under
`sec001/2026-08-24/` with an independent Object Lock retention.
