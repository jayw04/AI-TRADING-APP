# Governing factor corpus — countersignature v2.0

| Field | Value |
|---|---|
| Date | 2026-07-27 |
| Status | Countersigned — **governing** |
| Supersedes | corpus `022ffd01…` (countersigned 2026-06-30) |
| Reason for supersession | **Documented truncated-session defect**, not a routine refresh |
| Governs | forward-validation observation sessions (Workstream B), ADR 0047 witness boundary |
| Related | ADR 0047, ADR 0046, momentum-daily §8 drift-audit census, GITHUB-OPS-001 §6 |

## 1. Identity

| | SHA-256 | Bytes |
|---|---|---|
| **Superseded** | `022ffd01b52b04aacac1932448413d042f68d0bb37ddf4ccdec39292484a7831` | 1,634,217,984 |
| **Governing (this record)** | `2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87` | 1,772,630,016 |

The superseded file is **preserved unchanged**. Its hash was recomputed at countersignature time and
matches the value recorded on 2026-06-30 exactly, which establishes that no step of this correction
mutated it.

## 2. Historical correction

> **Historical correction:** 2026-06-15 was previously countersigned with an interrupted partial
> ingest of 3,428 rows versus 5,767 rows available for the governed universe.
>
> **Correction:** The session was re-ingested from the authoritative source using the original
> 14,150-ticker universe definition, then the corpus was extended forward using that same universe.
>
> **Universe change:** None.

### 2.1 Qualification to "Universe change: None"

The **ticker set** is unchanged: exactly 14,150, zero dropped, and the 569 instruments a full-market
pull would have admitted (preferred shares, warrants, SPAC units) were excluded at the universe gate.

The corrected session's **row membership** changed in both directions, and that is recorded here so
"Universe change: None" is not read as implying the repaired session is a pure superset:

- 2,339 ticker-days were **added** — rows the truncated ingest never wrote;
- **40 ticker-days were removed** — rows present in the superseded corpus that the authoritative
  source no longer reports for 2026-06-15 (`FTHAU`, `GCGRU`, `MTNE.U`, `PLUN.U`, `OTAI.U`, `KEYYU`,
  `NA` and similar, predominantly SPAC units). All 40 remain in the corpus on other dates.

An upsert could not have removed those 40; it converges rows the source *has* and cannot delete rows
it no longer has. The session was therefore replaced by `DELETE` + `INSERT` inside one transaction,
guarded on the inserted row count, which rolled back on the first attempt when the count disagreed.

## 3. Content

| Property | Value |
|---|---|
| SEP range | 1997-12-31 … **2026-07-24** |
| SEP sessions | 7,184 |
| SEP rows | 39,152,452 |
| Universe | **14,150 tickers, exact** |
| 2026-06-15 | **5,767 rows** (was 3,428) |
| Duplicate (ticker, date) | 0 |
| Pre-2026-06-15 content digest | `68ab5dd9ab3458e1ea1d75c37e22b7be` — **unchanged from the superseded corpus** |
| ACTIONS rows | 286,103 |
| ACTIONS range | 1997-12-31 … 2026-07-24 |
| ACTIONS authoritative | **true** (`declare_action_source`) |

Seam continuity across the repaired session: 5,777 / 5,748 / **5,767** / 5,766 / 5,765 / 5,766.

## 4. Artifacts

| Artifact | SHA-256 |
|---|---|
| `sep_governed_2026-06-15_2026-07-24.csv` (161,156 rows) | `012a4952b59e073c33cea72f590b20cbdc2a44eb41a7ebbdd679453c87e1906f` |
| `actions_governed_thru_2026-07-24.csv` (286,103 rows) | `e0be03f9c71b23278bfcf3dce664a7f1cfc6e2a7b38d2689b417620e9d6cadd1` |
| `actions_manifest.json` | `52839d3abda54f6dbf5326ec75636b88546c2966255e28f3dba8457a589f9cf8` |

Artifacts and the corpus itself are held in controlled storage and referenced here by hash, per
GITHUB-OPS-001 §6. They are not committed.

ACTIONS ingest receipt: `run_id 4608908ee92f198ecc122e625c7b4c5e`, 286,103 rows declared and 286,103
persisted, coverage 1997-12-31 … 2026-07-24, via the governed
`FactorDataStore.ingest_actions_from_artifact` path.

## 5. Exclusions, recorded rather than filtered

**Future-dated corporate actions — 4 rows, effective 2026-07-27, beyond the governed cutoff.**
Admitting them would let a point-in-time consumer see an action dated after the session it evaluates.

| Date | Action | Ticker | Name | Value |
|---|---|---|---|---|
| 2026-07-27 | split | `ZNB` | ZETA NETWORK GROUP | 0.125 |
| 2026-07-27 | split | `VYNE` | VYNE THERAPEUTICS INC | 0.02 |
| 2026-07-27 | split | `STKH` | STEAKHOLDER FOODS LTD | 0.33333 |
| 2026-07-27 | split | `SGLY` | SINGULARITY FUTURE TECHNOLOGY LTD | 0.07143 |

**Outside the governed universe — 385,133 ACTIONS rows and 15,006 SEP rows.** Tickers not in the
14,150-ticker set the corpus is bound to.

**Dropped column — `contraname`.** Not part of the store's ACTIONS schema (`_ACTIONS_COLS` is six
columns); dropped explicitly when the artifact was written, so the artifact is exactly what was
ingested rather than something a silent reindex reshaped.

## 6. Defect corrected in code during this work

The governed ACTIONS ingest could not run at all before commit `3408376`. `ingest_actions_from_artifact`
parsed its artifact with pandas' default NA handling, and SHARADAR carries **three ACTIONS rows whose
ticker is literally `NA`** — a real security, inside the governed universe. Those rows arrived with a
`NaN` ticker, the blank-ticker guard fired, and the entire ingest was refused reporting "3 row(s) with
no ticker", which was false. Corrected by `keep_default_na=False, na_values=[]`; the blank-ticker guard
is unweakened, since a genuinely empty field parses to `""` and is still refused.

All three `NA` rows are present in this corpus and were verified after ingest.

## 7. What this countersignature does and does not establish

**Establishes:** the corpus identity above, its coverage through 2026-07-24, an authoritative ACTIONS
declaration, and that the superseded corpus is preserved unmodified.

**Does not establish and does not authorize:** any performance claim, the opening of the forward
window, a first observation, removal of the Account-4 operational hold, broker order submission, or
Account-4 activation. Account 4 remains IDLE with `operational_hold` ACTIVE `_rev 2`
(`AWAITING_PRODUCTION_SIZING_VALIDATION`), session count 0, forward window not open.
