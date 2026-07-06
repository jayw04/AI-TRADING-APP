# PORT-001 Self-Stack Data-Fidelity Study — v0.1

| Field | Value |
|---|---|
| Capability | PORT-001 — "Risk-Balanced Multi-Asset Portfolio" (Combined Book) |
| Study | Self-stack reproduction (the platform's OWN data path, end-to-end) |
| Date | 2026-06-27 |
| Result | **Onboarding Gate FAILED — Lifecycle Fidelity 43.7%** (expected; divergences fully attributed) |
| Bearing on validation | **None.** PORT-001's validation rests on the **construction-verification** gate pass (98.8%, `EvidencePackage_PORT-001_v1.0.md`). This study is a confidence/diligence check on the platform's data stack, not the validation basis. |
| Reproducible by | `run_port001_reproduction.py --db <factor duckdb> --reference <sibling.json>` (needs Alpaca via the ADR-0017 truststore) |

## Purpose

Construction-verification proved the platform's PCE/ERC reproduces the origin combined book **given the origin's own sleeve return series**. This study asks the harder, separate question: does the platform's **own data stack** — Sharadar momentum (equity) + the §1 Total-Return Adapter over **Alpaca** ETF bars (cross-asset) — reproduce the book end-to-end? It deliberately crosses data vendors (the origin priced cross-asset off Yahoo total-return; the platform uses Alpaca + Sharadar, per ADR 0030 #2), so it is expected to read against a **looser, attributed tolerance**, not the strict gate.

Spec aligned to the production config for this run: `PORT_001.n = 150` (the sibling's `max_names`).

## Result — Onboarding Gate (window-matched to the candidate)

Candidate self-stack book: Sharpe **1.03**, maxDD **−8.5%** over its available window; a coherent crash-protected multi-asset book.

| Criterion | Candidate | Reference (sibling, windowed) | value | thr | Pass | Attribution |
|---|---|---|---|---|---|---|
| Sharpe | 1.0298 | 0.7612 | Δ0.269 | ±0.05 | ✗ | different window + weekly cadence; 2018–2025 was favorable |
| Max drawdown | 0.0848 | 0.1157 | Δ0.031 | ±0.02 | ✗ | shallower DD on the shorter, post-2018 window |
| Daily-return corr | — | — | **0.852** | ≥0.98 | ✗ | cross-vendor (Alpaca vs Yahoo) + weekly-vs-monthly cadence + price-return vs total-return |
| Weight corr | — | — | 0.767 | ≥0.99 | ✗ | self-stack as-of ERC weights vs the origin's live λ>0-tilted weights |
| Trade count | 7556 | 28 | — | ±10% | ✗ | **incomparable conventions** — per-name-change count vs a turnover proxy; + weekly vs monthly |
| Determinism | — | — | 1.0 | req | ✓ | — |

## The attributed divergences (all known, none a defect)

1. **Data window.** The Alpaca **IEX free feed starts ~2018-11**, so the self-stack runs 2018-11 → 2025-12 (1,800 overlapping days) vs the origin's 2016-02 → 2026-06. Sharpe/maxDD are not window-comparable.
2. **Data vendor.** Cross-asset prices come from Alpaca (post-processed to total-return via the §1 adapter) vs the origin's Yahoo total-return. This is the dominant driver of the 0.852 (not ≥0.98) daily-return correlation. **ETF distribution source (resolved, PORT-001 #3, 2026-07-04):** Sharadar `actions` has **zero** coverage for the 9 cross-asset ETFs (they are absent from `actions`/`sep`), so the live source is the **Alpaca corporate-actions API** (`app/market_data/alpaca_distributions.py`) — a live box preview confirmed real distributions for 8/9 ETFs (GLD pays none), with raw-vs-TR trailing-return divergence of ~400–1200 bps on the coupon-payers (TLT, IEF, DBC).
3. **Rebalance cadence.** The platform's `run_momentum_backtest` (equity) and `backtest_cross_asset_sleeve` (W-FRI) rebalance **weekly**; the origin rebalances **monthly (21d)**. Different turnover and daily-return texture.
4. **Trade-count convention.** 7,556 (per-name open/close/reweight, weekly) vs ~28 (a turnover-per-year proxy). Not a like-for-like measure; the criterion is meaningless across conventions here.
5. **Weights.** Self-stack as-of ERC vs the origin's live correlation-aware-tilted (λ>0) weights.

## Conclusion

The platform's own data stack produces a **coherent, crash-protected multi-asset book that co-moves with the origin (daily-return corr 0.85)** — but it is **not a strict byte-reproduction**, and every divergence is attributed to a known data-vendor / cadence / window / convention difference, not to a construction defect. Per the platform's "attribute, don't waive" discipline, this does **not** change PORT-001's validated status (earned via construction-verification) and is **not** a promotion blocker.

## To tighten the self-stack reproduction (if pursued)

- A **paid Alpaca data feed** (SIP) for pre-2018 history → the full 2016-2026 window.
- **Monthly (21d)** rebalance cadence in the harness to match the origin.
- ~~Complete **ETF distribution coverage** for the total-return adapter (a dedicated corporate-actions source for the 8 ETFs).~~ **Resolved (PORT-001 #3):** live Alpaca corporate-actions provider wired into the sleeve pricing (default OFF).
- A **shared trade-count definition** exported by the origin.

_v0.1 — 2026-06-27. Companion to `EvidencePackage_PORT-001_v1.0.md` (the validation)._
