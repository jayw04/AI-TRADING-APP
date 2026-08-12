# D-BOX Option 2A Execution Record

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-OPTION2A-RUN-001 |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 (Option 2A) |
| Start ruling | ADR0043-PH0-D-BOX-START-001 **EFFECTIVE** |
| Freeze body SHA-256 | `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f` |
| Runtime | Isolated harness / worktree `dbox/option2a-run` @ `7d12c68` |
| Pre-CORR-06 verify-seal | **exit 0** @ `2026-07-30T00:06:26Z` |
| Evidence root | `docs/design/evidence/dbox_option2a_run_001/` |

## Package dispositions

| Package | Disposition | Pytest |
|---------|-------------|--------|
| **CORR-06** | **APPROVE** | 23 passed |
| **O1** | **APPROVE** | 34 passed |
| **O2** | **APPROVE** | 49 passed |
| O3 | INCONCLUSIVE — REQUIRED CORPUS ABSENT | not executed |
| O4-A | INCONCLUSIVE — DECISION-TIME SET ABSENT | not executed |
| O4-B | INCONCLUSIVE — FORENSIC SET ABSENT | not executed |
| O5 | INCONCLUSIVE | not executed |

## D-WIRE

**BLOCKED.** Option 2A cannot create D-WIRE eligibility. O3/O4/O5 remain load-bearing and incomplete.

## HOLD (unchanged)

No broker submission, new live fills, production imports, deployed-path observation, canary,
ENFORCE, caps, or July 24 limits-digest changes. No O3/O4/O5 execution.

## Primary artifacts

- `corr06_exit_report.json`
- `credential_metadata_pre_post_hashes.json`
- `o1_structural_report.json`
- `o2_property_report.json`
- `loss_reconcile_vectors.json`
- `campaign_run_summary.json`
