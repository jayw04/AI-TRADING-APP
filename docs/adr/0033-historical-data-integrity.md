# ADR 0033 — Historical Data Integrity (Foundational)

| Field | Value |
|---|---|
| Date | 2026-07-03 |
| Status | **Draft** (owner's 2026-07-01 review requested elevating this to a *Foundational* Data Integrity ADR; pending ratification) |
| Phase | Cross-phase / Foundational — governs every research read from a cached historical dataset |
| Supersedes | — |
| Related | 0018 (PIT factor data — same "data available at decision time" discipline), 0014 (backtests = evaluation ground truth — a backtest is only ground truth if its data is complete), 0026 (Factor Lab — the programs that read the cache), 0019 (Research Engine — the read-only subsystem this protects) |

## Context

Every backtest, evidence package, and verdict this platform produces is only as trustworthy as the historical data beneath it. The methodology can be flawless and the verdict still wrong if the data silently under-represents the window it claims to cover.

RNG-001 made this concrete. The platform's intraday bar cache (`apps/backend/app/market_data/bar_cache.py`) was found to **silently truncate a cold multi-year fetch at the data provider's page limit and then poison the gap**: `_fetch_and_write` issues a single Alpaca `get_stock_bars` call for the whole missing span with `limit=10000`; for fine (intraday) granularity, buckets are per-day, so a cold multi-year request returns only the first ~10,000 rows (~126 sessions), and the per-bucket split loop then writes a zero-byte `.empty` marker for **every un-returned day beyond the truncation**. Those `.empty` markers block re-fetch (they read as "cached empty"), so the missing days are poisoned permanently until cleared. The observed result (2026-06-30): the Range Top-5 + SPY 5-minute caches held ~250 **non-contiguous** sessions with 2024 and 2026 almost entirely missing and ~800–970 bogus `.empty` markers per symbol — and the **Range Phase 1 and Phase 3 numbers had been computed on that biased ~⅓ sample**. The harnesses were correct; the data was incomplete, and nothing had asserted otherwise.

The defect was caught, disclosed via an **Evidence Correction Report**, corrected (a monthly-chunked cache rebuild), and the affected studies were re-run — the RNG-001 verdict held. The question this ADR answers is not "how do we fix that one bug" but **"on what terms does the platform treat historical-data completeness as a first-class, non-negotiable property of every research read?"** The owner's 2026-07-01 review asked for exactly this elevation: *"I would elevate ADR-0033 from a 'bug fix' to a Foundational Data Integrity ADR… without trustworthy historical data, none of the other research matters."*

## Decision

**Historical-data completeness is a foundational guarantee, enforced at three points, and a data-integrity fault is a stop-the-research event — never a silent degradation.**

1. **`.empty` markers are scoped to the actually-returned data range.** A cache writer may record a bucket as empty **only** for buckets that fall within the range the provider actually returned (`[df.t.min, df.t.max]`). Buckets **beyond** the returned range are left *missing* (re-fetchable), never marked empty. A truncated response must never poison the days it failed to return.
2. **Cold fetches that imply more than one provider page are chunked.** When a requested span implies more rows than the provider's single-page limit (per-day intraday buckets over multiple years), the fetch is split into sub-spans that each stay under the limit, so completeness does not depend on a single page.
3. **Coverage is asserted before any research read.** A research harness verifies that the dataset actually spans the requested window (row presence, date bounds, gap detection) and **fails closed** on a red flag, rather than silently computing on a partial sample. `app/factor_data/evidence.dataset_health` is the canonical primitive.
4. **A discovered data-integrity fault is disclosed, not quietly patched.** When a fault is found in data that has already produced results, it is recorded in an **Evidence Correction Report** (what was wrong, what it biased, the correction, the re-run outcome), and the affected results are re-run. Correcting one's own data faults *in the open* is a trust signal, not an embarrassment to hide.

## Rationale

- **Completeness failures are silent by nature.** A missing credential throws; a truncated dataset returns a number. The only defenses are (a) never producing the poisoned state and (b) asserting coverage before trusting a read. Points 1–2 address (a); point 3 addresses (b). Detection alone is insufficient because a biased sample still yields a plausible-looking verdict.
- **Scoping `.empty` to the returned range is the minimal correct rule.** The `.empty` marker's legitimate job is to avoid re-fetching genuinely empty days (holidays, inactive symbols). That job only justifies marking days the provider actually spoke to. Extending it to days beyond a truncated response conflates "the provider says nothing traded" with "we never asked past row 10,000" — the exact conflation that caused the poisoning.
- **Foundational, not incidental (owner framing).** Data integrity underpins ADR 0014 (backtests as ground truth) and ADR 0018 (point-in-time factor data). Recording it as a Foundational ADR — above any single program — means future programs inherit the guarantee instead of each re-discovering the failure mode the hard way.
- **Disclosure over silent repair preserves the evidence.** The platform's differentiator is honest evidence. Quietly rebuilding a cache and re-running would erase the fact that the platform *detected and corrected* a fault — which is itself evidence the process works. The Evidence Correction Report keeps that provenance.
- **The workaround proves the target, but isn't the guarantee.** `scripts/research/rebuild_5min_cache.py` (clear bogus markers, re-fetch month-by-month) recovers a poisoned cache today, but a manual rebuild script is a remedy, not a guarantee. The guarantee is points 1–3 holding by construction so the poisoned state is never produced in the first place.

## Implementation notes

Honest status — the *decision* is recorded here; enforcement is **partially landed**:

- **Point 3 (assert coverage) — implemented.** `app/factor_data/evidence.dataset_health(store, start, end)` returns date bounds, row/ticker counts, a `covers_window` flag, and `ok=False` on any red flag (no rows, coverage gap, survivorship suspicion) so a harness can fail closed.
- **Point 4 (Evidence Correction Report) — established as a pattern.** Used for RNG-001; to be standardized as a section of the per-program Evidence Package (follow-up).
- **Points 1–2 (scope `.empty`; chunk cold fetches) — NOT yet implemented.** `bar_cache._fetch_and_write` still marks any empty bucket (including those beyond a truncated response, `bar_cache.py:308-316`) and still fetches with a single `limit=10000` (`bar_cache.py:429`). The current mitigation is the monthly-chunk rebuild script plus the fact that the **live EC2 box is largely unexposed** (it fetches incrementally in small same-day ranges that stay well under 10k) — the defect bites multi-year *cold research* fetches, not live operation. Landing points 1–2 touches shared infrastructure the live box also uses, so it is a careful, separately-reviewed change tracked by this ADR.
- **CI invariant:** none introduced yet. A candidate future invariant is a cache-writer unit test asserting that a truncated (short) provider response leaves beyond-range buckets missing rather than `.empty`.

## Consequences

- **Positive:** research reads become trustworthy by construction, not by luck; the platform can state "this backtest ran on complete data" and mean it. The failure mode that invalidated Range Phase 1/3 cannot silently recur once points 1–2 land. Data-integrity faults become disclosed, auditable events.
- **Negative:** chunked cold fetches are slower and issue more provider requests than a single call (bounded by the rate limits already in place). A fail-closed coverage gate will *block* research that would previously have produced a (wrong) number — intended friction, but friction. Until points 1–2 land, the guarantee is aspirational for cold intraday research and depends on the rebuild workaround + reviewer vigilance.
- **Neutral:** the `.empty` marker keeps its role for genuinely empty days; only its *scope* narrows. Existing poisoned caches still require the one-time rebuild to clear stale markers — the new rule prevents recurrence, it does not retroactively heal old caches.

## Alternatives considered (not chosen)

- **Fix the RNG-001 cache and move on (no ADR).** Rejected: leaves the failure mode latent for the next multi-year cold fetch and undocuments a decision the whitepaper and RNG-001 case study already cite as foundational. The dangling "ADR-0033" references were themselves a symptom of the missing record.
- **Detect-only (coverage gate, but keep the poisoning writer).** Rejected as insufficient: a gate that fails closed protects the *read* but leaves the cache in a poisoned state that every subsequent read must re-detect and every rebuild must re-clear. Prevention at the writer (points 1–2) is the durable fix.
- **Raise the single-fetch `limit` instead of chunking.** Rejected: any fixed limit is still a ceiling; a large enough span re-hits it. Chunking removes the dependence on a single page rather than betting the span never exceeds it.
- **Silently rebuild and re-run (no Evidence Correction Report).** Rejected: destroys the provenance that the platform detected and corrected its own fault — the very evidence that the process is trustworthy.

## Re-evaluation triggers

- **Points 1–2 land:** flip this ADR to Accepted and update Implementation notes; add the cache-writer regression test (and consider promoting it to a CI invariant).
- **A second data provider or dataset** (beyond Alpaca bars / Sharadar) exhibits a different completeness failure mode — generalize the guarantee (and possibly merge with a broader data-quality ADR) rather than special-casing per source.
- **The live path stops being incrementally-fetched** (e.g., a live feature begins issuing multi-year cold fetches) — the "live box is largely unexposed" assumption no longer holds and points 1–2 become urgent rather than deferred.
- **A coverage-gate false positive** blocks legitimate research (e.g., a genuinely thin but complete window reads as a gap) — revisit `dataset_health`'s red-flag thresholds.
