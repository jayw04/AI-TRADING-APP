# ADR‑0043 Phase‑0 — Same‑Session Runbook v1.0 (staged; execute at a future open)

> ## ⛔ Status: Step B is HELD — this runbook cannot yet produce authoritative evidence
>
> As filed, **no authoritative session baseline may be captured by this procedure.** Two blocking
> conditions, both recorded 2026‑07‑24:
>
> 1. **The staged operator scripts are not governed instruments.** `adr0043_session_open.py` and
>    `adr0043_reachability.py` exist only on the validation host at `/home/ubuntu/adr0043_staging/`
>    and in a session scratchpad. They are unreviewed and unversioned, so their output cannot be
>    accepted as the authoritative Phase‑0 baseline / preflight evidence. Governing them requires
>    the operator‑tooling PR: review → merge → identify the exact merged git blob → verify SHA‑256 →
>    transfer that blob to the host → mount read‑only into the *unchanged* deployed image → record
>    host/container SHA equality. Until that lands, every run of Step A/B is **exploratory and
>    non‑authoritative**.
> 2. **The canary harness's loss observation is disarmed** —
>    `docs/incidents/ADR0043_Harness_AccountState_Missing_Defaults_To_Zero_20260724.md`. The driver
>    reads its authoritative loss from an `accounts_state` row that does not exist for account 3 and
>    silently substitutes zero, so Phase‑0's live stopping (§5) and overshoot (§10) measurements do
>    not work. A dedicated fix PR is required before any Phase‑0 session.
>
> Everything in the Step‑A execution log is therefore **preliminary and non‑binding**, including
> the 2026‑07‑24 07:37 ET entry. Reachability verdicts recorded here are planning inputs only.

> Companion to `docs/implementation/ADR0043_Phase0_FrozenExecutionPlan_v1.0.md`. **No broker orders /
> no breach are performed by any command in this runbook** — it ends at the frozen readiness package
> and STOPS for explicit broker‑submission authorization.
>
> ### ⚠ Which box
>
> Everything here runs on the **ADR‑0043 canary box** `adr0043-canary`:
>
> ```
> ssh -i ~/.ssh/workbench-paper.pem ubuntu@3.80.11.61
> ```
>
> **NOT `ssh workbench`** — that alias resolves to the production paper stack `ec2-paper`
> (13.217.236.134), which serves the live books. Every command below bind‑mounts
> `/opt/workbench/data`, so running one on the wrong host points canary tooling at the live
> database. The canary box's public IP changes across a stop/start; confirm identity after
> connecting (`hostname` → `ip-172-31-6-164`) before running anything.

## Prerequisites (all COMPLETE, frozen)

- Limits row id=3 frozen, **`limits_sha256 = da6659334909a68a2e800d429ff36e7c7de1d18f169082836c07de2973ef706f`** (audit id 153).
- Account 3 reconciled: MSFT:19 LONG, no unrelated positions, 0 open orders, 0 HELD reservations.
- Runtime config frozen: `ADR0043_USER=3 ACCOUNT=3 PROTECTED=MSFT LEGS=MSFT:19 CHURN=IEUS,KOKU`.
- Ambient `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE`; deploy marker `f98d082` (impl `c8b3ac2` ancestor).
- Staged operator tooling on the box: `/home/ubuntu/adr0043_staging/adr0043_session_open.py` (+ `adr0043_reachability.py`).

> The staged orchestrator is **operator setup tooling**, not the frozen canary harness. It only reads,
> except the single immutable session‑baseline write behind `--capture-baseline`. It is mounted into the
> container at run time (never baked into the deployed image), preserving the runtime‑continuity invariant.

## Step A — Read‑only precheck (safe any time, including now)

Confirms identity / MSFT:19 / flat / limits‑SHA / a pre‑lock preflight snapshot / a (non‑binding, stale
after‑hours) reachability read. Writes nothing but the credential `last_used_at`.

```
ssh -i ~/.ssh/workbench-paper.pem ubuntu@3.80.11.61
sudo docker run --rm \
  -v /opt/workbench/data:/app/data \
  -v /home/ubuntu/adr0043_staging/adr0043_session_open.py:/app/scripts/adr0043_session_open.py:ro \
  --env-file /opt/workbench/.env \
  -e WORKBENCH_DB_URL=sqlite+aiosqlite:////app/data/workbench.sqlite -w /app \
  trading-workbench-backend python -m scripts.adr0043_session_open
```

> `adr0043_session_open.py` computes reachability itself (step 8) and does not import the staged
> `adr0043_reachability.py`, which is a separate standalone read‑only tool. Mounting only the
> orchestrator is correct.

Expect: `READY_FOR_BASELINE_AND_PREFLIGHT: true`, `2_identity.identity_ok: true`,
`5_limits.sha_unchanged: true`. `1_session.market_open_now` is `false` outside RTH.

## Step B — At the chosen Phase‑0 session OPEN (before any activity): capture baseline + preflight

> ⛔ **HELD.** Do not run `--capture-baseline` until the operator‑tooling PR has merged and the exact
> merged blobs are verified on the validation host (see the status banner). A baseline minted by an
> unreviewed script is unauditable, and the same‑session rule means it cannot be retro‑justified —
> missing a session is always preferable. Step A without `--capture-baseline` remains permitted, and
> its output must be classified `EXPLORATORY_PREOPEN_OR_SESSION_READINESS` /
> `NON_AUTHORITATIVE` / `NO_BASELINE_CAPTURE` / `NO_ORDERS`.

Run the SAME command with `--capture-baseline`. The tool refuses the baseline unless the market is
**currently open** and identity/positions/flat/limits are all green — so it can only mint a
current‑session baseline, before activity.

```
sudo docker run --rm \
  -v /opt/workbench/data:/app/data \
  -v /home/ubuntu/adr0043_staging/adr0043_session_open.py:/app/scripts/adr0043_session_open.py:ro \
  --env-file /opt/workbench/.env \
  -e WORKBENCH_DB_URL=sqlite+aiosqlite:////app/data/workbench.sqlite -w /app \
  trading-workbench-backend python -m scripts.adr0043_session_open --capture-baseline
```

This performs the owner's same‑session sequence:

1. **Session eligibility** — trading day + `market_open_now=true` (else baseline refused).
2. **Identity** — broker `PA34USW0Q8UO` (never `PA3QRX9KSPXA`), paper, ACTIVE, prefix `PKZYTY`.
3. **Positions** — MSFT:19 only, broker == DB.
4. **Flat** — 0 broker open orders, 0 HELD reservations.
5. **Limits SHA** — equals `da665933…` (frozen). A mismatch = STOP (continuity broken).
6. **Baseline** — `SessionBaselineShadow.capture` writes the immutable `risk_session_baselines` row from
   the reconciled open equity. Records `CAPTURED` (or `REUSED` if already present, immutable).
7. **Read‑only preflight** — `run_preflight_checks` (persists nothing; never consumes the A4 identity).
   Pre‑lock, lock‑dependent checks read FAIL/INCOMPLETE — expected; the 12/12 PASS exists only post‑lock
   at A4 in the formal canary, NOT in Phase 0.
8. **Reachability** — fresh (≤10 s) quotes → `verdict` with `binding: true`. If ≤12 round trips cannot
   cross $3,000 at the fresh spread, this is **`BREACH_UNREACHABLE`** — preserved, **never** worked
   around by widening caps / adding symbols / lowering the target.
9. STOP. The printed `SESSION_PACKAGE` is the readiness package.

## Step C — Return the package; await explicit authorization

- If `READY_FOR_BASELINE_AND_PREFLIGHT: true`, baseline `CAPTURED`, and reachability is **BINDING
  REACHABLE**, return the package for **explicit broker‑submission authorization**.
- If reachability is **BINDING BREACH_UNREACHABLE**, return that verdict as‑is (do not tune controls).
- **Submit no orders until explicit authorization is issued.** The loss‑generating breach (runbook §0D)
  and the formal canary (`python -m scripts.adr0043_canary_run`) remain HELD.

## Hard stops (any → STOP, preserve evidence, do not engineer around)

Identity ≠ `PA34USW0Q8UO`; non‑paper / not ACTIVE; prefix ≠ `PKZYTY`; limits SHA ≠ `da665933…`; MSFT ≠ 19
or any unrelated position; any open order / HELD reservation; loss‑control state ≠ NORMAL at preflight;
baseline `MISSING_AFTER_ACTIVITY` / previous‑session / indeterminate; `BREACH_UNREACHABLE`.

## Continuity invariant

Same instance / image / config / database / credentials / captured baseline must hold continuously from
baseline capture through the formal canary and countersignature (no reprovision / DB copy / image swap /
config change).

## Step‑A execution log

Every Step‑A run is appended here. Step A submits no orders and captures no baseline; it is the
evidence that the frozen prerequisites still hold at the moment it ran.

### 2026‑07‑24 07:37 ET (pre‑open, read‑only)

`EXPLORATORY_PREOPEN_OR_SESSION_READINESS` · `NON_AUTHORITATIVE` · `NO_BASELINE_CAPTURE` · `NO_ORDERS`

Produced by the **ungoverned** staged script. Planning input only; it establishes nothing.

| Check | Result |
|---|---|
| `READY_FOR_BASELINE_AND_PREFLIGHT` | **true** |
| `2_identity` | prefix `PKZYTY`, paper, ACTIVE |
| `3_positions` | broker `{MSFT: 19}` == DB `MSFT 19 long` · `msft19_only_ok: true` |
| `4_flat` | 0 broker open orders · 0 HELD reservations |
| `5_limits` | `da6659334909a68a2e800d429ff36e7c7de1d18f169082836c07de2973ef706f` · `sha_unchanged: true` |
| `6_baseline` | skipped (no `--capture-baseline`) |
| `7_preflight_readonly` | 2 FAIL / 10 INCOMPLETE — **expected pre‑lock** (see note below) |
| `8_reachability` | `REACHABLE`, **`binding: false`** — quotes 56 248 s (IEUS) / 78 584 s (KOKU) stale; `current_day_change` +$82.08; KOKU $558.60/RT → 6 of 12 RT; `max_reachable_12rt` $6 703.20 |

The pre‑lock preflight reading is not a defect: `state_known_and_recoverable` and
`no_unresolved_integrity_condition` read FAIL and the remaining ten read INCOMPLETE until the breach
lock (A4) exists. The 12/12 PASS exists only post‑lock at A4 in the formal canary, never in Phase 0.

IEUS quoted a bid with **no ask** (unusable after‑hours) — reachability rested entirely on KOKU's wide
after‑hours spread. That is exactly why this verdict is non‑binding: the in‑session re‑derivation on
fresh (≤10 s) quotes may return `BREACH_UNREACHABLE`, which is preserved as‑is.
