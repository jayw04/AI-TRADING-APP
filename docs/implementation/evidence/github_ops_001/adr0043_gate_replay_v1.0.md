# ADR 0043 gate replay — 120 historical PRs (jayw04/AI-TRADING-APP)
Predicate: `requires_adr0043_by_backend_attribution` (conservative backend attribution, not a precise risk-path classifier).
## Safety
- PRs where backend FULL ran but the gate would skip: **0** (must be 0)

## Selection
- gate WOULD RUN: **97** (80.8%) — legitimate required execution
- gate WOULD SKIP: **23** (19.2%) — the avoidable portion
- projected saving: **~179 runner-min/month** (2.2% of the 8,007-min baseline)
- step total cost was 933 min/month; the difference is required execution, **not** remaining waste

## Category coverage

| Category | PRs | Gate runs on |
|---|---|---|
| backend app | 65 | 65 |
| backend tests | 81 | 81 |
| risk / order path | 13 | 13 |
| migrations | 12 | 12 |
| workflow | 6 | 6 |
| frontend | 3 | 1 |
| docs | 50 | 32 |
| auxiliary projects | 3 | 0 |

## Sample of skipped PRs

- #501 docs(risk): record ACCOUNT_SYNC_SWEEP_NOT_REFRESHING — a ris — `docs`
- #496 docs(adr-0043): Phase-0 frozen execution plan, same-session  — `docs`
- #518 docs(adr): ADR 0046 — AWS SDK dependency and the KMS witness — `docs`
- #515 docs(adr): ADR 0045 — algorithm-qualified witness receipts ( — `docs`
- #489 SCRATCH (do not merge): branch-protection probe — docs-only  — `docs`
- #488 SCRATCH (do not merge): branch-protection probe — agent FULL — `apps`
- #487 SCRATCH (do not merge): branch-protection probe — mcp-workbe — `apps`
- #486 SCRATCH (do not merge): branch-protection probe — mcp-server — `apps`
- #482 docs(adr-0043): record repeated shared-role IAM mutation dev — `docs`
- #479 docs(adr-0043): process-deviation record — unauthorized depl — `docs`
- #456 docs(adr-0043): execution preconditions — ambient ENFORCE, a — `docs`
- #455 docs(adr-0043): runbook A2 — deployed-commit lineage (preven — `docs`
- #454 docs(adr-0043): live ENFORCE canary runbook (Phase 0 → count — `docs`
- #445 docs(adr): remove duplicate ADR 0042; point 0043 at the gove — `docs`
- #443 docs(adr): formalize and accept loss-control ADRs 0042 and 0 — `docs`
