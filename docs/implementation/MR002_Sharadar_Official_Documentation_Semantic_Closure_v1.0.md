# MR-002 — Sharadar Official Documentation Semantic Closure v1.0

**Task type:** read-only evidence retrieval.
**Implementation changed:** NO. **Gate changed:** NO. **Validation read:** NO. **OOS read:** NO.
**Host started:** NO. **Fifth opening requested:** NO.

`relation` and `spinoff` remain **KNOWN_UNADJUDICATED**. Nothing in this document is a
classification; every entry is source evidence for a separate owner adjudication.

---

## A. Sources queried

All retrieval used the official Sharadar descriptions API with the authorized key. The key was never
printed and appears in no tracked file; every recorded request is sanitized to `api_key=<REDACTED>`.

| Source | Endpoint / table | Retrieved (UTC) | SHA-256 | Status |
|---|---|---|---|---|
| Sharadar descriptions API | `tablename=actiontypes&indicator=relation` | 2026-08-14T21:15:26Z | `f97be8cb…` | 200 |
| Sharadar descriptions API | `tablename=actiontypes&indicator=spinoff` | 2026-08-14T21:15:26Z | `0b6a8bbd…` | 200 |
| Sharadar descriptions API | `tablename=actiontypes&indicator=spinoffdividend` | 2026-08-14T21:15:26Z | `93debb3a…` | 200 |
| Sharadar descriptions API | `tablename=actiontypes` (full, 19 rows) | 2026-08-14T21:15:26Z | `70c43794…` | 200 |
| Sharadar descriptions API | `tablename=actiontypes&indicator=spunofffrom` | this session | see `official_sweep_manifest.json` | 200 |
| Sharadar descriptions API | `tablename=actions` (field-level, 7 rows) | this session | see `official_sweep_manifest.json` | 200 |
| Sharadar descriptions API | **unfiltered** (359 rows, 16 tables) | this session | `descriptions_full.json` | 200 |

Raw JSON preserved under `docs/implementation/evidence/sharadar_actiontypes/`.

**Zero-row results verified, not assumed.** `tablename=SEP` and `tablename=SFP` each returned
`count=0`. Per the frame, that was not treated as "no rule exists" until the spelling was checked:
the unfiltered retrieval shows the descriptions endpoint exposes 16 tables, and the price tables are
named **`stocks`** and **`funds`**, not `SEP`/`SFP`. Those tables *are* documented, and were read.

**Third-party material:** none used as authority. The earlier search-snippet paraphrase of `relation`
is now superseded by the vendor's own wording and is discarded rather than relied upon.

---

## B. Remaining-question matrix

### `relation`

| Question | Status | Official source | Exact support | Remaining ambiguity |
|---|---|---|---|---|
| **Q1** meaning | **ANSWERED** | `actiontypes.relation` | "Provides linkage between multiple securities issued by the same issuer." | — |
| **Q2** ticker / contraticker | **ANSWERED** | `actiontypes.relation` | "The ticker field represents what we consider to be the primary security from the issuer. The contraticker field represents the ticker that is related to the primary ticker." | — |
| **R-Q3** economic / price / identity / execution consequence | **PARTIALLY_ANSWERED** | `stocks.*`, `actiontypes.relation` | Price adjustment bases are exhaustively listed as stock splits, stock dividends, cash dividends and spinoffs. `relation` is not among them. | No **price** consequence is documented. The vendor makes **no statement at all** about identity/lineage or execution consequence, and never says the consequence is "none". |
| **R-Q4** coexistence / composition | **UNANSWERED** | — | The vendor documents conjunction explicitly where it applies ("Must be viewed in conjunction with…", ticker changes only). No such statement for `relation`. | Absence of a conjunction statement is not a statement of independence. |
| **Q5** source evidence | **ANSWERED** | as above | — | — |
| **R-Q6** refusal condition | **UNANSWERED** | — | — | Not a vendor question in itself, but it cannot be settled while R-Q3/R-Q4 are open. |
| `relation.date` meaning | **PARTIALLY_ANSWERED** | `actions.date` | "The date of the corporate action." | Every other action type defines its own date semantics; `relation` alone does not. For a linkage with no transaction, "the date of the corporate action" is ambiguous. |
| `relation.value` ever populated | **PARTIALLY_ANSWERED** | `actiontypes.relation`, `actions.value` | `unittype: N/A`; `actions.value` defers to ACTIONTYPES, which defines no value for `relation`. | No explicit statement that it is *never* populated. |
| relationship classes represented | **UNANSWERED** | — | — | "multiple securities issued by the same issuer" is given without enumeration — share classes, ADR/ordinary, units/warrants are neither confirmed nor excluded. |

### `spinoff` / `spinoffdividend` / `spunofffrom`

| Question | Status | Official source | Exact support | Remaining ambiguity |
|---|---|---|---|---|
| **Q1/Q2** meaning, roles | **ANSWERED** | `actiontypes.spinoff` | ticker = "the parent company that has spunoff another company"; contraticker = "the company that has been spunoff"; value = "the number of shares of the spunoff company that are issued for each share of the parent company"; date = "the date of the spinoff transaction"; `unittype: ratio`. | — |
| `spinoffdividend` | **ANSWERED** | `actiontypes.spinoffdividend` | Same ticker/contraticker/date roles; value = "the dollar value of shares of the spunoff company that are issued for each share of the parent company"; `unittype: USD/share`. | — |
| `spunofffrom` | **ANSWERED** | `actiontypes.spunofffrom` | The child-side mirror: ticker = "the company that has been spunoff from the parent company"; contraticker = "the parent company"; same ratio value and date. | — |
| **S-Q3** price-series treatment | **ANSWERED** | `stocks.*` and `funds.*` | `open`, `close`, `high`, `low`, `volume`: "adjusted for stock splits and stock dividends. **Not adjusted for cash dividends or spinoffs.**" `closeadj`: "adjusted for stock splits; stock dividends; cash dividends **and spinoffs**." `closeunadj`: adjusted for none. Identical wording for SFP (`funds`). | — |
| **S-Q4** can both be emitted for one event / how read together | **PARTIALLY_ANSWERED** | `actiontypes.*` | Both records describe "spinoff transactions" with identical ticker/contraticker/date semantics, differing only in `unittype` (ratio vs USD/share). | The vendor **never states** that they are complementary, alternative, or independent, and issues no "viewed in conjunction" instruction as it does for ticker changes. Concluding complementarity from co-occurrence is expressly forbidden by the frame. |
| **S-Q6** refusal condition | **UNANSWERED** | — | — | Depends on S-Q4. |

---

## C. Material incidental finding — the full vendor vocabulary is now known

`tablename=actiontypes` returns **19** labels. Recorded because it bears directly on whether any
future opening can clear the `UNKNOWN_VOCABULARY` gate. **No classification is changed here.**

```
acquisitionby   acquisitionof   adrratiosplit   bankruptcyliquidation   delisted
dividend        initiated       listed          mergerfrom              mergerto
regulatorydelisting             relation        spinoff                 spinoffdividend
split           spunofffrom     tickerchangefrom                        tickerchangeto
voluntarydelisting
```

Comparing against the registered roster in `SemanticReconciliationMatrix_v1.1`:

* **Vendor labels absent from the roster entirely** — `adrratiosplit`, `initiated`,
  `regulatorydelisting`, `voluntarydelisting`. Any of these reaching a candidate's t+1 session would
  classify as `UNKNOWN_VOCABULARY` and breach that gate at incidence 1.
* **Roster labels that are not vendor labels** — `bankruptcy` (vendor: `bankruptcyliquidation`),
  `regulatorychange` (vendor: `regulatorydelisting`), and the specification-only
  `merger`, `cash_only_acquisition`, `stock_and_cash_acquisition`.

This confirms the root cause recorded in `ActionsVocabularyCensus_v1.0` from the other direction: the
economic set was assembled from specification vocabulary and never reconciled against the feed. The
reconciliation is now *possible* for the first time. Performing it is a separate authorized step and
is **not** performed here.

---

## D. Final retrieval disposition

```
SUPPORT_ESCALATION_REQUIRED
```

Official sources closed **S-Q3 outright** and confirmed Q1/Q2 for all four labels. They did not close
the composition and consequence questions, which are the load-bearing ones.

### QUESTIONS_REQUIRING_SHARADAR_SUPPORT

1. Does `relation` represent any economic event, transaction, price adjustment, or identity/lineage
   change, or is it purely informational? Please state explicitly if the consequence is none.
2. What does `relation.date` represent, and can `relation.value` ever be populated?
3. What categories of security relationship are represented by `relation`?
4. Can `relation` coexist with other ACTIONS records for the same ticker/date, and how should they be
   interpreted together?
5. For a single spinoff event, can `spinoff` and `spinoffdividend` both be emitted? How do they relate
   to each other and to `spunofffrom` on the child?

Question 6 of the prepared inquiry — SEP/SFP adjustment treatment — is **withdrawn as answered** by
`stocks.closeadj` / `funds.closeadj` and need not be asked.

---

## E. Governance state (unchanged)

```
openings spent:                 4
verdict:                        NONE
admissible validation evidence: none
gate:                           unchanged
relation:                       KNOWN_UNADJUDICATED
spinoff:                        KNOWN_UNADJUDICATED
host:                           stopped (termination protection enabled)
fifth opening:                  NOT REQUESTED / NOT AUTHORIZED
```
