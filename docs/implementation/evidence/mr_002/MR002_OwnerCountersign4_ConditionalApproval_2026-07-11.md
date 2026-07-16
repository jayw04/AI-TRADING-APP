Review decision

The package confirms the major corrections:

The universe is now correctly limited to January 2013–July 2026, with 163 months and 40,750 universe-months.
XLC and XLRE taxonomy dates are separated from ETF availability.
Provisional planning coverage reaches 99.38%, above the frozen 98% threshold.
The uploaded mapping and override file hashes match those recorded in the review package.

However, direct inspection of sic_sector_etf_mapping_v0.6.csv and security_sector_overrides_v0.4.csv found a final targeted correction set. I recommend conditional approval, not final countersign yet.

1. SIC 3812 must not remain HIGH → XLI

The mapping currently contains:

3812 → Industrials / XLI
confidence = HIGH

The rationale describes defense electronics such as NOC, RTN and LHX, but SIC 3812 is not sector-coherent. It also captures companies whose economic classifications differ.

Recommended correction:

3812 → LOW / excluded by default

Then use security-level overrides for verified names:

NOC / RTN / LHX → Industrials / XLI
GRMN            → Consumer Discretionary / XLY

Review every other preliminary-universe security carrying SIC 3812 before adding an override. A generic HIGH mapping would reintroduce the same problem that security overrides were designed to solve.

2. SIC 4800–4899 is too broad before October 2018

The current mapping applies:

4800–4899
through 2018-09-28 → Information Technology / XLK
from 2018-10-01    → Communication Services / XLC

The pre-2018 range combines traditional telecommunications with cable, broadcasting and media businesses. Those did not all belong to Technology.

At minimum, split it:

4810–4829:
    historical telecommunications treatment

4830–4849:
    through 2018-09-28 → Consumer Discretionary / XLY
    from 2018-10-01    → Communication Services / XLC

4850–4899:
    MEDIUM or LOW pending affected-security review

This is a semantic classification issue, not merely a confidence-label issue.

3. Add a BKNG security override

The PIT SIC validation correctly shows BKNG changing:

7389 → 4700

But generic SIC 4700 currently maps to Industrials. That would produce an economically incorrect sector assignment for Booking Holdings.

Add:

BKNG → Consumer Discretionary / XLY

for its complete independently verified research interval.

4. Review the UBER validation result

The genuine SIC-change test currently produces:

7372 → 7389
XLK  → XLI

That proves the pipeline preserves old and new SIC segments correctly. It does not prove Uber’s economic classification actually changed.

Verify UBER’s historical sector classification from its first eligible date. If it was Industrials throughout its public history, add a security override and retain the SIC transition only as provenance—not as a sector transition.

5. Populate permanent identifiers in the override table

Of the 27 override rows:

META, GOOGL and GOOG include permaticker and CIK.
The remaining 24 rows have both fields blank.

That conflicts with the established identity-control model. Ticker alone is not a sufficiently stable historical key.

Before freezing, populate:

permaticker
ticker
CIK, where available
effective_from
effective_to

The resolver should use:

(permaticker, date) → sector

Ticker should be descriptive metadata or a preliminary lookup only.

This is especially important for:

TWTR
TT
Renamed securities
Delisted securities
Any symbol that could be reused
6. Close the archived-history flags

Several override rationales still explicitly say historical verification is pending:

SHW
WMT
COST
DHR
TMO

Those rows currently begin on January 1, 2013, but the file itself says that date remains subject to an archived-history check.

Before final approval, either:

Attach evidence supporting the sector assignment from the research start date; or
Move effective_from to the earliest independently verified date.

TT also says its pre-2020 predecessor treatment may be extended after an archived check. Leave the current 2020 start unless that evidence is completed.

7. Reviewer metadata remains incomplete

Direct inspection shows:

All 106 mapping rows still have review_status = pending.
All 27 override rows still have review_status = pending.
Reviewer and review-date fields are blank.

After corrections, use:

HIGH accepted    → approved_high
MEDIUM accepted  → approved_medium
LOW excluded     → excluded_low
Unresolved       → needs_revision

Each row should carry:

reviewer = Jay Wang
review_date = 2026-07-11

or the actual countersign date if finalized later.

8. Keep the 0.62% exclusions

I approve leaving the remaining genuinely ambiguous names excluded, including the reported ROP, TTD and smaller residuals. The mapping does not need to force 100% coverage.

The current result should be described as:

99.38% provisional planning coverage under current-SIC approximation.

The final V2 gate must still be recomputed after the EDGAR PIT-SIC crawl. The preliminary impact report was intentionally based on current TICKERS SIC for coverage planning, not final research construction.

Final disposition
Item	Decision
Corrected universe dates	Approved
XLC/XLRE taxonomy dates	Approved
98% threshold governance	Approved
0.62% deliberate exclusions	Approved
Mapping v0.6	Conditional approval
Overrides v0.4	Conditional approval
Final hashes	Hold
Full V1/V2 crawl	Hold
Research-Design Freeze	Not yet eligible
Required final sequence
Downgrade generic SIC 3812 and add verified security overrides.
Split the pre-2018 4800-series mapping.
Add BKNG.
verify UBER’s historical classification.
Populate permaticker and CIK throughout the override table.
Close the SHW/WMT/COST/DHR/TMO evidence flags.
Complete review statuses, reviewer and review date.
Rerun the validator and provisional impact calculation.
Generate final artifact and canonical hashes.
Release the full PIT V1/V2 crawl.

After those targeted corrections, the mapping package should be ready for final countersign and crawl authorization.