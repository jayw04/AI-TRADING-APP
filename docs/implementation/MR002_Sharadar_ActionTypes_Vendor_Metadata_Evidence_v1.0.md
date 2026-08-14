# MR-002 — Sharadar `actiontypes` Vendor Metadata Evidence v1.0

Read-only evidence collection for the frozen `relation` / `spinoff` adjudication questions
(prospective frame committed at `06985e1`; attempt recorded INCOMPLETE at `f508403`).
This document records vendor metadata **only**. It makes no classification, changes no code,
and both labels remain `KNOWN_UNADJUDICATED`. Owner adjudication is the next step.

---

## A. Retrieval identity

```text
retrieved_at_utc:         2026-08-14T21:15:26Z (four requests, 26.03s–26.99s within that second)
source:                   Sharadar official descriptions API
endpoint:                 https://api.sharadar.com/v1.0/data/descriptions
query filters:            tablename=actiontypes [&indicator=<label>] &format=json
authentication:           API key used (api_key query parameter), value not recorded anywhere
transport:                HTTPS, truststore-injected system trust (ADR 0017 pattern)
scope:                    actiontypes metadata only
validation_data_accessed: false
oos_accessed:             false
implementation_changed:   false
```

Raw responses preserved byte-exact alongside this report:

| File | HTTP | SHA-256 | Bytes | Rows |
|---|---|---|---|---|
| `evidence/sharadar_actiontypes/relation.json` | 200 | `f97be8cba6113c719c25422b41eadc765122462d748ae25a810fce61b332eb2d` | 450 | 1 |
| `evidence/sharadar_actiontypes/spinoff.json` | 200 | `0b6a8bbd75600aa4561cfadccb85efee2c14009a9b57aba76cbec29596aad531` | 592 | 1 |
| `evidence/sharadar_actiontypes/spinoffdividend.json` | 200 | `93debb3a8699246e5a8d2415b4351882e2ed1397c7acbb9a047af21221e4ad42` | 612 | 1 |
| `evidence/sharadar_actiontypes/actiontypes_full.json` | 200 | `70c4379471b1366e6e8e9ca2a4eecd07e8a2f9242cf95ebeb012368acb2a123b` | 9,779 | 19 |

Retrieval details (sanitized request URLs, per-request UTC timestamps, auth variant) are in
`evidence/sharadar_actiontypes/retrieval_manifest.json`. Each targeted query returned
**exactly one** matching `actiontypes` record (`count: 1`) — no zero-row or ambiguous-multi-row
stop condition fired. The response schema matches the documented `descriptions` schema
(`docs/design/data/descriptions.sqlite.sql`, as-of 2026-08-02): `table, indicator, isfilter,
isprimarykey, title, description, unittype`.

---

## B. Raw vendor records (verbatim)

### `relation`

```json
{"count":1,"data":[{"table":"actiontypes","indicator":"relation","isfilter":"N","isprimarykey":"N","title":"Relation","description":"Description of action types in the [actions] table. Provides linkage between multiple securities issued by the same issuer. The ticker field represents what we consider to be the primary security from the issuer. The contraticker field represents the ticker that is related to the primary ticker.","unittype":"N/A"}]}
```

### `spinoff`

```json
{"count":1,"data":[{"table":"actiontypes","indicator":"spinoff","isfilter":"N","isprimarykey":"N","title":"Spinoff Ratio","description":"Description of action types in the [actions] table. Provides details of spinoff transactions.\tThe ticker field represents the parent company that has spunoff another company. The contraticker field represents the company that has been spunoff. The value field represents the number of shares of the spunoff company that are issued for each share of the parent company. The date field represents the date of the spinoff transaction.","unittype":"ratio"}]}
```

(The `\t` after "transactions." is a literal tab character present in the vendor payload.)

### `spinoffdividend`

```json
{"count":1,"data":[{"table":"actiontypes","indicator":"spinoffdividend","isfilter":"N","isprimarykey":"N","title":"Spinoff Dividend","description":"Description of action types in the [actions] table. Provides details of spinoff transactions. The ticker field represents the parent company that has spunoff another company. The contraticker field represents the company that has been spunoff. The value field represents the dollar value of shares of the spunoff company that are issued for each share of the parent company. The date field represents the date of the spinoff transaction.","unittype":"USD/share"}]}
```

---

## C. Complete vocabulary presence

The full `actiontypes` table contains **19** indicators:
`acquisitionby, acquisitionof, adrratiosplit, bankruptcyliquidation, delisted, dividend,
initiated, listed, mergerfrom, mergerto, regulatorydelisting, relation, spinoff,
spinoffdividend, split, spunofffrom, tickerchangefrom, tickerchangeto, voluntarydelisting`.

```text
relation             PRESENT   (exact spelling, single record)
spinoff              PRESENT   (exact spelling, single record)
spinoffdividend      PRESENT   (exact spelling, single record)
spunofffrom          PRESENT   (cross-check only)
tickerchangefrom     PRESENT   (cross-check only)
tickerchangeto       PRESENT   (cross-check only)
delisted             PRESENT   (cross-check only)
```

No alternate spellings of the targeted labels exist in the vocabulary; "not documented" cannot
be attributed to a filter or spelling error.

Contextual observation (recorded, **not** used to answer any frozen question): the
`tickerchangefrom`/`tickerchangeto` descriptions explicitly state composition semantics
("Must be viewed in conjunction with the tickerchangeto/tickerchangefrom action"). This shows
the vendor *does* document cross-action composition where it intends it. The absence of any
such statement on `relation`, `spinoff`, or `spinoffdividend` is a structural observation about
the metadata, not a semantic answer, and is not converted into one here.

---

## D. Frozen-question assessment (vendor metadata only)

| Label | Question | Status | Exact vendor support | Remaining ambiguity |
|---|---|---|---|---|
| relation | Q1 — meaning of `action="relation"` | ANSWERED | "Provides linkage between multiple securities issued by the same issuer." | Which security relationships qualify (share classes, units, ADR pairs, etc.) is not enumerated. |
| relation | Q2 — meaning of `ticker` / `contraticker` | ANSWERED | "The ticker field represents what we consider to be the primary security from the issuer. The contraticker field represents the ticker that is related to the primary ticker." | "Related" is not further specified. |
| relation | Q3 — economic/execution consequence (incl. explicit NONE) | PARTIALLY_ANSWERED | The record characterizes `relation` as a linkage between securities and defines no transaction, no `value` semantics (`unittype: "N/A"`), and no event mechanics. | Sharadar states **no explicit consequence and no explicit "NONE"**. Concluding inertness from the absence of value semantics is exactly the prohibited structural→semantic inference; a positive vendor statement is still required. |
| relation | Q4 — coexistence/composition with other actions | UNANSWERED | None. The record says nothing about co-occurrence with other action rows, nor what `date` represents for a linkage record. | Entire composition question open. |
| relation | Q5 — vendor evidence supporting classification | PARTIALLY_ANSWERED | A direct, official vendor definition now exists (record above, hashed). | The definition covers meaning and field roles but is silent on consequence (Q3) and composition (Q4), so it cannot yet fully support a classification. |
| relation | Q6 — condition requiring refusal rather than classification | UNANSWERED | None. The metadata contains no reliability, caveat, or edge-condition statement. | Entire question open. |
| spinoff | Q1 — meaning of `action="spinoff"` | ANSWERED | Title "Spinoff Ratio"; "Provides details of spinoff transactions." | — |
| spinoff | Q2 — meaning of `ticker` / `contraticker` | ANSWERED | "The ticker field represents the parent company that has spunoff another company. The contraticker field represents the company that has been spunoff." | — |
| spinoff | Q3 — economic/execution consequence; meaning of `value` | ANSWERED (economic limb) / PARTIALLY_ANSWERED (execution limb) | "The value field represents the number of shares of the spunoff company that are issued for each share of the parent company." `unittype: "ratio"`. `date` = "the date of the spinoff transaction". The economic consequence — a per-share distribution of child-company shares to parent holders — is explicitly stated by the vendor. | The metadata does **not** state how Sharadar's price/fundamental series treat the distribution (adjusted vs unadjusted), which the frozen execution consequence may hinge on. That lives outside `actiontypes` and was not retrieved here. |
| spinoff | Q4 — coexistence/composition; relationship to `spinoffdividend` | PARTIALLY_ANSWERED | The vendor documents `spinoffdividend` as a distinct action with distinct `value` semantics: "the dollar value of shares of the spunoff company that are issued for each share of the parent company", `unittype: "USD/share"` — vs `spinoff`'s share-count ratio. | Whether `spinoff` and `spinoffdividend` are alternative representations of one event or can co-occur for the same ticker/date — and whether either composes with `spunofffrom` on the child — is not stated. |
| spinoff | Q5 — vendor evidence supporting classification | ANSWERED | The record above: official definition of meaning, all four fields (`ticker`, `contraticker`, `value`, `date`), and unit type. | Composition (Q4) and price-series treatment remain outside this record. |
| spinoff | Q6 — condition requiring refusal rather than classification | UNANSWERED | None. No reliability/caveat statement in the metadata. | Entire question open. |

Note on prior prohibited inference: the earlier hypothesis "spinoff `value` is a share ratio"
was not permitted as an inference; it is now **explicitly confirmed by the vendor** in the
`spinoff` record (`value` = shares of child per parent share; `unittype: "ratio"`).

`spinoffdividend` (retrieved as a targeted record per the task):

```text
metadata found: YES (single record)
title:          Spinoff Dividend
description:    value = dollar value of spunoff-company shares issued per parent share;
                ticker = parent, contraticker = spunoff company, date = spinoff date
unittype:       USD/share
```

---

## E. Conclusion

```text
INCOMPLETE_VENDOR_METADATA
```

The vendor metadata fully resolves the *identity* questions (what the actions are, what the
fields mean, what `spinoff.value` is), but at least one load-bearing question per label remains
open on vendor evidence alone:

- `relation`: no explicit statement of economic/execution consequence (not even an explicit
  "NONE"), no composition semantics, no meaning for `date`, no reliability caveats (Q3/Q4/Q6).
- `spinoff`: no composition rule versus `spinoffdividend`/`spunofffrom`, no statement of how
  price series treat the distribution, no reliability caveats (Q4/Q6, execution limb of Q3).

### Exact questions for `connect@sharadar.com`

1. For `action="relation"` rows in the ACTIONS table: does a `relation` row represent any
   economic event or transaction, or is it purely an informational linkage with no economic or
   price consequence? Please state explicitly if the consequence is "none".
2. For `relation`: what does the `date` field represent, and is the `value` field ever
   populated? If so, what does it mean?
3. What kinds of security relationships does `relation` cover (e.g., multiple share classes,
   units/warrants, ADR vs ordinary lines)?
4. Can `relation` rows co-occur with other action rows for the same ticker and date, and if so,
   how should they be read together?
5. For a single spinoff event, are `spinoff` and `spinoffdividend` mutually exclusive
   representations or can both be emitted? How do they relate to a `spunofffrom` row on the
   spun-off company?
6. Are SEP/SFP price series adjusted for `spinoff` / `spinoffdividend` distributions (and if
   so, via which adjustment mechanism)?

### Task-boundary attestation

```text
code changed:             NO
classifier changed:       NO
gate/threshold changed:   NO
relation classification:  KNOWN_UNADJUDICATED (unchanged)
spinoff classification:   KNOWN_UNADJUDICATED (unchanged)
validation read:          NO
OOS read:                 NO
fifth opening requested:  NO
```
