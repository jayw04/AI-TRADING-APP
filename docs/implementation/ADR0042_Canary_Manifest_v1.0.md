# ADR 0042 — Canary Manifest v1.0

**Purpose:** the paper-account verification required by the ADR 0042 release gate.
**Status:** Frozen (pre-activity). Parameters below are recorded BEFORE the first trade and are
not to be changed mid-run.
**Owner authorisation:** 2026-07-13.

> **This account is a permanent risk-engine verification account.** It is not to be converted
> into a strategy account after the canary. A dedicated, controlled account is the only way to
> re-verify a risk gate without contaminating a book that has a mandate.

---

## 1. The account

| Field | Value |
|---|---|
| User | 3 |
| Account | 3 — `Alpaca Paper (Conservative)` |
| Broker account | `PA34USW0Q8UO` (paper) |
| Baseline equity | $100,000.00 *at the first run (2026-07-13)* — **not a precondition**, see below |
| Baseline cash | $100,000.00 at first run |
| Baseline positions | **none (flat)** ← precondition |
| Baseline open orders | **none** ← precondition |
| Breaker at baseline | **clear** (`circuit_breaker_tripped_at = NULL`) ← precondition |

> **Equity is NOT a precondition.** This is a permanent verification account: its equity drifts
> with every canary, because reaching the breach costs real money by design. The harness checks
> **flat / no open orders / breaker clear / limit frozen** — never a specific equity. Do **not**
> "reset the balance" to $100k: an Alpaca paper reset rotates the API keys (as on 2026-07-07,
> which cost a full credential re-sync) and buys nothing.
>
> Run history: 2026-07-13 start $100,000.00 → end **$96,912.33** (the −$3,087 breach was real
> realized loss).

### Reaching the breach — what actually works (MEASURED 2026-07-13)

**Alpaca paper fills at the MID, not the ask.** IEUS was quoted bid 67.59 / ask 71.75 and
**filled at 69.57**. So there is *no spread cost in paper*, which kills two mechanisms at once:

* the "buy a wide-spread instrument and take the instant mark-to-bid loss" idea — **void**;
* the churn cost estimate derived from spreads — **also wrong**.

What genuinely costs money is the **real round trip**: measured **−$297 realized across ~$76k of
turnover (~0.4% per cycle)**, flowing through the true `equity − last_equity` path. Roughly ten
cycles reaches −$3,000.

Two properties make this the right mechanism:

* it is a **genuine realized loss** — nothing is fabricated, and the frozen limit is never moved;
* churning while **unlocked writes ZERO risk-decision rows** (ADR 0042 is not in the unlocked
  path), so the evidence ledger — the thing the canary exists to produce — stays clean. The
  noise lands in `orders`, where it belongs.

⚠ **The churn must NOT flatten the test legs.** On the first run it sold every position each
cycle, so by the time the lock armed the account was flat and there was nothing left to reduce.
Buy and **hold** the legs; cycle only the churn instruments.
| Strategy 4 (`momentum-conservative`) | **IDLE** — not in `ENGINE_RUNNABLE_STATUSES`, therefore not resumed on boot, no cron job, no overlay job |
| Authorised submitter | **the canary harness only** |
| Spare | user 4 / account 4 (`PA32AC6G1HB2`) — held in reserve, untouched |

**Account 1 is retained UNCHANGED as incident evidence** until the 2026-07-13 incident is
formally closed. It is not to be traded, reset, or re-armed for any purpose, including this one.

---

## 2. Frozen risk parameters — recorded BEFORE any activity

| Parameter | Frozen value |
|---|---|
| `max_daily_loss` | **$3,000.00** — owner-set 2026-07-13, **before any activity on this account** |
| `max_gross_exposure` | 100,000.00 |
| `risk_policy_version` | `0042.1` |
| Ledger capture | **enabled before the first trade** |
| Broker-event capture | **enabled before the first trade** |

The $3,000 figure is recorded here **first** and is not to be touched again for the duration of
the canary. If the breach proves hard to reach, the answer is more churn — **not** a smaller
limit. Moving the limit to meet the account is the very thing § 2 forbids.

### The breach must be REAL — not manufactured by moving the limit

> **Rejected approach (mine, withdrawn).** "Buy the positions, then set `max_daily_loss` to
> zero." This manufactures the lock by moving the limit *after activity begins*. It would
> exercise the **gate** while bypassing the **account-state calculation that produces the
> lock** — so a green canary would prove strictly less than it appeared to, which is the worst
> possible outcome for a verification account.

The limit is **frozen first and recorded above**. The breach is then produced through
**controlled paper trades** that realise genuine losses, so `day_change = equity − last_equity`
crosses the threshold through the **real account-state path** — the same computation that
tripped account 1 at 09:30:25 ET on 2026-07-13.

Mechanism: a **throwaway churn position**, opened and closed repeatedly, realising the spread on
each round trip until `day_change ≤ −max_daily_loss`. The two long positions under test are
established **first**, while the account is still unlocked, because once it locks no buy will
pass — that ordering is a constraint of the system under test, not a convenience.

`max_daily_loss` is therefore sized so that a bounded number of round trips reaches it. It is
set **once**, in this manifest, before anything trades.

---

## 3. Required sequence (owner-specified; all steps mandatory)

| # | Step | Required outcome |
|---|---|---|
| 0 | **Baseline reconciliation** | Broker positions/orders/fills/equity/cursor agree with local state. No reservations exist. **Record the baseline snapshot hash.** |
| 1 | **Controlled exposure** | ≥ 2 long positions, sized to permit partial reductions *and* concurrent reservations (one leg ≥ 500 units). |
| 2 | **Enter daily-loss breach** | Via realised losses (§ 2). Then: a new risk-increasing **BUY is rejected at step 9**. Ledger records the account + policy versions used. |
| 3 | **Verified reduction** | Partial sell-to-close → `REDUCING / ALLOW / VERIFIED_REDUCTION`. **Passes both step 9 and step 13.** Fill reduces position *and* gross exposure. |
| 4 | **Zero-crossing rejection** | Sell > available reducible qty → `INCREASING / REJECT`. |
| 5 | **Concurrent double-reduction** | Against a long of 500, submit two sells of 300 **concurrently**. Exactly one reserves capacity; the other reclassifies or fails closed. **The account must never become short.** |
| 6 | **Cancellation classification** | Cancel a pending risk-increasing BUY → allow (worst-case exposure improves). Cancel a pending **sell-to-close** while locked → **reject** unless separately proven reducing under projected state. |
| 7 | **Source neutrality** | The same valid reduction via `STRATEGY` and via `MANUAL` → **identical** policy treatment and reason semantics. |
| 8 | **Snapshot race** | Classify a reduction, then inject a fill / order-state change before submission → **version conflict, reservation rollback, fresh reconciliation, reclassification.** The prior decision is never reused. |
| 9 | **Breaker interaction** | A verified reduction passes **while the breaker is tripped**. Neutral and increasing actions stay blocked. **The breaker is NOT reset as part of the test.** |

---

## 4. Release gate

**A filled canary order is not a pass.** ADR 0042 is not operationally complete until *all* of:

- [ ] all classifier and integration tests pass
- [ ] ledger rows **reconcile with broker events**
- [ ] no duplicate reservations
- [ ] no zero crossing
- [ ] no stale-snapshot approvals
- [ ] no source-specific bypass
- [ ] **no unclassified decision** (every action produced a ledger row)
- [ ] no increasing order passed step 9 or step 13
- [ ] **every** verified reduction passed **both** gates

Any single failure blocks the release. `momentum-portfolio` remains **HALTED** until the gate is
green.

---

## 5. Evidence to be captured

For every step: the `risk_decisions` row (policy version, before/after state hashes, broker
cursor, position and gross exposure before/after, reducible qty, risk_effect, decision, reason
codes, correlation id), the corresponding broker event, and the reconciliation between them.

A step that produces no ledger row is a **failure of the ledger**, not a step that "didn't
apply" — an unclassified decision is precisely the hole this ADR was written to close.
