# EVIDENCE-GAP Acquisition Stage 2 — Inventory & Recoverability

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE2-001 |
| Capture ID | `20260731T002055Z` |
| Analyzed against freeze body | `af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e` |
| Start ruling | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001 @ `eb9b660` |
| Opening | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-OPENING-001 @ `561e524` |
| Eligibility window | `[2026-06-30T00:00:00Z, 2026-07-30T19:39:07Z)` |
| Account | `3` / `PA34USW0Q8UO` (broker verified) |
| Sources modified | **false** |
| Window widened | **false** |
| Mappings relaxed | **false** |
| Construction performed | **false** |
| Stage 3 authorized by this record | **false** |

## Pins verified (Stage 1 identities only)

| Pin | SHA-256 | Match |
|-----|---------|-------|
| Sqlite snapshot | `9e40a9ad2f0176acf884140594ddfa9e946e42d2723794f464bbb0efdc2d9db6` | PASS |
| bar_cache manifest | `b32e118732669c2880291cd0a7226589e4b0e2ef20839dc8172c26ce51e0adc7` | PASS |
| market_projection manifest | `c0148389daa4139dd60a5921d6bec55a224a4156fb7cca080cc2b8fdfb7eb2c1` | PASS |
| O5 evidence tree manifest | `1c209b068e89456dbdbb8f380fc8672d0b3d04d1460752e12d32dd8717832d26` | PASS |

## Count reconciliation

| Stage | Count |
|-------|------:|
| source_count (account-3 orders) | 292 |
| window_eligible | 292 |
| outside window (EXC-010) | 0 |
| deduplicated (`ord:<id>`) | 292 |
| complete O3 | 0 |
| complete O4-A | 0 |
| complete O4-B | 0 |

Identity checks: source≥window, window=dedup, complete+incomplete=dedup — **PASS**.  
`emitted` = `NOT_APPLICABLE_STAGE2_NO_CONSTRUCTION`.

### Predetermined reason-code counts (across 292 episodes)

| Reason code | Count |
|-------------|------:|
| `MISSING_REPLAY_SURFACE:quote_provenance` | 292 |
| `MISSING_REPLAY_SURFACE:checkpoint_tuple` | 292 |
| `MISSING_REPLAY_SURFACE:loss_accounting_inputs` | 292 |
| `MISSING_REPLAY_SURFACE:recovery_inputs` | 292 |
| `MISSING_DECISION_TIME_QUOTE` | 292 |
| `MISSING_PROVENANCE` (`model_available`) | 292 |
| `MISSING_FORENSIC_BASELINE` | 292 |
| `MISSING_CUTOFF` | 5 |
| `O4B_INCOMPLETE` | 6 |

Authority inputs remain recoverable from order rows; they are not sufficient alone for O3 completeness.

## Corpus recoverability (honest presence)

| Surface / signal | Found in frozen snapshot? |
|------------------|---------------------------|
| QuoteProvenance contract object (account-scoped) | **No** |
| CheckpointBinding object | **No** (no checkpoint table; audit_log not account-scoped) |
| TerminalPackage / recovery_inputs object | **No** |
| `model_available` field | **No** |
| `accounts_state.day_change` column | **Yes** — `1032.27`, basis `BROKER_LAST_EQUITY` (snapshot as-of only) |
| `risk_session_baselines` account-3 | **0 rows** |
| `equity_snapshots` account-3 | **25 rows** (ts/equity/day_change_pct; episode linkage not proven) |

Per-episode O4-B QUALIFIED binding still requires forensic as-of lineage; snapshot-global `day_change` alone → `MISSING_FORENSIC_BASELINE`.

## O5 Tier-A locate-only

| Field | Value |
|-------|-------|
| Search set | Stage 1 pinned evidence paths (50 files) |
| Non-empty qualifying Tier-A manifests | **0** |
| `anchors` | `[]` |
| Disposition | **`anchors:[]` VALID — predetermined INCONCLUSIVE** |

No new fills; no broker activity.

## Artifacts

| Path | Role |
|------|------|
| `docs/design/evidence/dbox_evgap_acq_001/stage2/20260731T002055Z/stage2_report.json` | Sealed inventory report |
| `…/o3_episode_recoverability.json` | Per-episode O3 missing codes |
| `…/o4a_episode_recoverability.json` | Per-episode O4-A missing codes |
| `…/o4b_episode_recoverability.json` | Per-episode O4-B missing codes |
| `…/window_exclusions.json` | Outside-window exclusions |
| `docs/design/evidence/dbox_evgap_acq_001/run_stage2_inventory.py` | Deterministic Stage 2 tooling |

## Disposition

Stage 2 **COMPLETE**. Count reconciliation and recoverability inventory are published.  
Stage 3 construction is **not** authorized by this record alone — begin only after owner
acceptance of this sealed inventory (systematic gap surfaces; O5 empty anchors valid).

Gates **CLOSED**. D-WIRE **BLOCKED**. HOLD unchanged. SG ingress `79.127.147.206/32`
retained for the governed session (operational access only; not evidence-scope).

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE2-001.*
