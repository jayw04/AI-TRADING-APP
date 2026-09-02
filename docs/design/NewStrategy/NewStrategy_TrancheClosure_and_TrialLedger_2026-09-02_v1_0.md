# NewStrategy tranche closure record and trial-ledger entry — 2026-09-02

| Field | Value |
|---|---|
| Version | **v1.0 — OWNER ACCEPTANCE OF 2026-09-02 INCORPORATED — READY FOR CUSTODY** |
| Closes | the NewStrategy C1 / C2 / C3 tranche frozen by `NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` — sha256 `47a2e26201b6c68ab8105ee08f0169fe64cdd3bca67f63d864b4efa85af34998` (25,279 B), custodied #721, merge `26cf4627e1a7745d65d0f4ad02389bbe873341d9` — as amended by `NewStrategy_ResearchAmendment_A_2026-09-01_v1_0.md` — sha256 `273800beef0624922ed65970aa099b137f409ba2261a686fe423b1b029c3e648` (32,188 B), custodied #724, merge `3cdde216119a6166bc4404718f964c60feecae9e` |
| Scope | **Record only.** C3 decisive result of record · frozen-rule classification · owner acceptance · trial-ledger entries for C1, C2, C3 (both attempts) · tranche disposition · successor boundary. |
| Does NOT change | any frozen hypothesis, parameter, threshold, estimator, window, verdict leg, or the 0.85 redundancy falsifier. Nothing here reopens the spec or the amendment. |
| Authority basis | Owner rulings of 2026-09-02: merge + execution ruling (~11:50Z) · interruption adjudication + Attempt 2 ruling (~15:20Z) · DO NOT INTERFERE ruling (~16:50Z) · **acceptance of the C3 classification and tranche disposition (~22:35Z)** |
| Companion evidence | S3 `workbench-backups-219024422756`, prefix `research/newstrategy/2026-09-01/evidence/` — every object pinned by VersionId + SHA-256 in §4 |

⛔ **Execution boundary unchanged.** Nothing here authorizes production code, account assignment, scheduler change, deployment, PAPER activation, or orders. This record grants nothing operational; it closes a research tranche.

**Tranche state after this record**

```
C1 = NOT EVALUABLE / TERMINAL FOR THIS TRANCHE
C2 = NOT EVALUABLE / TERMINAL FOR THIS TRANCHE
C3 = REJECT / DECISIVE ATTEMPT 2 CONFORMING / FROZEN PRIMARY ACCEPTANCE NOT MET / SAME-FACTOR REDUNDANCY TRIPPED
NEW-STRATEGY TRANCHE = CLOSED / ZERO IMPLEMENTATION-CAPITAL CANDIDATES / ZERO PAPER PROMOTIONS
```

---

## 1. C3 execution history — two attempts, one verdict

| attempt | launched (UTC) | terminal state | disposition (owner) |
|---|---|---|---|
| 1 | 2026-09-02T12:52:36Z | killed by a host reboot at 14:29:23Z during the cost sweep (Windows System event 1074, user-initiated restart); no `EXIT` marker; no result artifact | **INTERRUPTED / HOST REBOOT / RESULT-BLIND / PARTIAL EVIDENCE SEALED / ZERO VERDICT CREDIT** — does not consume the decisive run |
| 2 | 2026-09-02T15:45:47Z | `[c3] done in 22946s`, `EXIT=0` at 22:08:17Z | **CONFORMING / DECISIVE / REJECT / VERDICT CREDIT** |

Attempt 2 was authorized as a **replacement** execution (owner ruling 2026-09-02 §1, §9) under the standing principle that a rerun may be authorized only when the first execution is independently proven invalid before a decisive result became observable. Attempt 1 emitted stage markers only; the driver prints numbers only after writing `c3_result.json`, which never existed. No checkpoint resume was used; Attempt 2 ran clean from the beginning in a fresh namespace. The Attempt 1 directory and its S3 mirror are retained permanently as interruption evidence and are **not** strategy evidence.

**Governed execution identity (both attempts):** code commit `3cdde216119a6166bc4404718f964c60feecae9e` (post-#724 main; current main had moved to a later docs-only commit, which the owner ruled not required for C3) · driver `c9d0d71c97d961a2a143430b7f853d7cc5368188077413ac2d514676358e282d` · parameter artifact `b1e99698b2432585ab27dea333036bb03446cc4a52fadd4535ef0662765f1a05` · dataset `factor_data.deepen.duckdb` 678,440,960 B `bafc6007f20f6edb8c9fcc7c60b5f77a6d5bb5021a060f8d0bfa7191b768c97a` (re-hashed before each attempt) · seed 17 · 2,000 resamples · block 21 · primary cost 10 bps · `--with-sensitivities`. Attempt 2 ran detached (Windows Scheduled Task, user context, sleep-inhibited) from `C:/LLM-RAG-APP/wt-research-exec` at a clean detached checkout of the bound commit; launch mechanism recorded in `host_environment.json` as provenance, not research logic.

## 2. C3 decisive result of record (Attempt 2)

Actual curve 2017-01-09 → 2026-06-12, 2,370 points, 493 rebalances, 0 skipped. OP-6 screened universe ≈2,200–3,100 names per rebalance; book ≈440–620 names.

| book | Sharpe | max drawdown | CAGR | Calmar |
|---|---|---|---|---|
| C3 — OP-6 low-vol (decisive) | 0.5905 | -0.3925 | 0.0826 | 0.2104 |
| OP-6 equal-weight benchmark | 0.5213 | -0.4291 | 0.0963 | 0.2243 |
| Strategy-8 reference (B-3, n=200) | 0.7860 | -0.3235 | 0.1073 | 0.3316 |

### 2.1 Frozen-rule inputs

| leg | value | frozen reference | outcome |
|---|---|---|---|
| **H1** ΔSharpe vs OP-6 equal-weight | **+0.069**, 95% CI **[-0.222, +0.451]** | CI must exclude zero for PASS | **CI spans zero** |
| Drawdown advantage vs equal-weight | **0.0367** (-0.3925 vs -0.4291) | must exceed the LOW-001 record **0.3024** for REVISE | **does not exceed** |
| Return-redundancy falsifier | Pearson corr of date-aligned daily returns with the S8 reference **0.9044** (2,369 common days) | > 0.85 trips | **TRIPPED** |
| Holdings-redundancy falsifier | mean holdings-weight overlap **0.0786** (492 common rebalances) | > 0.85 trips | not tripped |
| SAME-FACTOR REDUNDANCY (either) | | | **TRUE** |

### 2.2 Diagnostics — recorded, never deciding

Walk-forward, 5 windows (`factor_lab.runner._windows` arithmetic): **3/5** windows beat equal-weight on Sharpe; **5/5** windows shallower drawdown.

| # | actual curve | points | ΔSharpe | book maxDD | eqw maxDD |
|---|---|---|---|---|---|
| 1 | 2017-01-09 → 2018-11-23 | 474 | +0.379 | -0.0846 | -0.1421 |
| 2 | 2018-12-03 → 2020-10-13 | 469 | -0.083 | -0.3925 | -0.4291 |
| 3 | 2020-10-19 → 2022-09-01 | 472 | +0.530 | -0.1602 | -0.3323 |
| 4 | 2022-09-06 → 2024-07-19 | 470 | +0.003 | -0.1235 | -0.1746 |
| 5 | 2024-07-29 → 2026-06-12 | 471 | -0.092 | -0.1329 | -0.2561 |

Cost sweep (ΔSharpe vs equal-weight at equal cost): 0 bps +0.0762 · 10 bps +0.0692 · 25 bps +0.0586 · 50 bps +0.0410 — positive throughout, never decisive.

Named sensitivities (`NAMED SENSITIVITY / NOT A VERDICT`): screen $4 / $1M ΔSharpe +0.0688 (maxDD -0.3940) · screen $6 / $3M +0.0713 (-0.3907) · unscreened full tape -0.0667 (-0.3539).

## 3. Classification and owner acceptance

**Frozen legs** (parameter artifact `acceptance` / `verdict_legs`, Amendment A §4.3, frozen spec C3 — all three agree): PASS = H1 CI excludes zero **and** book maxDD shallower than equal-weight · REVISE = CI spans zero **and** DD advantage exceeds the LOW-001 record 0.3024 · REJECT = CI spans zero **and** it does not.

**Applied:** CI spans zero; DD advantage 0.0367 < 0.3024 ⇒ **C3 = REJECT.** The artifact's `verdict_indicated` is `REJECT`. NOT EVALUABLE does not apply: book/benchmark alignment was asserted date-identical before the estimator ran, no rebalance was skipped, the falsifier comparator was computed in the same execution before any C3 number was read, and every input identity is bound and re-verified. The redundancy falsifier independently refutes the standalone-alpha framing under which C3 was funded.

**Owner acceptance (2026-09-02):**

```
C3 / LOW-002 = REJECT / DECISIVE ATTEMPT 2 CONFORMING / FROZEN PRIMARY ACCEPTANCE NOT MET
             / SAME-FACTOR REDUNDANCY TRIPPED / NO PAPER-PROMOTION DECISION OPENED
```

The owner recorded that the decisive evidence is sufficient and internally consistent, that the diagnostic findings (positive 0–50 bps sweep, 5/5 shallower walk-forward drawdowns, tighter-screen point estimates, negative unscreened sensitivity) are non-verdict evidence that may inform future discovery but rescue nothing, and that this is **a valid research outcome, not a failed program cycle**: the tranche eliminated two currently unanswerable hypotheses and one economically unsupported / redundant candidate without manufacturing a survivor.

## 4. Trial-ledger entries — low-volatility family and tranche

Frozen spec §0.5 item 3 requires every decisive result to be recorded **whatever it is**; §0.5 item 4 discloses three shots in this family. This section is that record.

| candidate | program | hypothesis (frozen) | decisive shots | outcome | ledger status |
|---|---|---|---|---|---|
| C1 | FI-003 / CAP-022 crash insurance | trend de-risk overlay improves ≥3 of 4 frozen crises, none worsened (OP-2) | 0 completed (execution-defect run, then history-window conformance) | **NOT EVALUABLE** — owner Option B, OP-2 not weakened (Amendment A §5) | shot taken; no verdict credit; hypothesis not refuted |
| C2 | MF-001 V2 value/quality multifactor | standalone ΔSharpe vs momentum + diversification comparators | 1 (registered ΔSharpe +0.065, positional-alignment defect; date-aligned diagnostic +0.063 CI [−0.334, +0.522] is post-defect, non-primary) | **NOT EVALUABLE** — alignment defect ⇒ zero primary credit; comparators unavailable from frozen evidence (Amendment A §3) | shot taken; no verdict credit; hypothesis not refuted |
| C3 | LOW-002 broader-universe low volatility | standalone low-vol alpha strengthens on the OP-6 screened universe; not redundant with Strategy 8 | Attempt 1 interrupted (zero credit) · **Attempt 2 conforming** | **REJECT** — CI spans zero, DD advantage 0.0367 < 0.3024, return corr 0.904 > 0.85 | **consumed decisive shot for the low-vol family; verdict credit** |

**In-sample declaration.** All motivating C3 data and every number observed in Attempt 2 — the decisive legs, the walk-forward, the cost sweep, the sensitivities, and the redundancy measurement — are now **in-sample** for any successor hypothesis in the low-volatility family. They may be cited as motivation and used for census; they may not serve as a successor's decisive validation evidence.

### 4.1 Sealed evidence — Attempt 1 (interruption evidence only)

Local `C:/LLM-RAG-APP/research-out/2026-09-01/C3_attempt1_interrupted_2026-09-02T1429Z/` (the original `research-out/2026-09-01/C3/` is retained untouched). S3 prefix `research/newstrategy/2026-09-01/evidence/`:

| object | bytes | sha256 | VersionId |
|---|---|---|---|
| `C3_attempt1_interrupted_2026-09-02T1429Z/INTERRUPTION_RECORD.json` | 3,100 | `d55d0bc93734a69da7ef1d1db021a0286dd8c66455476c3728bda74ae9e2ec35` | `Nf7O7NCLVeeRtvmyrVCH6DfeSMCNo.Vy` |
| `C3_attempt1_interrupted_2026-09-02T1429Z/environment.json` | 775 | `031d1bad4a1cddb34783ee815cfeab3cbd1ea4a9bc37cddde48a7eba0359c649` | `Fa.7E.aCHHfDX18pg5kA2v0f84ylsAfk` |
| `C3_attempt1_interrupted_2026-09-02T1429Z/host_environment.json` | 1,339 | `6c3722f2b3ddbcad55ce145d8f2ea823f1744c91138bacb944ac668ec4a2a3bc` | `rmHl7zlLDjAi4RZe67S8EagaWfkNA5ox` |
| `C3_attempt1_interrupted_2026-09-02T1429Z/run.log` | 961 | `8c2a923731651db9f4e047a71c5c0a9324f9014b2464dcd9a364e282d7b5d453` | `cl6eV_KGxXnCWx2OnNjbVAXIJKewSi03` |

### 4.2 Sealed evidence — Attempt 2 (decisive result of record)

Local `C:/LLM-RAG-APP/research-out/2026-09-01/C3_attempt2_2026-09-02T1544Z/`, sealed at 2026-09-02T22:09:10+00:00 with the result file unread. S3 prefix `research/newstrategy/2026-09-01/evidence/`:

| object | bytes | sha256 | VersionId |
|---|---|---|---|
| `C3_attempt2_2026-09-02T1544Z/SEAL.json` | 1,645 | `a47df96794f6a92107571c31a3935eb960da9fbcab689f4c54b31878ed6e1357` | `yXdskMVbqLuEB3D2trMVkIE5pjCCRvjw` |
| `C3_attempt2_2026-09-02T1544Z/c3_result.json` | 28,807 | `68fecb5411f1ba14e298000e053c46444617768fa9aceac25e35e31d220de4ab` | `zmDoMyGjuQboQVLhMiJS36jLUoZWN7mu` |
| `C3_attempt2_2026-09-02T1544Z/c3_sensitivities.json` | 323 | `29542b95e1669f395024187471b9c824d12419ab12c1482dc1cd8b303dfbf0f6` | `WzeX_r.pHDCIXusn5h09Xq5bs_eOCKld` |
| `C3_attempt2_2026-09-02T1544Z/c3_series.json` | 8,017,473 | `1116c9f5c34172953d85b05ef4373c7c3da16c7e8d3b1fe3b7e0fb90576a7f86` | `GSwyF.wTtKm8Ij8E_JT0UZdQANiv_3al` |
| `C3_attempt2_2026-09-02T1544Z/environment.json` | 775 | `18a06e8c9530e7a3e8e319a915212e9ec497341ea821d3c35498fd0807788044` | `izcLp_gzhTSkPrQ26qlpihYF.J3.zdB7` |
| `C3_attempt2_2026-09-02T1544Z/host_environment.json` | 2,166 | `641c1c7659314022ff0b72e3aa171741c4e5a5813202f681e26b7209e20a33a6` | `0NGnfY79j32.G3ssdPXb.IQ0dT6GoflG` |
| `C3_attempt2_2026-09-02T1544Z/run.log` | 3,160 | `cdd652a26834cd62d1802e55bfb391e9adc2a5dc0d01f946c6c6e0b8403745a1` | `tk2MnWrvOxrB4M3191_8JBMtrNBLtgJ6` |

### 4.3 Governed document identities at closure

| artifact | bytes | sha256 |
|---|---|---|
| `NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` | 25,279 | `47a2e26201b6c68ab8105ee08f0169fe64cdd3bca67f63d864b4efa85af34998` |
| `NewStrategy_ResearchAmendment_A_2026-09-01_v1_0.md` | 32,188 | `273800beef0624922ed65970aa099b137f409ba2261a686fe423b1b029c3e648` |
| `params/C1_crash_insurance.json` | 4,741 | `a9747a462466181c21a6c4a9f618d59971f63fbc95a9d90d23cde5b5af77b6f9` |
| `params/C2_value_quality.json` | 2,384 | `45e943436c5b6a60b3f58d83eb7675f6f279929fdfbfb7f29f95f234b493520a` |
| `params/C3_broader_lowvol.json` | 7,800 | `b1e99698b2432585ab27dea333036bb03446cc4a52fadd4535ef0662765f1a05` |

Implementation custody: OP-6 module + universe-provider seams merged as **#723** (`c7fa8dc41ce1653554be9fbc5c70f6604130f4c7`); Amendment A + parameter artifacts merged as **#724** (`3cdde216119a6166bc4404718f964c60feecae9e`) — the C3 governed execution SHA.

## 5. Prohibitions — permanent for C3

⛔ **NO** window recut · **NO** rerun or Attempt 3 under any authority · **NO** weakening of the 0.85 redundancy threshold · **NO** reinterpretation of the drawdown leg (5/5 shallower walk-forward drawdowns is a diagnostic, not a verdict input) · **NO** promotion or revival on sensitivity results (the $6 / $3M screen's +0.0713 is not a rescue path) · **NO** tuning around the Strategy-8 redundancy (frozen spec: "do not tune around it") · **NO** transfer of C3 evidence to any successor as decisive evidence.

## 6. Successor boundary — DISCOVERY hypothesis only, not authorized research

The owner accepted the following framing **as a discovery hypothesis only**. It is not a candidate, not a census, not a freeze, and carries no research capital.

The useful question is no longer *"does broader-universe low-vol produce standalone alpha?"* — C3 answered that negatively. A future candidate could instead ask whether an **explicitly differentiated low-vol construction provides incremental portfolio value beyond Strategy 8 despite common-factor exposure.** Any such candidate must receive a new candidate identity, a census, a prospective freeze, untouched validation evidence, and a new trial-ledger shot; today's C3 history and diagnostics are motivation and in-sample evidence for it, never its decisive validation data. Admission runs through the ATP §1 test and is scheduled by an ATP successor, not by this record.

## 7. Tranche disposition (owner, 2026-09-02)

```
C1 = NOT EVALUABLE
C2 = NOT EVALUABLE
C3 = REJECT
NEW-STRATEGY TRANCHE = CLOSED / ZERO IMPLEMENTATION-CAPITAL CANDIDATES / ZERO PAPER PROMOTIONS
C3 LANE = CLOSED / REJECT ACCEPTED / TRIAL LEDGER RECORDED (this document)
        / NO IMPLEMENTATION / NO PAPER / NO FURTHER C3 EXECUTION
```

The next strategy-factory action is a **new discovery batch**, not another C3 iteration.

## 8. What this record does not do

It executes nothing, re-runs nothing, and changes no frozen artifact. It opens no PAPER-promotion decision for any candidate. It does not schedule, census, or freeze a successor. It does not alter Strategy 8, RANK-001, or any account, scheduler, or order-path state. Custody of this record grants no operational authority.
