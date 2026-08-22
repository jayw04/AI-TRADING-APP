# GAPPER v2.1.1 — Stage-0 Preparation Scoping Memo

| Field | Value |
|---|---|
| Date | 2026-08-17 |
| Version | v0.1 (DRAFT — developer preparation record; decides nothing) |
| Authorization basis | Approval record §2/§3-am.7: developer-side Stage-0 preparation may proceed after v2.1.1 owner approval (in hand). Stage-0 **execution** remains blocked on MR-002 Steps 1–2 / the G4 ruling (ATP plan §8 items 3+8). |
| Scope | Read-only scoping survey for the field-sufficiency harness (ATP plan Track 5 §5.1, "prep now"). No code built, no data touched, no verdicts. |

## 1. Design identity — verified

The governing artifact is `docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx`. Its SHA-256 was **re-hashed locally on 2026-08-17 and matches the approval record exactly**: `2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d` (26,062 bytes). Superseded hash `84913de0…` is never approved. Any edit to the DOCX — a single character — invalidates the approval; the hash is the approval identity anchor.

⚠ **Custody defect:** both the approval record (`GAPPER_Research_Design_v2_1_1_ApprovalRecord_v1.0.md`) and the DOCX are **untracked working-tree files**, despite the record's own §7 requiring it to be readable in Git without an AWS dependency. Committing the `.md` (the DOCX is gitignored by ADR 0050 design) fixes the record half without touching the approved bytes. Owner action.

## 2. What Stage 0 measures (from the hash-bound design)

Two independent properties — Stage 0 "may not pass on field size alone":
1. **Upstream field sufficiency** — the scanner/data system regularly exposes enough legitimate tradeable events ("field" = population of names, not a schema column).
2. **Contrast preservation** — the funnel `scanner/event field → tradability → coverage → eligible → ranking → selected` keeps a genuine selected-vs-non-selected contrast; **no unexplained `eligible_panel` → `eligible_count` collapse permitted** (the v1 defect).

**0A measures only:** eligible-event frequency · direction-normalized post-open return dispersion (30m/60m/close/next-close) · spread and slippage · liquidity · halt frequency · long/short availability per cell · oracle top-subset upper bound (**DIAGNOSTIC_ONLY, permanently branded**).
**0B:** 2–3 pre-cutoff signals only (gap magnitude; prior momentum; premarket RVOL; optional sector-relative residual). No fitted ranker, no ML, no parameter search.
**Frozen GO thresholds (§3.3, locked once Stage 0 executes):** ≥10 eligible names on ≥50% of usable event days · primary-horizon IQR ≥150 bps · friction/IQR ≤25% · oracle net-positive ≥65% (corroboration only) · cheap-signal edge ≥20 bps/traded day · positive days ≥55% · serious execution-failure rate ≤10%.
**Dataset contract (§3.1, frozen before any analysis):** date range · **≥250 (pref. 500+) trustworthy PIT event-days across materially different environments** · source/vendor · survivorship · corporate-action handling · PIT rules · minimum analyzable sample. 0A reconstructs the frozen event definition from **raw premarket prints**, never the vendor top-N; a fidelity check vs live scanner output blocks 0B on material disagreement.

## 3. The SIP question — resolved by absence

The approved design contains **zero mentions of SIP, IEX, feed, consolidated, or any vendor feed identity** (verified against the full document text). So the plan's conditional "add SIP evidence only if that design permits it" resolves to: **the design neither permits nor forbids SIP — the `source/vendor` term of the §3.1 dataset contract is still open (Stage 0 un-executed) and choosing it is a pre-execution governed decision, recorded outside the DOCX** (amending the DOCX would destroy the approval). The harness must therefore carry `source/vendor` as an explicit **unset owner-decision field**, defaulted to neither IEX nor SIP. Note the dependency direction: MDQ-001 K4 *consumes* the Stage-0 field-sufficiency report; the harness must not presuppose SIP.

The strongest technical argument for SIP is a **code** finding, not design permission: `gapper_shadow.py` documents that entry-time bid/ask spread is unobservable from OHLCV bars — the half-spread model and 25 bps gate are "deferred to a quote-data source."

## 4. Data reality — the honest headline

**§3.1's ≥250 trustworthy PIT event-days is not satisfiable from local data today:**

| Need | Status |
|---|---|
| Raw historical premarket prints | ❌ `bars_cache/` ≈ 240 symbols, ~93 day-files (AAPL), ~2026-03→06, partial extended hours, IEX |
| Prior-close dailies / ADV / sectors | ✅ `factor_data.duckdb` `sep` 1997→2026-06-12 (~2 months stale) + `tickers.sector` |
| Scanner output for the fidelity check | ⚠ local evidence store holds **1 file**; v1 census (42 records) is development-only, 16 MISSING_PROVENANCE, capture rate 1/5 days as of 08-11 |
| Quotes/spreads (0A + §6.3 short cells) | ❌ none; MDQ collector would supply, pre-deployment (G2 open) |
| Locate/borrow/SSR | ❌ no source in repo (design assumes borrow prohibited; long side fully discoverable) |
| Halt/LULD | ❌ only via SIP ws channels `s`/`l`, not captured |

Per §3.1 this is a legitimate **HOLD** shape ("cannot be obtained cheaply → HOLD"; re-entry requires a dataset improvement, not a re-run). **A harness that measures and reports this shortfall is the correct deliverable** — and is exactly the per-field available/partial/absent census MDQ-001 K4 needs.

## 5. Reusable code inventory (highest value first)

`app/services/premarket_scan.py` (funnel counters `gappers_in/store_covered/eligible_panel/eligible_count/candidate_count` + PIT `store_features_for`) · `premarket_evidence.py` (evidence schema `scan_001_premarket_gate/v1`) · `premarket_gappers.py` (external scanner ingest, fail-soft) · `premarket_outcomes.py` · `factor_data/gapper_intraday.py` (candidate+SPY+sector SPDR 1/5-min cache) · `gapper_shadow.py` (slippage grid, breakeven slippage) · `bar_cache.py`. ⚠ Hazards: the void v1 verdict path is still human-invokable (PR #511 open); `repair_premarket_gate_provenance.py` conflicts with "provenance cannot be repaired retroactively"; the box-native screener (PR #407 / GAP-NATIVE-001) is unmerged and default-off.

## 6. Harness prep plan (buildable now; executes no Stage-0 verdict)

1. Startup re-hashes the DOCX; refuse to run unless SHA-256 == `2706c4dc…d73d` (constant, not config); hard-reject `84913de0…`.
2. Dataset contract as a declarative artifact with all §3.1 terms; `source/vendor` explicitly **unset / owner decision**.
3. Funnel instrumentation emitting every stage with a **reason code per excluded name**, reusing the existing counter names for v1 comparability.
4. Unexplained-collapse detector: `sum(reason_coded_exclusions) == eligible_panel − eligible_count` per date; residual = hard fail, first-class metric.
5. Event-definition reconstructor (pure, PIT-strict `date < asof`), gap% vs prior close from raw premarket prints + filters — never vendor top-N.
6. Fidelity-check harness vs live scanner days, frozen disagreement threshold, blocks-0B flag; honest low-N reporting.
7. **Data-sufficiency census** — per candidate date: bar coverage, premarket presence, first/last bar, missing bars, quote/halt/locate availability → available/partial/absent matrix. *The K4 deliverable; producible without Stage 0 running.*
8. 0A measurement stubs frozen but unexecuted; oracle bound behind a schema-stamped `DIAGNOSTIC_ONLY` brand.
9. §3.3 thresholds as frozen constants + early-STOP; verdict function returns `NOT_EVALUABLE` on incomplete contract; no ad-hoc verdict path (PR #511 lesson).
10. Write-time provenance on every output (source hash, code version, run ID, write class = `reconstruction`); unstamped ⇒ invalid.
11. Guardrails: development store only; no evidence-series writes; no order path; passes feed-pinning + research-plane checks; **execution interlock** — no GO/HOLD/STOP emission without an owner-supplied §9/G4 token.

## Authority

Preparation record only. The hash-bound design, its approval record, the G4 ruling, and MR-002 program artifacts control. Nothing here starts Stage 0, chooses the dataset source, or amends any frozen document.
