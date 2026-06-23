# SCAN-001 v0.4 — The Confidence Model (calibration + composability) evidence

*Generated 2026-06-23T11:04:11+00:00 · read-only · SCAN-001 §0a: candidate set is evidence, not a signal. Lift at the evidence layer only — no P&L simulation.*

## Verdict: CONFIDENCE-UNINFORMATIVE — per-candidate confidence does not predict expansion

*v0.2 Validated + v0.3 Operating-Envelope verdicts are unchanged; v0.4 annotates HOW to weight the candidate set. L4 stays gated on the premarket-data replication.*

### Calibration curve — does confidence predict expansion? (headline cut)

The single readable test of the model: realized expansion `E` by confidence band. If it steps up Low → Medium → High, the per-candidate confidence is informative.

| Confidence band | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 19130 | [0.0031, 0.6904] | 1.4344 | 4.4725 |
| Medium | 19130 | [0.6905, 1.0] | 1.0944 | 4.3914 |
| High | 19130 | [1.0, 1.0] | 0.9163 | 4.6206 |

Monotone Low<Med<High: **False** · high−low edge -0.4505 CI [-0.4864, -0.4151] (p=1.0, 3496 days) → **H-conf-1 not supported**

## HEADLINE (top-200, 2010–2026) — 2010-06-12 → 2026-06-12, 3826 scored days (180 warm-up)

### Lever A — calibration
| Confidence band | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 19130 | [0.0031, 0.6904] | 1.4344 | 4.4725 |
| Medium | 19130 | [0.6905, 1.0] | 1.0944 | 4.3914 |
| High | 19130 | [1.0, 1.0] | 0.9163 | 4.6206 |

- **H-conf-1** (per-candidate calibration): monotone=False, high−low E -0.4505 CI [-0.4864, -0.4151] → **not supported**
- **H-conf-3a** (top-8 of top-15 by confidence): top-K mean E 1.0355 vs flat 1.1484, Δ -0.1129 CI [-0.1222, -0.1035] → **not supported**

### Lever B — regime throttle (expected small; REGIME-ROBUST)
- **H-conf-2** (forward calibration): covariance(conf, edge) 0.0007 CI [0.0002, 0.0011] → **SUPPORTED** · median split: high-conf days edge 0.2331 vs low-conf 0.187 (3646 non-warm days)
- **H-conf-3b** (exposure throttle): edge/exposure throttled 0.2074 vs flat 0.2069 (Δ 0.0006, mean exposure 0.9768)
- **H-conf-3c** (composite): E/exposure 1.0363 vs flat book 1.1489 (Δ -0.1126)

## RECENCY cross-check (top-500, 2021–2026) — 2021-06-12 → 2026-06-12, 1057 scored days (180 warm-up)

### Lever A — calibration
| Confidence band | n | conf range | realized E | realized CM |
| --- | --- | --- | --- | --- |
| Low | 5285 | [0.0083, 0.6004] | 1.503 | 4.7134 |
| Medium | 5285 | [0.6005, 0.852] | 1.5089 | 6.2007 |
| High | 5285 | [0.8521, 1.0] | 1.3381 | 6.9442 |

- **H-conf-1** (per-candidate calibration): monotone=False, high−low E -0.0834 CI [-0.1439, -0.019] → **not supported**
- **H-conf-3a** (top-8 of top-15 by confidence): top-K mean E 1.4397 vs flat 1.45, Δ -0.0103 CI [-0.0248, 0.004] → **not supported**

### Lever B — regime throttle (expected small; REGIME-ROBUST)
- **H-conf-2** (forward calibration): covariance(conf, edge) 0.0036 CI [0.0005, 0.007] → **SUPPORTED** · median split: high-conf days edge 0.0 vs low-conf 0.5329 (877 non-warm days)
- **H-conf-3b** (exposure throttle): edge/exposure throttled 0.5117 vs flat 0.5093 (Δ 0.0024, mean exposure 0.9745)
- **H-conf-3c** (composite): E/exposure 1.4425 vs flat book 1.4527 (Δ -0.0102)

## Honest scope

- **PIT confidence is a normal-approx** of v0.3's block bootstrap (an expanding-window bootstrap per day is prohibitive); the blend/branch logic is identical to v0.3.
- The per-day Discovery Confidence throttles on the **market regime** (bull/bear/sideways); the vol axis is left to v0.3's heatmap.
- Within a day the composite rank equals the opportunity-confidence rank (Lever B is constant per day) — by design; Lever B only weights across days.
- Lift is **evidence-layer** (expansion edge / edge-per-exposure), never a P&L backtest — the premarket-data gate (PR #221) stays the hard prerequisite before any live use.
- Survivorship-biased universe (today's liquid names) — read effects as relative.
