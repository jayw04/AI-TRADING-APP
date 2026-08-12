# Defect record — ADR0043_B4_CREDENTIAL_NEAR_COMMIT

- **Date:** 2026-08-03
- **Severity:** **CAUGHT PRE-COMMIT SECRET-HANDLING DEFECT** — contained before repository exposure
- **Component:** working draft of `apps/backend/tests/scripts/test_adr0043_b4_credential_staging.py`
- **Status:** CLOSED — contained, verified, permanent preventive test added

> ⚠ **This record deliberately contains no credential material.** The successor credential is
> referred to only by its one-way fingerprints (`sha256(value)[:12]`), which are already published
> in the effective authorization. Do not add a value to this file or to any attachment.

## Summary

While building the B4 credential-staging checkpoint, the live successor API key and secret were
temporarily placed into an **uncommitted local test draft** in order to exercise the fingerprint
logic against real values. That is the wrong place for them: a test file is a repository artifact,
and the next `git add -A` would have committed both.

They were **removed before staging and before any commit**. Nothing was staged, committed, pushed,
or included in a PR. The repository was never exposed.

The draft was then rebuilt around **synthetic fixtures** — the functional tests rewrite the
harness's expected fingerprints to those of clearly-labelled synthetic strings, so the real
`stage`/`verify` logic is exercised end to end without any live value entering the repository.

## Why it happened

The fingerprint check is the substance of B4, and the obvious way to convince yourself it works is
to run it against the thing it will actually see. The correct move — fingerprints are one-way, so a
synthetic value with a recomputed expectation exercises identical logic — is only obvious in
retrospect. Nothing about the staging design required a live value at any point.

## Containment and verification

| Step | Result |
|---|---|
| Live values placed in an uncommitted draft | yes — the defect |
| Removed before `git add` / commit | yes |
| Staged, committed, pushed, or in a PR | **no** |
| Synthetic fixtures substituted | yes |
| Alpaca-shaped-key meta-test added | yes |

The scan was **re-run independently for this record** rather than transcribed, and by fingerprint
rather than by string match — which does not require the value to be present in order to search for
it:

```
files scanned         : 2151   (all tracked files at this commit)
tokens fingerprinted  : 159133
matches for ffab8796516a (successor API key)    : NONE
matches for c2cab6509f1b (successor API secret) : NONE
```

Every `[A-Za-z0-9/+_.~-]{16,80}` token in every tracked file was hashed and compared against both
governed fingerprints. Neither credential value appears anywhere in the repository.

> The initial review cited 2,156 tracked files; the measured count at this commit is **2,151**. The
> difference is the commit the scan ran against, not a change in coverage — both scans covered the
> complete tracked set. The measured figure is recorded here in preference to the quoted one.

## Permanent prevention

`test_no_real_credential_material_in_this_test_file` asserts that no Alpaca-shaped key
(`\bPK[A-Z0-9]{18,}\b`) appears in the B4 test file. It guards the guard: the failure mode was a
live value pasted into *this specific file*, so the test lives in that file and fails on
recurrence.

The staging script reinforces the same boundary structurally — the credential is read from
`/dev/tty` with echo disabled and is never accepted from an argument, an environment variable, or
piped stdin, so there is no ergonomic path that puts it in a shell history, a CI variable, or a
transcript.

## Separate pre-existing observation — NOT this incident

The verification sweep surfaced an unrelated finding worth its own disposition: a plaintext
Alpaca-shaped key for the **legacy canary** account is committed in
`apps/backend/tests/scripts/test_adr0043_install_canary_credentials.py:22`.

- Its fingerprint is **`2acf8e9c0c0d`** — it is **not** the successor credential
  (`ffab8796516a`), despite sharing the 26-character shape.
- It predates this work and is outside the WS5 successor authorization's scope.
- No action taken here. Flagged for the owner to rule on separately; rotation of canary material is
  governed by its own authorization, not by this checkpoint.

## Assessment

The near-commit was serious. The response was appropriate: containment happened before repository
exposure, the full tracked set was scanned by a method that does not depend on possessing the
value, and a permanent test now fails on recurrence.
