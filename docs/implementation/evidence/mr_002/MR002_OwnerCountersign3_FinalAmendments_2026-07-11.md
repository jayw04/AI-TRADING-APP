Final review status

The package is much stronger, and the three review-2 corrections are confirmed:

The preliminary universe is now correctly limited to January 2013–July 2026: 163 months and 40,750 universe-months.
XLC and XLRE classification boundaries are correctly separated from ETF availability.
The planning coverage calculation reaches 99.38% without changing the 98% threshold.

The uploaded CSV hashes also match the provisional hashes recorded in the review package.

However, I am not yet giving the final countersign. Direct inspection found three remaining semantic mapping problems and one identifier-control issue. These should be the final targeted correction set.

Approved
Taxonomy dates

Approve:

Communication Services:
effective 2018-10-01

Real Estate:
effective 2016-09-01

The GICS Communication Services change was implemented after the September 28, 2018 close, and the Real Estate sector became effective after the August 31, 2016 close.

Residual exclusions

Approve leaving these unresolved and excluded:

ROP
TTD
APP
FLUT
ROK
TER

A remaining exclusion rate of 0.62% is acceptable under a 98% coverage gate. There is no need to force ambiguous names into a sector merely to increase coverage.

Existing override groups

The following override designs are approved:

V/MA 2023 transition
DIS 2018 transition
SHW
WMT/COST
TGT/DG/DLTR 2023 transition
META/GOOG/GOOGL
DHR/TMO/TT
SNAP/TWTR/PINS/ZM

The actual archived-history flags discussed below still need to be closed before final status is assigned.

Remaining correction 1: SIC 3812 cannot be HIGH → XLI

Mapping v0.6 assigns:

3812 → Industrials / XLI, HIGH

That code is not sector-coherent.

Garmin files under SEC SIC 3812, but S&P classifies Garmin as Consumer Discretionary, and Garmin is held in XLY.

Therefore, the generic 3812 row cannot remain HIGH Industrials.

Required treatment

Change:

3812 → LOW / excluded by default

Then use verified security overrides for the exposed securities:

NOC / RTN / LHX → Industrials / XLI
GRMN            → Consumer Discretionary / XLY

Also list every other preliminary-universe security carrying SIC 3812 and verify it individually before adding an override. The generic code must not decide the sector.

Remaining correction 2: SIC 4800–4899 is overbroad before 2018

The current mapping assigns the full range:

4800–4899
pre-2018  → XLK
post-2018 → XLC

The post-2018 result is broadly reasonable. The pre-2018 result is not.

Comcast’s SIC is 4841, but Comcast was among the companies moving from Consumer Discretionary into Communication Services during the 2018 restructuring. S&P explicitly identifies Comcast as a Consumer Discretionary media company entering the new sector.

Required minimum split
4810–4829:
    telecom-specific historical treatment

4830–4849:
    through 2018-09-28 → Consumer Discretionary / XLY
    from 2018-10-01    → Communication Services / XLC

4850–4899:
    MEDIUM or LOW pending affected-security review

This should correctly handle cable, broadcasting and satellite businesses rather than treating them as historical Technology holdings.

Remaining correction 3: BKNG needs a security override

The V2 test correctly demonstrated a genuine SIC change for BKNG:

7389 → 4700

But the generic mapping sends SIC 4700 to Industrials. Booking Holdings is classified by S&P as Consumer Discretionary and is an XLY constituent.

Add:

BKNG → Consumer Discretionary / XLY

for its entire verified research history.

Also review UBER

The UBER validation currently produces:

7372 → 7389
XLK  → XLI

That proves the PIT SIC pipeline preserves a SIC change, but it does not prove that Uber’s economic sector actually changed. S&P classifies Uber as Industrials.

Verify Uber’s classification from its first eligible research date. If it was Industrials throughout its public history, add a security override rather than allowing the filing SIC change to create a false XLK-to-XLI sector transition.

Identifier-control issue: most security overrides are ticker-only

Direct inspection of security_sector_overrides_v0.4.csv found:

27 rows total
Only the META/GOOG/GOOGL rows contain a permaticker
24 rows have blank permaticker and CIK fields

That conflicts with the crosswalk’s core rule that historical joins are performed through stable permanent identities rather than ticker alone.

Before hashing, populate at least:

permaticker
ticker
CIK where available
effective_from
effective_to

The canonical override resolver should be:

(permaticker, date) → sector

Ticker should be descriptive metadata or an ingestion lookup, not the primary override key.

This is especially important for TWTR, TT and renamed or delisted securities.

Archived-history checks remain open

The CSV rationales still say historical verification is pending for:

SHW
WMT
COST
DHR
TMO

Those rows should not receive final approved_* status while their own rationale says the research-start boundary is awaiting independent archived evidence.

Either:

Attach the archived classification evidence and approve the row from January 2013; or
Start the override at the earliest independently verified date and leave earlier periods governed by the generic mapping or exclusion.
Important coverage-label correction

The 99.38% result is a successful planning-coverage result, not yet the final V2 gate result.

The preliminary impact calculation uses current TICKERS SIC as an explicitly labelled approximation. The registered V2 gate must be recalculated after the full EDGAR PIT-SIC crawl.

Recommended wording:

The frozen mapping and proposed security overrides achieve 99.38% provisional coverage on the preliminary universe under current-SIC planning data. Final V2 coverage remains subject to the full PIT-SIC crawl and must independently clear 98%.

This distinction does not prevent releasing the crawl once the mapping corrections are complete.

Countersign decision
Artifact	Decision
Crosswalk identity artifacts	Approved
Taxonomy dates	Approved
Mapping v0.6 structure	Conditionally approved
Security overrides v0.4	Conditionally approved
0.62% deliberate exclusions	Approved
Final hashes	Hold
Full V1/V2 crawl	Hold pending targeted corrections
Research-Design Freeze	Not yet eligible
Exact final amendment set
Downgrade generic SIC 3812 and add verified 3812 security overrides.
Split the pre-2018 4800-series media/cable codes.
Add the BKNG override.
Review UBER’s pre-SIC-change classification.
Populate permaticker/CIK fields for all security overrides.
Close the five archived-history flags.
Rerun the impact report and confirm provisional coverage remains at least 98%.
Populate reviewer/status/date fields and produce final artifact and canonical hashes.

After those corrections, I would authorize the full PIT V1/V2 crawl.