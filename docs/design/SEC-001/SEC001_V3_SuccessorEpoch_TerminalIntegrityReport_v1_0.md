# SEC-001 V3 — Successor Epoch `SUCCESSOR_EPOCH_0_1167`
## Terminal Integrity Report v1.0

**Status:** **SEALED 2026-08-26 (owner).** Conjunctive completion gate **PASS**, terminal identity
reassertion **PASS**. The terminal epoch is ruled **SUCCESSOR EPOCH — COMPLETE / INTEGRITY PASS**.
F-1 and F-2 are adjudicated in §0 below; F-3…F-6 carry forward to the taxonomy/coverage freeze.

---

## 0. Owner adjudication — 2026-08-26

**Terminal epoch — `SUCCESSOR EPOCH — COMPLETE / INTEGRITY PASS`.** The 1,167/1,167 conjunctive gate
and the terminal identity reassertion are sufficient. ⛔ **Do not rerun or repair the crawl.**

**F-1 — 177 divergent accession collisions —
`ACCEPT AS A BOUNDED EVIDENCE-CUSTODY NONCONFORMANCE; DOES NOT INVALIDATE CLASSIFICATION OR BLOCK
COVERAGE.`** ⛔ Defect G is **not** reopened retroactively. Recorded as a successor-epoch
collision/custody finding, carried forward with these statements and no others:

> 177 observations are not fully byte-reproducible; therefore **no claim of complete byte-level
> artifact custody** is made for those 177 · header boundaries agree 177/177 · classification
> outcomes agree · divergence begins after `</SEC-HEADER>` · for 100/177 the lost variant is
> **proven** prefix-related · for 77/177 the prefix relation is **not proven and must remain stated
> that way**.

⛔ Do not repair the completed epoch. ⛔ Do not re-acquire these filings. Preserve the collision
ledger and evidence; carry the limitation forward in every downstream artifact.

**F-2 — coverage denominator / join —
`APPROVED — COVERAGE MUST JOIN THROUGH CIK, NOT SEGMENT TICKER/FILENAME.`** The measurement rule is:

> for each frozen weekly-grid ticker identity:
> **ticker/week → frozen CIK resolution → effective-dated CIK classification → attach the ticker
> identity back to the result**

The 21 shared-CIK cases therefore **inherit the same CIK classification** rather than being scored
unclassified because one ticker-specific segment filename was overwritten. ⛔ Do **not** rewrite the
classification artifact to manufacture ticker rows — the spine stays semantically **CIK-keyed** and
expands to ticker identities only at the governed coverage-measurement join. Both figures are
reported: **ticker-week coverage** is the V3-RC eligibility denominator; **CIK-week coverage** is
diagnostic only, useful for detecting shared-CIK effects.

**F-3 … F-6 — do not stop for them now.** F-3 carried into coverage · F-4 measured on the governed
weekly grid · F-5 carried as a taxonomy/history characteristic, no repair before measurement · F-6
**preserved as an explicit source-semantics finding, not interpreted or changed**, for the
taxonomy/coverage-freeze adjudication *after* coverage is measured.

**Custody.** S3 custody of the epoch evidence must precede deletion of `vol-0c55ac93dc1736a80`, but
does not delay the read-only coverage measurement while the volume remains preserved.

**Successor artifact:** `SEC001_V3_WeeklyGrid_CoverageMeasurement_v1_0.md` (measurement run under the
F-2 rule above).

---

| | |
|---|---|
| Epoch token | `SUCCESSOR_EPOCH_0_1167` |
| Coverage freeze token | `5b26ffa2…` — **CONSUMED** at Gate 6 |
| Sealed execution package | Gate 6 = `eca87f6` |
| Host | `i-0407ca119eb85cdb1` (m7g.large, us-east-1c) |
| Epoch volume | `vol-0c55ac93dc1736a80`, 250 GiB encrypted, `DeleteOnTermination=false`, mounted `/opt/epoch` (`/dev/nvme1n1`) |
| Runner | `/opt/epoch/successor_runner.py`, PID 2273, PPID 1, detached (`setsid nohup`) |
| First request | 2026-08-26T01:26:48.472213Z |
| First unit credited | 2026-08-26T01:27:30.932237Z (`0000001800:ABT`) |
| Completion | 2026-08-26T09:03:21.247889Z |
| Elapsed | 7 h 36 min 33 s |
| Throughput | 122,127 requests / 35 retries / mean 4.46 req·s⁻¹ (policy cap 5.0) |
| Report compiled | 2026-08-26, read-only over the epoch volume via SSM |

---

## 1. Completion state — clean, self-declared, independently corroborated

* `RUNNER_STOPPED.json` — **absent**. No stop record was written, i.e. no Gate-5 reserve trip, no
  `check_unit` hard stop, no `check_state_invariants` hard stop.
* `EPOCH_COMPLETE.json` — present, 123 B, parseable:
  `{"completed_utc":"2026-08-26T09:03:21.247889Z","requests":122127,"retries":35,"terminal_identities":1167}`
* `successor_stdout.log` (3,389 B, intact) terminates with
  `SUCCESSOR EPOCH COMPLETE: 1167 unique terminal identities in frozen order, 122127 requests, 35 retries`.
* No runner process remains (`pgrep -f successor_runner.py` → none). `ALIVE=no` here is **normal exit
  after completion**, not the unhandled-death case the monitor rule warns about — the completion
  record and the log terminator distinguish them.

⚠ **`build/classification/2026-08-24/crawl_outcome.json` is NOT the epoch record.** It reports only
the final per-unit driver invocation (`units_crawled_this_run: 1`, `observations_written: 7`,
2-second span). The epoch-level record is `EPOCH_COMPLETE.json` plus the terminal ledger.

⚠ The `2026-08-24` path component in `raw/edgar/…` and `build/classification/…` is the **frozen
policy constant `CAPTURE_DATE`**, not the date this epoch ran. It is correct, and it will mislead a
reader who assumes otherwise.

---

## 2. Conjunctive completion gate — **PASS (3 of 3)**

Count alone is satisfiable by a duplicate plus a gap; all three limbs were evaluated separately.

| limb | measured | verdict |
|---|---|---|
| `terminal_count == 1167` | 1,167 records in `state/crawl_progress.jsonl` | **PASS** |
| `unique_terminal_ids == 1167` | 1,167 distinct `unit_key` | **PASS** |
| `terminal_sequence == frozen_identity_sequence` | element-wise equal to the sealed order | **PASS** |

Supporting measurements:

```
ledger bytes                    312,423   ends with newline: True   unparseable lines: 0
first unit                      0000001800:ABT        (frozen first identity)
last  unit                      0002041610:PSKY
completed_utc monotonic         True (no out-of-order credit)
frozen order sha256             e8445b0b6ea08bf1ff5ad5a08db6cc3797f5161fb53be3a0aed4b9b24c8f9c35  == seal
CIK artifact sha256             1f7d523b9419301a16d36234f19584266f3e61fc4e5673e589d0ba7016877146  == seal
independent re-derivation       order re-derived from the CIK artifact by the v1.4 controller
                                construction == sealed frozen order (n=1,167)
```

The order was **not** regenerated from prose. It was re-derived by the only correct construction
(sorted `WorkUnit` set over `status == "RESOLVED_CIK"`), and that derivation matched the sealed
artifact, which in turn matched the ledger sequence. Three independent representations agree.

---

## 3. Terminal identity reassertion vs the Gate-6 seal — **PASS**

Governed review condition 4 (protected/runtime identity changes) has **no live detector**; the runner
asserts identity at import only. This terminal comparison is what closes that gap retrospectively.
All hashes below were recomputed **on the host at completion** (git blob SHA-1, computed with a real
NUL byte).

| file | terminal | seal (`eca87f6`) | |
|---|---|---|---|
| `app/altdata/sec/client.py` | `6c1d7006f42f` | `6c1d7006f42f` | PASS |
| `app/altdata/sec001_v3/spine.py` | `3f37faba3861` | `3f37faba3861` | PASS |
| `app/altdata/mr002/sic_history.py` | `48779adaaaec` | `48779adaaaec` | PASS |
| `app/altdata/sec001_v3/sections.py` | `ae97502b1c9a` | `ae97502b1c9a` | PASS |
| `app/altdata/sec001_v3/forbidden.py` | `8570677325aa` | `8570677325aa` | PASS |
| `app/altdata/sec001_v3/__init__.py` | `a50bc6c76896` | `a50bc6c76896` | PASS |
| `app/altdata/sec001_v3/decision_bytes.py` | `06de91a92acc` | `06de91a92acc` | PASS |
| `app/altdata/sec001_v3/evidence.py` | `cdd61346212c` | `cdd61346212c` | PASS |
| `app/altdata/sec001_v3/driver.py` | `c6f147eda499` | `c6f147eda499` | PASS |
| `app/altdata/sec001_v3/state.py` | `0d23793590d8` | `0d23793590d8` | PASS |
| `app/altdata/sec001_v3/fetch.py` (authorized-changed) | `62646f2d2190` | `62646f2d2190` | PASS |
| `app/altdata/sec001_v3/policy.py` (authorized-changed) | `53d21a15ac62` | `53d21a15ac62` | PASS |

```
runner sha256   337a0472cac53f1f3cdea439eee94a4e241307f1afb71259a44c115822db1958   == seal
httpx           0.28.1        == seal
httpcore        1.0.9         == seal
READ_NUM_BYTES  65536         == seal (httpcore _sync HTTP11Connection, the proved guard-band M)
```

**Gate-6 startup identity == terminal identity.** Identity did not drift at any point during the run.

📌 **Seal-label correction (record it, do not silently fix the seal).** The Gate-6 token written as
`http11 f644ff92` is the SHA-256 of **`httpcore/__init__.py`** (`f644ff92a0a10822544c…`), not of
`httpcore/_sync/http11.py`. The token reasserts correctly under its true meaning; only the label was
wrong. For future seals the two digests are:

```
httpcore/__init__.py          sha256 f644ff92a0a10822544c…   (the value carried by the seal)
httpcore/_sync/http11.py      sha256 205a1b0f531de4916524…   (13,476 B; not previously sealed)
```

---

## 4. Acquisition bound at population scale — Defect F did not recur

The Defect-F canary proved the bound on **one** response. This epoch is the population-scale
demonstration: 122,127 responses, none exceeding the governed ceiling.

```
governed consumption ceiling        1,048,576 B      stop threshold  983,040 B
max wire_bytes observed               471,977 B      = 45.0% of ceiling
responses over ceiling                        0
consumption-ceiling stop events               0      (the bound was never approached, let alone hit)
total wire bytes                    844,447,772 B    (805.3 MiB) over 122,127 responses
```

HTTP outcome distribution over all 122,127 requests:

| status | n | interpretation |
|---|---|---|
| 200 | 79,185 | success |
| 404 | 42,907 | `-index-headers.html` absent for pre-modern filings → governed fallback to the legacy ranged `.txt` header read. Expected, handled, and exactly equal to the 42,907 `HEADER_TERMINATED` observations. |
| 503 | 24 | transient; all retried and satisfied on attempt 2 |
| — | 11 | `ReadTimeout` after ~30 s; all retried and satisfied on attempt 2 |
| 403 / 429 | **0** | the halt path (`HALT_STATUSES=(403,)`, 600 s cooldown) never armed |

`attempt` histogram: 122,092 × 1, 35 × 2. **Zero terminal request failures.**

**Retention, against the failed v1.4 epoch:**

| | v1.4 (Defect F) | successor epoch |
|---|---|---|
| identities acquired | 374 | 1,167 |
| retained bytes | 94.7 GB | 1,680,134,038 B (1.56 GiB) |
| per identity | ≈ 253 MB | ≈ 1.44 MB |

**≈176× reduction per identity.** The repair holds across the whole population, not just the canary.

---

## 5. Gate-5 storage reserve — never approached

```
requirement per artifact   free >= 2,149,646,336 B  (2 GiB reserve + 1,114,112 artifact + 1,048,576 metadata)
TERMINAL_RESERVE.bin       2,147,483,648 B, still allocated at completion
volume                     246 GiB usable · 3.9 GiB used · 229 GiB free · 2% utilisation
```

Storage was never the binding constraint. The reserve file remains allocated because the epoch ended
in the completion path, not the controlled-stop path — correct behaviour.

---

## 6. Evidence-ledger cross-consistency — no torn records

The v1.4 epoch died mid-append, leaving one unparseable record and a zero-byte stop file. Nothing of
that kind is present here.

| check | measured |
|---|---|
| `source_evidence.jsonl` lines | 122,127 — **equals** the ledger's summed `requests_issued` |
| `source_decision_bytes.jsonl` lines | 76,821 — **equals** the ledger's summed `observations` and `filings_seen` |
| unparseable records, either ledger | **0** |
| `document_complete` | True for 76,821 / 76,821 |
| `parser_body_sha256 == artifact sha256` | 76,821 / 76,821 |
| artifact `.bin` files on disk | 75,151 |
| recorded artifact paths missing from disk | **0** |
| orphan artifact files not referenced by any record | **0** |
| full re-hash of every artifact vs its record | 76,644 match / **177 mismatch** → see F-1 |

**Observation inventory (the epoch's product):**

```
observations                76,821    of which SIC found  75,372 (98.114%)   NO_SIC  1,449 (1.886%)
acquisition path            HEADER_TERMINATED 42,907 (legacy ranged, identity encoding)
                            HEADER_INDEX      33,914 (index-headers.html, gzip, decoded)
forms                       10-Q 52,927 · 10-K 17,138 · 10-K/A 2,332 · 10-Q/A 1,851
                            20-F 1,812 · 40-F 485 · 20-F/A 223 · 40-F/A 53
classification segments     1,511 rows across 1,146 per-CIK files · 275 distinct SIC codes
                            937 CIKs single-segment · 206 CIKs multi-segment · 3 CIKs empty (F-3)
```

The 20-F / 40-F extension (Gate 2) is confirmed *by execution*, not merely by manifest inspection:
2,573 foreign-private-issuer observations were acquired.

---

## 7. Findings requiring a ruling

### F-1 — 177 observations are no longer byte-reproducible (retention defect; **Defect G's mechanism is NOT refuted in this epoch**)

Artifacts are keyed by accession. 21 CIKs carry two ticker identities each, so every filing of those
CIKs is acquired **twice** and written to the **same** artifact path.

```
colliding artifact paths            1,670   (multiplicity 2 in every case)
  byte-identical                    1,493   no loss
  divergent sha256                    177   the later write overwrote the earlier bytes
observations affected                 177 / 76,821 = 0.230%
```

For each of the 177, one decision record now references a file whose bytes are not the bytes that
record hashed. **Those bytes are gone from this epoch.**

The damage is bounded, and the bound was measured rather than assumed:

| property | measured |
|---|---|
| `byte_length` delta between the two variants | 20 B × 173 · 24 B × 2 · 44 B × 2 |
| `sec_header_open_offset` identical | **177 / 177** |
| `sec_header_close_offset` identical | **177 / 177** |
| both variants longer than the close offset | **177 / 177** → divergence lies **entirely past `</SEC-HEADER>`** |
| lost variant is a byte-exact **prefix** of the surviving artifact | **100 / 100** of the testable cases, 0 exceptions |
| `parser_result` agrees | 177 / 177 |
| `sic_field_present_anywhere` agrees | 177 / 177 |
| `form` agrees | 177 / 177 |
| acquisition path | `HEADER_TERMINATED` (legacy ranged) in 177 / 177; `attempts == 1` on both sides |

⚠ **Limit of the prefix proof.** In 100 of the 177 the surviving file is the longer variant, so the
shorter variant could be reconstructed and hashed — all 100 matched exactly. In the other **77** the
shorter variant survived, so the longer variant's bytes are unavailable and prefix-exactness there is
**inferred**, not proven. The identical header offsets hold in all 177 by record.

**Consequence:** the classification is unaffected — the determining region is byte-identical and every
outcome agrees. What is lost is *byte custody* for 177 observations: their decision remains evidenced
by the record's own `sha256`, `parser_body_sha256` and header offsets, but cannot be re-derived from
retained bytes. This is a real gap in the "every decision is reproducible from retained bytes"
property, and it is the same mechanism (artifact path collision) that was investigated as **Defect G**
and **refuted** for v1.4, where all 616 collisions were byte-identical. It is not refuted here.

**No repair is proposed in this report.** Options span "accept with the bound above", "re-acquire the
177 accessions into a collision-safe path", and "change the artifact key to include the unit" — each
changes epoch conformance and needs an explicit ruling.

> **RULED 2026-08-26 (owner): ACCEPT AS A BOUNDED EVIDENCE-CUSTODY NONCONFORMANCE.** Does not
> invalidate classification and does not block coverage. Defect G is not reopened retroactively.
> No repair, no re-acquisition. The evidence and collision ledger are preserved and the limitation
> is carried forward. See §0 for the exact wording that must accompany it.

### F-2 — the classification artifact drops one ticker per duplicated CIK (**act before the coverage measurement**)

Segments are written one file per CIK. For the 21 duplicated CIKs the second identity's write
overwrites the first, and the file retains only the **later-sorting** ticker (21 / 21 — deterministic,
consistent with unit execution order). The SIC series itself is per-CIK and identical, so nothing is
mis-classified; but **the earlier ticker does not appear anywhere in the classification output.**

| CIK | identities | ticker kept | **ticker absent** |
|---|---|---|---|
| 0000006201 | AAL, AAMRQ | AAMRQ | **AAL** |
| 0000031235 | EKDKQ, KODK | KODK | **EKDKQ** |
| 0000040730 | GMH, MTLQQ | MTLQQ | **GMH** |
| 0000101830 | PCS1, S2 | S2 | **PCS1** |
| 0000310158 | MRK, SGP1 | SGP1 | **MRK** |
| 0000723527 | MCIP, WCOEQ | WCOEQ | **MCIP** |
| 0000833444 | JCI, TYC | TYC | **JCI** |
| 0000858339 | CZR2, HET | HET | **CZR2** |
| 0000860730 | HCA, HCA1 | HCA1 | **HCA** |
| 0000883980 | FDC, FDC1 | FDC1 | **FDC** |
| 0001054522 | UMG, USW | USW | **UMG** |
| 0001067983 | BRK.A, BRK.B | BRK.B | **BRK.A** |
| 0001091667 | CHTR, CHTRQ | CHTRQ | **CHTR** |
| 0001119639 | PBR, PBR.A | PBR.A | **PBR** |
| 0001166691 | CMCSA, CMCSK | CMCSK | **CMCSA** |
| 0001306965 | RDS.B, SHEL | SHEL | **RDS.B** |
| 0001308161 | TFCF, TFCFA | TFCFA | **TFCF** |
| 0001437107 | DISCK, WBD | WBD | **DISCK** |
| 0001570585 | LBTYA, LBTYK | LBTYK | **LBTYA** |
| 0001617640 | Z, ZG | ZG | **Z** |
| 0001652044 | GOOG, GOOGL | GOOGL | **GOOG** |

⭐ **This is a denominator trap, not a data gap.** A weekly-grid coverage measurement that joins on
ticker against `segments/*.jsonl` will score **GOOG, MRK, CMCSA, BRK.A, JCI, HCA, CHTR, PBR, Z, AAL**
and eleven others as *unclassified* — currently-tradeable, fully-acquired names. Resolve the join key
(CIK, with the ticker set attached) **before** measuring coverage, or the measurement will understate
coverage by up to 21 identities and the error will be invisible in the totals.

> **RULED 2026-08-26 (owner): APPROVED — coverage joins through CIK, never the segment
> ticker/filename.** The classification artifact is **not** rewritten to manufacture ticker rows; the
> spine stays CIK-keyed and expands to ticker identities only at the measurement join. Ticker-week
> coverage is the V3-RC eligibility denominator; CIK-week coverage is diagnostic only. Applied in
> `SEC001_V3_WeeklyGrid_CoverageMeasurement_v1_0.md`; measured effect of the shared-CIK cases is
> **2,396 duplicate ticker-slot cells**, which the CIK join resolves rather than scores unclassified.

### F-3 — three CIKs have no classification segment

| unit | filings in window | cause |
|---|---|---|
| `0001071189:GX` | 0 | no `10-K/10-Q/20-F/40-F` (+/A) filing since 2000-01-01; 1 request (submissions JSON) |
| `0001132979:FRCB` | 0 | same |
| `0001002131:LHSP` | 6 | all 6 observations `NO_SIC` — acquired, but no SIC field found |

⇒ **1,143 of 1,146 CIKs classified.** The two zero-filing identities are terminal-credited correctly
(unit-boundary credit does not require observations); they are a *population* question for the
coverage step, not an acquisition failure.

### F-4 — SIC absent in 1,449 of 76,821 observations (1.886%)

Spread across 660 of 1,167 units; per-unit maximum 7 (`0000732485:GENZ1`), then `0000008670:ADP`,
`0000034088:XOM`, `0000859360:LGTO1`, `0001002131:LHSP` at 6. Only LHSP is left with no segment at all
(F-3). Non-blocking, but it is the direct input to the coverage measurement and should be reported
with the coverage number rather than after it.

### F-5 — SIC oscillation inflates segment counts (2 units flagged `conflicts`)

`0000788784:PEG` and `0001109357:EXC` each produced **19 segments** from repeated 4931 ⇄ 4911
alternation (ELECTRIC & OTHER SERVICES COMBINED ⇄ ELECTRIC SERVICES) across consecutive filings. This
is genuine churn at the source, not an acquisition defect — but a segmenter that treats every SIC
change as a boundary will report 19 sector changes for a company whose sector never changed. The
taxonomy freeze should decide whether SIC-level or a coarser sector-level segmentation is the governed
unit. 206 of 1,146 CIKs are multi-segment; this choice moves that number.

### F-6 — SIC located outside `<SEC-HEADER>` in a large minority

```
sic_field_present_inside_sec_header   True 41,458   False 35,363
sic_field_present_anywhere            True 75,372   False  1,449
```

So ~35.4k observations were classified from a SIC found **outside** the SEC header block. The
acceptance rule ("anywhere") is what produced the 98.1% SIC rate. Whether "anywhere" is the governed
acceptance, or whether inside-header should be a stronger tier, is a taxonomy-freeze question. Stated
here as measured fact; **no interpretation is offered and none should be inferred.**

---

## 8. What this report does **not** establish

* ⛔ It does **not** establish that the SIC classifications are **correct**. It establishes that the
  field was present in consumed bytes and that the decision records are internally consistent.
* ⛔ It does **not** produce coverage. No coverage number exists yet; §5.1b Q5 stays unamended.
* ⛔ It does **not** unblock V3-RC. Completion ≠ V3-RC unblocked.
* ⛔ It does **not** make the v1.4 **374** admissible. They remain preserved, nonconforming acquisition
  evidence and never enter this count.
* ⛔ It does **not** authorize any repair of F-1 or F-2, nor any re-acquisition.

---

## 9. Governed sequence — position and next step

```
successor epoch complete  ✅ this report
  → governed WEEKLY-GRID classification coverage measurement      ← next, AFTER an F-2 ruling
  → source / taxonomy / coverage freeze                            ← F-5 and F-6 land here
  → §9.4 becomes servable
  → V3-RC                                                          ← first real economic evidence
```

**Status of the next acts (updated at seal, 2026-08-26):**

1. ✅ **F-2 ruled** — coverage joins through CIK. Applied.
2. ✅ **F-1 ruled** — accepted as a bounded evidence-custody nonconformance.
3. ⏳ **S3 custody of the epoch evidence** — still owed, and must precede deletion of
   `vol-0c55ac93dc1736a80`: 1.56 GiB across 75,151 artifacts plus the two ledgers, the terminal
   ledger, `EPOCH_COMPLETE.json`, `successor_stdout.log`, and the manifest trio. Version-pinned and
   checksum-verified, per the standing principle that evidence custody is S3 and never EC2/EBS.
   Owner-ruled not to block the read-only measurement while the volume remains preserved.
4. ✅ **Weekly-grid coverage measured** — `SEC001_V3_WeeklyGrid_CoverageMeasurement_v1_0.md`.
   ⚠ **The frozen coverage gate FAILS.** That is a §10.3 adjudication, not a finding of this report.

**Cleanup still owed** (unchanged by this report): recovery volume `vol-04b5ad3065530d20e`
(attached `/dev/sdf`, mounted `/mnt/recover` read-only on the investigation host) — detach and delete,
its provenance role having been sealed at Gate 6.

---

## Appendix — verification method

Every figure above was computed **on the epoch host** over the epoch volume, read-only, via
`AWS-RunShellScript` (base64-shipped scripts; no laptop dependency, nothing written to the volume).
Blob identities use git blob SHA-1 with a real NUL separator. Artifact verification re-read and
re-hashed all 75,151 `.bin` files (1.56 GiB) and compared against all 76,821 decision records. The
frozen order was verified three ways: sealed-artifact digest, independent re-derivation from the CIK
resolution artifact, and element-wise comparison against the terminal ledger.
