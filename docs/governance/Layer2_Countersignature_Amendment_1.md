# Layer 2 countersignature — Amendment 1

**Scope: reporting and provenance metadata only.** The prior countersignature remains effective subject
to this amendment. It does **not** change the governed corpus, the corpus manifest, the July 27
decision, the quarantine disposition, or the deployment conditions.

| | |
|---|---|
| amends package | `72b98dbb40f8eadae16e91799062dd378f43b64738e814176a839aa3601817c5` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| supersedes | `a69ad50ffc3c6925b3c9b6c8fd1c2adc7143ef9d5c98e9378e1c3ea21ca75c49` — **unchanged** |
| amended | 2026-07-30 |

## 1. Builder equivalence — RESOLVED

The producer-provenance gap recorded in the countersignature is closed by an independent rebuild from
identical sealed inputs.

```
original producer bytes : UNAVAILABLE
preserved builder       : ed212e787ea6edd0b3acac48d6656582f8237ff68689952566c512b754e3eae2
status                  : INDEPENDENTLY PROVEN VALUE-EQUIVALENT
equivalence basis       : INDEPENDENT REBUILD FROM IDENTICAL SEALED INPUTS
equivalence verdict     : VALUE_IDENTICAL_WITH_EXPLAINED_PHYSICAL_DIFFERENCE
platform limitation     : WINDOWS-PATH DEPENDENT
```

**Inputs proven identical before the run:** sealed vintage CSV digests match the recorded
`row_set_identity_sha256` for SEP, ACTIONS and TICKERS; the superseded corpus used as the read-only
quarantine source hashes to `2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87`, exactly
the `superseded_corpus_sha256` the original build recorded.

**What reproduced.** Both governed universe digests (`fd2c843a…` mapped / `34e426e4…` price); all guards
G1–G5; the universe reconciliation 14,150 → 14,145 → 5 → 2 → 14,143 with 0 unadjudicated; the quarantine
of 7 histories / 17,143 rows; `dataset_coverage` in every column except `recorded_at`; and `ingest_runs`
including the **deterministic, source-vintage-derived `run_id`** and `started_at`.

**Row counts, confirmed by direct query of both stores:**

```
SEP      39,125,482
TICKERS      14,143
ACTIONS     286,087
```

**Bidirectional table comparison — zero differing rows in either direction, for all three tables.** This
is the decisive evidence and is what establishes equivalence.

**Physical difference, fully attributed.** The store file hash differs (`5960a0f7…` countersigned vs
`d3719da2…` rebuild). It is accounted for entirely by wall-clock and path metadata:

- `ingest_runs.finished_at` — build wall clock;
- `dataset_coverage.recorded_at` — build wall clock;
- build evidence `built_utc`, and `store.path` (the rebuild used a scratch output directory by design).

The build-evidence documents differ in exactly **three leaves** — `built_utc`, `store.path` and
`store.store_file_sha256`. Every identity, count, guard and load record is identical. The residual byte
difference is DuckDB physical page layout.

### Platform limitation

The preserved builder is **Windows-path dependent**: its recorded-path rebase uses `Path(rec).name`,
which on Linux does not strip a Windows absolute path. A non-Windows run requires the recorded CSV paths
to resolve by other means. Recorded as a known limitation of the preserved artifact; no remediation is
made here.

## 2. Experimental value identity — RETRACTED

```
store_value_identity_sha256 455a7b0c…   RETRACTED
replacement                              NONE — DEFERRED
registered store_identity()              UNCHANGED
```

The extended whole-corpus value identity introduced in the supersession package is **withdrawn from all
active governance claims**. It was never part of the registered runtime contract, and it was not
well-defined: its ordering was not total over a table containing identical duplicate rows, so the same
data could yield different digests. It must not be cited, and no replacement is defined in this
increment.

Equivalence does not depend on it. It rests on exact table counts, bidirectional zero-row differences,
reproduced universe digests, the registered evidence identities, quarantine reconciliation, and the
deterministic `run_id` / `started_at`.

⚠ The superseded-vs-rebuilt value-identity comparison reported in the supersession package used the same
withdrawn definition and is likewise retracted. The two corpora do differ; that particular figure did not
establish it.

The registered `data_finality.store_identity()` is unaffected and remains the runtime proof.

## 3. Everything else preserved

Every other ruling, wording requirement and artifact identity in the countersignature and the complete
package stands unchanged — including the SHOP/TLN quarantine language, the headroom wording, the
winsorization-tie note, the loader requirements, and the 13 conditions precedent to deployment.

The equivalence build log and its digest are preserved in governed artifact storage, not in Git.
