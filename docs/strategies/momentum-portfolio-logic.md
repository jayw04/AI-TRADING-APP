# momentum-portfolio — Strategy Logic (trader review)

*A plain-language description of what the `momentum-portfolio` strategy does, when and why it buys and sells, what the weekly rebalance does, and what data it runs on. Written for traders to review the logic — not the code.*

---

## 1. The idea in one paragraph

`momentum-portfolio` is a **systematic, long-only, weekly price-momentum portfolio**. Once a week it ranks a fixed list of large, liquid US stocks by their recent price momentum, **holds the strongest ~20% (the "winners")**, equal-weighted, and **sells the ones that have dropped out of that top group**. It is fully rules-based — there is no discretion, no news reading, no earnings calls. It rides what's working and cuts what isn't, on a fixed weekly schedule. A market-trend filter can pull the whole book to cash in a downtrend.

The economic premise is the well-documented **momentum premium**: stocks that have outperformed over the past several months tend, on average, to keep outperforming over the next few weeks. The strategy harvests that tendency in a disciplined, diversified way.

---

## 2. What data it runs on

| Data | Source | Used for |
|---|---|---|
| Daily price history (split/dividend-adjusted), survivorship-free | Sharadar (via Nasdaq Data Link) | The momentum ranking signal + building the tradeable universe |
| Live current prices per stock | Alpaca (brokerage) | Sizing each position (how many shares) |
| Live account equity | Alpaca | How much capital to deploy |
| SPY (S&P 500 ETF) daily prices | Alpaca | The market-trend (regime) filter — SPY is **never held**, only used as a market gauge |

All price data is **daily closing prices** (not intraday). The momentum signal uses split/dividend-adjusted closes so corporate actions don't distort returns.

---

## 3. What it can trade (the universe)

The strategy only ever buys names from a **fixed candidate list** set at activation — currently the **top ~200 most-liquid US stocks** (ranked by trailing dollar volume). It cannot buy anything outside that list. SPY is in the list only so the trend filter can read it; SPY itself is never bought as a holding.

This keeps the book in large, liquid, easily-tradeable names and avoids thin/illiquid stocks.

---

## 4. The signal — how it ranks stocks

Each stock gets a **momentum score** based on its **6-minus-1 month price return**:

- Take the stock's total return over roughly the **past 6 months**, but **skip the most recent ~1 month**.
- *Why skip the last month?* Very recent moves tend to **reverse** short-term (a stock that spiked last week often pulls back). Skipping the last month measures the durable trend, not the short-term noise.
- These returns are then standardized across the universe (a relative score), so the strategy is comparing each name's momentum **against its peers that week**, not against an absolute threshold.

**Higher score = stronger relative momentum = more likely to be held.**

---

## 5. What the weekly rebalance does

The strategy rebalances **once per week — Monday at ~10:00 AM ET** (30 minutes after the open). One rebalance per week, no intraday trading. Each Monday it runs these steps:

1. **Trend check first.** If the market (SPY) is in a downtrend (below its 200-day moving average) → **go fully to cash** (sell all holdings) and stop. (See §8.)
2. **Rank the universe** by the 6-1 momentum score (§4).
3. **Pick the target book** = the **top quintile (top 20%)** of the universe by score, capped at a maximum number of names (currently **5**), and only names with a **positive momentum score** (it won't buy names that are falling).
4. **Compare target vs. what's currently held**, and trade the difference:
   - **Sell** any holding that is **no longer in the target** (it lost momentum and dropped out).
   - **Buy / top up** the names in the target toward an **equal dollar weight**.
5. Apply two anti-churn rules so it doesn't over-trade (see §7).

Between Mondays it does **nothing** — it holds the book as-is until the next rebalance.

---

## 6. When it BUYS — and why

The strategy **buys (or adds to) a stock when**, at the Monday rebalance:

- The stock is in the **top 20% of the universe by 6-1 momentum** (and within the max-names cap), **and**
- Its momentum score is **positive** (above the minimum floor), **and**
- The market is **not** in a downtrend (SPY above its 200-day average), **and**
- The strategy isn't already holding it at the target size.

**Why:** these are this week's strongest, still-rising names among liquid large-caps. The momentum premium says the strongest recent performers tend to continue, so the book concentrates capital in them. New leaders that climb into the top group get bought; existing winners get topped up toward their target weight.

Each buy is sized to an **equal share of the book** (see §9).

---

## 7. When it SELLS — and why

The strategy **sells a stock when**, at the Monday rebalance:

- The stock **fell out of the top group** (its momentum faded and it's no longer in the target) → **sold to flat (exit).** *Why:* the thesis for holding it (strong momentum) is gone, so capital rotates to current leaders. This is the strategy's built-in "cut losers / fading names" discipline — it happens automatically every week, which is why it uses **no per-stock stop losses**.
- The stock is **trimmed** if it's still in the target but the book needs rebalancing toward equal weight (e.g. it grew too large).
- **Everything is sold** if the market trend filter flips risk-off (SPY below its 200-day average) → the whole book goes to cash.

**Two anti-churn guards** prevent needless trading:
- **Rank hysteresis:** a name you already hold that has slipped *just* below the cut-off is **kept**, not sold — so the book doesn't flip a name in and out on a tiny rank wobble.
- **Turnover threshold:** small adjustments to an existing position (below a few percent of its target size) are **skipped** — it won't trade a handful of dollars to chase a perfect weight.

---

## 8. The market-trend filter (risk-off to cash)

Before doing anything else each week, the strategy checks the broad market:

- **If SPY is below its 200-day moving average → sell everything and stay in cash.** It will not hold a momentum book into a confirmed market downtrend.
- **If SPY is above its 200-day average → trade normally.**

**Why:** momentum strategies suffer their worst losses ("momentum crashes") during market downturns and sharp reversals. Sitting out downtrends avoids the worst of that. If SPY data is temporarily unavailable, the filter **"fails open"** — it trades normally rather than freezing the book on a data glitch.

---

## 9. Position sizing

- **Equal weight:** each held name gets the same target dollar amount = *investable equity ÷ number of names held*.
- **Per-name cap:** no single name can exceed a set fraction of the account (currently **20%**).
- **Cash buffer:** a small slice (currently **2%**) is kept in cash, not deployed.
- **Whole shares** by default. *(On a small account this can leave money undeployed because expensive stocks round down — an optional fractional-share mode can deploy more fully; currently off.)*
- All orders are **market orders, day orders** — submitted at the Monday rebalance and filled near the open.

---

## 10. Safety nets — what can stop it

The strategy relies on **portfolio-level** risk controls, not per-stock stops:

- **Weekly turnover** — losers/faders exit every Monday automatically.
- **Diversification** — equal-weight across several names.
- **Market-trend filter** — to cash in a downtrend (§8).
- **Account circuit breaker** — a separate, account-wide safety gate: if the account's daily loss exceeds its limit, **all trading halts** (this is enforced by the platform's risk engine, independent of the strategy, and is monitored continuously — not just when an order is sent).
- **"Hold on missing data"** — if the momentum data isn't available on a given week, the strategy **does nothing** (keeps its current positions) rather than trading on bad/stale inputs.

---

## 11. Optional risk overlays (currently OFF)

These are built in but **switched off by default** — listed so reviewers know they exist:

- **Volatility targeting:** scale total exposure *down* when market volatility is high (extra crash protection), capped at 100% (no leverage).
- **Sector caps:** limit how much of the book can sit in any one sector (prevents, e.g., the whole book becoming a single semiconductor/AI bet).
- **Fractional shares:** deploy capital more fully on small accounts.

Each is a deliberate, separately-validated switch — none changes the core buy/sell logic above.

---

## 12. What it does NOT do

- **No shorting** — long-only.
- **No leverage** — at most 100% invested (minus the cash buffer).
- **No intraday trading** — one rebalance per week, at the Monday open.
- **No per-stock stop losses** — risk is managed at the portfolio level (§10).
- **No discretion / news / fundamentals** — it is purely price-momentum and rules-based. (Fundamental factors are a separate, future addition, not part of this strategy.)
- **No earnings or event timing.**

---

## 13. Current live settings (for review)

| Setting | Current value | Meaning |
|---|---|---|
| Universe | ~200 most-liquid US stocks (+ SPY as gauge) | What it can buy |
| Momentum window | 6 months, skipping the last 1 | The signal |
| Hold | Top 20% by momentum | Selection cut |
| Max names | 5 | Most positions held at once |
| Minimum score | 0 (positive momentum only) | Won't buy falling names |
| Per-name cap | 20% of equity | Concentration limit |
| Cash buffer | 2% | Always-uninvested slice |
| Rebalance | Weekly, Monday ~10:00 ET | Cadence |
| Trend filter | SPY vs its 200-day average | Risk-on / risk-off to cash |
| Shares | Whole shares | (fractional optional, off) |
| Vol targeting / sector caps | Off | Optional overlays |

Mode: **paper trading** (simulated, no real money). Account ≈ \$10,000 simulated.

---

## 14. A worked example

Suppose on a Monday the market is healthy (SPY above its 200-day average). The strategy ranks the ~200 names; the top 5 by 6-1 momentum (all with positive scores) are **A, B, C, D, E**. It currently holds **A, B, C, X** from last week.

- **X** is no longer in the top 5 → **sold to cash** (faded).
- **A, B, C** are still in the target → **held / trimmed toward equal weight**.
- **D, E** are new leaders → **bought** to an equal share of the book.

Result: an equal-weight book of A, B, C, D, E. If the next Monday SPY has fallen below its 200-day average, **all five are sold to cash** until the trend turns back up.

---

*Questions or changes a reviewing trader might raise — momentum window, number of names, the trend-filter threshold, whether to enable vol targeting / sector caps / fractional shares — are all configurable settings, not code rewrites.*
