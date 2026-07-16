# Incident — account 2 holds a SHORT on a book where shorting is disallowed

**Date raised:** 2026-07-16 (owner, from the user-2 dashboard)
**Severity:** Medium — a risk limit (`allow_short = 0`) is **violated at the broker** on a live paper
book. Financial exposure is small (−$1,984); the *class* of defect is not.
**Status:** Diagnosed, root cause confirmed. **No remediation applied** — awaiting owner decision.
**Class:** Same family as [[incident_2026_07_13_risk_gate_traps_risk]] and the ADR-0042 reservation
leak — **the risk engine acting correctly on a view of the world that had drifted from reality.**

---

## 1. How it surfaced, and what was actually wrong

The owner noticed the user-2 dashboard did not add up:

```
starting balance  100,000
total gain           +258
Cash            102,235.19
Account total   100,258      <- Cash > total. "Cash not match account total balance"
```

**The dashboard is correct.** Alpaca `raw_payload` for account 2:

```
cash                102235.19
long_market_value        0
short_market_value   -1976.34
equity              100258.85     ->  102235.19 + 0 - 1976.34 = 100258.85  ✓
```

Cash exceeds equity because the account is **short**. That is ordinary margin accounting, not a UI
defect. The owner's instinct that something was wrong was right; the fault is one layer below the
number they were looking at.

**The real finding:** account 2 (`Alpaca Paper (Range)`, user `range@local.dev`) holds
**AMD −4 SHORT**, while `risk_limits` for user 2 has **`allow_short = 0`**.

## 2. Timeline

| When | Event |
|---|---|
| 2026-06-22 21:38:03 | `risk_limits` id=6 created for user 2 with `allow_short = 0`. **Never modified since** (`created_at == updated_at`). |
| 2026-07-07 14:15:01 | Order **#466 BUY 7 AMD** — recorded `FILLED` in the local ledger. |
| **2026-07-07 15:36:01Z** | **The Alpaca paper account was reset/recreated** (`account_number PA3NLDNZJQ32`, `created_at` = this timestamp). Broker orders and positions wiped. The local ledger kept everything. |
| 2026-07-07 → 07-15 | Latent. The local view is long by the pre-reset ghosts; nothing trades AMD. |
| 2026-07-15 13:55:01 | #1286 BUY 3 AMD → broker +3. |
| 2026-07-15 14:05:01 | #1298 SELL 3 AMD → broker 0. |
| **2026-07-15 14:15:01** | **#1300 SELL 7 AMD → `risk_check` #3310 = `PASS ["OK"]` → broker 0 → −7. The short is opened.** |
| 2026-07-16 14:55:01 | #1354 BUY 3 AMD → −4 (the strategy partially covered, incidentally). |
| 2026-07-16 ~15:00 | Owner raises the dashboard discrepancy. |

## 3. Root cause — confirmed, not inferred

**The 2026-07-07 15:36 Alpaca account reset orphaned every pre-reset fill in the local order ledger.**

Two independent proofs:

**(a) The pre-reset order does not exist at the broker.** Queried `/v2/orders/{broker_order_id}` for
all five AMD orders:

```
#466   BUY  7   ledger=FILLED   | ALPACA 404   <== NOT AT THE BROKER
#1286  BUY  3   ledger=FILLED   | ALPACA 200 filled=3
#1298  SELL 3   ledger=FILLED   | ALPACA 200 filled=3
#1300  SELL 7   ledger=FILLED   | ALPACA 200 filled=7
#1354  BUY  3   ledger=FILLED   | ALPACA 200 filled=3
```

#466 predates the account's `created_at`. Every post-reset order is present and filled.

**(b) Partitioning the ledger at the reset timestamp reproduces the broker exactly**, for every
symbol:

```
SYM     LEDGER_ALL  LEDGER_POST  BROKER  LOCAL
AMD              3          -4      -4     -4     ghost +7   | SHORT
INTC            35           0       0      0     ghost +35
MU               4           0       0      0     ghost +4
GOOGL            0           0       0      0
TSLA             0           0       0      0
```

`LEDGER_POST == BROKER` for **all five symbols**. The entire divergence is pre-reset fills. Three
ghosts: **AMD +7, INTC +35, MU +4**.

## 4. Why the gate passed

`app/risk/engine.py:211-227`:

```python
# 6. Short restriction. A SELL is "opening a short" if we don't
# already hold >= qty long shares.
if req.side == OrderSide.SELL and not limits.allow_short:
    pos = (await session.execute(select(Position).where(
        Position.account_id == req.account_id,
        Position.symbol_id == symbol.id))).scalars().first()
    current_qty = pos.qty if pos else Decimal(0)
    if current_qty < req.qty:
        return ... reasons=[ReasonCode.SHORT_NOT_ALLOWED]
```

The gate consults the **local `Position` row**. Order #1300 (SELL 7) recorded
`risk_check #3310 = PASS ["OK"]`. Since `allow_short = 0` was in force (proven unchanged since
06-22), a PASS **deductively requires** `current_qty >= 7` at 14:15:01 — i.e. the local position
still carried the ghost. At the broker the position was 0, so the order opened a −7 short.

> **The gate was not bypassed. It was told the wrong position.**

This is the recurring theme: on 07-13 the daily-loss gate blocked de-risking because its view was
wrong; the ADR-0042 reservation leak starved reducible capacity because its view was wrong; here the
short gate authorised a short because its view was wrong.

## 5. Why reconciliation did not catch it

Position-domain reconciliation compares the **local `positions` table** against the **broker**. Those
now agree (both −4), so it reports `pass` — 23,106 runs, `n_discrepancies: 0`. It is working as
specified.

The divergence lives between the **order ledger's implied position** and reality — a relationship no
current reconciliation domain covers (domains today: Position + Intent; Order/Account/Cash are
future work per ADR 0021). **This is a coverage gap, not a reconciliation failure.**

Note also that reconciliation is **alert-only by design** (ADR 0021 prop. 4 — it never auto-corrects),
so even detection would not have prevented this.

## 6. Scope

- **Confined to account 2.** The ghosts arise only from that account's 07-07 reset.
- **Three ghosted symbols**; only AMD converted into an actual short, because only AMD saw a
  post-reset SELL large enough to cross zero at the broker.
- **Not a strategy defect.** Range Trader is long-only and every order it placed was legal against
  the position it was shown.
- ⚠ **AMD is in the Range Trader universe and the strategy is `PAPER` on a `*/5 * * * *` schedule** —
  it is actively trading the symbol it is short, and may deepen or cover the position unattended. It
  already covered 3 of the 7 without being asked.

## 7. Recommendations (owner decision — none applied)

**Immediate — cover the short.** BUY 4 AMD on account 2 to restore `allow_short = 0` compliance.
Small and reversible. Left undone, the live strategy keeps trading around a position the risk policy
forbids.

**Structural — the short gate must not trust a ledger-derived position.** Test against a
broker-verified position (or refuse when the local view is unreconciled). Otherwise **any future
paper-account reset silently re-arms this identical trap**, and resets are routine (a reset also
rotates the API keys — noted in the ADR-0042 canary manifest).

**Hygiene — the ghost rows remain.** AMD +7 / INTC +35 / MU +4 are still `FILLED` in the ledger and
will skew any ledger-derived position math indefinitely. They should be reconciled against the
broker or explicitly annotated as pre-reset, not silently deleted (they are historical record).

**Detection — close the coverage gap.** A reconciliation domain comparing *ledger-implied* vs
*broker* position would have caught this on 07-07, eight days before it mattered. Cheap: the query in
§3(b) is the whole check.

## 8. What was NOT done

No orders placed. No positions changed. No limits altered. No ledger rows edited. Account 2 is
exactly as found. This document is diagnosis only.

## 9. Evidence

All reproducible read-only against the box:

- `/v2/account` raw_payload for account 2 (cash/long_mv/short_mv/equity, `created_at`).
- `/v2/orders/{broker_order_id}` for the five AMD orders — #466 → 404.
- `orders` + `positions` + `risk_limits` + `risk_checks` (#3310) for account 2.
- The ledger partition at `2026-07-07 15:36:01` reproducing the broker for every symbol.
