Overall assessment

The new package is strong. v0.4 is a sound build-authorizing specification, and the pilot demonstrates that both EDGAR pipelines are technically feasible:

V1 produced a plausible quarterly earnings-anchor series extending before Sharadar’s approximately 2016 floor.
V2 successfully generated PIT SIC observations, including older filings requiring SGML-header fallback.
META, NFLX, VZ and AMT correctly exercised effective-dated sector-proxy transitions.
GOOG/GOOGL exposed an important issuer-versus-security design issue, which the pilot corrected rather than hiding.

My disposition is:

Approve continuation to the full-universe data build, but do not treat V1 or V2 as closed yet.
Two items require correction before the full run: V1 event-time semantics and the historical CIK/permaticker crosswalk specification.

1. Critical V1 correction: in-session acceptance cannot be treated as BMO

v0.4 currently says an ambiguous or in-session EDGAR acceptance is treated as BMO. Under the frozen cooling rule, a BMO event on session s prohibits execution at opens s and s+1.

That is not PIT-safe when the filing was accepted during session s: the opening trade has already occurred before the information became available. Classifying it as BMO could retroactively cancel a trade using information that arrived later that day.

Replace the session rule with this

The event time is the earliest independently verified public earnings-release timestamp. When no reliable release timestamp is available, the EDGAR acceptance timestamp is used as a conservative availability proxy.

If the event or filing is available before the regular-session open on session s, prohibited execution opens are s and s+1.

If it becomes available during the session or after the close on s, prohibited execution opens are s+1 and s+2.

No execution that occurred before the recorded availability timestamp is retroactively cancelled.

Also store:

event_time_basis =
    verified_release_timestamp
    | edgar_acceptance_proxy

Do not label acceptance-time classifications as true BMO or AMC unless the actual earnings-release time has been verified.

Why the pilot’s 100% match is not enough

The 100% match between Sharadar event-code-22 dates and EDGAR Item 2.02 anchors within ±1 day is excellent evidence of date coverage. It does not prove exact release timing or BMO/AMC classification. Both records may refer to the same 8-K event rather than independently confirming when the market first received the earnings information.

Before freeze, manually compare a stratified sample against the attached earnings exhibit or another archived release timestamp. Report separately:

Correct earnings-event identification
Correct calendar date
Correct market-session classification
Percentage using EDGAR acceptance as a proxy

The pilot currently reports zero rejections and zero ambiguous timestamps, but it does not report the required manual validation error rate. V1 therefore remains pilot-validated, not fully re-verified.

2. Historical CIK crosswalk is the principal remaining blocker

The pilot correctly discovered that current company_tickers.json is insufficient:

Alphabet’s predecessor history is under a different CIK.
Delisted TWTR is unresolved.
Retired tickers such as FB are not independently recoverable from the current map.
Dual-class securities share an issuer CIK but require separate permanent security identities.

This is not a minor enrichment issue. It affects survivorship freedom and the historical availability of both earnings anchors and SIC classifications.

Freeze the crosswalk schema before continuing

Recommended fields:

permaticker
ticker
cik
effective_from
effective_to
relationship_type
source
source_record_id
confidence
mapping_rationale

Suggested relationship_type values:

direct
ticker_rename
share_class
predecessor_cik
successor_cik
spin_off
acquisition
manual_override
Register a deterministic source hierarchy

Use a frozen precedence order, for example:

Sharadar security metadata and secfilings identifier
EDGAR submissions and filing-header identity
Corporate-action/predecessor-successor evidence
Archived historical ticker mappings
Manually reviewed override table

Every manual override should include evidence, effective dates and reviewer approval. Unresolved periods must be excluded; they must not inherit the current issuer’s CIK automatically.

The full build should not begin until this crosswalk rule and source precedence are registered. Otherwise identity resolution could change after coverage results are observed.

3. Pilot success should not be described as V1/V2 closure

The pilot record is appropriately marked provisional, but v0.4 says that “no open items remain in this draft; v1.0 waits on §8a.” That is no longer accurate in light of the pilot.

Change it to:

No conceptual strategy-design items remain. Research-Design Freeze remains blocked by completion and acceptance of the historical identity crosswalk, full-universe V1/V2 builds, mapping-table countersign, required manual validation cases, coverage gates and §8a.

The strategy rules are closed. The data implementation is not.

4. Freeze coverage acceptance criteria before the full run

The documents require coverage reporting but do not define how much coverage is sufficient. Without thresholds, the owner could review the full results and then decide whether the coverage is “good enough.”

Register coverage gates before seeing the full-universe output.

A reasonable proposal for this large-cap universe is:

Area	Suggested pre-freeze minimum
CIK/permaticker resolution	≥99% of preliminary universe-months
Valid V1 earnings anchor	≥95% of universe-months after warm-up
Valid V2 PIT sector mapping	≥98% of universe-months
Any individual calendar year	V1 ≥90%; V2 ≥95%
Manually validated V1 precision	≥98%
Critical false-positive earnings anchors	0 in validation sample
Unexplained identity conflicts	0
Silent current-sector fallbacks	0

The exact percentages can differ, but they must be registered before the full results are inspected.

Freeze the start-date selection rule too

Do not select the research start date after seeing which years have favorable coverage.

Recommended rule:

The first eligible research month is the earliest month after all required warm-up history for which the registered V1 and V2 coverage thresholds are met for 12 consecutive months. The final date is the last complete month available in the pinned snapshots.

Then split the resulting eligible session sequence according to the frozen 50%/25%/25% method.

5. V2 pilot is promising, but validation remains incomplete

The effective-dated mappings for META, GOOGL, NFLX, VZ and AMT support the intended design. The issuer-level treatment for GOOG/GOOGL is also correct.

The following remain mandatory:

At least one genuine PIT SIC-change case
A resolved predecessor/successor CIK chain
A resolved delisted-security case
A resolved retired-ticker case
A spin-off with parent and child identity boundaries
Manual inspection of coarse SIC mapping rows
Owner review of all rows affecting the actual preliminary universe
Mapping-table recommendation

Add these fields if they are not already present:

mapping_confidence
mapping_specificity
review_status
reviewer
review_date
source_reference

For coarse SIC ranges, consider:

HIGH: direct and historically well-supported
MEDIUM: broad but economically coherent
LOW: ambiguous across multiple sectors

Low-confidence rows should be excluded in the primary construction or separately reported. They should not silently receive a forced sector ETF.

I cannot sign off on the 74-row mapping table from the validation record alone because the CSV itself is not included in the reviewed package.

6. Full-universe construction must avoid circularity

The pilot says the full build will use the top-250/150 monthly universe to derive the issuer list. That is correct only if this first universe is clearly a preliminary price-and-security-type universe, constructed before applying V1 and V2 eligibility.

Register this sequence:

SEP price/liquidity/type filters
→ preliminary monthly universe
→ union of all preliminary-universe permatickers
→ historical identity crosswalk
→ V1/V2 EDGAR builds
→ V1/V2 eligibility exclusions
→ final monthly eligible universe

This prevents missing-anchor or missing-sector exclusions from changing which issuers are crawled in the first place.

7. Full-run provenance controls

The pilot’s approximately eight-requests-per-second throughput is acceptable operationally, but the full build should be resumable and immutable.

Required artifacts:

Preliminary-universe permaticker manifest
Complete accession-request manifest
Cached raw EDGAR documents or content hashes
HTTP failures and retry log
Extraction-version hash
Crosswalk version and hash
Mapping-table version and hash
Per-security rejection and exclusion reasons
Checkpoint/resume state
Final row-count reconciliation

Do not regenerate individual filings from live EDGAR after the snapshot is pinned unless the entire affected snapshot is versioned again.

8. Specific document corrections
v0.4

Update:

In-session acceptance semantics as described above
Status statement to acknowledge remaining data-build blockers
V1 terminology to distinguish actual release timestamps from EDGAR acceptance proxies
Full-universe coverage acceptance gates
Deterministic research-start-date rule
Preliminary-universe construction sequence
Pilot validation record

Change:

“Item-2.02 ≡ earnings release — quantitatively confirmed”

to:

“Item 2.02 anchor dates show complete agreement with Sharadar code-22 dates in the pilot; exact earnings-event identification and market-session timing remain subject to independent manual validation.”

Also add explicit pilot verdicts:

Component	Recommended status
V1 extraction pipeline	✅ Technical pilot passed
V1 event identification	🟡 Preliminary validation passed
V1 exact session timing	🟡 Not yet validated
V2 SIC extraction pipeline	✅ Technical pilot passed
V2 effective-dated mapping	🟡 Pilot cases passed
Historical identity crosswalk	🔴 Unresolved
V2 genuine SIC-change case	🔴 Not yet exercised
Mapping-table approval	🟡 Pending owner countersign
Final recommendation

Proceed, but in this order:

Correct the V1 in-session timing rule.
Freeze the historical crosswalk schema and source precedence.
Freeze coverage thresholds and the deterministic start-date rule.
Resolve TWTR, FB and Google-to-Alphabet as mandatory identity tests.
Review and countersign the SIC mapping table.
Run the full preliminary-universe V1/V2 builds.
Complete independent V1 timing validation and a genuine SIC-change case.
Re-run V1/V2 verification.
Run the Data Availability Gate and populate §8a.
Present the completed v1.0 freeze candidate.

The pilot is a successful proof of implementation, but the historical identity layer and exact earnings-event timing still prevent Research-Design Freeze.