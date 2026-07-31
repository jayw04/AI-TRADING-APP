# EVIDENCE-GAP Acquisition Stage 3 — No-Bindable-Corpus Construction Refusal

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE3-001 |
| Mode | **NO_BINDABLE_CORPUS_CONSTRUCTION_REFUSAL** |
| Capture ID | `20260731T002055Z` |
| Freeze body SHA-256 | `af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e` |
| Stage 1 merge | `561e52409eda6c552029da20113caa211aba2256` |
| Stage 2 merge | `3f256bb2affae631c22eed72a0f54b2e10aabadd` |
| Stage 2 report SHA-256 | `aac5b599f16324d12a91ca792dc406063d68c7628d1eec9a27b47fde66e3fb0c` |
| Substantive candidate construction | **false** |
| Gate campaign basis | **false** |
| Rows emitted | **0** |
| Missing surfaces reconstructed | **false** |

## Source pins (bound)

| Pin | SHA-256 |
|-----|---------|
| Sqlite | `9e40a9ad2f0176acf884140594ddfa9e946e42d2723794f464bbb0efdc2d9db6` |
| bar_cache | `b32e118732669c2880291cd0a7226589e4b0e2ef20839dc8172c26ce51e0adc7` |
| market_projection | `c0148389daa4139dd60a5921d6bec55a224a4156fb7cca080cc2b8fdfb7eb2c1` |
| O5 evidence tree | `1c209b068e89456dbdbb8f380fc8672d0b3d04d1460752e12d32dd8717832d26` |

## Stage 2 reason-code counts (bound exactly)

| Reason code | Count |
|-------------|------:|
| `MISSING_CUTOFF` | 5 |
| `MISSING_DECISION_TIME_QUOTE` | 292 |
| `MISSING_FORENSIC_BASELINE` | 292 |
| `MISSING_PROVENANCE` | 292 |
| `MISSING_REPLAY_SURFACE:checkpoint_tuple` | 292 |
| `MISSING_REPLAY_SURFACE:loss_accounting_inputs` | 292 |
| `MISSING_REPLAY_SURFACE:quote_provenance` | 292 |
| `MISSING_REPLAY_SURFACE:recovery_inputs` | 292 |
| `O4B_INCOMPLETE` | 6 |

## Outcomes

| Package | Result | Artifact |
|---------|--------|----------|
| O3 | **REJECTED_AS_NON_BINDABLE** | `O3_CONSTRUCTION_REFUSAL.json` |
| O4-A | **REJECTED_AS_NON_BINDABLE** | `O4A_CONSTRUCTION_REFUSAL.json` |
| O4-B | **REJECTED_AS_NON_BINDABLE** | `O4B_CONSTRUCTION_REFUSAL.json` |
| O5 | **INCONCLUSIVE** (`anchors: []`) | `O5_LOCATE_MANIFEST.json` |

Artifacts are labeled `CONSTRUCTION_REFUSAL_CENSUS` / `O5_LOCATE_MANIFEST` with
`not_a_candidate_archive=true`. They are **not** `CANDIDATE` / `QUALIFIED_CANDIDATE`
empirical gate evidence.

## O4-B day_change note

Snapshot-wide `accounts_state.day_change=1032.27` (`BROKER_LAST_EQUITY`) was **not**
copied into episodes. Doing so would be prohibited reconstruction; Stage 2
`MISSING_FORENSIC_BASELINE` stands.

## Statement

No row was emitted and no missing surface was reconstructed. Ordinary candidate
archives were not created because they cannot cure missing evidence and must not be
presented as progress toward gate eligibility.

Package path: `docs/design/evidence/dbox_evgap_acq_001/stage3/20260731T002055Z/`  
Package SHA-256: `3e31e0be78d9908e21c017d4679bbc8ab5eac66efd439da79bd36e743a38e10d`

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE3-001.*
