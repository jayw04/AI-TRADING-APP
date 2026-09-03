# A3 — recorded execution variance from v0.5 §7.1

**Sealed BEFORE any mutation.** 2026-08-25, after the 16:00 ET regular-session close.

## What the runbook says, and why this run differs

v0.5 §7.1 step 5 reads *"deploy `956e932` via the governed full-cutover path."* That wording was
written on 2026-08-23, when the box was a **mixed tree 13 commits behind main** (base `02e77a76` plus a
surgical 4-file v1.0.1 overlay). Full reconstruction was the correct instrument for that state.

**This run is a bounded execution variance, not a reinterpretation of §7.1.** The runbook is not being
read as though it always meant selective deployment; it meant full reconstruction, and this deployment
deliberately narrows the unit of *service reconstruction* while preserving the unit of *provenance*.

## Measured basis for the variance

```
source (deployed)  0344337787a6ce27df64995f7a556b19a4bf297a
target             956e932c8860602060b627b9c8f7966d31565337
commits between    exactly 1  —  PR #667
```

`git diff --name-only 0344337 956e932` = **14 files, all under `apps/backend/`**:

```
apps/backend/app/factor_data/store.py                      apps/backend/app/universe/owned_holdings.py
apps/backend/app/universe/security_identity.py             apps/backend/app/universe/strategy_ownership.py
apps/backend/strategies_user/templates/low_volatility.py
  + 9 test files under apps/backend/tests/
```

Counted explicitly:

| Category | Count |
|---|---:|
| Alembic migrations | **0** |
| `deploy/**`, `docker-compose*`, `.github/**` | **0** |
| `apps/frontend/**` | **0** |
| `apps/agent/**`, `apps/mcp-server/**`, `apps/mcp-workbench/**` | **0** |

## Reason

Minimize restart blast radius while preserving the governed artifact and provenance path. Rebuilding
five services adds operational risk — an unnecessary restart of the agent, both MCP services and the
frontend — without producing any evidence A3 requires. A3's objectives are the governed v1.0.3
deployment, health / build-marker / runtime verification, and Strategy 8 remaining IDLE. Unrelated-service
reconstruction is not among them.

Non-backend services are intentionally left untouched **because their governed inputs are unchanged**.

## STOP condition checked and cleared

The variance would be dishonest if any supposedly untouched service embedded or reported the repository
SHA in a way requiring global agreement with `DEPLOYED_BUILD_INFO.json` — that would create a
mixed-identity state. Checked by search:

```
consumers of .deploy_src_sha / DEPLOYED_BUILD_INFO.json
  apps/backend/app/research/disc_mdq/ledger.py      apps/backend/scripts/adr0043_wp0_seal.py
  apps/backend/scripts/mdq_preflight_readiness.sh   apps/backend/tests/deploy/*
  deploy/aws/build-deploy-archive.sh                deploy/aws/provision-from-s3.sh
  deploy/aws/provision-adr0043-validation.sh        deploy/aws/verify_deploy_object.py

references in apps/agent, apps/mcp-server, apps/mcp-workbench, apps/frontend/src :  NONE
```

Every consumer is backend or deploy-tooling. **Deployment identity for this cutover is the
backend/runtime/source marker pair, and no unchanged service carries a competing binding.** Condition
cleared; Option 1 is the honest operation.

## What stays identical to a normal governed deployment

- artifact built by `build-deploy-archive.sh` with **`ADR0043_IMPLEMENTATION_SHA=38f40b46906fc91497049924f7a62e7384d67653`**
  (the owner re-baseline, #535 — the script's `ea6db6e` default produces a NON-EMPTY governed-path delta
  against this target and hard-refuses with exit 3);
- archive hash, ancestry proof, ADR-0043 governed-path proof, generated `DEPLOYED_BUILD_INFO.json`;
- **delivery of the complete `956e932` repository artifact via S3** — never a hand-built five-file patch.
  The unit of provenance remains the full repository artifact even though the unit of service
  reconstruction is backend-only.

## What differs

- `docker compose up -d --build **backend**` only, over SSM. Frontend, agent, mcp-server and
  workbench-mcp are **not** restarted.
- `.deploy_src_sha` is treated as a controlled deployment marker: old / new / timestamp / verification
  recorded, and **promoted only after the backend rebuild is verified healthy**. If the cutover fails
  and is rolled back, the markers remain at / revert to `0344337`.

## Preconditions rechecked at execution time

Not inherited from the earlier read: Account-6 open orders, Strategy 8 state, deployed SHA and build
marker, live runtime flags, and strategy 1 / open-order state immediately before the backend restart.
