# O34 Selection Attempt — Source Snapshot Unreachable

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-O34-ACQ-SELECT-BLOCK-001 |
| Attempted at (UTC) | 2026-07-30T11:35:00Z |
| Authorized next step | Deterministic record selection under O34-ACQ-START-001 |
| Freeze body SHA-256 | `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0` |
| Capture ID | `20260730T022316Z` |
| Bound sqlite SHA-256 | `26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b` |
| Bound snapshot path | `/opt/workbench/data/ops/adr0043_o34_acq_snapshots/20260730T022316Z/workbench.sqlite.snapshot` |
| Host | `workbench` → `13.217.236.134:22` |
| Result | **STOPPED — REQUIRED SOURCE SNAPSHOT UNAVAILABLE FOR READ** |

## Stop condition (freeze § stop_conditions)

> Required source snapshot is unavailable

The snapshot remains **BOUND** in CAPTURE-001 (identity + SHA-256 recorded). This stop is
**reachability**, not an unbound identity: SSH/TCP to `13.217.236.134:22` times out
(100% ping loss; banner exchange timeout). No local copy of the sqlite snapshot exists
outside the box.

## Actions taken

| Action | Result |
|--------|--------|
| Freeze seal re-verify | Prior PASS retained (`80dfd8ec…`) |
| SSH `workbench` | Connection timed out |
| Selection / filter / join / row inspection | **Not started** |
| Broker calls | **None** |
| Archive construction | **Not started** |

## Predetermined handling

Per freeze `predetermined_inconclusive_handling`: construction selection closes
**INCONCLUSIVE** for this attempt until the bound snapshot bytes are readable again.
Do **not** manufacture observations. Do **not** select from live `workbench.sqlite`.

## Ready tooling (blocked on host)

`docs/design/evidence/dbox_o34_acq_001/construct_o34_archives.py` — deterministic
selection + CONSTRUCTED candidate archives from the bound snapshot once reachable.

## Resume condition

1. Restore SSH to `workbench` (or otherwise deliver the exact sqlite bytes matching
   `26bae1f5…`).
2. Re-hash file; must equal bound SHA-256.
3. Run `construct_o34_archives.py` against the snapshot path.
4. Independent qualification only after CONSTRUCTED.

HOLD / D-WIRE / gate execution remain unchanged.

*End of ADR0043-PH0-D-BOX-O34-ACQ-SELECT-BLOCK-001.*
