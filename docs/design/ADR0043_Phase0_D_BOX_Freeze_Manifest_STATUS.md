# D-BOX Status — CAMPAIGN-001 v1.2 / FREEZE-MANIFEST-003

| Field | Value |
|-------|-------|
| Campaign scope | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** (draft) |
| Campaign path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.2.md` |
| Campaign SHA-256 | `ae9c333c92ec8af5a43f37b116467956cb06ff796df28045f0640df74236d272` |
| Freeze draft | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json` |
| Document ID | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| Manifest status | **UNSEALED_DRAFT** — content readiness **PASS** (`ready_to_seal: true`) |
| Recomputed body SHA-256 | `05e261b4f951f8e22ac20a627c856f67cd898e8576fc381535b6333b20bcd5e2` |
| Prior freeze | FREEZE-002 **SEALED** body `d35de863…` — **not mutated in place** |
| Option 2A inheritance | CORR-06/O1/O2 **INHERITED APPROVE** @ `5cb711c` + FREEZE-002 |
| Executable | **O3 → O4-A → O4-B** only |
| Deferred | **O5** INCONCLUSIVE (`anchors: []`) |
| D-WIRE | **BLOCKED** even if O3/O4 all-PASS |
| Harness contract | `plan_id=ord:<orders.id>` via `phase0_o34_archive_adapter.py` |
| Adapter SHA-256 | `a2780e51782aca6853f895ae1a81deac426536535d16889ceb7f3a502d6ff89f` |
| Runtime | isolated harness only; production `b0058bf` reference-only / no modify |
| HOLD | all prior HOLD conditions preserved |
| Campaign start | **HOLD** — separate owner decision after seal |
| Seal | **NOT performed** — commit pins are `content_bound_pre_publish_tip_v1_2_o34` until published clean tip |
| Publication | Commit/PR authorized; seal deferred until tip rebind + readiness re-run |
| Campaign start | **HOLD** — separate v1.2 start ruling required after seal |

## Readiness (local)

```text
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py check \
  --manifest docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json
→ ready_to_seal: true; error_count: 0
pytest apps/backend/tests/risk/test_phase0_o34_archive_adapter.py \
       apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py -q
→ all passed
```

## Next (owner)

1. Authorize commit + PR of campaign v1.2, adapter, validator readiness gate, FREEZE-003 draft, STATUS.  
2. Rebind FREEZE-003 `commit` / `git_commit_full` / verifier tip to published clean SHA.  
3. Re-run readiness on clean tree.  
4. Owner seal + countersign FREEZE-003.  
5. Separate owner **start** decision.  
6. Execute O3 → O4-A → O4-B only (inherited APPROVE packages not rerun).
