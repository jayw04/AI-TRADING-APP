# SEC-001 V3-RC — STOP / REDESIGN Closeout Record v1.0

**Status:** **CLOSED 2026-08-26 (owner).** Disposition: **STOP / REDESIGN — classification-coverage
gate failed.** No economic evaluation was run and none is authorized.
**Governing artifacts:** `SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md` (θ values and decision rule,
sealed 2026-08-23) · `SEC001_V3_SuccessorEpoch_TerminalIntegrityReport_v1_0.md` (epoch integrity,
sealed 2026-08-26) · `SEC001_V3_WeeklyGrid_CoverageMeasurement_v1_0.md` (the governed measurement).

---

## 1. Disposition

**SEC-001 V3-RC — STOP / REDESIGN.**

The frozen classification-coverage gate failed. The governed coverage execution measured **92.801%
resolved ticker-weeks** and **425 of 1,247 qualifying rebalances**. No trailing start satisfies
`θ_window`; therefore the earliest-qualifying-start candidate set is **empty** and `θ_span_min` is
never reached.

| | |
|---|---|
| Successor acquisition | **COMPLETE / conforming execution** |
| Coverage measurement | completed, dispositive |
| Coverage gate | **FAIL** |
| V3-RC | **STOP / REDESIGN** |
| Economics | **DENIED / NOT REACHED** |
| Coverage freeze token `5b26ffa2…` | **SPENT / CONSUMED** |
| Primary redesign finding | historical issuer/CIK lineage is insufficient |
| Threshold / taxonomy retuning | **PROHIBITED** |
| Successor authorization | **WITHHELD**, pending the FPI adjudication in §6 |

The decision rule was applied **once and mechanically**, as freeze §3 requires. The best trailing
span (start 2022-10-31) reaches a **65.089%** qualifying fraction against a required 95%; zero spans
of any length qualify. The gate was decided **without constructing a single window**: the five
regenerated windows partition the span, so "all five ≥ 0.95" implies "span-wide fraction ≥ 0.95", and
no window boundary was ever exposed to a result.

---

## 2. Sequencing — no operator checkpoint-bypass nonconformance

**Coverage sequencing was explicitly reordered by later owner instruction.** An earlier sequence
placed Defect-G custody repair and F-6 adjudication before coverage. A later instruction superseded
that order and directed: seal the terminal report → run governed coverage → return with F-4/F-5/F-6.
The operator followed that later instruction. **There was no unauthorized checkpoint bypass**, and
the earlier wording "PREMATURE COVERAGE SPEND / OWNER-CHECKPOINT BYPASS" is **withdrawn**.

The remaining governance fact is narrower, and it is unconditional:

> **The coverage freeze was irreversibly consumed when the governed coverage table was produced and
> observed.**

**`5b26ffa2…`: SPENT / CONSUMED — final authoritative state.** Earlier artifacts were inconsistent,
with Gate-6 custody describing it as consumed while pre-crawl and critical-path records still
described it as unspent. **The coverage execution removes the ambiguity permanently.** The token
cannot govern another attempt; a successor requires a new coverage freeze and a new token.

⭐ The lesson this record carries forward: **state inconsistency existed; later owner sequencing was
followed; the token is now unquestionably spent.**

---

## 3. Why no outstanding precondition changes the disposition

### F-1 / Defect G — unconditional

Byte-custody repair creates **no historical observation and no additional SIC evidence**. It cannot
move a single unresolved cell. The 177 divergent-collision observations retain agreeing classification
outcomes and agreeing header boundaries; nothing about their custody state bears on coverage.

### F-6 — the 92.801% figure is not an admissible-final result, and the STOP survives that

**92.801% is the measured pre-F-6-adjudication coverage result, not an admissible-final header-only
coverage figure. F-6 could move individual cells in either direction.** Restricting acceptance to a
SIC found inside `<SEC-HEADER>` removes observations; removing an outside-header observation can
expose an **earlier** effective segment, and where the removed observation mapped to `excluded_low`
while the surviving earlier one maps to an approved row, a previously unresolved cell becomes
**resolved**. A monotone-decreasing claim would therefore be wrong.

The STOP is made independent of that uncertainty by a **measured bound**, not a directional
assumption:

| quantity | value |
|---|---|
| immutable no-SIC unresolved cells (can never improve) | **12,670** |
| maximum potentially recoverable `excluded_low` cells | **5,224** |
| theoretical best-case coverage if every such cell became resolved | **94.896%** |
| theoretical maximum qualifying rebalances | **834 / 1,247 = 66.9%** |
| required `θ_window` | **95%** |

> **Even the impossible best-case F-6 reassignment cannot satisfy the frozen coverage gate.**

Short by **28.1 percentage points** on the binding criterion. **F-6 therefore cannot change the STOP
disposition**, and no header-only classification artifact needs to be regenerated to decide this
candidate.

---

## 4. Failure anatomy

| cause | unresolved cells | share | interpretation |
|---|---|---|---|
| **successor-CIK lineage** | 10,800 | **60.2%** | structural identity-lineage defect |
| `excluded_low` mapping rows | 5,224 | 29.1% | frozen taxonomy working as specified |
| 2000 warm-up | 1,870 | 10.4% | left-edge / source-history limitation |
| 3 CIKs without a segment | 60 | 0.3% | small residual |
| effective-date conflict | **0** | — | resolver behaved correctly |
| identity / crosswalk failure | **0** | — | identity chain behaved correctly |

**The failure is not principally the EDGAR crawler.** With the lineage and `excluded_low` classes set
aside the epoch classifies **99.226%** of ticker-weeks; with the warm-up boundary also removed,
99.976%. The acquisition executed conformingly and is not the limiting factor.

**Primary redesign finding — historical issuer/CIK lineage is insufficient.** Using a *current* CIK as
though it were historically valid for a permanent identity is not adequate for a 26-year PIT
classification program. `DIS` is the concrete case: current CIK `1744489` cannot supply filings for
PIT-200 membership dating to 2000-01-03, because that registrant identity begins at 2019-05-08 — 899
unresolved cells from one name. 366 of 1,167 identities are affected.

The existing crosswalk cannot solve this by joining differently: **only 2 of 754 permatickers carry
more than one CIK**, and of the top 20 lineage contributors only `GOOGL` carries the earlier
registrant. A successor must **prospectively resolve predecessor registrants and reacquire the
corresponding historical filings.**

---

## 5. Prohibited responses

The following are **contaminated by the observed coverage result** and are prohibited:

* ⛔ remapping SIC 7370, or any other code whose treatment costs the gate
* ⛔ promoting `excluded_low` rows to resolved
* ⛔ changing `θ_name` (0.95)
* ⛔ changing `θ_window` (0.95)
* ⛔ moving the evaluation start, or changing `θ_span_min`
* ⛔ altering the five-window construction
* ⛔ erasing, re-running, or otherwise treating the coverage table as unobserved
* ⛔ running V2 reference economics or V3 economics

**No threshold, mapping, start date, `excluded_low` treatment, or window construction was altered
after coverage was observed.**

**Findings preserved as closeout, not repaired for this candidate.** F-1 / Defect G remains a real
**evidence-system** defect and should be fixed before the same retention machinery is reused
elsewhere — but it no longer gates anything, because there will be no V3-RC economic run. F-6 remains
recorded as an **admissibility** defect; regenerating a header-only artifact solely to produce a worse
coverage number is not warranted. F-4, F-5 and the 40-F / 20-F / 10-K405 observations stay
**uninterpreted**.

---

## 6. Successor authorization — **WITHHELD**

The SEC-001 idea is **not** permanently terminated. The result says the *present* historical-
classification construction is inadequate. A legitimate successor would be a **new candidate** with a
prospective design and freeze — not a repair of V3-RC.

**Authorization is withheld pending a bounded FPI / pre-2002 source-availability adjudication.**

> Were the apparently missing pre-2002 20-F/40-F-class filings actually electronically available
> through SEC/EDGAR under some admissible historical form or path that the current frozen acquisition
> scope omitted, or do they genuinely not exist electronically for those issuer-years?

This must be answered **without** changing `θ_name`, `θ_window`, the `excluded_low` treatment, or the
current failed candidate. It is material because the measured impact nearly exhausts the missingness
budget on its own:

| measure | value |
|---|---|
| FPI-filing CIKs in the population | 141 |
| of those, with no acquired filing before 2002 | **122** |
| mean such names inside the PIT-200 per rebalance, 2000 | **8.1** |
| maximum, 2000 | **11** |
| mean, 2001 | 6.1 |
| `θ_name` total unresolved budget | **10** |

In 2000 the FPI issue alone consumes nearly the entire missingness budget, leaving ~1.9 names of
headroom for every other cause combined. ⭐ **Lineage repair cannot help these names** — they are
single-CIK foreign private issuers, not re-registered successors. If the missing history genuinely
does not exist electronically, then **a successor retaining the same coverage standards and historical
ambition may be structurally unsatisfiable**, regardless of how completely predecessor-CIK lineage is
repaired. That must be known **before** launching another large acquisition program.

### 6.1 What a successor would require (recorded so its scope is not underestimated)

A lineage-correct successor **cannot reuse** the frozen identity order `e8445b0b…` or the union
artifact `d338e65f…`. Once predecessor CIKs become governed acquisition identities the acquisition
population changes, and with it every artifact derived from it:

```
new lineage artifact → new acquisition population / union → new deterministic frozen order
→ new CIK resolution artifact → new coverage freeze + token → new manifest / epoch
```

Likewise, if the design introduces a pre-2000 warm-up, **`CRAWL_SINCE = 2000-01-01` is no longer
valid**: the acquisition horizon must be prospectively moved earlier and frozen before acquisition.

**This is not a small repair to V3-RC; it is a genuinely new candidate infrastructure definition.**

A successor should keep **unchanged**: `θ_name` 0.95 · `θ_window` 0.95 · ≥20-year span ·
`excluded_low` treatment · the V3 economic construction · transaction-cost assumptions. Holding those
fixed is what isolates the genuine defect — historical CIK lineage — rather than tuning the test after
seeing why it failed. The defensible redesign chain is narrow:

```
permanent identity → effective-dated issuer/CIK lineage → predecessor-CIK acquisition
→ effective-dated SIC → frozen sector mapping
```

with, optionally, a principled pre-period warm-up sufficient to establish classification state at the
first rebalance of the evaluation span.

---

## 7. Custody and remaining closeout work

**Git custody — complete and verified.**

| commit | content |
|---|---|
| `9398528` | terminal integrity report sealed with the F-1/F-2 dispositions; coverage measurement v1.0; measurement tool |
| `d92c471` | executable identity, the F-6 measured ceiling, the successor feasibility signal |
| *this record* | STOP / REDESIGN closeout |

Pushed to `origin/research/mr002-validation2-lineage`; local `HEAD` verified equal to `origin`.
Measurement tool identity: git blob `c877b3091f0018a8e82453b109437ad384560dee`, content sha256
`28f4182b2bfbade8dd056f03291ede905eb65bb36f87a8ec4e8a87477b15fb05` (worktree and blob digests
compared, identical — no CRLF divergence).

**S3 custody — complete.** Bucket `workbench-sec001-v3-research-219024422756`, prefix
`sealed/epoch/SUCCESSOR_EPOCH_0_1167/2026-08-26/`. Manifest in Git at
`manifests/s3/objects/sec001-v3-successor-epoch-evidence.v1.json` (package basis sha256
`81e9fa5c2d11cfaa…`); the repository S3 manifest gate passes.

| object | bytes | S3 VersionId | sha256 |
|---|---|---|---|
| `epoch_evidence.tar.gz` | 152,784,085 | `oF6TQj4..ivc5heZGX_n8.zz5q8EQtzw` | `a8d100c66425f3db…` |
| `INVENTORY.json` | 17,561,542 | `G0RTcy6CZNjpGAeCnq9ZxFWl6yn8.h.l` | `c7946144d732ab4f…` |
| `PACKAGE.json` | 455 | `BCtOCfD6ydKHblV6jwLrITpkdnTw8vQf` | `03d76428638a546b…` |
| `measurement/segments_projection.json` | 83,066 | `DVAGTb8wL2z3peRI7ZyqtQjJDXaTTuiq` | `90d7d9f7b55482ea…` |
| `measurement/identity_rows.json` | 47,150 | `eDDEskSPpRP8nqqTSxQGe9xgU0lhnxy8` | `82f317acb791cc94…` |
| `measurement/sic_mapping.json` | 52,158 | `l1tVyhzqON6BUVWfpQY2QSeuAR9ICs0t` | `633dc4cfa4ee9e7f…` |
| `measurement/coverage_result_v1.json` | 100,525 | `RuKV_lvSDT0JyaE7DGEVDqkWDf2KKtiZ` | `788755facfc2f205…` |

The package covers **77,523 files / 1,682,515,377 uncompressed bytes** — the whole
`crawl-successor` tree, the three frozen manifest artifacts, the executed implementation
(`code2/apps`), the runner and its stdout log, and the Gate-6 canary result. `INVENTORY.json`
carries path, size, sha256 and mtime for **every** member. Excluded and recorded as such: the 2 GiB
`TERMINAL_RESERVE.bin` zero-fill, third-party site-packages (pinned instead by httpx 0.28.1 /
httpcore 1.0.9 and `httpcore/__init__.py` sha256 `f644ff92…`), the superseded pre-Gate-6 payload
tree, and transport encodings of files already included.

⭐ **Separation of duties was preserved, not worked around.** The `sec001-v3-research-role` instance
profile is denied `s3:*` on `sealed/*` and denied every retention/lock/delete action — *the builder
may not declare its own output immutable*. The package was therefore **staged to `build/` by the
host** and **promoted to `sealed/` by the owner principal**. Every object was verified twice: S3-side
on PUT with `ChecksumAlgorithm=SHA256`, and by independent round-trip read-back.

⚠ **The custody package inherits the F-1 limitation** and says so in the manifest: 177 of 76,821
observations are not fully byte-reproducible, so **no claim of complete byte-level artifact custody**
is made for those 177.

**Bucket controls verified:** versioning `Enabled` · default encryption `AES256` with bucket keys ·
all four public-access blocks `true` · Object Lock **enabled at the bucket** with **no default
retention rule**, and none applied to these objects.

⚠ **Owner decision, surfaced not taken:** once `vol-0c55ac93dc1736a80` is deleted these S3 objects
are the **only** copy of the epoch evidence. Versioning protects against overwrite and delete-marker,
but an admin principal can still delete a specific version. If any evidence class in this program
warrants an Object Lock retention, this is it. **No retention was applied** — that is a deliberate
non-action, since Object Lock materially restricts later administration and was not authorized.

**Restorability — fresh-fetch, restore, and full re-verification: PASS.** Because the next step is
deleting the source volume, the property that matters is that the package **reconstructs** the
evidence, not merely that it is stored. Verified independently of the producing host: the sealed
`epoch_evidence.tar.gz` and `INVENTORY.json` were fetched **by Version ID** with a fail-closed digest
check, the archive was extracted, and **every** member was re-hashed against the inventory.

```
fetched by VersionId, digest fail-closed   epoch_evidence.tar.gz OK · INVENTORY.json OK
verified                                   77,523 / 77,523 files   (158 s)
missing 0    hash-mismatch 0    size-mismatch 0    unlisted extras 0
RESTORABILITY VERDICT                      PASS — the sealed archive reconstructs the evidence exactly
```

The restored copy was then removed; the sealed S3 objects were not modified.

**Remaining, in order:**

1. ✅ **S3 custody** of the successor-epoch evidence — complete and verified.
2. ✅ **Fresh-fetch and verify** — see the restorability check below.
3. **Only after custody succeeds**, dispose of `vol-0c55ac93dc1736a80` — **not done**, pending the
   Object Lock decision above.
4. Handle `vol-04b5ad3065530d20e` separately as infrastructure cleanup — **not done**.
5. ⛔ **Do not start successor lineage acquisition.**
6. Next research question: the bounded **pre-2002 FPI source-availability / satisfiability
   adjudication** (§6).

⚠ **CI note.** Branch `research/mr002-validation2-lineage` carries a **pre-existing 119-error backend
Ruff baseline** that predates this work. A red Tier-3 run attributable solely to that baseline is
**recorded as baseline noise**, not as a validation failure of these commits. The measurement tool
itself is Ruff-clean and mypy-clean.

---

*The research process stopped where it should: before a backtest could turn an inadequate historical
classification spine into an apparently meaningful economic result.*
