# WBS-DISPOSITION — gate 0 of the factor-store publication halt

**Status:** 0A RESOLVED (evidence-based, contradicts the provisional ruling) · 0B RESOLVED-IN-PACKAGE, pending owner confirmation
**Date:** 2026-08-28 · **Method:** read-only investigation over SSM. No change to WBS, the universe, the provider path, the stores, or any service.
**Relates to:** `docs/incidents/2026-08-27-factor-store-publication-halt-RED.md` · ADR 0056 · PR #698 (`dd873bbb`)

---

## 0A — Classification

**`WBS` is `PROVIDER_EXHAUSTED`. It ceased trading. It is NOT a provider coverage regression.**

The provisional ruling — *"primary provider history has stopped/regressed while an alternate source
demonstrates WBS is still a current, economically existing security"* — was correct in form but its
premise is false. The alternate source does **not** show WBS current. Both sources stop on the same day,
and the store's own corporate-actions table says why.

Observed facts, all read from live production state:

| Fact | Value | Source |
|---|---|---|
| Instrument | WEBSTER FINANCIAL CORP, NYSE, Domestic Common Stock Primary Class | live store `tickers` |
| `isdelisted` | **True** | live store `tickers` |
| `lastpricedate` / `lastupdated` | **2026-08-19** / 2026-08-19 | live store `tickers` |
| Final SEP row | **2026-08-19**, close 77.57, volume **91,317,000** (~10× the prior-week average — a terminal print) | live store `sep` |
| Corporate action 2026-08-19 | **`delisted`**, value 12568.9 | live store `actions` |
| Corporate action 2026-08-19 | **`acquisitionby`**, contraticker **`SAN`** (Banco Santander), value 12568.9 | live store `actions` |
| Corporate action 2026-08-19 | `relation` → `WBS-PG`, `WBS-PF` (preferred series) | live store `actions` |
| **Alpaca (alternate source) last bar** | **2026-08-19** — 27 bars in 45d, then nothing | live read-only probe, 2026-08-28T10:30Z |
| Alpaca control `AAPL` | **2026-08-27** (current) — the probe path is healthy | same probe |
| Alpaca acquirer `SAN` | **2026-08-27** (current) — the surviving entity trades | same probe |
| Held qty / open orders / ever-ordered | **0 / 0 / 0** | app DB, read-only |
| Registered in any strategy | **none** | app DB, read-only |

Webster Financial was acquired by Banco Santander and delisted effective 2026-08-19. Sharadar stopped
because the instrument stopped. This is the `EA` shape, not a coverage question.

**Why the refresh could not say so.** The verifier returned `FAILED_OR_UNEXPLAINED` with
*"no exhaustion evidence supplied"* — there is **no record for WBS in the artifact at all**. The artifact
was hand-built on 2026-08-11 and holds 11 records; WBS went stale on 08-19. Running the shared rule
(`diagnose_unexplained`) against the real artifact returns **`EVIDENCE_ABSENT`** — *not*
`EVIDENCE_PRESENT_REFUSED`.

**⚠ This reverses a claim carried in PR #698, ADR 0056 and the 08-27 incident record.** Each hedges
correctly — *"**if** WBS is that shape in production"* — but the operator-facing conclusion drawn from it
("regeneration was never a legitimate recovery path for a name of this shape") does not apply to WBS.
WBS is precisely the shape the PR's new writer fixes.

Verified by running `classify_stale_symbol` from the candidate branch against the observed values:

```
A) with a regenerated record -> PROVIDER_EXHAUSTED
   "ceased trading: provider last 2026-08-19, alpaca last 2026-08-19, control AAPL current to 2026-08-27"
B) today (no record)         -> FAILED_OR_UNEXPLAINED | "no exhaustion evidence supplied"
C) diagnose_unexplained      -> {'WBS': 'EVIDENCE_ABSENT'}
```

Every precondition the rule checks is satisfied on production values: frontier equality holds
(stage 08-19 == live 08-19, unlike the EA 08-17 failure), zero provider rows after the frontier, the
corroboration control is current, and the operational requirements (no holding, no open order, no
registration) are met. WBS becomes attributable, leaves the gating denominator, and stops blocking.

## 0B — Convergence path

**Mechanism: option 1 is not required; option 2 is not required; option 3 is not required.**
The general recovery mechanism already exists in the candidate package and needs no new policy:

> **Regenerate the evidence artifact with `scripts/factor_evidence.py` (PR #698), which supplies the
> missing writer.** The generator decides nothing — it records observations; the verifier re-derives
> every verdict from live facts. WBS then adjudicates `PROVIDER_EXHAUSTED` on its own merits.

This is a **general** mechanism, not a WBS exception: it writes a record for whatever name has gone
attributable-stale since the last generation, and the no-ticker-special-cases CI invariant
(`check_no_factor_symbol_special_cases.py`) forbids the alternative.

Source substitution (option 1) is **not** the answer here and should not be pursued for WBS: there is no
current data to substitute — the security no longer exists. Alpaca is authorized and proven sufficient
as a *lifecycle* signal, and precedent exists for Alpaca as a *price* input (the total-return adapter,
PORT-001 / ADR 0030 #2). Substituting it as a **factor** price source remains a PIT/methodology change
requiring an ADR, and no such change is needed to clear this gate.

Ad-hoc universe exclusion (option 2) is **not** required and should not be introduced. WBS leaves the
ranking pool on its own once its `lastpricedate` excludes it — exactly as `EA` did on 08-17.

## What this does NOT clear

* Regeneration must actually be **run on the box against the real store**, and its output adjudicated.
  It has never been executed in production (`factor_evidence.py` is **not yet deployed** — it ships with
  PR #698). Until then 0A is a classification, not a cleared gate.
* Gates 1–6 of the 08-27 closure record are untouched.
* The **2026-09-10 expiry cliff** is unaffected by this ruling: the other 11 records still share one
  observation timestamp. Regeneration clears WBS and the cliff in the same action.
* The live store is now **5 trading days stale** (frozen at SEP `2026-08-21`; store file dated 08-24).
  The 06:00 ET refresh has now aborted **four** consecutive mornings — 08-25, 08-26, 08-27 and **08-28**
  (the 08-27 incident record says three; 08-28 is new).

## Status after this record

| Item | Ruling |
|---|---|
| PR #698 | ENGINEERING GREEN / REVIEW READY — unchanged; no code defect found by this investigation |
| Factor store | **RED / publication blocked** — unchanged |
| Gate 0A | **RESOLVED — `WBS` = `PROVIDER_EXHAUSTED` (acquired by SAN, delisted 2026-08-19)** |
| Gate 0B | **Mechanism identified — regenerate via `scripts/factor_evidence.py`; no new governance needed.** Executes only after PR #698 is reviewed, merged and deployed. |
| MERGE / DEPLOY | still **not authorized** — owner's call, and an independent review of #698 is still outstanding |
