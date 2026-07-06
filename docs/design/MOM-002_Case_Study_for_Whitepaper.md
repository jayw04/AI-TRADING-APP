# Case Study 3 — MOM-002: Rejecting a Plausible *Enhancement* with Evidence

*Finished prose for Whitepaper Chapter 14 (place after Case Study 2 — RNG-001). Sources:
`docs/implementation/evidence/mom_002_broad_momentum/broad_momentum.md`,
`apps/backend/scripts/mom002_broad_momentum.py`, `apps/backend/research/mom002/`.*

---

Case Study 2 showed the platform rejecting a plausible *strategy* — the opening-range fade — on
reproducible evidence. This one shows something a step more demanding, and for a diligent buyer more
convincing still: the platform rejecting a plausible *enhancement to a strategy it had already
validated*. Momentum is the platform's reference book, live on paper and backed by a clean multi-year
edge. The temptation, after a sharp down day, is to "fix" the winner. MOM-002 is the record of that
temptation being tested — one variable at a time — and declined.

## At a glance

```
Observation           three live momentum books lost together — too correlated (one macro bet)
      │
      ▼
Hypothesis            broaden Top-5 → Top-20 and cap each sector to de-concentrate
      │
      ▼
Breadth Test  ──►  Sector-Cap Test  ──►  Correlation Analysis
      │
      ▼
Rejected              reshaping the same factor is not diversification
      │
      ▼
Portfolio Engineering combine independent factors instead
```

## The hypothesis

On 2 July 2026 the three live momentum books lost together. A daily-report review made the correct
diagnosis: the loss was not a bug and not a strategy failure — momentum is *expected* to take occasional
sharp drawdowns — but the three books were **too correlated**, effectively one macro bet (semiconductors,
storage, AI infrastructure) rather than independent evidence. The intuitive fix is to *broaden* the book:
hold the Top-20 names instead of the Top-5, and cap any single sector, so the portfolio is less
concentrated. It is exactly the kind of enhancement that *feels* prudent. MOM-002 asked the only question
that matters: **can reshaping a concentrated momentum book actually improve its risk-adjusted
performance — and can we prove it, either way?**

## Same framework, one variable at a time

The study reused the production backtest engine — the same survivorship-free price store, weekly
rebalance, long-only equal-weight construction, and last-price-to-cash delisting the live book uses — and
changed exactly one thing at a time: first the **breadth** (Top-5 / 10 / 15 / 20), then a **30% per-sector
cap** layered on each. Every configuration was judged on risk-adjusted metrics (Sharpe, Calmar, maximum
drawdown, out-of-sample Sharpe), never on headline return.

**Experiment 1 — breadth.** Over 2019–2026, widening the book monotonically *reduced* its risk-adjusted
quality:

| Book | CAGR | Sharpe | Max drawdown | Calmar | OOS Sharpe |
|---|---:|---:|---:|---:|---:|
| **Top-5** | +77% | **1.37** | −55% | **1.40** | **1.67** |
| Top-10 | +54% | 1.25 | −48% | 1.11 | 1.39 |
| Top-15 | +50% | 1.28 | −42% | 1.20 | 1.50 |
| Top-20 | +38% | 1.12 | −40% | 0.96 | 1.33 |

Breadth bought exactly one thing — a shallower drawdown (−55% → −40%) — and paid for it in Sharpe, Calmar
and return, out-of-sample included. It is a return-for-drawdown trade, not a free lunch, and not
diversification.

**Experiment 2 — sector cap.** Run on the sector-populated data store, a 30% per-sector cap did not
recover the drawdown and *cost* Sharpe: the Top-10/15/20 books lost 0.17–0.29 Sharpe and saw slightly
*deeper* drawdowns; the Top-5 book was unaffected (five equal-weight 20% positions rarely breach a 30%
cap). The cap forces the book off its strongest momentum names into weaker sectors — degrading the signal
while the drawdown, which is driven by broad market beta rather than single-sector concentration, barely
moves.

## The load-bearing finding

The most useful number in the study is not any Sharpe ratio. It is a correlation: **the Top-5 and Top-20
books' monthly returns still correlate 0.90.** Widening the *same factor* four-fold does not manufacture
independent evidence — it is still one momentum bet. The redundancy the review flagged (three momentum
books correlating ~1.00, with 100% holdings overlap) therefore *cannot* be engineered away by reshaping a
momentum book. Independent evidence has to come from a **different factor** — low volatility, sector
rotation, cross-asset trend — not a different shape of momentum.

> **Key finding.** Diversification comes from **independent factors**, not from reshaping the same factor.

## The honest caveat

The sector-cap arm ran on the only store with sector data, which has full universe breadth only from
2025, so its precise result holds *within the available 2025–2026 universe*; a full-history confirmation
remains desirable when a complete sector dataset exists. The platform records that limitation rather than
generalizing past it — and classifies the confirmation as medium-priority future research, because
whether a sector cap moves Sharpe by a few hundredths over eight years is not on the critical path once
the practical decision is made.

## Verdict: Rejected — not Failed

MOM-002 is closed **Rejected**. A rejected enhancement is a *successful* research outcome: it narrows the
design space and prevents future effort from being spent rediscovering the same dead end. A plausible,
intuitive enhancement to a validated strategy was tested against the same evidence framework as everything
else and did not survive. Placed beside RNG-001 the
pair tells a single, durable story:

> **RNG-001:** a plausible *strategy* was rejected after systematic testing.
> **MOM-002:** a plausible *enhancement to a validated strategy* was also rejected after systematic
> testing.

Almost every quantitative platform markets its winners. TradingWorkbench is designed not only to
discover alpha but to *decline attractive ideas that do not survive rigorous evidence* — and to preserve
both the evidence and the reasoning so future researchers can build from known results rather than
repeating them. MOM-002's lasting contribution is that
decision, recorded: the project's focus now shifts from optimizing momentum to engineering a portfolio of
*independent* validated factors — the transition from strategy research to portfolio research.
