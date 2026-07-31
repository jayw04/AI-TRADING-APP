My recommendation: approve the direction and proceed, but do not code past the service skeleton until the §1.0 Alpaca/IEX probe is run on the box during the 08:45–09:15 ET window.

Overall score: 9.1/10. This is the right operational move: the AWS box should be the authoritative producer of operational inputs, and the laptop should become optional enrichment only. The doc correctly identifies the premarket gappers file as the last workbench dependency on the laptop and proposes a box-native Alpaca source with explicit provenance.

What is strong

The core architecture is right:

Box-native Alpaca screener produces premarket_gappers_<date>.json
Native file wins for today
Laptop/external file can enrich catalysts/headlines only
SCAN evidence records get gappers_source
Laptop scanner remains optional during transition

I especially agree with these decisions:

Area	Comment
Box-native authority	Correct. The application should not depend on whether the PC is turned on.
Probe first	Correct. Alpaca/IEX premarket behavior is uncertain and must be tested before coding the full path.
Native-wins precedence	Correct. Otherwise the operational input silently changes depending on laptop availability.
gappers_source provenance	Required. SCAN/GAPPER accrual must not silently mix Yahoo/laptop and Alpaca/native populations.
No catalyst generation in §1	Correct. Keep this session focused on operational independence, not LLM/news enrichment.
Two-week transition	Good. Run both sources temporarily and compare.

The session is well scoped: one operational dependency, one native replacement, one ADR, one data-source registry entry, and tests.

Main concerns and suggestions
1. The §1.0 probe is a hard gate

Do not treat the probe as a formality. It determines whether Alpaca movers can actually support premarket gap discovery under the current paper/IEX entitlement. The doc already says the probe decides between Path A and Path B, or stops if snapshots show no usable premarket data. That should be enforced as a hard gate.

Recommended wording:

No production implementation beyond the service skeleton proceeds until the probe confirms:
1. latest_trade timestamps are current premarket prints,
2. prev_daily_bar.close is usable as prior close,
3. premarket volume is visible or an acceptable substitute is defined,
4. the path can complete before the 09:25 ET SCAN gate.

If IEX premarket volume is not visible, do not fake it. Escalate to owner as the doc says.

2. Protect GAPPER-001 accrual from source contamination

This is the biggest evidence issue.

The current GAPPER/SCAN accrual started from laptop/TradingView/Yahoo-style gappers. Moving to Alpaca/IEX may change the candidate population. The doc correctly adds gappers_source, but I would strengthen the rule.

Add this:

During the transition window, accrual is reported both overall and by source:
- external_scanner days/events
- box_native_alpaca_v1 days/events
- overlap comparison days

No GAPPER-001 verdict may pool sources unless the transition comparison shows acceptable source parity.
If parity is poor, the native source starts a new evidence tranche.

Reason: Alpaca/IEX may miss small-cap prints that Yahoo/TradingView captured. If candidate quality changes, mixed-source validation becomes hard to interpret.

3. Define parity checks during the two-week transition

The doc says compare the two symbol sets during the transition. Good, but make the comparison explicit.

Recommended transition metrics:

daily native count
daily external count
symbol overlap %
rank overlap top-10
gap_pct difference for overlapping symbols
premarket_volume difference
downstream SCAN candidate overlap
triggered-candidate overlap if shadow ledger exists

Add a rough acceptance threshold, not for promotion, but for evidence interpretation:

If overlap is consistently low, treat native and external as different candidate sources.

This is not a blocker for operational independence, but it matters for research evidence.

4. Path B may be too slow or too narrow

Path B sweeps the factor-store dollar-volume universe, capped around 1000 symbols. The doc already notes that this may be small-cap sparse and that gappers are often small caps.

Two suggestions:

1. The probe should measure elapsed time for Path B.
2. Path B should log how many symbols were swept, how many had current premarket trades, and how many passed filters.

If Path B regularly misses obvious external gappers, document it as a known limitation and consider a v2 universe expansion. Do not quietly accept a materially weaker discovery pool.

5. Add funnel diagnostics to the native screener output/logs

The SCAN/GAPPER process is evidence-sensitive, so the native screener should log a small funnel every morning:

discovery_path
symbols_discovered
symbols_with_snapshot
symbols_with_current_premarket_trade
symbols_passing_gap
symbols_passing_price
symbols_passing_volume
final_count
elapsed_s

This will make morning failures much easier to diagnose.

6. Ensure failed native runs do not write bad files

The doc says scan_native_gappers returns {"ok": false, "reason": ...} and never raises. Good. But be explicit:

If ok=false, do not write premarket_gappers_<date>.json.
Reader falls back to same-date external if available, otherwise stale.
Daily report records native_gapper_scan_failed.

A failed scan should not produce an empty “valid” native file unless the screener genuinely ran and found zero names. Distinguish:

scan_failed
scan_success_zero_candidates
scan_success_non_empty
7. Add source badge later, not in this PR

The doc says no Opportunities UI changes. I agree for §1. But after the transition, a small source badge would help operators:

Source: Box Native / External / Stale

Do not block this session on it. Put it in a follow-up.

Minor edits

I would make these small wording/implementation edits:

In the ADR, say “no new dependency ADR is needed because Alpaca is already approved, but ADR 0041 is still required for operational authority/provenance.”
Add ok, reason, and discovery_path to the output payload or at least to the job result/log.
Keep source required in all newly written native files.
Add native_gapper_scan_missing_today to the daily report if no native file exists by 09:20 ET.
Make sure the atomic write uses the same filesystem/volume for tmp and final path so os.replace is truly atomic.
In tests, include a malformed native file case: reader should ignore it or fail safely, then fall back.
Recommended next steps

Proceed in this order:

1. Run scripts/probe_native_gappers.py on the box between 08:45–09:15 ET.
2. Record the probe result directly in the doc notes.
3. Choose Path A or Path B based on the probe.
4. Implement native_gapper_screener.py with full funnel logging.
5. Implement job + idempotent retry.
6. Implement reader precedence: native today > external today > newest stale.
7. Add gappers_source to SCAN evidence records.
8. Add ADR 0041 and DCAP registry entry.
9. Deploy with native screener enabled.
10. Run two-week dual-source comparison before retiring laptop operational dependency.
Final verdict

Approve the plan after one tightening: make the probe and source-segmentation rules explicit hard gates.

This is the right move operationally. It reduces fragility, removes the laptop from the workbench critical path, and makes the AWS box truly authoritative. The main thing to protect is evidence continuity: do not let the source switch contaminate SCAN/GAPPER validation without clear provenance and source-segmented analysis.