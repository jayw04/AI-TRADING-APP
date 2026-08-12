# Preregistration Amendment 2 — measurement-instrument re-freeze

**Scope: the measurement-instrument binding only.** PREREG v1.0 otherwise stands unchanged.

| | |
|---|---|
| supersedes measurement commit | `764883b58cb96936f23e49182dd02b70d969501b` (2026-07-22) |
| ratified measurement commit | `d13310a32227c67163250566eca719d5f734dd53` (2026-07-31) |
| deployed-tree verification | 619/619 files verified, 0 carriage-return bytes |
| post-merge CI | run 1361 — success (full matrix, push to `main`) |
| reason | `AUTHORIZED_MEASUREMENT_INSTRUMENT_EVOLUTION_REQUIRED_FOR_GOVERNED_CORPUS` |
| amended | 2026-07-31 |

## 1. Why the original binding could never hold

The §0 freeze stored the expected measurement identity as a constant **inside the code it pinned**:

```python
VALIDATION_MEASUREMENT_COMMIT = "764883b5…"   # in app/validation/forward_window.py
```

This is a fixed point with no solution. Changing the constant produces a new commit, so the constant
can never name the commit that contains it; each attempt to correct it produces another commit needing
another correction. The binding was therefore **guaranteed to drift**, and it did — 28 authorized
commits moved the measurement code past the frozen SHA.

The drift is not a lapse in discipline. Every one of those increments was authorized and countersigned
individually. What was missing was any mechanism by which the pin *could* have been updated truthfully.

A second defect compounded it. `build_forward_context` declared:

```python
code_commit: str = VALIDATION_MEASUREMENT_COMMIT,   # the EXPECTED value, as the default ACTUAL value
```

Unless a caller overrode it, the gate compared the constant to itself and passed unconditionally. **A
check that cannot fail is not a check**, and this one had never been exercised against a real
deployment identity.

## 2. Why the frozen commit cannot simply be redeployed

At `764883b5` the entire Layer 1 / Layer 2 apparatus does not exist:

```
app/validation/governed_corpus.py     ABSENT
app/validation/security_lineage.py    ABSENT
app/validation/data_finality.py       ABSENT
```

That code cannot load the countersigned corpus, run a readiness assessment, or produce an attestation.
Leaving the original binding in force would make the governed program **permanently non-executable**:
the pinned instrument cannot measure the corpus that the subsequently authorized increments require.

## 3. What is ratified

The measurement-code evolution from `764883b5` through `d13310a`, comprising:

- witness protocol v2 and immutable-evidence work (KMS signer, S3 Object-Lock sink, Steps 4A–4D);
- ACTIONS-ingest prerequisites A1–A4;
- **ADR 0048** — governed corpora as an immutable base plus ordered, countersigned deltas;
- **PR #542** — security-lineage contract; permanent-identity resolution;
- **PR #577** — Layer 2 governed-corpus reconstruction and native loading;
- **PR #581** — census-complete narrow readiness and exact relevance-set attestation.

The complete commit list is generated, not narrated: `manifests/forward/ratified_increments.json`,
bound by digest in the freeze manifest.

## 4. What is NOT changed

This is a **measurement-instrument re-freeze**. It does not modify:

| | |
|---|---|
| the strategy | unchanged |
| ranking rules | unchanged |
| frozen parameters (`FROZEN_CONFIG`) | unchanged — including `regime_gross_above` 0.98 and `initial_seed_investable_gross` 0.60 |
| forward start | 2026-07-24, unchanged |
| benchmark identities | unchanged |
| trial ledger / DSR trial count | unchanged (`b7d9d715…`, N=45) |
| DGS3MO snapshot and cutoff | unchanged (`87d8ba2f…`, 2026-07-21) |
| shadow capital and costs | unchanged ($100,000, 10.0 bps) |
| Account-4 isolation | unchanged — the gate still refuses Account 4 as the ledger |

## 5. The replacement binding

The expected identity moves to a governed manifest **outside the tree it pins**:
`manifests/forward/measurement_freeze.json`. Editing it does not change the validation tree, so there
is no fixed point, and expected and actual values can genuinely disagree.

Two bindings, because neither alone suffices:

**`measurement_commit`** — the last ratified measurement-code commit. Required to be an **ancestor** of
the deployed HEAD, proving the deployment descends from ratified history. Deliberately *not* required
to equal the HEAD: a later documentation- or manifest-only commit changes the HEAD without changing
executable content.

**`validation_tree_sha256`** — the **controlling** identity. An exact digest over the executable
measurement content (`app/validation/**/*.py`), computed from file bytes. Ancestry alone would admit
any descendant, including one that rewrote the verifier; exact content equality does not.

The included path set is defined **positively** (`MEASURED_PATHS`), not as "everything except the
manifest". The manifest is outside the set because it lives in a different tree, not because it was
carved out.

### 5.1 The canonicalization contract

The manifest names the algorithm that produced its digest, so a digest computed under different rules
is not silently compared against one computed under these:

```
validation_tree_identity_algorithm:  PATH_SORTED_SHA256_CRLF_TO_LF_V1
```

Pinned rules — each enforced and each covered by a test:

| Rule | Behaviour |
|---|---|
| membership | only the positively enumerated `app/validation/**/*.py`; adding or removing a file moves the digest |
| ordering | paths sorted deterministically; input order does not affect the result |
| binding | both the **relative path** and the normalized content, so a rename moves the digest |
| line endings | CRLF → LF, **and nothing else** |
| whitespace | **not** trimmed — leading, trailing and blank lines are content |
| Unicode | **not** normalized — NFC and NFD are different content |
| BOM | **not** stripped — a BOM is content |
| lone CR | **REFUSED**, never normalized |
| undecodable text | **REFUSED**, never re-encoded with replacement characters |
| final newline | presence preserved |

The refusals are load-bearing. Normalizing a lone CR, or decoding with `errors="replace"`, would let
two *different* sources produce the *same* identity — the one property a content identity must not
have.

### 5.2 Transport integrity is a separate question

The content identity asks "is this the ratified **source**?". A second check asks "did checkout or
archive processing alter the committed **bytes**?" — answered by comparing the deployment against an
authoritative per-file byte manifest (`manifests/forward/measurement_bytes.json`, digest-bound as
`byte_manifest_sha256`), derived from the committed git blobs.

It is a general comparison, **not** a carriage-return scan: a CR scan would catch only the
transformation already observed, while a byte comparison catches any of them — re-encoding, BOM
insertion, whitespace stripping, smudge filters, a substituted file.

A deployment can be semantically correct and byte-altered at once. That is exactly what happened:
`git archive` under `core.autocrlf=true` rewrote 581 of 592 deployed `.py` files; the runtime ran
(Python tolerates CRLF) and the bytes were not the committed bytes. A Windows working tree may satisfy
the content identity while failing the byte check — correct, since only the deployed artifact must
satisfy the transport condition.

### 5.3 One implementation, not two

The generator **imports** `tree_identity` / `canonicalize` from the runtime module rather than
transcribing them. A generator holding its own copy of the rules is a second implementation that can
drift, and a manifest produced by a drifted generator would pin a digest no deployment could ever
reproduce. A test re-derives the committed `validation_tree_sha256` from the working tree through the
same versioned implementation, so the manifest cannot have come from a one-off command.

Additional controls:

- **`code_commit` has no default.** Every production caller must supply the actual deployed HEAD;
  omission is a fail-closed preflight error. The composition root supplies
  `verify_deployment_identity(...).agreed_commit` — evidence-derived, with dirty-tree refusal — never
  a caller assertion.
- **No environment variable or command-line flag may override the expected values.** They come from
  the manifest and nowhere else.
- Ancestry is verified by git where a repository exists, and otherwise by a deploy-time attestation
  naming both commits. Where neither is available the check **fails closed** rather than assuming a
  descendant.
- The superseded constant is retained as `SUPERSEDED_VALIDATION_MEASUREMENT_COMMIT` — **history, never
  a binding** — and a test asserts `preflight` does not read it.

## 6. Boundary

This amendment resolves the measurement-commit mismatch and nothing else. In particular it does **not**
make 2026-07-24 ready. The standing session record is unchanged:

```
2026-07-24     INELIGIBLE_UNRESOLVED_ADJUSTMENT_EVIDENCE
               reason: UNRELIABLE_CLOSEADJ_AT_MOMENTUM_WINDOW_LEFT_EDGE
               observation sequence: NOT ASSIGNED

Observation 1  2026-07-27  (own session-bound readiness and attestation still required)

Account 4      IDLE — operational hold ACTIVE
Forward window CLOSED
Sequence 1     UNWRITTEN
```
