# SCAN-001 v0.2 — Candidate Engine: de-tautologized evidence

*Generated 2026-06-23T00:10:55+00:00 · read-only research · SCAN-001 §0a: candidate set is evidence, not a signal.*

## Overall verdict: SUPPORTED — engine finds genuine, tradeable expansion (holds on both cuts)

- H1′ (expansion beyond ATR) holds on both cuts: **True**
- H2 (2-of-3 tradeability) holds on both cuts: **True**
- Attribution: Keep signals: ATR + Gap + RVOL.

## HEADLINE (top-500, 3y) — 2023-06-12 → 2026-06-12, 754 days, top-500

### H1′ — expansion beyond ATR
- Candidate 1.4934× vs baseline 0.948× ATR · edge 0.5454 CI [0.483, 0.606] p=0.0 → **SUPPORTED** (need >1.0× and CI>0)

### H2 — tradeability (2-of-3)
| Metric | Candidate | Baseline | Edge CI | Clears |
| --- | --- | --- | --- | --- |
| Trend efficiency | 0.4776 | 0.4499 | [0.022, 0.0335] | ✓ |
| Capturable move % | 5.87 | 2.2837 | [3.4234, 3.7636] | ✓ |
| Net move % | 3.7603 | 1.418 | [2.2334, 2.4612] | ✓ |

→ 3/3 clear → **SUPPORTED**

### H3 — signal attribution (vs ATR-only screen)
| Signal set | ΔE CI | ΔCM CI | Additive |
| --- | --- | --- | --- |
| ATR_Gap | [0.2572, 0.3355] | [0.7289, 1.0599] | ✓ |
| ATR_RVOL | [0.4959, 0.611] | [0.4852, 0.875] | ✓ |
| full | [0.5046, 0.6253] | [0.8228, 1.2697] | ✓ |

## ROBUSTNESS (top-200, 5y) — 2021-06-12 → 2026-06-12, 1256 days, top-200

### H1′ — expansion beyond ATR
- Candidate 1.1807× vs baseline 0.9381× ATR · edge 0.2426 CI [0.2124, 0.2741] p=0.0 → **SUPPORTED** (need >1.0× and CI>0)

### H2 — tradeability (2-of-3)
| Metric | Candidate | Baseline | Edge CI | Clears |
| --- | --- | --- | --- | --- |
| Trend efficiency | 0.4755 | 0.4549 | [0.0162, 0.0249] | ✓ |
| Capturable move % | 5.2372 | 2.5068 | [2.5964, 2.8719] | ✓ |
| Net move % | 3.3393 | 1.5749 | [1.6793, 1.8566] | ✓ |

→ 3/3 clear → **SUPPORTED**

### H3 — signal attribution (vs ATR-only screen)
| Signal set | ΔE CI | ΔCM CI | Additive |
| --- | --- | --- | --- |
| ATR_Gap | [0.1121, 0.1466] | [0.3245, 0.5283] | ✓ |
| ATR_RVOL | [0.2131, 0.2621] | [0.222, 0.4033] | ✓ |
| full | [0.242, 0.3022] | [0.3701, 0.6734] | ✓ |

## Honest scope

- Daily-bar gap/RVOL approximations carry over from v0.1 (gap≈open, daily-RVOL proxy).
- A real premarket feed (PR #221 gappers) stays a **hard gate before any promotion** — out of v0.2 scope.
- Verdict requires holding on BOTH cuts; divergence is reported as the finding, not smoothed over.
