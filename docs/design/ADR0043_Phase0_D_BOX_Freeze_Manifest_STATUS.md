# D-BOX Status — CAMPAIGN-001 v1.2 / FREEZE-MANIFEST-003

| Field | Value |
|-------|-------|
| Campaign scope | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** |
| Campaign path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.2.md` |
| Campaign SHA-256 (git blob @ tip) | `676fd5a5fa90dc1ef7fc874a090d8495ec7e5228f9a1e8b5cfa2252e9a1f5482` |
| Publication PR | [#562](https://github.com/jayw04/AI-TRADING-APP/pull/562) **MERGED** |
| Content tip | `9b62abb98b8adbcf9713cee006201e45f3015deb` |
| Merge tip | `974e374271aa04e0bd3d542faf856fcdddd3ff3c` |
| Freeze draft | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json` |
| Document ID | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| Manifest status | **READY_UNSEALED** — tip rebound; content readiness **PASS** |
| Recomputed body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Prior freeze | FREEZE-002 **SEALED** body `d35de863…` — **not mutated in place** |
| Option 2A inheritance | CORR-06/O1/O2 **INHERITED APPROVE** @ `5cb711c` + FREEZE-002 |
| Executable | **O3 → O4-A → O4-B** only |
| Deferred | **O5** INCONCLUSIVE (`anchors: []`) |
| D-WIRE | **BLOCKED** even if O3/O4 all-PASS |
| Harness contract | `plan_id=ord:<orders.id>` via `phase0_o34_archive_adapter.py` |
| Adapter SHA-256 (git blob) | `8e7215176ed2106f251e7f8c88d0164443bc16eb7bad1585af44767a9f787632` |
| Validator SHA-256 (git blob) | `652e31336a6606ee8f0e0733e0a924f417b0aafb72f97f2802d397979621bacc` |
| Runtime | isolated harness only; production `b0058bf` reference-only / no modify |
| HOLD | all prior HOLD conditions preserved |
| Seal | **NOT performed** — separate publication step after this tip-rebind lands |
| Campaign start | **HOLD** — separate v1.2 start ruling required after seal |

## Post-merge readiness (tip rebound)

```text
pytest apps/backend/tests/risk/test_phase0_o34_archive_adapter.py \
       apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py -q
→ all passed
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py check \
  --manifest docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json
→ ready_to_seal: true; error_count: 0
ord: probe → harness_can_consume_ord_mapping() True; parse_ord_plan_id('ord:1080')==1080
archive hashes → QUAL-001 pins (53b3310c… / 3ba73e61… / e349f494…)
```

## Next

1. Publish tip-rebind PR (this STATUS + rebound FREEZE-003).  
2. Owner seal + countersign FREEZE-003 (separate step).  
3. Separate owner **start** ruling — then execute O3 → O4-A → O4-B only.
