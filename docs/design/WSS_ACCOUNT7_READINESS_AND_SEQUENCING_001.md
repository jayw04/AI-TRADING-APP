# WSS on Account 7 — Readiness State and Sequencing Plan

| Field | Value |
|---|---|
| Document ID | `WSS-ACCOUNT7-READINESS-AND-SEQUENCING-001` |
| Status | **Active working plan** — supersedes no governed authorization |
| Date | 2026-08-03 |
| Owner | Jay Wang |
| Scope | Sequencing and blocker state only. **Authorizes nothing.** |

This document records why WSS delivery was held, what is now closed, what is still open,
and the order the remaining work should run in. Every operational action remains governed by
its own authorization; nothing here grants permission to act.

---

## 1. Identity — bind these, and only these

```
workbench logical account  = 7
alpaca paper account       = PA3E97RWHKQZ
alpaca account uuid        = 0fa55b0d-74d6-4a61-a361-ab154857cfb5
credential key fingerprint = ffab8796516a
credential secret fp       = c2cab6509f1b
strategy                   = WSS / strategy 9, construction v1.3 / C40 (ADR 0049)
```

⚠ **Do not repoint account 7 to `PA34USW0Q8UO`.** That is the legacy canary's account. It appears
**zero times** in the governing successor authorization; the verifier hard-pins `PA3E97RWHKQZ` and
binds it into `binding_manifest_sha256`. Where `PA34USW0Q8UO` does appear is as a *tag* on the WS5
runtime instance — canary-era provenance, not a binding, preserved deliberately by the
additive-tag design in §4A.

⚠ **Do not reuse the interrupted historical account-7 portfolio state**, and do not reuse manifest
`1e9e0f94…2bf2bb36` (standing owner instruction). The dedicated account is clean, so the old
47-fill residual plan is void. Exits should be empty — the gate must *verify* that, not assume it.

---

## 2. Why WSS was held — four gates, each of which found something real

Delivery was never deferred for schedule reasons. Each gate exposed the next.

### Gate 1 — the live strategy was not the validated strategy (2026-07-28)

At the account-7 rebalance review gate the manifest was *faithful* but the economics were wrong:
the book ran ~67% cash. Option B ruled — manifest not approved, strategy 9 **temporarily held
pending portfolio-construction review**, not rejected.

The review found the cash was unintended on two stacked counts:

| Cause | Effect | Disposition |
|---|---|---|
| Beta-cap governor enforced (scale 0.3559), equity sleeve 40% → 14.24% | −32.44pp to cash | **CF-1 resolved** — intentional and properly approved |
| Universal 4% `max_position_pct` applied **post-blend to the whole book**, incl. the cross-asset sleeve (UUP 31.98%→4%, KMLM 9.22%→4%, DBC 5.40%→4%), no redistribution | −34.60pp to cash | **CF-2 — the decisive defect** |

Validated PORT-001 construction was gross **1.0**; live was **0.33**.

**Root cause of invisibility:** every PORT-001 promotion gate ran in the research layer.
`_apply_targets` — production sizing — was never inside any gate, and the equity sleeve is an
inline reimplementation that was never formally gated. The parameter was born mislabeled as
"per-name cap (the sibling equity sleeve's 4%)" while being applied globally.

CF-3 (entries bypass `min_trade_pct`) was found independently and is not resolved by the CF-2 fix.

### Gate 2 — rebuilding the construction

Variant decomposition, then a 14-candidate walk-forward over ~210 weekly rebalances
(2022-06 → 2026-06), concentration gates, breadth adjudication. All three breadths failed the
frozen concentration gate identically — the concentration lived in the **uncapped cross-asset
sleeve**; equity breadth barely moved it. **C40** (40 names · 20% pre-blend CA cap · corrected
equity-only 4% cap · enforced governor with released exposure as explicit cash · bounded hybrid
threshold) displaced uncapped N40 under a governed exception on criterion 3.

Shipped as PR #537 with **ADR 0049**.

### Gate 3 — market data broke the execution gate (2026-07-29)

T3 gate held. The account has **no SIP entitlement**, so every quote is IEX top-of-book. The 50bps
single-stock half-spread gate was measuring single-venue thinness rather than real spread — AMD
379–474bps, NBIS 718bps, while SPY read 0.27bps. **46 of 82 orders would have aborted on the
artifact** and all three stages would have halted. Cross-asset ETFs are the inverse: tight fresh
quotes, sparse prints. ⇒ quotes for ETFs, trades for stocks.

Owner ratified a bounded re-attempt (reference age 300s · fill window 120s · K=2 · 1.5% drift vs
the reviewed manifest price · $250/stage residual tolerance · no market-order fallback).

The SPY $95 canary passed 9/10 and **caught a real duplicate-order hazard**: the platform ledger
lagged the broker by 8m31s, so polling the platform would have read zero-filled for a fully-filled
order and attempt 2 would have double-bought. `INV-EXEC-01` follows from this — no real-time
decision may infer unfilled/terminal/safe-to-retry from the *absence* of a platform fill record.

### Gate 4 — runtime isolation refused (2026-08-03)

ADR-0043 WS5 attempt 1: **Stage 1 PASS, Stage 2 REFUSED, terminal.** The legacy canary was not a
dormant evidence host — five live containers on `restart=unless-stopped`, sharing a
trading-capable credential with the target account. Both required broker write-prevention controls
did not exist in code, and §4A had pinned the image while §14 makes post-Stage-1 amendments
terminate the attempt. Structurally unrepairable.

⇒ successor authorization on a **dedicated clean** account 7 (`PA3E97RWHKQZ`).

---

## 3. State as of 2026-08-03

### Closed

- Construction defect — v1.3 / C40 settled, parity-proven, merged, ADR 0049 accepted.
- Execution design — bounded re-attempt ratified; canary passed 9/10.
- Runtime isolation — successor authorization amendment-1 merged.
- Dedicated clean Alpaca account, broker read-only controls, Stage-C reconciliation runner
  (image-pinned), successor resources clean and frozen, legacy quiesced.

### Governing authorization identity

```
authorization_sha256               = 9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8
normative_body_sha256              = 15e13585860027c2e55833421b2218111407abb8b62e1062f17961d04a7fa57d
binding_manifest_sha256            = 8769ba3013e18835c118a81e4bce378426ed2eada1ec7ba80024b1049255e118
authorization_document_blob_sha256 = 2d588eb788ffa9f5c98941d49181b12aac09a0defe7fa9d0a64a4ca45d93a7ea
amendment_merge_sha                = 5393dd42f3b5e242b2984353a960fb58dc30f98c
expiration_rule                    = authorization_effective_at + 336 hours exactly
```

Retired: `c7eb9737…` = `OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS` (not REFUSED, no refusal
count consumed). `1f8366d8…` = intermediate drafting identity, never owner-approved, no disposition.
Refusal ledger unchanged: original WS5 = refusal 1, successor = attempt 2.

### Not yet effective

Effectiveness trigger PR is open and green, **not merged**. No clock has started. Stage A held.

---

## 4. ⚠ Scope boundary — the successor authorization ends at READY

This is the largest schedule-perception risk in the program and must not be misread.

The authorization pins:

```
broker_access_mode           = read_only
strategy_execution_enabled   = false
scheduler_enabled            = false
alpaca_startup_enabled       = false
permitted_endpoints          = GET /v2/account | GET /v2/positions
                               GET /v2/orders  | GET /v2/account/activities
```

| Stage | Under this authorization? |
|---|---|
| A — adopt and verify clean resources | ✅ yes |
| B — inert runtime preparation | ✅ yes |
| C — read-only account reconciliation → `READY` | ✅ yes |
| D — readiness record | ✅ yes |
| **Bind WSS config to account 7** | ❌ **no** |
| **Fresh target + activation manifest** | ❌ **no** |
| **Canary activation / any order** | ❌ **no** |
| **Scheduler activation** | ❌ **no** |

**Completing this authorization produces a verified-ready, flat, inert account — not a trading
one.** Everything from binding onward requires a separate authorization, which does not yet exist.
It should be drafted in parallel with Stage A rather than after Stage D.

---

## 5. Open blockers

### 5.1 Factor-data refresh — the true critical path (VERIFIED IN `main`)

`deploy/aws/factor-refresh.sh:48`:

```sql
SELECT symbols_json FROM strategies WHERE status='PAPER'
```

Three defects, of which only the first is commonly understood:

1. **Wrong universe.** The refresh derives its ticker set from `symbols_json` (~200 registered
   names) rather than the ranking universe (~500). C40 ranks over the broader set to select 40.
   The script's own comment states the premise — "the books only rank over their own universes" —
   and that premise is the bug.
2. **IDLE strategies contribute nothing.** The `status='PAPER'` filter means strategy 9 supplies
   zero symbols while held. **Binding WSS to account 7 while IDLE therefore leaves its universe
   unrefreshed** except by incidental overlap with strategies 7/8. This is a chicken-and-egg:
   the strategy cannot become dispatch-ready without fresh data, and cannot get fresh data while
   not yet activated.
3. **Freshness is evaluated wrongly.** Staleness must be assessed **per-day-per-name**, not by
   `max(date)`. The `max(date)` reading is what allowed 301/500 names to sit frozen at 07-06 while
   every readiness gate reported green.

The 2026-08-03 catch-up was a one-time patch, not a fix. The gap re-opens at each 06:00 ET refresh
and widens every session. **This is the only workstream where delay compounds**, and it is the one
that actually gates dispatch.

Consequence if unfixed: WSS binds successfully, Stage C returns `READY`, and the strategy still
cannot dispatch.

### 5.2 Forced-expiry / partial-fill negative-path evidence

A stated precondition for transition. Both canary legs filled on attempt 1, so the negative path
was never exercised. Owner directed it onto **account 3** ($10 non-marketable buy limit, K=1) —
parked since 2026-07-29 because account 3 is not activated, its breaker is tripped (the risk engine
would refuse the order, testing the wrong path), and it holds ADR-0042 incident evidence.

Two acceptable resolutions: deliberately unblock account 3, or re-scope how the negative path is
evidenced. Leaving it parked is not one — it silently blocks transition.

---

## 6. Recommended sequencing — two parallel tracks

Serialized, the readiness track becomes the long pole after the governance track finishes, and the
authorization window is spent waiting on data.

| When | Track A — governance / runtime | Track B — trading readiness |
|---|---|---|
| Immediate | merge trigger → Record 2 → Stage A → Stage B | **factor-refresh fix before the next 06:00 ET run** |
| Next day | Stage C → `READY` → Stage D record | account-3 decision (unblock or re-scope) |
| Parallel | draft the **execution** authorization for binding onward | verify per-name freshness green |
| Then | bind WSS · fresh manifest · staged canary · reconcile | — |

Track A is unblocked by anything in Track B: Stages A–C are metadata verification, inert runtime
preparation, and four read-only GETs. Neither touches factor data or account 3.

---

## 7. Standing constraints

- Activation order is fixed: exits → reconcile → cross-asset sleeve → reconcile → equity entries →
  final reconciliation. For a clean account exits should be empty; the gate verifies rather than
  assumes.
- Constrained order counts / notional, regular-market-hours execution, scheduler off during canary.
- WSS dispatch stays **disabled** while factor readiness is non-green. The factor issue does not by
  itself block account *binding*.
- Account 7 must be exclusively owned by WSS — no other strategy may point at `PA3E97RWHKQZ`.
- Any account mismatch, unexpected holdings, endpoint deviation, or mutation attempt stops the
  process. Stage C already enforces account identity: `account_number == PA3E97RWHKQZ` gates the
  remaining approved reads.

---

## 8. Open owner decisions

1. Effectiveness-trigger merge — approval of the exact reviewed head (starts the 336-hour clock).
2. Factor-refresh fix — scope and timing. Touches `deploy/**` ⇒ **Tier 3 CI**.
3. Account 3 — unblock, or re-scope the forced-expiry evidence.
4. Execution authorization for steps beyond Stage D — who drafts, and when.

---

## 9. Evidence pointers

- `docs/design/ADR0043_LIVE_CANARY_WS5_SUCCESSOR_START_001.md` — governing authorization
- `scripts/governance/hash_adr0043_ws5_successor_authorization.py` — verifier, `authorization` and
  `selftest` subcommands
- `apps/backend/tests/scripts/test_hash_adr0043_ws5_successor_authorization.py` — structural contract
- `docs/adr/0049-strategy9-v13-c40-portfolio-construction.md` — C40 construction
- `deploy/aws/factor-refresh.sh` — the refresh defect described in §5.1

*This document authorizes nothing. It records state and recommended order of work.*
