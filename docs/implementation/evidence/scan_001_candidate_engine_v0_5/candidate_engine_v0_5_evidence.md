# SCAN-001 v0.5 — The De-Tautologized (ATR-decoupled) Confidence evidence

*Generated 2026-06-23T11:42:26+00:00 · read-only · SCAN-001 §0a: candidate set is evidence, not a signal. Confidence under test = Gap+RVOL only (ATR excluded). Lift at the evidence layer only — no P&L.*

## Verdict: DECOUPLED-CALIBRATED — Gap+RVOL strength predicts a de-tautologized outcome and lifts the book; ship confidence_gr as the Candidate Report confidence (ranking gated)

*v0.2 Validated / v0.3 Operating-Envelope / v0.4 Confidence-Uninformative verdicts are unchanged; Capability Maturity stays L3; L4 gated on the premarket-data step.*

### De-tautologized calibration curve — does Gap+RVOL strength predict expansion? (headline)

Realized `E` by ATR-decoupled (Gap+RVOL) confidence band. The ATR signal is excluded from the confidence, so this is not the v0.1 mechanical channel.

| Gap+RVOL confidence | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 20125 | [0.0, 0.0] | 0.8043 | 3.2657 |
| Medium | 20125 | [0.0, 0.2203] | 1.0481 | 4.1228 |
| High | 20125 | [0.2203, 1.0] | 1.5807 | 5.8988 |

Monotone Low<Med<High (E): **True** · high−low E 0.8909 CI [0.847, 0.9348] → **H-cm-1 SUPPORTED**

### Discovery Confidence distribution (headline)

Where the bounded [0,1] Gap+RVOL confidence lands across candidates:

| Bin | count | % |
| --- | --- | --- |
| [0.0,0.1) | 35330 | 58.5 |
| [0.1,0.2) | 4188 | 6.9 |
| [0.2,0.3) | 3272 | 5.4 |
| [0.3,0.4) | 2677 | 4.4 |
| [0.4,0.5) | 2157 | 3.6 |
| [0.5,0.6) | 2291 | 3.8 |
| [0.6,0.7) | 1899 | 3.1 |
| [0.7,0.8) | 1505 | 2.5 |
| [0.8,0.9) | 1218 | 2.0 |
| [0.9,1.0] | 5838 | 9.7 |

## HEADLINE (top-200, 2010–2026) — 2010-06-12 → 2026-06-12, 4025 days, 60375 candidates

### H-cm-1 — ATR-decoupled calibration on E
| Gap+RVOL confidence | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 20125 | [0.0, 0.0] | 0.8043 | 3.2657 |
| Medium | 20125 | [0.0, 0.2203] | 1.0481 | 4.1228 |
| High | 20125 | [0.2203, 1.0] | 1.5807 | 5.8988 |

monotone=True, high−low E 0.8909 CI [0.847, 0.9348] → **SUPPORTED**

### H-cm-2 — ATR-stratified calibration on CM (3/3 bands, need ≥2)
| ATR band | candidates | paired days | high−low CM (CI) | pass |
| --- | --- | --- | --- | --- |
| low_atr | 20126 | 1722 | 1.2837 [1.1684, 1.4041] | ✓ |
| mid_atr | 20124 | 3222 | 0.3057 [0.2702, 0.3442] | ✓ |
| high_atr | 20125 | 1374 | 4.0097 [3.5543, 4.4795] | ✓ |

→ **H-cm-2 SUPPORTED** (3/3 bands separated)

### H-cm-3 — decoupled-confidence lift (top-K by Gap+RVOL vs flat)
- E lift: 0.1862 CI [0.1752, 0.1973] → **SUPPORTED**
- CM lift: 0.5081 CI [0.462, 0.5536]
- Decoupling check: mean ATR top-K 5.4757 vs flat 5.4808 (if topk≈flat ATR, the CM lift is not an ATR-selection artifact)

## RECENCY cross-check (top-500, 2021–2026) — 2021-06-12 → 2026-06-12, 1256 days, 18840 candidates

### H-cm-1 — ATR-decoupled calibration on E
| Gap+RVOL confidence | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 6280 | [0.0, 0.2632] | 1.128 | 4.8613 |
| Medium | 6280 | [0.2633, 0.7118] | 1.441 | 6.0233 |
| High | 6280 | [0.7118, 1.0] | 1.7704 | 7.5167 |

monotone=True, high−low E 0.5143 CI [0.4453, 0.5855] → **SUPPORTED**

### H-cm-2 — ATR-stratified calibration on CM (3/3 bands, need ≥2)
| ATR band | candidates | paired days | high−low CM (CI) | pass |
| --- | --- | --- | --- | --- |
| low_atr | 6281 | 595 | 1.4374 [1.1867, 1.6844] | ✓ |
| mid_atr | 6279 | 429 | 2.486 [1.8856, 3.1341] | ✓ |
| high_atr | 6280 | 550 | 4.3747 [3.245, 5.8161] | ✓ |

→ **H-cm-2 SUPPORTED** (3/3 bands separated)

### H-cm-3 — decoupled-confidence lift (top-K by Gap+RVOL vs flat)
- E lift: 0.1664 CI [0.1446, 0.188] → **SUPPORTED**
- CM lift: 0.674 CI [0.5801, 0.777]
- Decoupling check: mean ATR top-K 6.5371 vs flat 6.3138 (if topk≈flat ATR, the CM lift is not an ATR-selection artifact)

## Honest scope

- Confidence under test is **Gap+RVOL only** (`confidence_gr`); ATR still drives *selection*, never the tested confidence — the anti-tautology decoupling.
- Every CM test is **within ATR terciles** so the mechanical high-ATR→high-CM channel can't pose as a confidence signal.
- Lift is **evidence-layer** (E / CM diffs), never a P&L backtest — the premarket-data gate (PR #221) stays the hard prerequisite before any live use.
- Survivorship-biased universe (today's liquid names) — read effects as relative.
