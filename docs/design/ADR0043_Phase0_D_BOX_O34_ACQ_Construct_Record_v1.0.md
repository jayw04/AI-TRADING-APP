# O34 Construction Record — Candidate Archives CONSTRUCTED

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-O34-ACQ-CONSTRUCT-001 |
| Outcome | **CONSTRUCTED** (not gate-ready) |
| Constructed at (UTC) | 2026-07-30T11:48:00Z (approx; see archive provenance) |
| Capture ID | `20260730T022316Z` |
| Freeze body SHA-256 | `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0` |
| Sqlite snapshot SHA-256 | `26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b` |
| Broker verified | `PA34USW0Q8UO` (account 3) |
| Tooling commit | `e27d6aecd2c45c9bdfc9079099fdc618ef000761` |
| Prior block | SELECT-BLOCK-001 cleared after SSH restore |
| Gate ready | **false** |
| Qualification | **PENDING_INDEPENDENT_QUALIFICATION** |
| Broker calls | **none** |

## Restore note (host access)

Workbench instance `i-084f47fe4e69192e9` was **running**; SSH failed because SG
`sg-00dcdde89fa30e99a` lacked operator IP `79.127.147.206/32` (prior allow was
`79.127.147.204/32`). Ingress rule `sgr-00fa947b3b76c5c9b` added 2026-07-30.
Re-hashed bound snapshot → `26bae1f5…` **match**.

## Selection summary

| Metric | Count |
|--------|-------|
| Source orders (account 3) | 292 |
| Excluded outside window | 0 |
| Selected episodes (`plan_id=ord:<orders.id>`) | 292 |
| O4-A MISSING_CUTOFF | 5 |
| O4-B O4B_INCOMPLETE | 6 |

Unit mapping: no `execution_plan` table; episode = `ord:` + `orders.id` (deterministic).

## Candidate archives

| Archive | SHA-256 | Observations |
|---------|---------|--------------|
| O3 | `53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0` | 292 / 20 clusters |
| O4-A | `3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49` | 287 |
| O4-B | `e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95` | 286 (286 fills) |

Evidence root: `docs/design/evidence/dbox_o34_acq_001/constructed/20260730T022316Z/`

## Next

Independent qualification → `QUALIFIED` / `REJECTED_AS_NON-BINDABLE` / `INCONCLUSIVE`.  
Campaign amendment required before gate use. HOLD / D-WIRE unchanged.

*End of ADR0043-PH0-D-BOX-O34-ACQ-CONSTRUCT-001.*
