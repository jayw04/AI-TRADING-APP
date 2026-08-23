# LOW-001 Paper Window 2026-08-12 – 2026-08-21 — Pre-Remediation Seal

| Field | Value |
|---|---|
| **Status** | **SEALED — immutable pre-remediation benchmark** |
| **Disposition** | **KEEP / REPAIR** |
| **Program** | LOW-001 Low Volatility (defensive diversifier) |
| **Strategy** | `low-volatility` id **8** / user **6** / account **6** |
| **Comparator** | `sector-rotation` id **7** / user **5** / account **5** |
| **Window** | 2026-08-12 … 2026-08-21 inclusive (Mon 8/10–Fri 8/14 and Mon 8/17–Fri 8/21 reported as the two live weeks) |
| **Captured at** | `2026-08-22T15:33:54Z` |
| **Host** | `i-084f47fe4e69192e9` (`ip-172-31-7-230`) |
| **Capture** | Read-only SSM `8c340d8a-d543-4f8b-ac5b-7d67b2fcc98c` → `workbench-backend` python/sqlite3 on `/app/data/workbench.sqlite` |
| **Authority** | `OBSERVATION_ONLY` / `allocation_authority=0` |
| **no_post_seal_tuning** | `true` — this window must not be used to retune LOW-001 economics |

## Immutable hash

| Object | SHA-256 |
|---|---|
| `docs/implementation/low001_paper_window_20260812_20260821.json` | `81be681c6c3d1766a0098dbf7b82fdb199aef86c8076ff51dd5ec07ed244566b` |

Machine payload is the seal. This record is the human-readable envelope. Do not rewrite either after repairs land.

## Frozen rulings (owner, 2026-08-22)

| Area | Ruling |
|---|---|
| LOW-001 research thesis | **SUPPORTED / no adverse evidence** |
| Diversifier role | **Strengthened** by this live window |
| Standalone alpha claim | **Still not established** (six/seven weeks is too short) |
| News / SIP / mid-week rotation | **No** |
| SPY 200-day gate | Latent design nonconformity (research is always-invested) |
| Fractional / HON handling | Active execution problem |
| 6.5% cash vs 2% target | Observable implementation drag |
| Factor freshness | Missing protection |
| In-memory weekly lock | Operational correctness defect |
| Account 6 disposition | **KEEP / REPAIR** |

Nothing in this window upgrades LOW-001 from Diversifier (B) to standalone alpha. It **is** enough to forbid changing the strategy concept, and to authorize implementation repairs that do not optimize the working diversifier behavior.

## What the two books did

Mon–Fri returns from last-snapshot-of-day equity:

| Week | Sector (acct 5) | Low-vol (acct 6) |
|---|---:|---:|
| 8/10–8/14 | **+3.23%** ($101,964.93 → $105,259.60) | **+0.39%** ($103,424.53 → $103,832.61) |
| 8/17–8/21 | **−4.05%** ($105,581.77 → $101,303.68) | **+0.87%** ($102,925.64 → $103,824.95) |
| Fri–Fri 8/14→8/21 | −3.76% | **−0.007% (flat)** |

Low-vol did not participate strongly in the sector upside and did not participate in the subsequent downside. That is the H2/H3 diversification signature.

Monday 8/17: sector **78** fills (56 buy / 22 sell), then **−3.0%** on Tuesday 8/18. Low-vol the same Monday: **14** fills (7/7). No `regime_bear_cash` on either book in the window.

At capture (2026-08-22): low-vol 39 names, cash **6.47%** of $103,843.45; sector 99 names, cash 2.27%. Both still `PAPER`. Schedules: sector `24 10 * * mon`, low-vol `32 10 * * mon`.

Account 5's 8/17–18 path is a **sector-construction/rotation diagnostic**, not a platform-wide shock. It does not license changing LOW-001.

## Pre-remediation invariants this seal protects

LOW-001 in this window: remained invested, no regime-cash event, low turnover vs the sector sleeve, preserved capital through the sector book's 8/17–21 reversal.

Repairs authorized after this seal (economic logic frozen):

1. Remove the SPY 200-day cash gate from LOW-001 V1 (always-invested research).
2. Fractionability-aware execution; deterministic whole-share fallback (OrderRouter already floors non-fractionable qty).
3. HON / 7/27 cost-basis repair is **ops, not strategy logic** — out of this code change.
4. Session-aware factor-freshness HOLD.
5. Durable rebalance state: started → orders reconciled → completed (retry incomplete weeks).
6. PIT universe scoring at research `n=200`; unregistered PIT names are logged, not silently dropped from the score.

## Out of scope (frozen)

- Upgrading the Diversifier verdict
- News, SIP selection, or intraweek rotation
- Mutating account 5
- Rewriting this window after seeing post-repair P&L
