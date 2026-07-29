# ADR 0049 — Strategy 9 v1.3 (C40) portfolio construction

| Field | Value |
|---|---|
| Date | 2026-07-28 |
| Status | Draft — becomes Accepted on owner approval of PR #537 (the underlying decisions were owner-ruled 2026-07-28 in the WS-1 sessions; this document records them) |
| Phase | Strategy 9 / Account 7 (PORT-001 successor); cross-references the strategy-template layer |
| Supersedes | — (the v1.2.0 combined-book construction is REJECTED as nonconforming, not superseded by a versioned ADR; see Context) |
| Related | 0002 (single OrderRouter), 0005 (activation cooldown), 0042/0043 (risk-control governance precedents) |

## Context

On 2026-07-28 a review of a withheld one-time rebalance manifest for account 7 exposed that
the live combined-book strategy (v1.2.0, "V4" in the evidence record) was **not the
portfolio that PORT-001 validated**. Root causes, each independently confirmed:

1. **CF-2 — validation-to-production nonconformance.** The template applied its 4%
   per-name cap *globally after sleeve blending*, although every design document, the
   PORT-001 validation harness (which explicitly drops the parameter), the preview
   tooling, and the parameter's own comment scope it to the *equity sleeve*. The global
   cap truncated the cross-asset hedges (UUP raw ~32% → 4%), silently converting the
   validated gross≈1.0 construction into a ~33%-invested book and pushing equity-beta
   risk contribution back up from the governor's 0.80 target to ~0.90. No promotion gate
   ever exercised the weights→orders transformation, so the defect was structurally
   invisible (a separate platform finding: promotion verification must extend through
   sizing).
2. **CF-1 — governor-registration ambiguity.** `enforce_beta_cap=True` +
   `beta_cap_report_only=True` were registered together; the operating record later
   misread report-only as "dry run" although enforcement takes precedence in code. The
   audit trail proved the 2026-07-07 enforcement activation was intentional and
   runbook-governed; the ambiguity was in labeling, not authorization.
3. **CF-3 — economically meaningless trade thresholds.** `min_trade_pct` was 3% of each
   position's own target (≈$5 at 0.18%-weight positions) and entries had no floor,
   producing ~64 orders per rebalance, 57% below $100.

A four-phase governed research program (walk-forward evidence 2022-06-06 → 2026-06-08,
weekly, net 10 bps; all artifacts hash-sealed on the paper box under
`/opt/workbench/data/ops/acct7/ws1_evidence/`) evaluated corrected and redesigned
constructions against the corrected-conformance control and adjudicated a successor.

## Decision

Strategy 9's governed construction becomes **v1.3 ("C40")**, implemented as
`strategies_user/templates/combined_book_v13.py` (code version 1.4.0 — the 1.3.0 version
string was consumed by an earlier revision; the governance name remains v1.3):

1. **Equity sleeve:** fixed top-40 names by the production PIT momentum ranking
   (252/21), equal weight with the per-name cap applied **inside the sleeve**:
   `w = min(1/40, 0.04)`.
2. **Cross-asset sleeve:** the validated 9-ETF `cross_asset_tsmom` (corr-aware λ=0.5)
   with a **20% book-level per-name cap applied PRE-BLEND, sleeve-internally** —
   `min(w, 0.20/0.60)` — by truncation, never redistribution.
3. **Blend:** fixed 0.40 equity / 0.60 cross-asset; **no global post-blend position cap
   of any kind** (the CF-2 remediation).
4. **Beta governor:** `cap_equity_beta` (rc ≤ 0.80) **enforced by default** — in
   `default_params` *and* `params_schema` — with released exposure retained as explicit
   cash, never auto-redistributed (the "D1" policy).
5. **Trade threshold:** the bounded hybrid
   `max($50, min(3% × target notional, 0.10% × account equity))`, applying to entries
   and held-name deltas alike. **Structural exemption is exits only** (evidence-exact
   ruling). Skipped partial deltas are accumulated and reported per-rebalance as
   operational-debt telemetry (symbol, notional, account weight, sleeve, risk direction,
   persistence).
6. **Regime filter (frozen convention):** the freshest available price is compared
   against the moving average of the **prior 200 completed daily bars**; the current
   (possibly partial) bar never enters the average; insufficient history fails open
   (hold + signal), never a silently shortened window.
7. **The v1.2.0 live construction (V4) is REJECTED** as a valid strategy construction on
   conformance grounds and preserved only as the incident comparator in the sealed
   evidence.

Exact transformation sequencing (pinned by regression tests; reordering is a
construction change requiring a new ADR): sleeve generation → sleeve-internal caps →
0.40/0.60 blend → beta governor → released allocation to cash → cash buffer → sizing at
`investable × weight` → bounded threshold (exits exempt) → orders via
`ctx.submit_order` → OrderRouter (ADR 0002).

## Rationale

- **Why fix the cap scope rather than accept the live book:** the live book was never
  the validated portfolio; retaining it would launder a defect into a specification. The
  33%-invested posture also partially defeated the enforced governor (equity RC 0.90 vs
  its 0.80 target) because the global cap stripped mostly hedges.
- **Why 40 names:** breadth was adjudicated within {20, 30, 40} under frozen
  **non-return** criteria (risk-control conformance, tracking drift, concentration,
  operational behavior; returns explicitly excluded to avoid winner's-curse selection —
  N=20 had the best, statistically unresolved, return). N=40 had the best effective
  diversification among operational qualifiers under the frozen tie rule.
- **Why the 20% cross-asset cap:** all uncapped breadths failed a frozen concentration
  gate identically (top-1 mean 26.8%, max 58.8% of equity, driven by the uncapped
  vol-target sleeve piling into UUP). A pre-authorized, tightly bounded contingency
  (selected breadth + 20% cap + interaction-corrected threshold) passed the same gate
  with top-1 pinned at ~19.6% and *better* aggregate drift than the uncapped book.
  Redistribution designs were rejected: pro-rata redistribution concentrated UUP to 51%
  of the book, and within-equity redistribution rebuilt exactly the beta the governor
  removes (falsification-confirmed at RC 0.998).
- **Why the bounded threshold:** pure floors were rejected — a $100 floor accumulated
  12.1% mean / 27.2% max of equity in unexecuted deltas — and the pure relative
  threshold let capped hedge positions accumulate 13.4–13.6% concentrated drift (its 3%
  arm scales with a $19–24k position). Bounding the relative arm at 0.10% of equity
  collapsed hedge drift-share from ~44% to 2.9% while cutting orders ~60%.
- **Why exits-only exemption:** it is the exact behavior the sealed walk-forward and
  parity proof validated. A broader "mandatory risk-reduction" bypass sounds safer but
  is an untested construction (turnover, tracking, and path effects unknown); mandatory
  account-level actions (circuit breakers, daily-loss, operator de-risking) already act
  outside the template through the risk engine and OrderRouter and cannot be suppressed
  by any template threshold.
- **A governed exception is on the record:** the contingency displaced the uncapped book
  with 5/6 pre-registered criteria passed; the sixth (a "no name delayed >26 weeks"
  proxy) failed on immaterial diffuse single-stock residuals (≤$120, ≤0.12% of equity
  each, no hedge or dominant position). The proxy was adjudicated semantically invalid
  for its purpose and the exception granted explicitly — the measured failure was NOT
  rewritten, and the proxy is replaced **prospectively** by a materiality-aware per-name
  delay battery (delay scoped to positions >1% of equity / top-5 / hedges, with a frozen
  materiality floor and risk-direction attribution). This exception is not precedent for
  waiving pre-registered gates without formal adjudication.

## Implementation notes

- Template: `apps/backend/strategies_user/templates/combined_book_v13.py` (new file;
  the deployed `combined_book.py` remains for the IDLE v1.2.0 registration and the
  incident record). Single order call site via `ctx.submit_order` (ADR 0002 allowlist
  entry with justification).
- New params (schema-synced): `equity_fixed_n=40`, `ca_book_cap=0.20`,
  `trade_floor_usd=50`, `trade_rel_pct=0.03`, `trade_ceiling_equity_pct=0.0010`;
  `min_trade_pct` retired; `max_position_pct` rescoped to the equity sleeve;
  `enforce_beta_cap` default True in BOTH `default_params` and `params_schema`.
- Regression families: `apps/backend/tests/strategies/test_combined_book_v13.py` —
  pre-blend cap semantics, equity-only cap scope, threshold arms/exemption/telemetry,
  engine default-parameter merge (load-bearing: a bare params dict silently restores
  quantile behavior), rotated-out-holding exits, frozen regime convention, and
  schema-default-value parity.
- Evidence identities (sealed, hash-referenced; local evidence store + S3 per
  GITHUB-OPS-001): settled spec `8445fa8a…`, walk-forward results `a44463f1…`, breadth
  adjudication `eb6461d2…`, contingency evaluation `db08def1…`, template↔research parity
  proof `5740adc9…` (13 sampled dates: names exact, weights 0.0, governor 0.0, notionals
  ≤$0.001, post-trade ≤1e-8), harness rev-5 `9297936f…`.

## Consequences

- **Positive:** the live construction again matches a validated specification; the
  governor's risk posture (RC ≤ 0.80) is preserved end-to-end; single-name concentration
  is capped at ~20% of the book; orders drop ~60% with economically proportionate
  thresholds; every future deviation has a regression tripwire.
- **Negative:** the book intentionally carries material residual cash (governor +
  truncation; historically ~35–40% at this construction) — capital efficiency is
  sacrificed for the ruled risk policy; sub-threshold residuals persist by design
  (reported as operational debt, max observed ≤$120/name); the strategy's below-200dma
  underperformance (−9.9% annualized in 45 bear weeks) is NOT addressed by this
  construction and remains an open research question; two constructions now coexist in
  the template directory until v1.2.0 is retired.
- **Neutral:** the account-7 transition to this construction is a separate, staged,
  owner-gated execution event (see the sealed transition-plan draft); the code version
  string (1.4.0) and governance name (v1.3) intentionally differ.

## Alternatives considered (not chosen)

- **Keep the live V4 behavior:** rejected — conformance failure is disqualifying
  regardless of its (statistically indistinguishable) return.
- **Corrected 80-name book without caps/threshold changes (F0):** APPROVED as the
  fallback specification, not the successor — highest fidelity and diversification, but
  64 orders/rebalance with 57% below $100 and top-1 concentration up to 58.8%.
- **Cross-asset redistribution of governor cash:** rejected (UUP → 51% of book).
- **Within-equity redistribution:** rejected (rebuilds the governed-away beta; RC 0.998).
- **Pure $50/$100 floors, unbounded hybrid, tighter (10–15%) or no CA caps, 20/30/60/80
  breadths:** each rejected or subsumed on the frozen criteria above; full grid in the
  sealed evidence. Reconsidered only via a new governed study.

## Re-evaluation triggers

- Live operational-debt telemetry shows a **material** skipped delta (>1% of equity, or
  any hedge/top-5 position) persisting ≥4 rebalances → revisit the exits-only exemption
  via the prospective materiality battery.
- Realized top-1 concentration exceeds 25% of equity for 4 consecutive weeks despite the
  cap (e.g., through price drift between rebalances) → revisit the cap level/mechanism.
- The RANK-001 utility framework, once frozen **independently**, shows C40 materially
  outside the practical-tie range vs F0 → re-open the F0-vs-C40 choice (construction
  itself unchanged).
- The regime-weakness research program produces a validated defensive-state improvement
  → new ADR (never folded silently into this construction).
- Governor scale pinned at its floor (equity sleeve ~fully suppressed) for >8 consecutive
  weeks → the breadth/beta interaction assumption has drifted; re-run the neighbor study.
