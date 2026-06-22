# Candidate Engine — Market Opportunity Discovery (v1 intraday)

*Generated 2026-06-22T23:39:08+00:00 · read-only research · SCAN-001 §0a: the candidate set is evidence, not a signal.*

## H1 — does curation select opportunity?

- **Verdict:** SUPPORTED — candidate set shows a positive, statistically-separated opportunity edge
- Candidate mean intraday range: **6.3285%** vs baseline **3.0858%**
- Edge (candidate − baseline): **3.2428%** · 95% CI [3.0816, 3.4115] · p = 0.0
- Daily win rate (candidate > baseline): **99.9%** over 2123 days

Window 2018-01-01 → 2026-06-12 · universe top-200 by $-vol (monthly PIT) · top-15 candidates/day.

## Frozen filters (SCAN-001 §2)

| Filter | Threshold |
| --- | --- |
| Gap % | > 3.0 |
| RVOL | > 2.0× |
| ATR % | > 2.0 |
| Price | > $10.0 |
| $-volume | > $20,000,000 |

## Sample Candidate Report (latest scored day)

| # | Symbol | Gap % | RVOL | ATR % | Price | Reason | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ADBE | 7.4954 | 4.3361 | 4.9556 | 218.8 | Gap + RVOL + ATR | 1.0 |
| 2 | SATS | 2.4116 | 6.3317 | 6.6672 | 128.13 | RVOL + ATR | 1.0 |
| 3 | NBIS | 5.5841 | 0.9333 | 11.039 | 222.24 | Gap + ATR | 0.9307 |
| 4 | MRVL | 3.8574 | 0.7713 | 11.6271 | 280.71 | Gap + ATR | 0.6429 |
| 5 | RKLB | 2.8054 | 2.4791 | 10.2759 | 114.78 | RVOL + ATR | 0.6198 |
| 6 | SMCI | 3.5971 | 1.4119 | 14.4734 | 31.97 | Gap + ATR | 0.5995 |
| 7 | CRWV | 3.5878 | 1.336 | 8.958 | 95.74 | Gap + ATR | 0.598 |
| 8 | ARM | 3.3048 | 1.3205 | 11.4662 | 342.23 | Gap + ATR | 0.5508 |
| 9 | ASTS | 0.9205 | 2.1397 | 13.77 | 97.56 | RVOL + ATR | 0.5349 |
| 10 | MU | 2.416 | 0.7423 | 8.6622 | 995.87 | ATR | 1.0 |
| 11 | NVDA | 0.0049 | 0.6268 | 4.1577 | 204.87 | ATR | 1.0 |
| 12 | SNDK | 0.346 | 0.9973 | 7.9043 | 1881.51 | ATR | 1.0 |
| 13 | INTC | 0.389 | 1.1794 | 7.9923 | 116.96 | ATR | 1.0 |
| 14 | TSLA | 0.0777 | 1.3686 | 4.3348 | 399.15 | ATR | 1.0 |
| 15 | AMD | 2.3001 | 0.9932 | 7.1497 | 488.45 | ATR | 1.0 |

## Caveats — read before believing the headline

- MECHANICAL CORRELATION: candidates are selected partly on ATR % (a range measure), so a higher realized intraday range is partly DEFINITIONAL, not a discovered edge. The ~100% daily win rate confirms the relationship is near-mechanical. H1-as-stated is supported, but the headline edge overstates the discovery.
- The genuinely open questions (next iteration): (a) do candidates expand BEYOND their own ATR forecast — realized range vs ATR-implied range — or just track it? (b) is the range DIRECTIONAL (tradeable trend) or chop? (c) does the gap/RVOL signal add range over an ATR-only screen (H3 attribution)?
- PIT approximations (gap uses the official open ≈ 09:25 premarket; daily-RVOL proxy) need true premarket data before any promotion past prototype.

## PIT honesty & v1 limitations

- **Gap %** uses the official open as a ~5-min approximation of the live 09:25 premarket price.
- **RVOL** is a daily-volume proxy; true premarket relative volume is the v1 refinement.
- Universe is re-struck **monthly** (PIT, survivorship-free); the opportunity metric is the post-open outcome and cannot leak into selection.
