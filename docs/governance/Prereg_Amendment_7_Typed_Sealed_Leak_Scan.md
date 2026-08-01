# Preregistration Amendment 7 — typed leaf equality in the §5.4 sealed-leak scan

**Scope: one comparison inside `assert_open_record_has_no_sealed_content`, its regression tests, and
nothing else.** The corpus, countersignature, quarantine policy `76fc2606…`, v1.1 attestation
`9edcd472…`, the reviewed pre-commit package `22b14ff3…`, the outcome-pin expectations, the sealed
and open record schemas, the NAME scan, evaluation logic, Account 4 and the store are untouched.

| | |
|---|---|
| supersedes measurement commit | `1c73d442e3461530fbda59c9051d023102a291b6` (chain continues) |
| reason | `SUBSTRING_FALSE_POSITIVE_IN_SEALED_VALUE_SCAN` |
| amended | 2026-08-01 |

## 0. Governance status

```
OBSERVATION 1        :  STILL UNWRITTEN - the 2026-08-01 pinned commit run stopped at THIS gate
PIN APPROVAL         :  UNCONSUMED - receipt shows matched: true on both digests
ACCOUNT 4            :  UNCHANGED - IDLE, HOLD ACTIVE
FORWARD WINDOW       :  CLOSED
RUN 3                :  REMAINS THE REVIEWED PRE-COMMIT REFERENCE
```

## 1. What failed

The first pinned Observation 1 commit run (deployed `8a7659c0…`) reproduced the reviewed outcome
exactly — the Amendment 6 pin receipt records `matched: true` on both digests — and was then refused
by the commit protocol's sealed-value scan:

```
OBSERVATION_NOT_COMMITTED — OPEN record leaks a sealed value: 0.98
```

The scan tested each sealed value by **substring over the serialized document**:
`str(0.98) in json.dumps(open_record)`. The open record's `data_finality` provenance legitimately
carries per-action price marks, two of which are `90.98` and `350.98` — and `"0.98"` is a substring
of both. Sealed turnover is 0.98. **No sealed value appears in the open record**; digits of a larger
number are not a disclosure of the sealed one.

The false positive is structural, not incidental: any session whose relevance window contains any
price ending in `.98` collides with a seed turnover of 0.98. The July 27 commit could never pass the
gate as written. The gate was reachable only from the commit protocol, which the pre-commit driver by
design never exercises — the same class of gap as the external-freeze omission, surfaced the same
way: fail-closed, nothing written.

## 2. The ruling (owner, 2026-08-01)

Typed recursive leaf equality replaces the serialized-substring scan for VALUES:

| sealed | open-record leaf | verdict |
|---|---|---|
| `0.98` | numeric `90.98` / `350.98` | **allowed** — not the value |
| `0.98` | numeric `0.98` | refuse |
| `0.98` | string `"0.98"` | refuse — canonical spelling discloses it |
| `98` | numeric `98` | refuse |
| `0.98` | string `"90.98"` | allowed |
| `0.98` | string `"…was 0.98…"` (free text) | **allowed** — free-text scanning is not separately governed |
| numeric `0` / sealed anything | bool `False`/`True` | never compared — bool is not numeric here |
| sealed NaN / ±inf | anything | **deterministic refusal** — a sealed payload carrying one is malformed |
| any | exact leaf nested in lists/dicts | refuse |

No tolerance-based comparison: the gate detects disclosure of an exact sealed value, never
approximate similarity. No `Decimal` appears in these records; the sealed serialization contract
(`json.dumps(sort_keys, separators)`) is unchanged. **The NAME scan is unchanged** — a sealed field
name appearing anywhere in the serialized record, including free text, still refuses.

### 2.1 Disclosed relaxation

Two pre-existing tests encoded the substring semantics as free-text leaks
(`"return was 0.0137"`, `"session return was -0.0042"`). Under this ruling those are **allowed**;
both tests were reshaped to the exact-leaf form so they still pin the true-leak property (an exact
value smuggled through `note`/`operational_exceptions` refuses, nothing committed). This is the only
behaviour the amendment relaxes, and it is stated here rather than left to be discovered in a diff.

## 3. Verification

Owner's required matrix implemented verbatim in `test_first_session_atomic_open.py` (including the
measured `90.98`/`350.98` collisions), plus the reshaped recorder test proving the refusal commits
nothing. The scan's position is unchanged — inside the atomic commit protocol, before any
observation write, sequence allocation, `commit.json`, or durable-ledger mutation — and the
existing atomic-open/recorder suites continue to pin that ordering.

## 4. Post-fix execution (authorized sequence)

Exact-head CI green → squash merge (main #1377 must be green first) → redeploy the full unit
(runtime + freeze trio + ancestry marker) → rebuild evidence → identity PASS → **run the pinned
production commit once** → both pin digests must match → atomic Observation 1 commit → verify
committed holdings and hash chain. No new standalone pre-commit evaluation. The configuration —
including the unconsumed pin block (`acc9a9fa…`) — is unchanged by this amendment.
