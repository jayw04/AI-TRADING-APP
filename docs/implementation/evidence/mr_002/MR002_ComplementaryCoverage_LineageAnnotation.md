# Lineage Annotation — `runtime/MR002_ComplementaryCoverage.json`

**Owner ruling 2026-07-14 §5. The predecessor artifact is NOT edited. This annotation stands beside
it.**

| field | value |
|---|---|
| artifact | `docs/implementation/evidence/mr_002/runtime/MR002_ComplementaryCoverage.json` |
| sha256 | `790002c05c45e685…` |
| status | **historical artifact** |
| lineage | **predates the corrected Clarabel dual mapping** |
| authority | **NOT authoritative for current solver counts** |
| directed rounding | **not changed by the directed-rounding correction** |
| disposition | **preserved unchanged** |

## Why it disagrees

Its CLARABEL / PIQP_P1 / PIQP_P2 counts differ from the later retained artifacts **and from the
full-population recomputation**:

| solver | this artifact | later artifacts + recomputation |
|---|---|---|
| CLARABEL | 9 | **29** |
| PIQP_P1 | 58 | **59** |
| PIQP_P2 | 51 | **51** *(it records 50)* |

It also disagrees with `MR002_R2_RegressionSampleA.json` and `MR002_RepairSizingSample.json`, which
agree with each other and with the recomputation on **all seven solvers**. So the divergence is not
between "the past" and "the correction" — it is between *this artifact* and *every other record*.

The cause is documented in `app/research/mr002/certificate.py`: a hand-rolled Clarabel dual mapping
produced a false verdict earlier in this program, and the mapping was subsequently corrected and
centralised into the one certificate module. This artifact was produced before that fix.

**This is not a directed-rounding effect.** The correction proves zero verdict changes across all
27,265 affected verdicts under every rendering path (`L→D`, `N→D`, `D→EXACT`). Rounding cannot
account for a difference of twenty CLARABEL verdicts, and does not.

## Authoritative sources for current solver counts

* `MR002_DirectedRounding_Correction.json` — the full-population recomputation (`93666948…`)
* `runtime/MR002_R2_RegressionSampleA.json` (`2719e354…`) — post-dual-mapping
* `runtime/MR002_RepairSizingSample.json` (`aa0f4cf1…`) — post-dual-mapping

**Sample A does not use this artifact as its solver-verdict source.** It resolves the cascade itself,
from the frozen corpus, under the corrected serializer.
