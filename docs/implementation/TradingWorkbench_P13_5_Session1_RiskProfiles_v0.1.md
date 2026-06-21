# Trading Workbench — P13.5 §1: Momentum Risk Profiles (v0.1)

| Field | Value |
|---|---|
| Document version | v0.1 (2026-06-21) |
| Date | 2026-06-21 |
| Phase | **P13.5 — Platform Validation** (owner's milestone; the "three live risk profiles" item) |
| Predecessor | P14 §1 (multi-factor re-test → keep v1.1); P12 §2 (vol-scaling grid = monotonic risk dial) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A first-class **Risk Profile** construct (Conservative 10% / Balanced 15% / Growth 20%) + profile-aware paper activation, so the same momentum strategy runs as three live paper books at different vol targets — the customer-facing "risk dial." |
| Estimated wall time | 2–3 hours (code) + owner account setup |
| Out of scope | Product UI/API for switching profiles (P13); a profile-selector in the strategy form; any change to the alpha logic; live (real-money) trading. |

## 1. Why this session exists

The owner's `comments.md` (Option 2): don't add a *new* strategy — instead show that the platform
supports **configurable risk** by running momentum at three named vol targets. P12 §2's grid already
proved vol-scaling is a **monotonic risk dial** (every target 10–20% clears the enable gate; lower =
less drawdown/less return, higher = the reverse), so this is *packaging proven behavior as a product
concept*, not new research. It directly feeds P13.5 Platform Validation ("three live momentum risk
profiles, 90–180 days of evidence").

This is also the evidence-consistent answer to "should we build more strategies?": the **only**
sanctioned "more books" are these risk-dial variants of the one validated strategy — not the
multi-factor book (P14 §1: not decisive).

## 2. What this session ships

- **`app/strategies/risk_profiles.py`** — the canonical construct: `RISK_PROFILES`
  (Conservative→0.10 / Balanced→0.15 / Growth→0.20), `get_profile`, `profile_name`
  (`momentum-<profile>`), and `profile_params(profile, base)` (turns the daily vol overlay ON and sets
  `vol_target_annual`; everything else identical → same alpha). Pure + tested.
- **Profile-aware `scripts/paper_activate_momentum.py`** — new `--risk-profile {conservative,balanced,
  growth}` flag that applies `profile_params` and defaults the book name to `momentum-<profile>`.
- **`tests/strategies/test_risk_profiles.py`** — monotonic targets, case-insensitive lookup,
  param-merge/no-mutation, name convention.

## 3. The account model (why each profile needs its own account)

Strategies have **no `account_id`** — a strategy resolves its broker account via `(user, broker,
mode)` (P5 §7). So three momentum books on **one** paper account would compete (same picks,
account-level vol-scaling). Each profile therefore runs as its **own user + paper account**, exactly
like Range Trader uses `ALPACA_PAPER_1`.

Current accounts (`.env`): `ALPACA_PAPER` (BFY6 — **Balanced 15% is already live**, strategy id=2,
user jay) and `ALPACA_PAPER_1` (Range Trader). **Conservative and Growth each need a fresh paper
account** (`ALPACA_PAPER_2`, `ALPACA_PAPER_3` — owner creates at Alpaca + adds to `.env`).

## 4. Activation runbook (per new profile)

For **Conservative** (repeat for **Growth** with `ALPACA_PAPER_3`):

```bash
# 0. (owner) create an Alpaca paper account → add ALPACA_PAPER_2_API_KEY/SECRET to .env
# 1. create the profile's user
apps/backend/.venv/Scripts/python.exe apps/backend/scripts/create_user.py \
    --email momentum-conservative@local --display-name "Momentum Conservative"
# 2. provision that user's paper account from the new creds (existing tool, parameterized)
apps/backend/.venv/Scripts/python.exe apps/backend/scripts/provision_range_account.py \
    --email momentum-conservative@local --label "Alpaca Paper (Conservative)" \
    --key-env ALPACA_PAPER_2_API_KEY --secret-env ALPACA_PAPER_2_API_SECRET
# 3. create + start the momentum book at the Conservative vol target (10%)
apps/backend/.venv/Scripts/python.exe apps/backend/scripts/paper_activate_momentum.py \
    --risk-profile conservative \
    --email momentum-conservative@local --password '<pw>' --totp <code> \
    --symbols-file apps/backend/data/paper_symbols.txt
```

**Balanced** is already live — no action (it *is* the v1.1 default on BFY6). Preview any step with
`--dry-run` first.

## 5. Manual smoke

`--dry-run` each profile and confirm the params + name:
```
paper_activate_momentum.py --risk-profile growth --symbols-file <syms> --dry-run
# → params include use_daily_overlay=true, vol_target_annual=0.2; name 'momentum-growth'
```

## 6. Walk-away discipline

≥1 hour (config/tooling; no order-path or risk-engine code). Live activation is owner-gated and
follows the activation cooldown like any paper start.

## 7. What this session does NOT do

- No product UI/API to pick or switch profiles (that's P13 productization).
- No automatic account creation (owner provisions Alpaca paper accounts).
- No change to momentum alpha, the risk engine, or the order path.
- No real-money/live trading.

## 8. Notes & gotchas

1. **Stdout must stay ASCII** (cp1252) — the profile dry-run print uses `->`, not `→` (the recurring
   Windows-console trap; bit this script once during the build).
2. Balanced 15% is the **already-live** book — don't double-provision it on a second account.
3. All three profiles share the same symbols universe + weekly schedule; they differ *only* in
   `vol_target_annual`. The risk dial is the whole point.
