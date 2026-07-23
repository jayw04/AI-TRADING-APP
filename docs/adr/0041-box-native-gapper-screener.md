# ADR 0041 — Box-native premarket gapper screener as the authoritative gappers source

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Status | Draft |
| Phase | Ops / AWS independence (post-ADR 0032 cutover); consumed by SCAN-001 (ADR 0024) |
| Supersedes | — |
| Related | 0024 (SCAN-001 gate), 0032 (AWS hosting), 0033 (data integrity), 0037 (data source governance) |

## Context

The daily `premarket_gappers_<date>.json` file feeds two consumers on the box: the SCAN-001
Production Validation Gate's ~09:25 ET premarket scan (forward-evidence accrual, ADR 0024) and
the Opportunities-page watchlist. Until this ADR, the file's only producer ran on the
developer's laptop (the sibling `claude-trading-view` scanner: Yahoo gainers table + Benzinga/LLM
catalysts), synced to the box by a Windows scheduled task at ~09:00 ET.

After the ADR 0032 cutover the box is the platform's home and the laptop is warm standby,
powered off at unpredictable times. The 2026-07-10 pipeline audit found the gappers file to be
the **only** operational input still produced on the laptop: on any PC-off day the 09:25 scan
degrades to the newest older file (`stale: true`), silently thinning the gate's evidence accrual.
The owner directed the same day that operational inputs must be produced at AWS and pulled from
AWS — other machines may enrich, never gate, daily operation (Platform Principles §2.4).

The question: how does the box produce an equivalent gappers file itself, and which producer is
authoritative when both exist?

## Decision

1. The box produces its own daily gappers file via `app/services/native_gapper_screener.py`,
   scheduled weekdays 09:05 ET (+ idempotent 09:18 ET retry), sourced from the Alpaca movers
   screener verified through IEX snapshots — an already-approved external dependency.
2. The output is schema-compatible with the external scanner's file, written to a separate
   directory (`native_gappers_dir`), with `catalyst: null` and a `source` field
   (`"box_native_alpaca_v1"`).
3. **For today's date the native file is authoritative.** A same-date external (laptop) file
   contributes per-symbol `catalyst`/`headlines` enrichment only. The external file is the
   payload of record solely when the native file for today is missing; otherwise-newest-stale
   behavior is unchanged (`premarket_gappers.read_latest_gappers`).
4. SCAN-001 gate records carry the provenance (`gappers_source`, additive to
   `scan_001_premarket_gate/v1`). **Source segmentation is a hard rule** (review 2026-07-10):
   during the transition window, accrual is reported both overall and by source
   (`external_scanner` days, `box_native_alpaca_v1` days, overlap-comparison days —
   `scripts/compare_gappers_sources.py`); no SCAN-001/GAPPER-001 verdict may pool the two
   sources unless the transition comparison demonstrates acceptable source parity; if parity is
   poor, the native source starts a **new evidence tranche**.
5. The screener is default-off (`WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED`), enabled explicitly
   on the box — conservative defaults; tests/CI boots make no Alpaca screener calls.
6. Enabling the flag is gated on the §1.0 probe (hard gate, review 2026-07-10) confirming under
   the live entitlement: (a) `latest_trade` timestamps are current premarket prints, (b)
   `prev_daily_bar.close` is a usable prior close, (c) premarket volume is visible (if it is
   not, do not fake it — escalate to the owner), and (d) the scan completes before the 09:25 ET
   gate consumes it.

## Rationale

**Why produce on the box at all** — the alternative of hardening the laptop (wake timers, UPS,
retry syncs) still leaves daily evidence hostage to a machine whose defining property is that it
may be off. Fail-soft staleness already exists; the problem is not crashes but silent evidence
degradation on exactly the days nobody is watching the laptop.

**Why Alpaca** — the box already holds Alpaca credentials, the SDK, and the connection-layer
audit for it. No new-dependency ADR is needed because Alpaca is already approved — this ADR is
still required for the *operational authority and provenance* decisions (which producer wins,
how evidence records the switch), not for the data source itself (no ADR 0037-style onboarding
beyond a registry entry). The alternative — replicating the Yahoo/Benzinga scrape server-side — adds two new
unapproved dependencies plus an LLM summarization step, violating conservative defaults for a
field (`catalyst`) the gate never reads.

**Why native-wins rather than external-wins** — external-wins ("richer file preferred") would
make the operational input's provenance depend on whether the PC happened to be on, producing an
uncontrolled mixture in the gate accrual. Native-wins makes provenance deterministic:
`box_native_alpaca_v1` on every healthy box day. The cost — losing the consolidated-tape Yahoo
universe in favor of IEX-visible names — is accepted and made visible (next paragraph) rather
than silently averaged.

**Honest scope accepted** — IEX premarket coverage is thinner than the consolidated tape (the
2026-07-10 probe confirmed: SIP not entitled; illiquid names can show months-old "latest"
trades, which the screener drops). The native list may therefore be sparser than Yahoo's,
particularly for micro-caps. This is tolerable because the gate's own funnel already discards
names without historical-store coverage (`store_covered` was 6/10 on 2026-07-09), and because
provenance segmentation (Decision 4) keeps the change from contaminating the accrual.

**Why recompute the gap at verification time** — the movers ranking is trusted only for
discovery; the gap is recomputed from `latest_trade` vs previous close per symbol. A stale or
close-to-close movers ranking then cannot fabricate a gap: names without a live premarket print
simply drop out.

## Implementation notes

- Producer: `app/services/native_gapper_screener.py`; job `app/jobs/native_gapper_scan.py`;
  wiring in `lifespan.py` (ids `native_gapper_scan`, `native_gapper_scan_retry`).
- Filters mirror the external scanner exactly (strict >): gap 5%, price $3, premarket volume
  50k, top 10 by gap — parity is what makes the two sources comparable.
- Settings: `native_gappers_dir` (default `data/premarket_gappers_native`). Env gate:
  `WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED=1` on the box's prod compose only.
- Reader: `premarket_gappers.read_latest_gappers()` implements the precedence; payload gains
  `source`. Evidence: `run_premarket_scan` → `gappers_source` → persisted gate record.
- Registry: Alpaca screener/snapshots registered as DCAP-008 (`source_registry.py`),
  conservative entitlement flags (no redistribution, no external derived signals).
- Pre-flight probe: `scripts/probe_native_gappers.py` (§1.0 of the session doc); the
  2026-07-13 08:50 ET run is the go/no-go for enabling the flag on the box.
- No CI invariant added: the module is advisory-data-only; existing invariants
  (no-LLM-in-order-path, altdata isolation) are unaffected — it imports no order-path module.

## Consequences

**Positive** — the last workbench operational input produced off-box moves on-box; PC-off days
no longer degrade gate evidence; provenance of every gate record becomes explicit; the stale-
print and warrant/unit junk in raw movers output is filtered by construction.

**Negative** — the operational gapper universe narrows to IEX-visible names with live premarket
prints; catalyst text disappears from the Opportunities page on days the laptop file is absent;
the SCAN-001 accrual becomes two segments that must be analyzed separately, effectively
lengthening the time to a pooled verdict.

**Neutral** — the laptop scanner and sync task keep running as enrichment during (and after) the
transition; two gappers directories now exist on the box.

## Alternatives considered (not chosen)

- **Harden the laptop pipeline** (wake timers, retries, alerting): still violates the directive;
  the failure mode is availability, not reliability of the code. Reconsider: never — the
  directive is structural.
- **Replicate Yahoo/Benzinga scraping + LLM catalysts on the box**: two new external
  dependencies plus LLM cost for a display-only field. Reconsider if the owner wants catalysts
  box-side (would be its own session + ADR 0037 onboarding).
- **External-wins precedence**: rejected for non-deterministic provenance (above). Reconsider if
  the native screener proves systematically inferior during the transition comparison window.
- **Snapshot sweep of the factor-store universe as primary discovery**: the store is
  small-cap-sparse (the GOVCONTRACT-001 finding), and gappers are disproportionately small caps;
  retained only as the automatic fallback when movers returns nothing.
- **Alpaca SIP subscription** for consolidated-tape parity: recurring cost for an advisory
  input; the probe confirmed it is not currently entitled. Reconsider if the transition window
  shows the IEX universe missing a material share of store-covered gappers.

## Re-evaluation triggers

- The two-week transition comparison shows the native list missing >⅓ of the external list's
  *store-covered* names on a typical day (the gate-relevant subset — raw-list overlap doesn't matter).
- The 09:05/09:18 runs fail (no file written) on ≥3 trading days in any rolling month.
- SCAN-001's verdict harness finds the `box_native_alpaca_v1` segment's funnel systematically
  thinner than the `external_scanner` segment (evidence starvation).
- Alpaca changes movers/snapshot entitlements or the SIP cost calculus changes.
