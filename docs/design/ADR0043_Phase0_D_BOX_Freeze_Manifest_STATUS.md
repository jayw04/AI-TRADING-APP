# D-BOX Status — O34 Selection Blocked (Host Unreachable)

| Field | Value |
|-------|-------|
| O34-ACQ-START-001 | **EFFECTIVE** (`811a808`) |
| Capture | CAPTURE-001 `20260730T022316Z` — all mandatory sources **BOUND** |
| Selection | **STOPPED** — SELECT-BLOCK-001 (snapshot path unreachable) |
| Host | `13.217.236.134` SSH timeout |
| D-WIRE / HOLD | **BLOCKED / HOLD** |

## Next

Restore `workbench` SSH (or deliver sqlite bytes `26bae1f5…`), then run
`docs/design/evidence/dbox_o34_acq_001/construct_o34_archives.py` against the bound
snapshot. No selection until then.
