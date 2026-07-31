# ADR 0033 — Historical Data Integrity (Foundational)

| Field | Value |
|---|---|
| Date | 2026-07-03 |
| Status | **Accepted** (owner ratified 2026-07-03. Lineage: 2026-07-01 positioning review requested the Foundational elevation; 2026-07-03 ADR review folded — 9.9/10. The *decision* is accepted; enforcement of points 1–3 remains tracked below — an Accepted ADR may lead its implementation.) |
| Phase | Cross-phase / Foundational — the Data Integrity Layer that underpins every research read |
| Supersedes | — |
| Related | 0018 (PIT factor data — same "data available at decision time" discipline), 0014 (backtests = evaluation ground truth — a backtest is only ground truth if its data is complete), 0026 (Factor Lab — the programs that read the cache), 0019 (Research Engine — the read-only subsystem this protects), 0030 (Capability Onboarding — independent reproductions inherit this guarantee) |

## Context

Every backtest, evidence package, and verdict this platform produces is only as trustworthy as the historical data beneath it. The methodology can be flawless and the verdict still wrong if the data silently under-represents the window it claims to cover.

RNG-001 made this concrete. The platform's intraday bar cache (`apps/backend/app/market_data/bar_cache.py`) was found to **silently truncate a cold multi-year fetch at the data provider's page limit and then poison the gap**: `_fetch_and_write` issues a single Alpaca `get_stock_bars` call for the whole missing span with `limit=10000`; for fine (intraday) granularity, buckets are per-day, so a cold multi-year request returns only the first ~10,000 rows (~126 sessions), and the per-bucket split loop then writes a zero-byte `.empty` marker for **every un-returned day beyond the truncation**. Those `.empty` markers block re-fetch (they read as "cached empty"), so the missing days are poisoned permanently until cleared. The observed result (2026-06-30): the Range Top-5 + SPY 5-minute caches held ~250 **non-contiguous** sessions with 2024 and 2026 almost entirely missing and ~800–970 bogus `.empty` markers per symbol — and the **Range Phase 1 and Phase 3 numbers had been computed on that biased ~⅓ sample**. The harnesses were correct; the data was incomplete, and nothing had asserted otherwise.

The defect was caught, disclosed via an **Evidence Correction Report**, corrected (a monthly-chunked cache rebuild), and the affected studies were re-run — the RNG-001 verdict held. The question this ADR answers is not "how do we fix that one bug" but **"on what terms does the platform treat historical-data integrity as a first-class, non-negotiable property of every research read?"** The owner's 2026-07-01 review asked for exactly this elevation: *"I would elevate ADR-0033 from a 'bug fix' to a Foundational Data Integrity ADR… without trustworthy historical data, none of the other research matters."*

## What "Historical Data Integrity" means

> **Historical Data Integrity** is the property that historical datasets are **complete, temporally correct, point-in-time accurate, internally consistent, and accompanied by verifiable provenance** sufficient to support scientific conclusions. Completeness (the failure mode RNG-001 exposed) is one aspect; correctness, continuity, and provenance are the others. This definition is intended to be reusable across future ADRs.

Data integrity sits **beneath** every research discipline, not beside them — an underpinning the whole methodology depends on:

```
Evidence Engineering
        │
        ▼
Data Integrity            ← this ADR (the foundation everything else stands on)
        │
        ▼
Discovery Lab  ─►  Portfolio Engineering  ─►  Continuous Evidence
```

And it is the load-bearing middle of the evidentiary chain — if it fails, everything above it collapses:

```
Hypothesis  →  Method  →  Data  →  Evidence  →  Decision
                           ▲
                 integrity fails here ⇒ Evidence and Decision are void
```

The organizing principle, stated plainly:

> **Research must fail because the hypothesis is wrong — not because the data is incomplete.**

**Data integrity and reproducibility are complementary.** Reproducibility (a seeded, deterministic harness) guarantees the *same computation* every run; data integrity guarantees that the computation is performed on the *complete and correct dataset*. A perfectly reproducible result on a poisoned sample is reproducibly wrong.

## Decision

**Historical Data Integrity is a foundational guarantee, enforced by construction and verification, and a data-integrity failure is a stop-the-research event.** Concretely:

> **A data-integrity failure invalidates the evidentiary status of any result produced from the affected dataset until the dataset has been corrected and the evidence regenerated.** A poisoned dataset does not merely warrant caution — it voids the evidence built on it.

1. **`.empty` markers are scoped to the actually-returned data range.** A cache writer may record a bucket as empty **only** for buckets within the range the provider actually returned (`[df.t.min, df.t.max]`). Buckets **beyond** the returned range are left *missing* (re-fetchable), never marked empty. A truncated response must never poison the days it failed to return.
2. **Provider-page completeness is asserted, never assumed.** When a fetch returns **exactly** the provider's page limit, the response is treated as **possibly truncated** — not as a complete span — and the remaining range is re-requested. Completeness is never inferred from "the call succeeded."
3. **Cold fetches that imply more than one provider page are chunked.** When a requested span implies more rows than the provider's single-page limit, the fetch is split into sub-spans that each stay under the limit, so completeness does not depend on a single page.
4. **Coverage is asserted before any research read.** A research harness verifies that the dataset actually spans the requested window (row presence, date bounds, gap detection) and **fails closed** on a red flag, rather than silently computing on a partial sample. `app/factor_data/evidence.dataset_health` is the canonical primitive.
5. **A discovered data-integrity fault is disclosed, not quietly patched.** When a fault is found in data that has already produced results, it is recorded in an **Evidence Correction Report** (what was wrong, what it biased, the correction, the re-run outcome), and the affected results are re-run. Correcting one's own data faults *in the open* is a trust signal, not an embarrassment to hide.

**Provider-agnostic.** These guarantees apply regardless of provider (Alpaca bars, Sharadar, or any future source). The *implementation* may differ per provider; the integrity requirements do not.

## Rationale

- **Completeness failures are silent by nature.** A missing credential throws; a truncated dataset returns a number. The only defenses are (a) never producing the poisoned state and (b) asserting integrity before trusting a read. Points 1–3 address (a); point 4 addresses (b). **Detection alone is insufficient because a biased sample still yields a *plausible-looking verdict*** — the precise danger this ADR exists to prevent.
- **Scoping `.empty` to the returned range is the minimal correct rule.** The `.empty` marker's legitimate job is to avoid re-fetching genuinely empty days (holidays, inactive symbols). That job only justifies marking days the provider actually spoke to. Extending it to days beyond a truncated response conflates "the provider says nothing traded" with "we never asked past row 10,000" — the exact conflation that caused the poisoning.
- **The page-limit heuristic catches the subtle case.** A response of *exactly* the page limit is the fingerprint of truncation; assuming it is a complete span is how a single cold fetch silently drops years. Treating "== limit" as "possibly truncated" is a cheap, high-value guard.
- **Foundational, not incidental (owner framing).** Data integrity underpins ADR 0014 (backtests as ground truth) and ADR 0018 (point-in-time factor data). Recording it as a Foundational ADR — above any single program — means future programs inherit the guarantee instead of each re-discovering the failure mode the hard way.
- **Disclosure over silent repair preserves the evidence.** The platform's differentiator is honest evidence. Quietly rebuilding a cache and re-running would erase the fact that the platform *detected and corrected* a fault — which is itself evidence the process works. The Evidence Correction Report keeps that provenance.
- **The workaround proves the target, but isn't the guarantee.** `scripts/research/rebuild_5min_cache.py` (clear bogus markers, re-fetch month-by-month) recovers a poisoned cache today, but a manual rebuild script is a remedy, not a guarantee. The guarantee is points 1–4 holding by construction so the poisoned state is never produced in the first place.

## Implementation notes

Honest status — the *decision* is recorded here; enforcement is **partially landed**:

- **Point 4 (assert coverage) — implemented.** `app/factor_data/evidence.dataset_health(store, start, end)` returns date bounds, row/ticker counts, a `covers_window` flag, and `ok=False` on any red flag (no rows, coverage gap, survivorship suspicion) so a harness can fail closed.
- **Point 5 (Evidence Correction Report) — established as a pattern.** Used for RNG-001; to be standardized as a section of the per-program Evidence Package (follow-up).
- **Points 1–3 (scope `.empty`; assert page-limit; chunk cold fetches) — ✅ implemented.** `bar_cache._fetch_and_write` now **paginates** the provider: a `len == _PAGE_LIMIT` response is treated as *possibly truncated* and the fetch continues from just after the last returned bar until a short/empty page proves the span exhausted, reassembling the full span. `.empty` markers are written only for genuinely-empty buckets **within the range the provider actually covered** (`covered_end`); a bucket beyond an incomplete fetch (continuation failure or the `_MAX_PAGES` safety cap) is left *missing* — re-fetchable, never poisoned. The live box's small incremental same-day fetches (< 10k rows) return in one short page, so that path is unchanged. Regression tests: `tests/market_data/test_bar_cache.py` (pagination past the page limit; truncated-fetch → beyond-range days stay missing-not-`.empty` + re-fetchable; empty span still marks all days; in-range gap still marked). Pre-existing poisoned caches still need the one-time monthly-chunk rebuild to clear stale markers — the new writer prevents recurrence, it does not retroactively heal old caches.
- **CI invariant:** none introduced yet. A candidate future invariant is a cache-writer unit test asserting that (a) a truncated (short) provider response leaves beyond-range buckets *missing* rather than `.empty`, and (b) an exactly-page-limit response triggers a continuation fetch rather than being accepted as complete.

## Consequences

- **Positive:** research reads become trustworthy by construction, not by luck; the platform can state "this backtest ran on complete data" and mean it. The failure mode that invalidated Range Phase 1/3 cannot silently recur once points 1–3 land. Data-integrity faults become disclosed, auditable events. **Independent reproductions become more credible** because data completeness is explicitly verified before evidence is generated (ADR 0030 Capability Onboarding leans directly on this).
- **Negative:** chunked cold fetches are slower and issue more provider requests than a single call (bounded by the rate limits already in place). A fail-closed coverage gate will *block* research that would previously have produced a (wrong) number — intended friction, but friction. Until points 1–3 land, the guarantee is aspirational for cold intraday research and depends on the rebuild workaround + reviewer vigilance.
- **Neutral:** the `.empty` marker keeps its role for genuinely empty days; only its *scope* narrows. Existing poisoned caches still require the one-time rebuild to clear stale markers — the new rule prevents recurrence, it does not retroactively heal old caches.
- **Forward-looking:** the Continuous Evidence Engine (CEE) should eventually consume `dataset_health` as a first-class governed signal alongside Sharpe / drawdown / correlation — so **Dataset Health · Coverage · Integrity · Provenance** live under one governance framework rather than as a separate research-time check. (Operational track, CEE §4 — an integrity lapse is a fix-the-system signal, never an edge verdict.)

## Alternatives considered (not chosen)

- **Fix the RNG-001 cache and move on (no ADR).** Rejected: leaves the failure mode latent for the next multi-year cold fetch and undocuments a decision the whitepaper and RNG-001 case study already cite as foundational. The dangling "ADR-0033" references were themselves a symptom of the missing record.
- **Detect-only (coverage gate, but keep the poisoning writer).** Rejected as insufficient: a gate that fails closed protects the *read* but leaves the cache in a poisoned state that every subsequent read must re-detect and every rebuild must re-clear. Prevention at the writer (points 1–3) is the durable fix.
- **Raise the single-fetch `limit` instead of chunking.** Rejected: any fixed limit is still a ceiling; a large enough span re-hits it. Chunking plus the page-limit truncation guard removes the dependence on a single page rather than betting the span never exceeds it.
- **Silently rebuild and re-run (no Evidence Correction Report).** Rejected: destroys the provenance that the platform detected and corrected its own fault — the very evidence that the process is trustworthy.

## Re-evaluation triggers

- **Points 1–3 landed** (cache-writer pagination + scoped `.empty` + regression tests). Remaining optional hardening: promote the truncation/page-limit regression tests to a CI invariant, and run the one-time monthly-chunk rebuild wherever a pre-existing poisoned cache is found.
- **CEE consumes `dataset_health`:** when the Continuous Evidence Engine adds integrity/coverage/provenance to its governed signals (the forward-looking consequence above), revisit to align the two.
- **A second data provider or dataset** (beyond Alpaca bars / Sharadar) exhibits a different integrity failure mode — generalize the guarantee (and possibly merge with a broader data-quality ADR) rather than special-casing per source.
- **The live path stops being incrementally-fetched** (e.g., a live feature begins issuing multi-year cold fetches) — the "live box is largely unexposed" assumption no longer holds and points 1–3 become urgent rather than deferred.
- **A coverage-gate false positive** blocks legitimate research (e.g., a genuinely thin but complete window reads as a gap) — revisit `dataset_health`'s red-flag thresholds.

## Foundational lineage & whitepaper

ADR 0014 (Backtest Ground Truth), ADR 0018 (Point-in-Time Data), and ADR 0033 (Historical Data Integrity) together define the platform's **Evidence Integrity** foundation — Point-in-Time Integrity · Historical Data Integrity · Reproducibility · Continuous Verification. This ADR warrants a short whitepaper section, *"Data Integrity as Scientific Infrastructure"* (PIT correctness · coverage verification · evidence correction), and should be cited wherever the whitepaper discusses the credibility of the platform's research methodology.
