One terminology recommendation

Use these fields separately:

event_time
event_time_basis
availability_class
cooling_start_session
cooling_end_session

Do not overload availability_class as an assertion about when the company actually released earnings.

Suggested allowed values:

event_time_basis:
  VERIFIED_RELEASE_TIMESTAMP
  EDGAR_ACCEPTANCE_PROXY
  DATE_ONLY_PROXY

availability_class:
  PRE_OPEN
  IN_SESSION
  POST_CLOSE
  DATE_ONLY
2. v0.5 governance additions — approved

The following are exactly the controls needed before the full build:

Strategy rules closed; data implementation still open
Frozen crosswalk schema and source precedence
Mandatory TWTR, FB, Google→Alphabet, share-class and spin-off identity cases
Coverage gates registered before observing full coverage
Deterministic 12-consecutive-month start-date rule
Preliminary-universe-first sequence
Immutable provenance and no silent live regeneration after snapshot pinning
Explicit pilot component verdicts

These additions correctly prevent coverage results from influencing the research window or identity-resolution rules after the fact.

3. Historical identity crosswalk — approved to implement

Proceed with the crosswalk build, but freeze these additional invariants in code and tests.

Identity interval integrity

For each permaticker:

Effective intervals must not overlap.
Each trading date may resolve to no more than one CIK.
Gaps are allowed only when explicitly unresolved.
A successor CIK must not be applied before its legal effective date.
Ticker renames must not create duplicate issuer histories.
Share classes may resolve to the same CIK but remain separate securities.
Source precedence

The selected source should be stored on every interval, not only documented globally:

resolution_source
source_record_id
relationship_type
confidence
review_status

A lower-precedence source must never overwrite a higher-precedence interval silently.

Required test outcomes

Before the full crawl begins:

Test	Required result
Google → Alphabet	Two effective CIK intervals with no overlap or history loss
FB → META	Continuous issuer history across ticker rename
TWTR	Historical CIK resolved despite current-map disappearance
GOOG/GOOGL	Same issuer history, separate permatickers
Spin-off	Parent history not inherited by child before separation
Acquisition	No successor history backfilled into predecessor dates
Unresolved identity	Explicit exclusion, never current-map fallback

The earlier pilot showed exactly why current company_tickers.json is insufficient: it could not resolve TWTR and could not represent the pre-2015 Google CIK chain.

4. Mapping-table policy — method approved, content countersign pending

The changes to mapping v0.2 are good:

Confidence
Specificity
Review status
Reviewer metadata
LOW rows excluded from primary construction
Separate reporting instead of forced assignment

However, I cannot countersign the actual mapping content because sic_sector_etf_mapping_v0.2.csv is not present in the uploaded files or File Library results available to me. The latest accessible validation record still references v0.1 as a draft.

Important row-count reconciliation

The previous record described 74 rows. Your new counts are:

27 HIGH + 41 MEDIUM + 7 LOW = 75 rows

That may be a legitimate new row, but the mapping review should document:

Which row was added
Why it was added
Whether it changes historical eligibility
Whether any existing range was split
Whether any effective-date boundary changed

This reconciliation should appear in the mapping changelog before hashing.

Required automated mapping checks

Run these before owner countersign:

No overlapping SIC ranges for the same effective-date interval.
No overlapping effective periods for the same SIC range.
Every included row maps to exactly one ETF.
LOW-confidence rows produce EXCLUDED_LOW_CONFIDENCE, not a null silently.
XLC transition date is applied consistently.
XLRE transition date is applied consistently.
No ETF is used before its registered proxy-inception date.
Every MEDIUM row contains a specific rationale—not merely “best fit.”
Every coarse range reports the preliminary-universe securities it affects.
Hash is generated only after sorting by a frozen canonical key.

Recommended canonical hash ordering:

sic_start,
sic_end,
effective_from,
effective_to,
research_sector,
sector_etf
5. MEDIUM-confidence mappings need an impact review

Forty-one of 75 rows are MEDIUM confidence, more than half the table. That is not automatically a problem, but it means the confidence label alone is not enough.

Before countersign, produce:

Number of preliminary-universe securities affected by HIGH, MEDIUM and LOW rows
Percentage of universe-months mapped through each confidence tier
Top 20 securities by exposure to MEDIUM mappings
Any MEDIUM mapping that changes ETF at XLC or XLRE boundaries
Any MEDIUM row spanning industries plausibly belonging to multiple sectors

The key question is not how many mapping rows are MEDIUM; it is how much of the investable history depends on them.

I recommend:

HIGH and reviewed MEDIUM: eligible for primary construction
LOW: excluded
Unreviewed MEDIUM: excluded until reviewed
Diagnostic: rerun sector-coverage reporting with MEDIUM rows removed, without running strategy signals

This remains a data-coverage diagnostic, not a strategy sensitivity.

6. Coverage gates — approved, with denominator discipline

The frozen coverage gates are appropriate, but ensure all percentages use the same predeclared denominator:

Preliminary price/liquidity/type-qualified universe-months before V1 or V2 exclusion.

Do not calculate V1 coverage only among names already resolved by V2, or vice versa. That would hide crosswalk and mapping failures.

Report:

preliminary_universe_months
identity_resolved_months
v1_anchor_eligible_months
v2_sector_eligible_months
joint_v1_v2_eligible_months
final_eligible_months

Also report exclusions by reason without double-counting:

Identity unresolved
No prior earnings anchor
Earnings blackout
SIC unavailable
Mapping unavailable
LOW-confidence mapping
Sector ETF not yet live
7. Deterministic start-date rule — approved

The 12-consecutive-month rule is strong. Add one clarification:

Once the earliest qualifying 12-month sequence determines the start month, later temporary coverage deterioration does not move the research start date. Later months remain in the sample, with affected names excluded under the frozen eligibility rules, unless a registered annual minimum-coverage gate fails and forces the entire Data Availability Gate to stop.

Otherwise, the system might search for a later, cleaner interval after seeing the full history.

8. Provenance controls — approved

The no-regeneration rule is important. Also store:

EDGAR response body hash
Request URL or accession identifier
Retrieval timestamp
HTTP status
Parser version
Extraction result hash
Rejection reason
Retry count
Whether the record came from cached or newly retrieved content

After pinning, a missing or corrupt filing should fail the build rather than trigger an unrecorded live refetch.

9. Updated pilot verdict

Based on your stated corrections, I would now classify the pilot as:

Component	Verdict
V1 extraction pipeline	✅ Technical pilot passed
V1 date/event identification	🟡 Strong preliminary validation
V1 availability semantics	✅ PIT rule corrected
V1 independently verified release timing	🟡 Still sample-validation dependent
V2 SIC extraction	✅ Technical pilot passed
V2 effective-date transitions	✅ Pilot cases passed
Historical identity crosswalk	🟡 Specification frozen; implementation pending
Genuine SIC-change case	🔴 Still required
Mapping methodology	✅ Approved
Mapping content	🟡 Pending CSV countersign
Full-universe coverage	🔴 Not yet run
Research-Design Freeze	🔴 Not yet eligible
Final recommendation

Proceed now with:

Implement the historical identity crosswalk.
Pass all mandatory identity tests.
Reconcile the mapping-table 74-versus-75-row change.
Complete the owner review of every HIGH and MEDIUM mapping.
Exercise at least one genuine SIC-change case.
Freeze and hash the crosswalk and mapping table.
Construct the preliminary universe.
Run the full V1/V2 builds and coverage gate.
Populate §8a.
Present the completed v1.0 freeze candidate.

Go decision: start the historical identity-crosswalk work.

Hold decision: do not start the full-universe crawl until the crosswalk tests pass and the actual mapping CSV is countersigned.