# D-BOX Status — CAMPAIGN-001 v1.2 **CLOSED**

| Field | Value |
|-------|-------|
| Close-out | ADR0043-PH0-D-BOX-V12-CLOSE-001 **APPROVED / EFFECTIVE** |
| Close path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_v1_2_Closeout_v1.0.md` |
| Effective (UTC) | `2026-07-30T18:49:40Z` |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** — scope exhausted |
| Freeze body | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| START-002 merge | `952848c` |
| Evidence root | `docs/design/evidence/dbox_campaign_v1_2_run_001/` |
| O3 / O4-A / O4-B merges | `b542d1c` / `d85f487` / `83813a6` |

## Final dispositions

| Package | Disposition |
|---------|-------------|
| CORR-06 / O1 / O2 | Inherited APPROVE |
| O3 | INCONCLUSIVE — replay surfaces absent |
| O4-A | INCONCLUSIVE — decision-time quotes absent |
| O4-B | INCONCLUSIVE — day_change absent |
| Combined O4 | INCONCLUSIVE |
| O5 | INCONCLUSIVE (`anchors: []`) |
| D-WIRE | **BLOCKED** |

## Post-close rules

No rerun under FREEZE-003/START-002. No archive enrichment. New corpus requires new
design → auth → freeze → start. HOLD unchanged. Successor: evidence-gap design only
(not authorized by this close-out).
