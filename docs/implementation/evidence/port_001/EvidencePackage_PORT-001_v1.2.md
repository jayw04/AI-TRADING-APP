# Evidence Package — PORT-001 **v1.2** (lever #2: look-through equity-beta-cap governor, default OFF)

_Companion to `EvidencePackage_PORT-001_v1.1.md`. Documents the third and final sibling lever ported into the platform `combined-book`. Honest verdict unchanged: **crash-protected beta + diversification, NOT alpha.**_

## 1. What & why

The sibling Combined Book runs a **de-risk-only equity-beta-cap governor** (`portfolio_riskmodel.cap_equity_beta`, spec §11 #2). It targets the capability's headline disclosure **§6.2**: the equity sleeve is ~13% of capital but carries the majority of *risk*. The governor caps that: when the book's look-through **equity-beta risk contribution** exceeds 0.80, it scales the equity-beta names (single stocks + SPY/EFA/EEM) down, raising cash; bonds/gold/commodities/USD/KMLM are untouched.

**Honest value:** with the correlation-aware tilt now live (v1.1), the governor's *current* effect is small (sibling: ~1.4% freed, equity-beta RC 83%→80%). Its worth is a **standing safety net** against equity-beta drift + closing §6.2 + sibling parity.

## 2. The ported logic (faithful)

`cap_equity_beta(weights, returns, *, equity_names, cap=0.80, lookback=120, shrink=0.15)`:
- `C = (1−λ)·cov(returns[-lookback:]) + λ·diag(diag(cov))` — sample covariance (ddof=1), off-diagonals shrunk (λ=0.15), diagonal unchanged (Ledoit-Wolf-lite, faithful to the sibling `_shrink`).
- Per-name normalized risk contribution via the **reused, tested** `erc.risk_contributions(cov, w)`; `equity_beta_rc = Σ rc[mask]` where mask = names not in `{TLT, IEF, GLD, DBC, UUP, KMLM}`.
- If `≤ cap` or `< 3` priced names → no change. Else **monotone bisection** on `f∈[0,1]` scaling the masked weights until `equity_beta_rc ≤ cap` (lo side). De-risk only; never raises a weight; unpriced names untouched.

**Lookback = 120** (not the sibling's 504): live 1Day history is ~1-year-capped (`context.py:108`) and the common-date panel shrinks with short-history names (KMLM, fresh momentum picks).

## 3. Posture — default OFF + live dry-run (owner decision)

Shipped in the `combined-book` template with `enforce_beta_cap=False` (book unchanged) and `beta_cap_report_only=True`: the governor **computes and logs** the would-be equity-beta RC + haircut on every live rebalance without applying it. The **Monday rebalance log** is the platform-side real-data dry-run (analogous to the sibling's "real 6/24 book: 84.4%→80.0%, 3.4% freed"). The owner enforces it later via a param flip (`enforce_beta_cap=True`), no code change. Fail-open (any error / thin panel → book unchanged, logged).

## 4. Validation

- **Unit** (`tests/research/factor_lab/test_beta_cap.py`): over-budget de-risks equity names only + frees cash + hits the cap; within-budget no-op; `<3` priced → skip; unpriced names untouched; determinism; classification (`default_equity_names` excludes exactly the 6 non-equity ETFs).
- **Synthetic demonstrator** (`scripts/verify_beta_cap.py` → `port001_beta_cap_synthetic.json`): a deliberately equity-concentrated book — equity-beta RC **1.08 → 0.80**, equity scaled ×0.145, gross 1.00 → 0.44 (cash freed 0.56), hedges (TLT/GLD/UUP) untouched. (Synthetic is extreme by design; the real book is far less concentrated — the live dry-run reports the true number.)
- ruff + mypy clean; the reused `erc.risk_contributions` contract (`tests/research/factor_lab/test_erc.py`) is unchanged.

## 5. Scope / deploy

Template `version` → **1.2.0**. **No new ADR** (de-risk-only construction step; not a risk-engine gate; no invariant change; KMLM/SPY etc. already on the Alpaca path). Because the governor is default-OFF, re-registering id=9 to pick up the new params is low-risk (book behavior unchanged; only the report-only telemetry is added). Deferred: total-return live pricing for the sleeve.

_v1.2 — 2026-07-03._
