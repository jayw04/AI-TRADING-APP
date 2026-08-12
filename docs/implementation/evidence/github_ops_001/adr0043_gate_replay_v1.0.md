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

## Skipped PRs (all)

- #518 docs(adr): ADR 0046 — AWS SDK dependency and the KMS witness — `docs`
- #515 docs(adr): ADR 0045 — algorithm-qualified witness receipts ( — `docs`
- #501 docs(risk): record ACCOUNT_SYNC_SWEEP_NOT_REFRESHING — a ris — `docs`
- #496 docs(adr-0043): Phase-0 frozen execution plan, same-session  — `docs`
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
- #440 docs(incident): formally close the 2026-07-13 risk-gate-trap — `docs`
- #421 docs(mkt-proj-001): §4 plan v0.2 — resolved Q1–Q4 + amended  — `docs`
- #420 docs(mkt-proj-001): ModelCard corrections (owner evidence re — `docs`
- #418 docs(mkt-proj-001): §4 plan v0.1 — returned to the owner bef — `docs`
- #414 docs(mkt-proj-001): §2 baselines-only evidence — owner stop/ — `docs`
- #403 feat(insider-monitor): Insider Activity Monitor dashboard ca — `apps`
- #402 feat(insider-monitor): Insider Activity Monitor dashboard ca — `apps`
- #400 docs: Insider Reference Monitor onboarding spec + INSIDER-00 — `docs`

## Sampled population (exact — for reproduction)

The default sample is a *moving* window, so re-running plain `--sample 120` later will select a different population. To reproduce THIS report verbatim, replay the pinned list:

```bash
python apps/backend/scripts/ci_replay_adr0043_gate.py \
  --pr-numbers docs/implementation/evidence/github_ops_001/adr0043_gate_replay_v1.0.population.txt
```

All 120 PRs in this run, newest first:

```
537,536,535,533,531,528,527,526,525,524,523,521,520,519,518
517,516,515,514,513,510,509,508,507,506,505,504,503,501,500
499,498,497,496,495,494,493,492,491,490,489,488,487,486,485
484,483,482,481,480,479,478,477,476,475,474,473,472,471,470
469,468,467,466,465,463,462,461,460,459,458,457,456,455,454
453,452,451,450,449,448,447,446,445,444,443,441,440,439,438
437,436,435,433,432,431,430,429,428,421,420,418,417,416,415
414,413,412,411,410,409,408,406,405,404,403,402,401,400,399
```

### Per-PR decisions

| PR | ADR-0043 gate | backend FULL |
|---|---|---|
| #537 | RUN | yes |
| #536 | RUN | yes |
| #535 | RUN | yes |
| #533 | RUN | yes |
| #531 | RUN | yes |
| #528 | RUN | yes |
| #527 | RUN | yes |
| #526 | RUN | yes |
| #525 | RUN | yes |
| #524 | RUN | yes |
| #523 | RUN | yes |
| #521 | RUN | yes |
| #520 | RUN | yes |
| #519 | RUN | yes |
| #518 | skip | no |
| #517 | RUN | yes |
| #516 | RUN | yes |
| #515 | skip | no |
| #514 | RUN | yes |
| #513 | RUN | yes |
| #510 | RUN | yes |
| #509 | RUN | yes |
| #508 | RUN | yes |
| #507 | RUN | yes |
| #506 | RUN | yes |
| #505 | RUN | yes |
| #504 | RUN | yes |
| #503 | RUN | yes |
| #501 | skip | no |
| #500 | RUN | yes |
| #499 | RUN | yes |
| #498 | RUN | yes |
| #497 | RUN | yes |
| #496 | skip | no |
| #495 | RUN | yes |
| #494 | RUN | yes |
| #493 | RUN | yes |
| #492 | RUN | yes |
| #491 | RUN | yes |
| #490 | RUN | yes |
| #489 | skip | no |
| #488 | skip | no |
| #487 | skip | no |
| #486 | skip | no |
| #485 | RUN | yes |
| #484 | RUN | yes |
| #483 | RUN | yes |
| #482 | skip | no |
| #481 | RUN | yes |
| #480 | RUN | yes |
| #479 | skip | no |
| #478 | RUN | yes |
| #477 | RUN | yes |
| #476 | RUN | yes |
| #475 | RUN | yes |
| #474 | RUN | yes |
| #473 | RUN | yes |
| #472 | RUN | yes |
| #471 | RUN | yes |
| #470 | RUN | yes |
| #469 | RUN | yes |
| #468 | RUN | yes |
| #467 | RUN | yes |
| #466 | RUN | yes |
| #465 | RUN | yes |
| #463 | RUN | yes |
| #462 | RUN | yes |
| #461 | RUN | yes |
| #460 | RUN | yes |
| #459 | RUN | yes |
| #458 | RUN | yes |
| #457 | RUN | yes |
| #456 | skip | no |
| #455 | skip | no |
| #454 | skip | no |
| #453 | RUN | yes |
| #452 | RUN | yes |
| #451 | RUN | yes |
| #450 | RUN | yes |
| #449 | RUN | yes |
| #448 | RUN | yes |
| #447 | RUN | yes |
| #446 | RUN | yes |
| #445 | skip | no |
| #444 | RUN | yes |
| #443 | skip | no |
| #441 | RUN | yes |
| #440 | skip | no |
| #439 | RUN | yes |
| #438 | RUN | yes |
| #437 | RUN | yes |
| #436 | RUN | yes |
| #435 | RUN | yes |
| #433 | RUN | yes |
| #432 | RUN | yes |
| #431 | RUN | yes |
| #430 | RUN | yes |
| #429 | RUN | yes |
| #428 | RUN | yes |
| #421 | skip | no |
| #420 | skip | no |
| #418 | skip | no |
| #417 | RUN | yes |
| #416 | RUN | yes |
| #415 | RUN | yes |
| #414 | skip | no |
| #413 | RUN | yes |
| #412 | RUN | yes |
| #411 | RUN | yes |
| #410 | RUN | yes |
| #409 | RUN | yes |
| #408 | RUN | yes |
| #406 | RUN | yes |
| #405 | RUN | yes |
| #404 | RUN | yes |
| #403 | skip | no |
| #402 | skip | no |
| #401 | RUN | yes |
| #400 | skip | no |
| #399 | RUN | yes |
