# CEE Observation Record 001 — first governed session

**Program:** CEE (Continuous Evidence Engine) · **Session:** 001 · **Run:** `2026-08-22T03:05:20Z`
**Authorization:** `docs/design/MDQ-001_CEE_Authorization_2026-08-21.md` @ `dcc2c97` (#657) — recorded
prospectively, merged **before** the first read.

> **L0 observation only. INADMISSIBLE to K1–K6** (plan v0.13 §4.10.1). This record grants no strategy
> behavior, order, broker, ranking, admission, L1/L2, or production-trading authority, and changes no
> K-criterion definition, threshold, matching rule, evaluability clause, or the recorded PX-2
> determination.

**Headline disposition: NOT EVALUABLE on the current population (n = 17).** A directional signal is
present and is described below, but it must not be read as a finding.

---

## 1. What was done

The owner-specified nine-step sequence, ending in STOP:

| Step | Outcome |
|---|---|
| 1 authorization recorded | `dcc2c97` (#657), in Git before any read |
| 2 confirm ledger genesis/head | 1 record, `DISC-MDQ-001#1:a1aecc44b28611e8`, 0 conditions, 0 reads |
| 3 `AuthorizedScope` via `from_config` | 27 pairs = 9 symbols × 3 sessions; fingerprint `e5bb2c68…` |
| 4 open authorized non-holdout partitions | 6 partitions (sip/iex × 3 sessions), all manifest-verified |
| 5 ledger partition-read entries | seq 3–8, written **before** parsing, by the reader |
| 6 compute the frozen CEE measurements | K5 matching rule, ruling R2 |
| 7 ledger each condition + disposition | seq 9–12 |
| 8 observation record | this document |
| 9 **STOP** | no feature library, no additional condition mined |

**Ledger after the session:** 12 records — `ledger_opened` ×2, `partition_read` ×6,
`condition_examined` ×4. Head `ace89e7f43406b96`. File sha256
`51cf574f4fd37c3b0b16758cfecfc8171ef8f59ffc0ccd037b30786f658cbd1a`.

---

## 2. Population and scope

**21 qualifying paper fills** — 9 symbols (AAPL, AMD, AVGO, GOOGL, INTC, META, MSFT, NVDA, TSM) across
3 sessions (2026-08-19 ×4, 08-20 ×11, 08-21 ×6). Accounts 2 (17), 7 (3), 3 (1); 20 STRATEGY, 1 MANUAL.

Of 50 fills at or after D0, 29 were excluded as `unavailable_not_in_universe`.

⚠ **The embargo had nothing to deny in this session.** Zero holdout-symbol and zero holdout-date fills
existed in the population, and the scope was deliberately narrowed to symbols that actually traded.
`denials = 0`. The quarantine is armed and was carried on every ledger record, but it was **not
exercised** here — unlike the DISC-MDQ census, where it removed NBIS. This is stated so no one later
reads `denials = 0` as evidence the filter works.

Corpus read: 6 frozen partitions, 21,330 authorized observations, 19,750 rows scanned and 16,195
withheld per partition (the withheld rows are the 31 authorized-universe symbols outside this scope
plus `missing`/`feed_error` rows).

---

## 3. Measurements — K5 matching rule (ruling R2)

Match = latest snapshot **at or before** the reference, with `ref_ts − cycle_ts ≤ 5 s`. References are
`order.created_at` (decision) and `fill.filled_at` (execution). Unmatched references are excluded.

### 3.1 Quote coverage — `cee_quote_coverage_under_k5_r2` · `DISC-MDQ-001#9:6ef6a203679f09fd`

| Reference | SIP | IEX |
|---|---|---|
| decision (`created_at`) | **17 / 21** matched | **17 / 21** matched |
| execution (`filled_at`) | **11 / 21** matched | **11 / 21** matched |

⭐ Coverage is **identical on both feeds** — the sampler grid is shared, so a reference either falls
within 5 s of a slot or it does not, regardless of feed. Feed choice does not buy coverage; it changes
what the matched quote *says*.

⭐ Execution-reference coverage (52%) is materially worse than decision coverage (81%). Fills land on
broker time, decisions on the scheduler's minute boundaries — the same grid-alignment effect measured
pre-window for K5.

⛔ **This is coverage evidence and nothing more. It is NOT a reason to revisit R2**, the 5-second
tolerance, or any part of the frozen matching rule. R2 was ruled before any coverage figure was
computed, and §4.10.1 forecloses revising it now — including via a "clarification".

### 3.2 Decision price — `cee_decision_price_sip_vs_iex` · `DISC-MDQ-001#10:12491422c430f9cb`

`sip_iex_decision_mid_diff_bps` (n=17): median **0.92**, mean **−2.07**, p05 **−69.53**, p95 **9.66**,
min **−69.53**, max **11.14**.

### 3.3 Spread — `cee_spread_bps_sip_vs_iex` · `DISC-MDQ-001#11:622d482e7ab90d24`

| bps | n | median | mean | p95 | max |
|---|---|---|---|---|---|
| SIP decision spread | 17 | **2.21** | 3.56 | 9.29 | **10.05** |
| IEX decision spread | 17 | **11.20** | 21.32 | 31.38 | **171.12** |
| SIP − IEX | 17 | **−5.82** | −17.77 | 0.00 | (min **−161.07**) |

⭐ This is the clearest difference in the session: measured IEX spread is roughly **5× the SIP median**,
and its tail is an order of magnitude worse. A **171 bps** IEX spread on a megacap is not a market
condition; it is the documented IEX stub/one-sided-quote artifact.

### 3.4 Implementation shortfall — `cee_implementation_shortfall_sip_vs_iex` · `DISC-MDQ-001#12:ace89e7f43406b96`

`IS_bps = sign × (fill_price − decision_mid) / decision_mid × 10⁴`, `sign = +1 BUY / −1 SELL`, gross of
commission.

| bps | n | median | mean | p05 | p95 | min | max |
|---|---|---|---|---|---|---|---|
| IS (SIP) | 17 | 1.18 | 1.87 | −7.86 | 6.66 | −7.86 | 12.71 |
| IS (IEX) | 17 | 1.47 | −2.38 | −72.82 | 10.81 | **−72.82** | 12.71 |
| **SIP − IEX** | 17 | **0.00** | 4.25 | −9.67 | 11.14 | −9.67 | **69.51** |

---

## 4. Reading — what the numbers do and do not say

⛔ **Do not read this as "SIP improves shortfall measurement by ~4 bps."** The mean difference of
4.25 bps is an artifact of the tail. The **median difference is exactly 0.00 bps**: for at least half
the fills, SIP and IEX produce the *same* implementation shortfall to four decimal places.

✅ The defensible statement is narrower and more useful:

> On this population, SIP and IEX agree on decision price and shortfall for most fills. IEX produces
> occasional extreme outliers — a 171 bps spread, a −72.8 bps shortfall — that SIP does not, and those
> few observations dominate every mean. The value of SIP here is **tail suppression in the measurement**,
> not a systematic level shift.

That distinction matters for the decision this feeds: an L1 execution path that used IEX quotes for
decision pricing would be occasionally, severely misinformed rather than uniformly slightly wrong. Those
are different engineering problems with different fixes.

🔭 **FOLLOW-ON HYPOTHESIS — explicitly NOT a Session-001 result.** If the observed tail is driven by
invalid / stub IEX quotes, then a **quote-validity rule** could remove much of the apparent feed
difference **without any feed migration**. That is a hypothesis to be tested *prospectively* once more
population accrues. It is recorded here so it is not lost, and it is deliberately **not** added to this
session's condition set — retro-fitting a condition after seeing the data is precisely what the
discovery ledger exists to prevent.

⛔ **No condition in this session is promising, passed, or failed.** All four are recorded as
examined and not evaluable; the ledger carries no other disposition, and none should be inferred.

⚠ **Small-N.** All four conditions are dispositioned `examined_not_evaluable_small_n` (n=17 against a
declared floor of 30). With 17 observations, a median of exactly 0.00 and a mean of 4.25 are consistent
with a handful of stub quotes and tell us little about the population. **Per the frozen falsification
criterion, "not evaluable on the current population" is a valid and expected outcome, and that is the
disposition of record.**

⚠ **§4.10.4 generalization limit.** The population is 9 top-ADV megacaps over 3 sessions — small and
liquidity-biased by construction. Nothing here generalizes to the DISC universe or the tradable universe.

⚠ The pre-window feasibility figures (~117 fills/30 d, 54.7–66.7% match) are **inadmissible** and were
not used.

---

## 5. What would change the disposition

Per the §4.10 frame, re-running as the window accrues. The falsification/stop condition is unchanged: if
SIP-based reconstruction does not materially change measured shortfall, spread, or decision-price
quality relative to the IEX-only baseline — or the population stays too small to distinguish them — CEE
does not justify further work. A material, direction-consistent difference across **more than one**
measure would justify a *prospective* pre-registration proposal, and nothing more.

The tail-suppression observation is the specific thing to re-test: does it persist, and is it confined
to IEX stub quotes? If it is entirely a stub-quote artifact, the remedy may be a quote-validity filter
rather than a feed change — a cheaper answer than the one this program was set up to look for.

---

## 6. Operational findings from this session

**6.1 The box was redeployed mid-session, reverting byte-exact deployment.** At `2026-08-21T22:57:00Z`
— after the acceptance record and before this session — `ec2-paper` was redeployed to `02e77a7` (#655)
by a process outside this work, using a **default `git archive`**. Measured consequence:

| File | State now |
|---|---|
| deployed `ledger.py` | 26,374 B, **670 CR bytes**, raw `3b6fdb03…`; **LF-normalised `aa3f01d4…`** = the Git blob |
| app-tree `mdq_phase_a_holdout.json` | `7247ad59…`, **32 CR** — the CRLF variant |
| governed `/opt/workbench/data/mdq_config/*` | **unaffected**, 0 CR, `7832ff38…` / `0c57bd71…` |

⭐ **This session is unaffected**: the code is identical modulo line endings, `_sha256_lf()` normalises
before comparing pins, and the artifacts the ledger actually reads live on the data volume, which the
redeploy does not touch. Verified, not assumed.

⚠ But the acceptance record's `.deploy_src_sha = 50efc2f` and in-container `ledger.py = aa3f01d4…` were
point-in-time attestations that a later redeploy superseded within five hours. The EOL-determinism
follow-up named in that record is no longer theoretical — **it has now happened in production** — and
should be prioritised: extend `.gitattributes`, and enforce `core.autocrlf=false` in the deploy path
rather than relying on the operator remembering.

**6.2 Free-space guard, re-run after that redeploy.** `size_gb=58`, `avail_gb=35`,
`floor=11`, `avail_bytes = 36,678,393,856` against the effective threshold **10,737,418,240** →
**PASS**, margin 25,940,975,616 B. ⚠ Build cache has grown to **9.585 GB (8.311 GB reclaimable)** across
three redeploys today. Docker and the MDQ capture root remain the same mount.

🛑 **The pre-09:25 ET check before Monday 2026-08-24 remains mandatory** and is not discharged by this
one.

---

## 7. Disposition

```text
CEE session 001            COMPLETE — STOP
All four conditions        examined_not_evaluable_small_n  (n=17 < 30)
Directional observation    SIP suppresses measurement tails; medians agree
Admissibility              L0 observation; INADMISSIBLE to K1-K6
Next                       re-run as the window accrues; no scope expansion
Broad DISC-MDQ             HELD pending the repeated population census
```
