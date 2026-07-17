# Incident — account 2 holds a SHORT on a book where shorting is disallowed

**Date raised:** 2026-07-16 (owner, from the user-2 dashboard)
**Severity:** Medium — a risk limit (`allow_short = 0`) is **violated at the broker** on a live paper
book. Financial exposure is small (−$1,984); the *class* of defect is not.
**Status:** Diagnosed, root cause confirmed. **Short covered 2026-07-16 (owner-directed) — account 2
is FLAT and compliant.** The **ghost records remain** and the **control defect is unfixed in the
deployed build**; the gate fix is PR #438. See §8.
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

### 4.1 How the local position changed — the transition

§4 says the gate saw **≥ +7** at 14:15; §3 shows the local `Position` row now reads **−4**, agreeing
with the broker. Both are true, and the transition is the point:

> At decision time, the local `Position` row still represented **+7 AMD** and allowed `SELL 7`.
> After the broker fill and the subsequent `BUY 3`, the position-synchronisation path updated the
> local `Position` row to the broker state of **−4**. The historical **order ledger** still implies
> **+3**, because it retains the pre-reset ghost `BUY 7`.

So the `Position` row **self-corrected** (it is periodically overwritten from the broker); the
**ledger did not** (it is append-only history). The window in which the two disagreed is exactly the
window in which the gate could be misled — and the gate read the row *before* it was corrected. The
ledger remains corrupted today; only the derived row was healed.

This is the recurring theme: on 07-13 the daily-loss gate blocked de-risking because its view was
wrong; the ADR-0042 reservation leak starved reducible capacity because its view was wrong; here the
short gate authorised a short because its view was wrong.

## 5. Why reconciliation did not catch it

Position-domain reconciliation compares the **local `positions` table** against the **broker**. Those
now agree (both −4), so it reports `pass`. It is working as specified.

**Measured, for account 2 specifically** (not inferred from a table-wide total):

```
account 2, domain=position : 2,082 runs, result=pass, sum(n_discrepancies)=0
                             first 2026-06-30 14:17:54 → last 2026-07-16 20:02:32
                           + 4 runs result=unavailable (earliest 2026-07-07 15:51:52)
```

Those 2,082 passing runs **span the entire ghost window** (the reset was 07-07 15:36). Reconciliation
ran across it more than two thousand times and never saw it — because it was never looking at the
thing that was wrong.

⚠ Scope of that claim, stated precisely: it is **account 2 / domain `position`**. Table-wide the
store holds 23,401 runs of which **5 did fail with a discrepancy** (accounts 3, 5, 6 — unrelated to
this incident). This document does **not** assert that all historical reconciliation runs observed
zero divergence.

The divergence lives between the **order ledger's implied position** and reality — a relationship no
implemented reconciliation domain covers. **`position` is the only domain that has ever run**
(ADR 0021 designs Intent, and lists Order/Account/Cash as future work, but the run store contains
`position` only). **This is a coverage gap, not a reconciliation failure.**

Note also that reconciliation is **alert-only by design** (ADR 0021 prop. 4 — it never auto-corrects),
so even detection would not have prevented this.

## 6. Scope

- **The observed ghost data and resulting short are confined to account 2.** The ghosts arise only
  from that account's 07-07 reset.
- ⚠ **The control defect is systemic.** Any broker-account reset or recreation can produce the same
  failure unless local state is bound to the **broker-account epoch**. Nothing about the mechanism is
  specific to account 2, to AMD, or to the Range book — it requires only a reset plus a later
  zero-crossing sell.
- **Three ghosted symbols**; only AMD converted into an actual short, because only AMD saw a
  post-reset SELL large enough to cross zero at the broker.
- **Not a strategy defect.** Range Trader is long-only and every order it placed was legal against
  the position it was shown.
- ⚠ **AMD is in the Range Trader universe and the strategy is `PAPER` on a `*/5 * * * *` schedule** —
  it is actively trading the symbol it is short, and may deepen or cover the position unattended. It
  already covered 3 of the 7 without being asked.

## 7. Recommendations (owner decision — none applied)

**Immediate — cover the short, in this order.** Range Trader remains scheduled every five minutes,
so the account must stop trading itself before anything is measured or submitted:

1. **Pause autonomous trading for account 2.**
2. **Read and record the current broker position.**
3. **Submit the broker-verified risk-reducing BUY** needed to cover the short.
4. **Confirm the fill and reconcile the final position.**
5. **Preserve and annotate the pre-reset ghost records — do not silently delete them.**

The cover is **small and risk-reducing**. It is *not* "reversible": selling again would recreate the
prohibited exposure, so reversal is precisely the wrong operational message.

**Structural — the short gate must not rely on a local position whose broker-account generation and
freshness have not been verified.** The durable issue is **not merely ledger-versus-broker**: it is
the **absence of an account-generation boundary** after the Alpaca account was recreated. Local state
carried across an epoch change it had no way to represent. Otherwise **any future account reset
silently re-arms this identical trap**, and resets are routine (a reset also rotates the API keys —
noted in the ADR-0042 canary manifest).

**Hygiene — bind the ghost records to an epoch; do not purge them.** AMD +7 / INTC +35 / MU +4 are
still `FILLED` in the ledger. They are **historical record and must be preserved**. The remedy is to
bind orders to the broker-account epoch, e.g.:

```
broker_account_id
broker_account_created_at
account_generation
valid_for_position_reconstruction
```

**Detection — close the coverage gap.** A reconciliation domain comparing *ledger-implied* vs
*broker* position would have caught this on 07-07, eight days before it mattered. The query in §3(b)
is the whole check. It must compute ledger-implied positions **only within the active broker-account
generation** — otherwise it would simply re-derive the ghosts and report a permanent false
discrepancy.

## 8. What was done, and what was not

**Done — the short was covered (owner-directed, 2026-07-16 16:02 ET).** Order **#1355**,
`BUY 4 AMD LIMIT 505.00`, extended-hours, submitted through the **product path**
(OrderRouter + risk engine → `risk_check #3586 PASS`), **filled 4/4 @ $502.50**. Account 2 is now
**FLAT**: `cash 100,225.19 = equity 100,225.19`, `short_market_value 0`, `allow_short = 0`
**compliant**, 0 HELD reservations.

Two notes on that cover. It was placed **after the 16:00 close**, so the `MARKET_SESSION_CLOSED`
gate required an **extended-hours LIMIT** order (Alpaca forbids market orders in extended hours);
it was priced above the closing print rather than at a synthetic level. And it went through the
**audited product path**, not a broker bypass — which also demonstrated that a risk-reducing order
on this account is legal, in contrast to the 07-13 incident where de-risking had to bypass the app.

**NOT done — deliberately:**

- **The ghost records were not touched.** AMD +7 / INTC +35 / MU +4 remain `FILLED` in the ledger.
  They are historical record; the remedy is epoch-binding (§7), not deletion.
- **No limits altered. No ledger rows edited. No positions changed** beyond the authorised cover.
- **The control defect is not fixed in the deployed build.** The account is compliant *today*, but
  the deployed short gate still reads the local position, so the next post-reset zero-crossing sell
  would re-open a short by the same mechanism. The fix is **PR #438** (short gate → broker-verified
  position), which is separate from this diagnosis.

### 8.1 Tracked follow-ups (deliberately out of PR #438)

| # | Item | Why deferred |
|---|---|---|
| 1 | **Epoch-bind the order ledger** — add `broker_account_id`, `broker_account_created_at`, `account_generation`, `valid_for_position_reconstruction`; preserve, do not purge | schema change; independent of the gate fix |
| 2 | **Ledger-implied-vs-broker reconciliation domain**, computed **only within the active broker-account generation** | new domain; depends on (1) to avoid re-deriving the ghosts as a permanent false discrepancy |
| 3 | **`no_broker_registry` as a readiness/startup failure** rather than a runtime warning | changes service startup semantics |

## 9. Evidence

All reproducible read-only against the box:

- `/v2/account` raw_payload for account 2 (cash/long_mv/short_mv/equity, `created_at`).
- `/v2/orders/{broker_order_id}` for the five AMD orders — #466 → 404.
- `orders` + `positions` + `risk_limits` + `risk_checks` (#3310) for account 2.
- The ledger partition at `2026-07-07 15:36:01` reproducing the broker for every symbol.
