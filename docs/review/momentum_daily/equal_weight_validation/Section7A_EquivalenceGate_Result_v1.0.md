# §7 A Construct / Equivalence Gate — Result — 2026-07-23

**PREREG v1.0 §7 A.** Before any performance measurement, the production-faithful instrument must
reproduce the §8 census seams and every construct count must be zero. Owner-set pass criterion:
**reproduce the §8 census seams exactly.**

## Instrument & provenance

| item | value |
|---|---|
| instrument commit (current main, parity-complete) | `764883b58cb96936f23e49182dd02b70d969501b` |
| parity lineage | sizing seam #461 · pending_buy_qty #467 · durable state #469 |
| factor DB whole-file sha256 | `022ffd01…` — re-verified, **matches the census binding** |
| sep / tickers content digests | `d9472dfe…` / `2f21b154…` — re-verified fail-closed |
| window / universe | 2005-01-03 → 2026-06-12 (5,395 sessions) · `momentum_daily_stage2_4:top200_PIT_universe_asof_n200` |

## EXACT REPRODUCTION — PASS

The drive of the actual `MomentumDaily` class produced seams **byte-identical** to the countersigned
§8 census:

| artifact | this run | frozen census | match |
|---|---|---|---|
| live_seams.json | `9f682ecb7832bef77b2d1e08…` | `9f682ecb…` | ✅ identical |
| replica_seams.json | `70b99e1e494338d7b75c132a…` | `70b99e1e…` | ✅ identical |
| report seam counts | — | — | ✅ identical |

The validation instrument is provably the same one the §8 census countersigned. The #467/#469 parity
additions did not alter the seams (the drift-audit `DriftCtxAdapter` already carried them).

## The six §7 A construct counts — ALL ZERO

| count | value | basis |
|---|---|---|
| production seam mismatches (eligible / ranking / target) | **0 / 0 / 0** | census report, all 5,395 sessions |
| cap violations (production / live side) | **0** | live 5,393 five-name sessions, weight spread median 0.000000 (exactly equal weight) |
| unexpected trigger mismatches | **0** | when BOTH trade, held set identical on **1,518 / 1,518** sessions (0 different); the 3,194 live-only trades are the census-adjudicated holdings-neutral weight-drift maintenance |
| duplicate initial seeds | **0** | `cold_start_seed_count == 1` |
| unexplained pending-buy mismatch | **0** | seams byte-identical to census |
| unreconciled durable-state drift | **0** | seams byte-identical to census |

## The census's `MISMATCHES_TO_ADJUDICATE` verdict — reproduced, and already adjudicated

The raw census verdict reproduces exactly. Its two non-selection mismatch categories are **not** §7 A
construct counts and were **already adjudicated**:
- **weights (5,349)** = production **equal-weight** vs the replica's **defective hybrid** — the
  `VALIDATION_IMPLEMENTATION_DEFECT` reclassified in `weighting_defect_erratum_v1.0.md`; this is the
  *subject* of this validation, not a construct failure. Production has **0** cap violations.
- **regime_gross (86)** = the documented Option-D warmed-vs-window proxy boundary residual.

## Verdict

**§7 A CONSTRUCT / EQUIVALENCE GATE: PASS** (pending owner confirmation) — exact reproduction of the
§8 census seams, all six construct counts zero. The instrument is construct-valid for the forward
validation.

⚠ NO forward or historical performance was computed. The forward window is NOT open. Account 4
remains PAUSED and held; the retired `84466.41` baseline is not reused.
