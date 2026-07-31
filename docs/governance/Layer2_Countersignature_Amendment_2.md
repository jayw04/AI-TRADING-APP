# Layer 2 countersignature — Amendment 2

**Scope: the deployed narrow-readiness attestation contract only.** The prior countersignature and
Amendment 1 remain effective. This amendment does **not** change the governed corpus, the corpus
manifest, the July 27 decision, the quarantine disposition, or the deployment conditions.

| | |
|---|---|
| amends | countersignature package `72b98dbb40f8eadae16e91799062dd378f43b64738e814176a839aa3601817c5` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| deployed commit at failure | `7d8af096fcf0f06e08d4936100e9e7a3546b375d` |
| amended | 2026-07-31 |

## 0. Governance status

```
LAYER 2 CORPUS COUNTERSIGNATURE :  REMAINS VALID
FAILED ITEM                     :  the deployed readiness-attestation IMPLEMENTATION,
                                   NOT the corpus construction

JULY 27 PHASE C
  READINESS        : NOT VALIDATED
  CAUSE            : UNSATISFIABLE PAYLOAD-COMPLETENESS GUARD
                     AND STALE RELEVANCE-SET ATTESTATION
  FAIL-CLOSED      : PASS
```

The deployed runtime refused an internally inconsistent attestation rather than adapting itself to
pass. That is the control working, and it is the reason this defect was found on the box rather than
in a live observation.

## 1. What failed

Phase C ran the full deployed readiness path for session 2026-07-27 against the installed countersigned
corpus. It returned `NOT_READY_ADJUSTMENT_UNVERIFIED` with two refusals.

### Defect 1 — the guard checked the wrong completeness property

```
total_action_count     1764
max_actions             200   (MAX_EVIDENCE_ACTIONS, production observation cap)
omitted_action_count   1564
truncated              True
```

Clause (5) required `truncated == false`. `truncated` describes only the bounded per-action **detail**
carried in the immutable receipt; `checks_by_status` is computed over **every** check *before*
bounding. Truncation therefore says nothing about whether an action was assessed.

Against 1,764 relevant actions and a 200-action cap the clause was **structurally unsatisfiable in
production**, and was only ever satisfied by a diagnostic that raised the cap in its own process. It
gated nothing where it mattered and blocked everything where it ran.

### Defect 2 — the census described a different set of securities

| | diagnostic runner | deployed readiness path |
|---|---|---|
| relevant identities | 689 | **670** |
| assessed actions | 1,791 | **1,764** |
| `PROVEN_REFLECTED` | 1,676 | 1,670 |
| `PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE` | 94 | 91 |
| `PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT` | 3 | 3 |
| `UNRESOLVED_NONDECISION_MA_SEMANTICS` | 18 | **0** |

`expected_status_counts` was carried from a **diagnostic** runner that assembled its own relevance set.
Both censuses were internally consistent; only one described the session. Nothing in the contract could
detect the divergence, because the two sets were never compared.

The `0` is a consequence, not a second defect: the 18 adjudicated acquired-side events are not inside
the readiness relevance set, so those checks do not exist on this session.

## 2. The corrected contract

### Census completeness replaces payload non-truncation

`truncated == false` is **removed** as a requirement. In its place, clause (5) requires:

```
sum(checks_by_status.values()) == total_action_count
omitted_action_count           == total_action_count - len(serialized_action_checks)
truncated                      == (omitted_action_count > 0)
len(serialized_action_checks)  <= max_actions
max_actions                    <= MAX_EVIDENCE_ACTIONS
```

`serialized_action_checks` is measured on the list actually carried, not on the count the record claims
for it. The last clause is new and deliberate: an evidence object bounded at a **raised** cap is a
diagnostic record, and a diagnostic must not be able to satisfy a production readiness contract — which
is precisely how the July 27 attestation came to exist.

```
PRODUCTION EVIDENCE CAP :  UNCHANGED AT 200
CENSUS COMPLETENESS     :  REQUIRED
PAYLOAD NON-TRUNCATION  :  NOT REQUIRED
```

`data_finality` imports `MAX_EVIDENCE_ACTIONS` from `adjustment_verifier` rather than restating it, so
one number governs both the bound and the clause that checks it.

### The attestation is derived, never carried

`NarrowReadinessAttestation` gains a **required** `relevance_set_sha256`, and clause (7) refuses any
attestation whose relevance-set digest differs from the one this assessment constructed — checked
*before* the counts, because it is the clause that explains them. An attestation carrying no
relevance-set binding is refused outright: unattributed counts are not evidence about anything.

`build_narrow_readiness_attestation()` is the single derivation path. It runs the identical production
assessment, captures the relevance set at the one boundary it crosses, and derives the digest and the
census from that one run. It binds: session date, scoring universe, proxy relevance set, relevance-set
digest, the resulting relevant identities, the status-count census, the quarantine digest and the
limitation/disclosure digest.

⛔ It is **not** reachable from `assess_data_finality`, and a source-level test pins that. An assessment
that derived its own expectations would agree with itself by construction and the staleness clause
would prove nothing. What makes the derivation honest is that its output is an artifact — reviewed,
published, digest-bound — consumed by a later independent run that re-derives every clause.

The diagnostic runner may remain useful for research. It must not produce production-readiness
expectations unless it invokes the identical relevance-set builder.

### Corpus-wide adjudication is not a session limitation

An event the readiness relevance set never contains cannot limit a decision that set produced. The two
figures are now reported side by side and never collapsed:

```
known corpus-wide unsupported semantics :  18
present in July 27 readiness relevance set :  0
```

`nondecision_limitations_present` is derived from the measurement. It is not held true to preserve an
earlier expected result, and not held false to make a session look cleaner. A reason code that fired
zero times is no longer listed as a finding.

The **active** July 27 limitation is therefore the governed SHOP/TLN quarantine — 4 unexplained factor
movements, all on quarantined permanent identities excluded from the decision path — not the M&A
semantics. The narrow verdict's detail text is now assembled from what was actually measured rather
than asserting a fixed sentence about economically terminal actions.

## 3. Expected July 27 outcome under the corrected contract

```
ready                        true
fully_proven                 false
has_disclosed_limitations    true
full_action_semantics_proven false
```

`fully_proven` stays false and **must** stay false: quarantined unexplained movements remain. The flag
combination is derived from evidence; it is not a target. If the evidence does not support the narrow
claim, the run refuses — as it just did.

## 4. What is unchanged

Every other ruling, wording requirement and artifact identity in the countersignature, the complete
package and Amendment 1 stands — including the SHOP/TLN quarantine language, the loader requirements
and the conditions precedent to deployment. The corpus, its manifest and the July 27 decision are
untouched.

```
ACCOUNT 4        :  UNCHANGED — DISABLED
FORWARD WINDOW   :  CLOSED
OBSERVATION 1    :  NOT AUTHORIZED
```

After this increment is green, exact-head merged and deployed, Phase C is rerun **once**. The corpus
reconstruction and Steps 2–7 are not repeated.
