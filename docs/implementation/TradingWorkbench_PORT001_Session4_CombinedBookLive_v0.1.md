# TradingWorkbench — PORT-001 §4: Combined Book Live Template (v0.1)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-27 |
| Phase / Session | PORT-001 (Capability Onboarding) §4 — live paper deployment |
| Predecessor | Onboarding Gate PASSED (construction-verification), `programs.py` PORT-001 = validated, Capability Certificate v1.0 Gate-Passed (L1+L2) — PR #303 |
| Scope | Build the `combined_book` live strategy template (code) + the owner-gated activation recipe. Advances **L3** on activation. |
| Tag on completion | (none until activated) |
| Out of scope | Live activation itself (owner-gated); the self-stack data-fidelity study; correlation-aware λ tilt; §5 Continuous Evidence |

## Why this session exists

PORT-001's construction engine is validated (Onboarding Gate, L1+L2). §4 makes it **operational** as a live paper book — the deployment step that advances the Capability Certificate to **L3 (Paper operational)**. Like SEC-001 / LOW-001 before it, the *template* ships here as code; *activation* is owner-gated (it needs a provisioned Alpaca paper account + the ADR-0005 24-hour cooldown).

## What this session ships

- **`apps/backend/strategies_user/templates/combined_book.py`** — `CombinedBook(Strategy)`, a regular deterministic template:
  - Two sleeves blended at a **fixed 0.40 equity / 0.60 cross-asset** (production live config, λ=0).
  - **Equity sleeve:** top-quantile 12-1 momentum (`ctx.factors.momentum_scores`), equal-weight, per-name capped (4%); crash protection = the market-regime filter (de-risk the equity sleeve to cash below the market MA — the live analogue of the sibling vol-target/VIX crash engine).
  - **Cross-asset sleeve:** the validated `cross_asset_tsmom` (PORT-001 §1) over the 8-ETF daily-close panel — risk-parity, vol-targeted (de-risk only, gross ≤ 1).
  - Every order through `ctx.submit_order` → OrderRouter + risk engine (ADR 0002). No broker/DB/network/LLM.
- **`apps/backend/tests/strategies/test_combined_book_template.py`** — 9 tests: schema↔params parity, frozen 40/60 + sleeve defaults, weekly cadence, the weighted two-sleeve blend (equity 0.40 × equal-weight + cross-asset 0.60 × TSMOM), the regime filter zeroing the equity sleeve while the cross-asset sleeve keeps trading, cross-asset insufficient-history bail-out, equity-factor-unavailable hold, per-name cap, rejection policy.

Loads cleanly via the real `StrategyLoader` (plain class — the exec/`@dataclass` footgun avoided); ruff + mypy clean; no forbidden imports (strategy isolation).

## Honest verdict (carried on every artifact)

**Crash-protected BETA + diversification, NOT alpha.** The product's value is drawdown reduction + diversification, not selection skill. Success at §4 is *operational correctness* (clean rebalances, expected positions, proper risk gating), not P&L (ADR 0014).

## Owner-gated activation recipe (when ready)

Mirrors the SEC-001 / LOW-001 activations (see those memories). **Requires the owner to provision an Alpaca paper account.**

1. **Provision the account** — add a new `ALPACA_PAPER_*` keypair to `.env`; create the user + account (`scripts/create_user.py`, needs `MASTER_KEY` exported; creds live in the encrypted CredentialStore, not env).
2. **Restart/rebuild the backend** so `BrokerRegistry.load_all()` picks up the new account. The `combined_book` template lives in the *mounted* `strategies_user/`, so it is visible without a rebuild — but `app/research/factor_lab/cross_asset.py` is `app/`-level (already on the image after the PORT-001 merges); confirm the running image is current (`docker compose build backend` if in doubt).
3. **Register the strategy** — `combined-book`, schedule `0 14 * * mon` (Monday 09:00 ET; day-name avoids the APScheduler off-by-one), symbols = the momentum universe (top-N + the 8 cross-asset ETFs SPY/EFA/EEM/TLT/IEF/GLD/DBC/UUP). Default params = the frozen 40/60 + sleeve config.
4. **Activate** with the ADR-0005 24-hour cooldown (deterministic strategy). First rebalance the following Monday.

## What this session does NOT do

- Activate the book (owner-gated; needs the paper account).
- The **self-stack data-fidelity study** (`--db` real mode: Sharadar momentum + the §1 Total-Return Adapter over Alpaca) — confirms the platform's own data path end-to-end; separate, looser-tolerance study.
- The correlation-aware λ tilt (deferred; production is λ=0).
- §5 Continuous Evidence (L4).

## Notes & gotchas

1. **SPY is both** the market-regime proxy and a held cross-asset ETF. The equity sleeve excludes the cross-asset ETF set (and the bare proxy) from its universe so SPY is not double-counted; the cross-asset sleeve still holds SPY per its TSMOM weight.
2. The cross-asset sleeve prices off daily **close** bars (a small price-return approximation of the research path's total-return panel — distributions are immaterial for intra-rebalance sizing).
3. Total gross ≤ 1: equity_sleeve_weight × 1 + cross_asset_weight × (gross ≤ 1); the remainder is cash. No leverage.
