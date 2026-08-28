# Algo Trader Plus / Strategy Proposals v1.4.1 — Final Design & Implementation Plan

| Field | Value |
|---|---|
| **Document version** | **v1.0 — FINAL implementation baseline** |
| **Final-review date** | **2026-08-27** |
| **Status** | **FINAL DESIGN / IMPLEMENTATION PLAN** — Review 2 complete. Operational owner gates remain explicit; this document does not grant them. |
| **Canonical repository path** | `docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v1_0.md` |
| **Repository** | `github.com/jayw04/AI-TRADING-APP` |
| **Repository state at finalization** | `main = 3f32c75b1053f8181f98ddf51bbc473364ffd34c` (#695 squash). |
| **Supersedes** | v0.14 in Git and the unlanded v0.15/v0.16 review drafts. **Do not commit v0.15 or v0.16 as current plans.** |
| **Historical companion** | `AlgoTraderPlus_v1_4_1_History_v0_3_to_v0_16.md` — exact byte copy of the supplied v0.16 final-review draft; SHA-256 `51ae39e670b451d70764fb0372f4b1b6c13381df093fae47acb19aa623923dd8` (LF, repository form). |
| **Byte form** | **LF-only — 0 CR bytes in both files**, verified by direct byte inspection. `git hash-object` with and without `--no-filters` returns the identical blob SHA under `core.autocrlf=true`, so committing cannot invalidate the companion digest above. No normalization was applied or required. *(verified 2026-08-28)* |
| **State sync** | **2026-08-28**, applied **in place** per the ONE CURRENT PLAN rule — §2.1, §2.2, §3, §5.2, §11, §12. No historical section was rewritten. |
| **Sole program objective** | **Generate robust, deployable, net-profitable strategies at acceptable risk.** Research, data, infrastructure and governance are means, not products. |
| **Authority hierarchy** | Frozen registrations / sealed evidence / accepted ADRs / explicit owner rulings > this plan > subordinate task lists. A merge, test pass, document statement or planning priority never grants live mutation or strategy activation by implication. |

---

## 1. Executive directive — profit is the product

Every active task must pass this admission test **before** engineering time is allocated:

1. Name the strategy or economic decision it serves.
2. State how it can improve net P&L, risk-adjusted return, capacity, execution cost, drawdown, or time-to-paper validation.
3. State a measurable stop condition or time-box before work starts.
4. State the next conversion gate:

   `observation → frozen mechanism → governed validation → paper candidate → promotion decision`

5. If no named conversion target exists, **DEFER / MOVE TO OPS / STOP**.

Only two classes belong in the strategy program:

- **STRATEGY-DIRECT** — generates, validates, improves, or promotes a named economic mechanism.
- **REQUIRED ENABLER** — the minimum engineering/data/governance work without which a strategy-direct step cannot run safely or produce admissible evidence.

“Useful platform work,” “more complete research,” “better custody,” “more features,” and “we already have the data” are **not sufficient reasons** to consume strategy-program time.

---

## 2. Current governed state — latest verified/reported snapshot

### 2.1 Repository / deployment

- `main = 3f32c75b1053f8181f98ddf51bbc473364ffd34c` after #695.
- Amendment 8 / runtime-derived deployment identity is **MERGED** through #693, squash `47715b4e9de61ae4e95e6d37e62b08650b8bf204`.
- **Amendment 8 is DEPLOYED / CLOSED** *(state sync 2026-08-28; it was NOT deployed at the 08-27 finalization, and the deployment postdates it)*. Deployed at the pinned pre-#696 object with **no substitution**: commit `3f32c75b1053f8181f98ddf51bbc473364ffd34c`, `code_digest sha256:813be1b9775fb98e4276a499e8c715b745c7a518decf04072ef5a75999b72610`. Container recreated 2026-08-27 17:02:21 EDT; first governing **`READY — all six gates pass`** 2026-08-27T21:04Z.
- **Runtime identity is now measured, and all three legs agree** (re-verified read-only 2026-08-28): `/opt/workbench/app/.deploy_src_sha` = `3f32c75b…`; `DEPLOYED_BUILD_INFO.json` `commit`/`deployed_repository_commit` = `3f32c75b…` with `tree_clean: true` and the `code_digest` above; backend boot log `runtime code identity verified: sha256:813be1b9…`. The known-stale host self-report is therefore **closed** — the pre-deployment record is retained beside it as `DEPLOYED_BUILD_INFO.json.pre-catchup` (commit `956e932c8860602060b627b9c8f7966d31565337`).
- ⚠ The marker path is **`/opt/workbench/app/.deploy_src_sha`**, not `/opt/workbench/.deploy_src_sha`; probing the latter returns "No such file" and reads exactly like a missing marker.
- The governing preflight is now **six-gate**; the first valid success is `READY 6/6` and **there is no legitimate post-deployment `READY 5/5` state**.
- #693 and #695 merges confer **zero operational authority**.

### 2.2 2026-08-27 MDQ acquisition — **SEALED GOVERNED PARTITION** *(state sync 2026-08-28)*

⚠ At finalization this section read *"ACQUISITION RUNNING — NOT YET A GOVERNED PARTITION"* (157 cycles at `16:01:21Z`). That was correct then. The complete chain has since closed, verified independently on 2026-08-28 rather than read off the freeze unit's own journal:

- sampler `09:25:01 → 15:59:00 EDT`; **19,750 rows per feed = 395 × 50**, both feeds identical, matching the 395/395 scheduled slot grid;
- EOD 16:30:03/04 wrote **16,705 iex / 27,715 sip** 1-minute bar rows;
- freeze 16:45:02→05: **frozen → verified → mirrored**, both feeds, 3 files per feed;
- `ALERTS_TODAY = 0`; acquisition identity `PA3BGKRLH2AP` / fp `b56421a28128`; `universe_sha256 a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563` unchanged ⇒ **the corpus did not split**;
- **S3 custody verified independently, 6/6 objects** — every `ContentLength` equals the manifest byte count and every returned ETag equals the host MD5, stated as *measured equality*; manifest `sha256` equals host `sha256sum` on all four payload files. `ChecksumSHA256` is null, so no S3-side SHA-256 exists; SHA-256 is verified host-side.

**Status: ADMITTED — SEALED GOVERNED PARTITION.**

**Corpus: six sealed governed trading days** — 08-19, 08-20, 08-21, 08-25, 08-26, **08-27**.

⛔ **2026-08-28 is day 7 IN FLIGHT, not partition 7.** At the time this sync was prepared the sampler was mid-session (healthy: identity latch verified, both feed partitions present, `ALERTS_TODAY = 0`), with the EOD and freeze stages still ahead. Mid-run health is **not** capture evidence; a day is admitted only from its terminal, 3 files per feed, verified manifest and custody. **Do not amend the count to seven** until that chain completes.

The day earns governed-partition status only from the complete chain:

`terminal 395/395 → EOD write → freeze → verify → mirror → independent S3 custody verification`

If terminal completeness or any downstream leg fails, classify the day according to the governing admissibility record. **No salvage, backfill, reconstruction, hand-start or manufactured partition is permitted.**

The 08-27 seal/state record must explicitly say that runtime identity for this date was established through the running-container/code-hash authority, **not** the known-stale host self-report.

### 2.3 B-1 / PR #696

Remote GitHub state at finalization:

- PR **#696** remains **DRAFT**;
- remote head `02bdae3097d7e8e96032fcada500ddca856a8fb7`;
- base `3f32c75b…`;
- 2 commits / 11 files.

Latest developer-reported local successor, **not yet pushed and therefore not repository evidence**:

- `AuthorityRef` binding/provenance adjustment implemented locally;
- 49 focused tests reported passing;
- ruff and mypy reported clean;
- full `tests/research/` rerun still requires an unambiguous result because the previous background invocation produced no observable output.

No claim about the local successor becomes governing until it is pushed, frozen to an exact SHA, independently reviewed, and CI completes on that exact head.

### 2.4 LOW-001 / B3a

- B3a risk repair is **PINNED**: PR #683, head `3307e0cf328243823c39cf970a44b185b259f7be`, merged as `07a92330108390f8d5299e36b411150c08b9160c`.
- A prior LOW-001 v1.0.3 S8.6 execution produced a **12/12 PASS**; PR #687 carries its execution-variance and S8.6 custody records and remains an activation prerequisite until closed or explicitly superseded.
- Strategy 8 remains **IDLE**. Dynamic BUY / reactivation authority remains closed.
- There is **no forced 2026-08-31 or 2026-09-14 activation deadline**. The governing LOW record says B1/B3a must close **before any Strategy-8 reactivation**. If the owner does not choose a rebalance window, IDLE is the correct default.
- Because Amendment 8 will recreate/change the backend runtime, the old 12/12 S8.6 result remains historical evidence but does **not substitute for the required fresh post-deployment no-transition proof** before activation.

---

## 3. Final executable priority queue

| Priority | Work | Class | Serves | Stop rule / acceptance | Next gate |
|---|---|---|---|---|---|
| ~~**P0-1 time-bound**~~ ✅ **DISCHARGED** *(state sync 2026-08-28)* | Finish the 08-27 MDQ terminal sequence without intervention | REQUIRED ENABLER | MDQ evidence / ATP retention context | Met in full: 395/395 + EOD + freeze→verify→mirror + independent 6/6 S3 custody. No salvage was needed or used. | ✅ Partition **ADMITTED** — see §2.2 |
| **P0-2 finish-only** | Finish #696 K3/K1 evaluator candidate | REQUIRED ENABLER | MDQ decision machinery, then close B-1 | Real research-tree PASS + push exact successor + focused immutable review + exact-head CI. Merge remains a separate ruling. | B-1 engineering closure |
| ~~**P0-3**~~ ✅ **DISCHARGED** *(state sync 2026-08-28)* | Separately authorize and deploy Amendment 8; capture wrapper/unit SHAs before/after; first governing `READY 6/6`; close production identity evidence | REQUIRED ENABLER | **LOW-001** activation path | Met: deployed at the pinned object with no substitution; runtime identity independently proven by two implementations converging on `code_digest 813be1b9…`; first governing `READY — all six gates pass` 2026-08-27T21:04Z. | ✅ Fresh LOW-001 no-transition window — **now additionally gated on factor-system GREEN, see §5.2** |
| **P0-4** *(amended 2026-08-28)* | Fresh no-transition window → S8.6 1–12 → rollback-baseline restore iff genuine 12/12 → B3a production proof on the **same runtime**; close required custody such as #687; **then factor-system GREEN confirmed** | STRATEGY-DIRECT ENABLER | **LOW-001** | Any failed check stops the chain. No substitution and no “equivalent” prior-runtime proof. ⛔ **Blocked at the factor-consumption boundary while factor readiness is RED** — checks 3/4/8 take no PASS credit, so a genuine 12/12 is unreachable until GREEN (§5.2.1). | Owner reactivation decision |
| **P0-5** | Freeze LOW-001 paper-observation protocol before reactivation; then, only if separately authorized, observe paper economics | STRATEGY-DIRECT | **LOW-001** | Proposed minimum: ≥13 weekly rebalances / one quarter; EVIDENCE_NOT_FEEDBACK; KEEP/DEMOTE only, no economic upgrade from paper alone. Must be owner-frozen in LOW track before activation. | End-window owner disposition |
| **P1-1** | SF1 NO-START census, if owner grants the sequencing exception | STRATEGY-DIRECT | New PIT fundamental-change alpha hypothesis | 4–6 h; first verify Sharadar refresh state. Stale spine ⇒ `NOT EVALUABLE — STALE SPINE`; insufficient population/PIT/OOS/power ⇒ STOP. Zero strategy code. | One pre-registration or STOP |
| **P1-2** | GAPPER data-source disposition | STRATEGY-DIRECT ENABLER | **GAPPER** | By **2026-09-11** choose exactly one: PURCHASE a named qualified dataset, or STOP-FOR-CYCLE with passive forward accrual. “Keep investigating” is not an outcome. | Census rerun or passive accrual |
| **P1-3 conditional** | MOM-001 L1 execution enhancement | STRATEGY-DIRECT | **MOM-001** | Reopen only at ≥50 governed fills in a rolling 60-session Phase-A population; otherwise HOLD. | L1 overlay pre-registration |
| **P1-4 owner decision** | ATP economic retention test | STRATEGY-DIRECT DECISION | Any strategy with a stated SIP dependency | Decide at/before G3 on strategy-direct execution evidence; K verdict is frozen context, not an automatic keep/cancel trigger. | Keep/cancel subscription |
| **P2** | MOM-CAND-001 / RSI-REV-001 | STRATEGY-DIRECT | New alpha | Specification only until mechanism, cost model, falsification and untouched prospective test are frozen. | Pre-registration |
| **P2 conditional** | MOM-LIQ / SIP-CONT / SIP-LSR | STRATEGY-DIRECT | New alpha | Start only after evidence shows SIP contains material economic information beyond data-quality/execution safety. | Pre-registration |
| **Future conditional** | OPRA overlays / options-derived strategy work | STRATEGY-DIRECT | Named strategy only | No capture-first project. A strategy interaction and corpus sufficiency target must exist first. | G8 → G9 |

**Parallelism rule:** #696 engineering may proceed while the 08-27 collector runs because it does not touch the acquisition path. Once terminal capture proof begins, the time-bound capture sequence has priority over PR administration.

---

## 4. B-1 / #696 final implementation contract

B-1 is **engineering-complete when the evaluator machinery is sound**, even if governed K1 remains NOT EVALUABLE. A missing K1 authority is then a bounded provenance question, not an open-ended engineering project.

### 4.1 Admissibility / evidentiary boundary

The implementation must satisfy these invariants, independent of class/function naming:

1. `evidentiary` is **derived**, never a caller-supplied Boolean.
2. An evidentiary K result requires real admissibility token(s) produced through the governed §7.1 gate path.
3. `NOT_ADMISSIBLE` and `UNDETERMINED` never mint admissibility authority.
4. Tokens are bound to the evaluated root/session scope; a token for one partition cannot launder another.
5. Arbitrary dictionaries, caller assertions, environment switches, `force=` paths, or direct test minting cannot create governed evidence.
6. Tests obtain passing tokens by driving the real `require_admissible` path through controlled adjudication fixtures.
7. Diagnostic evaluation remains allowed, but the serialized result must preserve `evidentiary=false` and why.

Python cannot be made hostile-code-proof by convention; the acceptance boundary is that **normal production/research callers have no supported path to governed evidence that bypasses the real gate**.

### 4.2 K1 three-valued OR

Frozen K1 remains a disjunction. Required truth behavior:

| Limb A | Limb B | K1 |
|---|---|---|
| PASS | any | PASS |
| any | PASS | PASS |
| FAIL | FAIL | FAIL |
| FAIL | NOT EVALUABLE | NOT EVALUABLE |
| NOT EVALUABLE | FAIL | NOT EVALUABLE |
| NOT EVALUABLE | NOT EVALUABLE | NOT EVALUABLE |

**PASS dominates. FAIL requires both limbs evaluable and both failing. Otherwise K1 is NOT EVALUABLE.**

The test suite must pin this behavior directly.

### 4.3 K1 governed-input provenance / `AuthorityRef`

Current state: **no K1 decision-provider authority and no predeclared-defect-registry authority are bound.** Therefore governed K1 is currently **NOT EVALUABLE**.

Final contract for a future binding:

- a Boolean declaration such as `DECISION_PROVIDER_BOUND=True` or `DEFECT_REGISTRY_BOUND=True` has **zero authority by itself**;
- a binding requires an `AuthorityRef` (or equivalent immutable provenance object) carrying at minimum:
  - stable authority identifier;
  - SHA-256 of the governed artifact establishing the authority;
  - reviewable artifact reference/location;
- empty identifiers, malformed digests and missing artifact references are refused;
- `InputProvenance` / `ungoverned_inputs` is **derived from actual supplied inputs and actual bound authority**, not caller flags;
- stable reason identifiers must survive serialization, including at least:
  - `decision_provider_unbound`
  - `predeclared_defect_registry_unbound`
- supplying an arbitrary provider or defect list without a governed binding remains **diagnostic-only**, even when every partition is admissible;
- a test showing that a constructed valid `AuthorityRef` makes the mechanism capable of governed evaluation is a **future-contract test only**. It is not evidence that such an authority exists today;
- when a real authority is later proposed, the owner/custody step must independently verify that the referenced governed artifact exists and its actual bytes match the declared SHA-256 before the binding is accepted.

The visible current-state declarations should remain false/none until that separate governance event is completed. Flipping a Boolean must never grant authority.

### 4.4 Frozen threshold regressions

Tests must pin the actual boundary, not merely nearby values:

- K1: exactly `1/10 = 0.10` and another exact denominator such as `2/20 = 0.10` ⇒ PASS; below 10% ⇒ FAIL for that evaluable limb.
- K3: construct an exact 50% reduction case, e.g. IEX missing 0.40 and SIP missing 0.20 ⇒ reduction 0.50 ⇒ PASS; below 0.50 ⇒ FAIL.

### 4.5 K3 invariants already accepted

Do not reopen unless the successor diff materially changes them:

- grid is the **union** of observed symbol-minute cells, not a symbols×minutes Cartesian product;
- half-open window **04:00–16:00 ET**;
- `missing_rate_IEX = 0` ⇒ NOT EVALUABLE, not PASS;
- raw row-count difference is diagnostic-only;
- naive timestamps are refused;
- sub-minute events collapse to one minute cell.

### 4.6 #696 completion procedure

1. Re-run full `tests/research/` with an unambiguous exit code/output; silence is inconclusive, not PASS.
2. Confirm focused tests (latest local report: 49), ruff, and mypy.
3. Commit/push the provenance successor.
4. Freeze and report exact successor SHA, commit count, changed-file count, clean working tree, focused-test count, research-tree result, ruff and mypy.
5. Keep #696 **draft** for the focused immutable review of §§4.1–4.4.
6. After review, ready-state CI must pass on the exact approved head.
7. **Merge requires a separate owner ruling.**
8. After merge, conduct at most **two working sessions** of provenance-only K1 authority discovery (target close by 2026-09-04). If no unique pre-corpus governed authority is found, record `K1 = NOT EVALUABLE` and close B-1. Do not create a provider or “predeclared” defect list after the corpus exists.

---

## 5. LOW-001 activation path — corrected final sequencing

LOW-001 is a strategy path, not an ATP data project. Its frozen economics remain separate from DISC/Opportunity/MDQ signals.

### 5.1 Known completed facts

- Dynamic-PIT v1.0.3 S8.6 historically passed 12/12 on the prior runtime.
- B3a code artifact is pinned by #683 / merge `07a92330108390f8d5299e36b411150c08b9160c`.
- Strategy 8 remains IDLE.

### 5.2 Required post-Amendment-8 chain before any reactivation *(amended 2026-08-28 — factor gate inserted)*

The first six steps are **✅ discharged** by the 2026-08-27 deployment (§2.1). The chain now reads:

```text
[done] separate owner approval of exact deployment SHA
[done] pre-deploy read: record mdq_run.sh + three MDQ unit SHA-256s
[done] deploy the exact owner-approved repository SHA containing Amendment 8
[done] verify deployed control VERSION
[done] first governing READY 6/6
[done] independently close production deployment-identity evidence
   -> post-deploy re-read wrapper/unit SHA-256s; unchanged or explicitly account for delta
   -> fresh no-transition observation window
   -> fresh S8.6 checks 1-12 on this runtime
   -> genuine 12/12  --  ONLY REACHABLE AFTER factor readiness is GREEN   (see 5.2.1)
   -> rollback-baseline restore
   -> prospective B3a production proof on the SAME runtime
   -> required custody closure (#687 unless explicitly superseded)
   -> FACTOR-SYSTEM GREEN CONFIRMED                                       (see 5.2.1)
   -> freeze LOW-001 paper-observation protocol
   -> separate owner Strategy-8 reactivation ruling
```

Do **not** reuse the prior-runtime 12/12 result as the new-runtime activation proof. Do not start Strategy 8 merely because #693 is merged, deployment succeeds, S8.6 passes, or a factor PR is merged. Each is necessary and not sufficient.

### 5.2.1 FACTOR-READINESS INTERLOCK — a global blocker above individual strategies *(owner ruling, 2026-08-27/28)*

> While live factor readiness is **FAIL** or factor publication is **stale**, no factor-dependent strategy may transition **IDLE → PAPER/LIVE**, generate a new factor-ranked book for activation, or execute a scheduled factor-driven rebalance.

**Existing positions remain untouched** unless an independently governed strategy/risk rule requires action. RED is **not** a liquidation trigger.

⛔ **`factor-system GREEN` is not “the PR is merged.”** It requires, all observed and none inferred: one adjudication authority consumed by both producer and readiness/watchdog with no per-ticker special cases; producer/readiness behavioural equivalence; successful live publication advancing the live store off its frozen SEP date; `overall_readiness=PASS`; and **one subsequent unattended scheduled refresh PASS**. The last is the only one production alone can supply.

**S8.6 checks 3, 4 and 8 are factor-dependent and take NO PASS CREDIT while factor readiness is RED — even though they currently return pass.** They resolve through a permanent-security-identity adapter over the factor store, dated by `identity_coverage_date()`, which is a high-water mark of the store's *own contents*. A stale store therefore yields a stale-but-internally-valid frontier against which every holding resolves and readiness reports READY. **The failure mode is a misleading green, not a red.** A returned pass from 3/4/8 under RED is that known stale-tolerant artifact and must be recorded **WITHHELD**, never counted.

Consequently the other nine checks (1, 2, 5, 6, 7, 9, 10, 11, 12) are factor-independent and **may be exercised separately if separately authorized**, but **no aggregate 12/12 can exist until factor readiness is GREEN**, and therefore **SAFE ROLLBACK BASELINE is unreachable while RED**. That is a sequencing fact, not a reason to halt LOW-001 engineering: the stop belongs precisely at the **factor-consumption boundary**, not broadened into “all LOW-001 work stops.”

⚠ **A second, factor-independent bar stands on check 2**: it pins running SHA `956e932` and requires agreement with `DEPLOYED_BUILD_INFO.json`. The box now runs `3f32c75b` (Amendment 8), and rollback to `956e932` is separately prohibited. S8.6 as written therefore cannot pass check 2 on the current runtime regardless of factor state — this needs an owner ruling before any rerun is scheduled.

### 5.3 Paper observation design

Before reactivation, freeze the observation design in the LOW-001 track. The profitability-oriented default proposed by this plan is:

- ≥13 weekly rebalances / approximately one quarter;
- net return versus the frozen PIT-static reference;
- maximum drawdown;
- turnover;
- implementation shortfall versus decision price;
- conformance-check pass rate;
- EVIDENCE_NOT_FEEDBACK inside the observation window;
- paper results may support KEEP or DEMOTE, **not upgrade the frozen economic verdict by themselves**;
- RANK-001 may allocate only among independently validated strategies; LOW-001 paper observation does not silently alter RANK standing.

This protocol itself must be explicitly owner-frozen before activation; this planning document does not activate Strategy 8.

---

## 6. MDQ economics, G3 reachability and subscription treatment

### 6.1 Frozen qualification rules stay frozen

The ratified G3 floor remains **≥2 of K1–K6 both evaluable AND PASS**. No definition, threshold, holdout, completeness rule or GO floor is changed by the profitability-first plan.

Current planning reachability:

- **K3**: computable once #696 lands and partitions are admissible.
- **K1**: NOT EVALUABLE unless a genuinely pre-corpus governed authority is discovered.
- **K2**: NOT EVALUABLE unless G10 opens.
- **K4**: requires the non-waivable ≥250 trustworthy PIT event-day contract; current GAPPER census is far below it.
- **K5**: cannot contribute to the GO floor under the signed ruling.
- **K6**: event-contingent.

Therefore, under the profitability allocation decision **GO is not the expected outcome** unless K1 becomes legitimately evaluable or K6 occurs. Before any K value is used for disposition, the owner should prospectively record that HOLD-with-stated-extension or STOP is an expected legitimate outcome of the allocation decision, not a reason to rewrite criteria.

### 6.2 Do not open G10 merely to rescue MDQ

The 20-session / ≥250-symbol K2 streaming test is a qualification capability, not alpha. **Do not implement Phase-B/G10 solely because K1 is unavailable or because the MDQ GO floor becomes difficult.**

Open G10 only when a named strategy/overlay requires broad streaming and states the economic mechanism it will test. Otherwise K2 remains NOT EVALUABLE for this cycle. The 2026-09-21 last-start date is factual only if such an economic justification appears.

### 6.3 ATP subscription retention is an economic owner decision

The frozen K verdict must still be reported exactly as registered, but subscription retention should not be treated as an automatic consequence of K1–K6 if those criteria are largely non-strategy qualification tests.

Recommended owner rule to ratify before G3:

1. Determine whether any strategy expected to trade in the next cycle **requires SIP** to avoid the known IEX stub/spread false-reject class in its governed execution path.
2. Determine whether CEE reaches `N ≥ 50` qualifying fills with a median SIP–IEX shortfall difference whose 95% interval excludes 0 bps.
3. If a named strategy has a governed SIP dependency, retain as a required execution enabler regardless of the K verdict.
4. If no strategy dependency exists and CEE remains NOT EVALUABLE or economically ≈0, cancel at the economic decision point unless a newly pre-registered strategy names a SIP dependency.

This is a **recommended owner economic rule**, not developer authority to cancel or retain a subscription.

---

## 7. Next profitable-strategy generation queue

### 7.1 SF1 — pull forward only by explicit owner exception

Purpose: cheaply test whether a distinct PIT fundamental-change mechanism is even viable while GAPPER remains data-blocked.

Procedure:

1. Check Sharadar `sep` / required SF1 spines for freshness before the census.
2. If stale beyond the census's own freshness requirement: record `NOT EVALUABLE — STALE SPINE` and stop.
3. Run the 4–6 hour NO-START census only after the owner grants the one-time sequencing exception.
4. Measure minimum/maximum dates, eligible-security count, PIT fields, missingness, OOS/power feasibility.
5. Write **zero strategy code** in this tranche.
6. If population/PIT/OOS/power is inadequate, STOP. If viable, next step is exactly one prospectively registered fundamental-change hypothesis.

### 7.2 GAPPER — purchase or stop, no endless feasibility program

Current frozen Stage-0 contract is not satisfiable by the present ~4/250 event-day corpus.

By **2026-09-11**, choose one:

- **PURCHASE** — bind `source_vendor` to one qualified dataset identity, coverage period, field set and PIT semantics; then rerun the census from the new source; or
- **STOP-FOR-CYCLE** — no additional preparation work; passive forward accrual may continue naturally; reopen only when ≥250 trustworthy event-days exist or a later owner-approved purchase changes the corpus.

Do not populate metadata to make `contract_complete=true` without a real qualified dataset.

### 7.3 MOM-001 L1 execution enhancement

This is the preferred enhancement path when enough observations exist because it improves an already validated alpha mechanism rather than inventing a new one.

Reopen only when ≥50 governed fills exist within a rolling 60-session Phase-A population. Measure lower implementation shortfall / fewer false spread-staleness rejects / better execution timing **without changing the underlying ranking alpha**. If population remains below the threshold, HOLD; do not manufacture observations.

### 7.4 New alpha candidates

MOM-CAND-001 and RSI-REV-001 may advance only through:

`candidate observation → mechanism → cost model → falsification → discovery-ledger citation / multiple-comparison disclosure → prospective pre-registration → untouched prospective validation → paper candidate`

Candidate/watchlist output is not a signal and cannot touch order, risk, sizing or LOW-001 inputs without a separately registered economic mechanism.

SIP-native MOM-LIQ / SIP-CONT / SIP-LSR work begins only if prior evidence shows SIP adds material economic information beyond data-quality or execution-safety value.

OPRA work remains future/conditional; no options capture program exists merely because entitlement is available.

---

## 8. Work explicitly outside the active strategy queue

The following may live in an OPS/product backlog or prove themselves naturally, but receive **no dedicated strategy-program session** unless they become the minimum blocking slice for a named P0/P1 strategy:

- wrapper/systemd source custody as a standalone PR (the pre/post deployment SHA read in §5 is the only current blocking slice);
- scheduled SQLite-backup file proof;
- 90-day JSON-prune survival proof;
- branch hygiene / stale PR cleanup;
- generic documentation-location cleanup;
- broad DISC-MDQ feature-library construction while the population remains empty/narrow;
- repeated manual DISC census work beyond cheap natural recomputation;
- RANGE-SIP observation without a new prospectively named economic mechanism;
- local live-cache migration ADR/build before a specific L1/L2 strategy requires it;
- OPRA-CAP capture before a named options/risk strategy requires it;
- G10/K2 solely to rescue the MDQ GO floor;
- general platform refactors with no named strategy consumer.

If one becomes a real blocker, promote **only the minimum blocking slice**, then return it to OPS.

---

## 9. Evidence and implementation invariants

### 9.1 MDQ partition admissibility

A partition may enter K evaluation only after the registered §7.1 adjudication. Integrity/readiness is necessary but not evidence by itself.

Required properties include registered account/credential identity, explicit feed, frozen universe/cadence/session scope, approved collector identity, terminal completeness, freeze, successful verification, no stray/unmanifested files, no post-freeze mutation, and the frozen completeness/gap thresholds.

Inadmissible, smoke, scratch, reconstructed or post-hoc manufactured material is excluded from all K criteria. Value-extraction outputs (CEE, DISC, candidate features, etc.) never flow back into qualification evidence.

### 9.2 Feed semantics

Every governed request remains explicit: `feed=iex`, `feed=sip`, or `feed=opra`. Entitlement must never select semantics implicitly.

### 9.3 Research-plane isolation

K calculators and strategy-research programs remain read-only research/analytics code. No order-path, broker SDK, live risk capability or execution token is permitted unless a separate governed design explicitly authorizes a migration.

### 9.4 No post-hoc criterion repair

Do not revise K definitions, thresholds, evaluability clauses, holdouts, completeness thresholds, or “predeclared” inputs after looking at the governed corpus merely to make a criterion evaluable or pass.

---

## 10. Developer PR / CI / live-change discipline

1. **Exact immutable candidate:** every substantive review and merge ruling names the exact head SHA.
2. A head change reopens only the review surface affected by the change unless the diff expands unexpectedly.
3. Draft-time fail-closed CI artifacts are not substantive failures when prerequisite jobs never ran; inspect whether the test jobs actually executed.
4. Ready-state required CI must pass on the exact approved head before merge.
5. **No merge by implication.** A green PR remains HOLD until the explicit merge ruling when one is required.
6. **No deployment by implication.** Merge to `main` does not authorize image build/recreate, backend restart, live identity mutation, strategy activation, S8.6 execution, B3a proof or broker activity.
7. For live mutations, preserve pre-state, exact source SHA, runtime/build identity, rollback target and post-state evidence.
8. Do not expose or log credentials/secrets in evidence records.
9. Acquisition deadlines outrank routine PR administration when the two conflict.
10. “No output” or a masked exit status is **inconclusive**, never green evidence.

---

## 11. Owner decisions still required — final list

These are explicit gates, not developer TODOs to resolve by inference:

| Decision | State / required action |
|---|---|
| ~~**Amendment 8 live deployment**~~ | ✅ **RESOLVED 2026-08-27** — authorized and deployed at `3f32c75b…`; see §2.1. |
| **Factor-system deployment + restoration to GREEN** | **HOLD.** The merged factor repair is **NOT deployed**; deployment is a separate owner ruling. Schedule pressure is not authorization. Until GREEN, §5.2.1 applies. |
| **#696 merge** | **HOLD.** Successor must be pushed, focused review closed, ready-state CI green, then explicit merge ruling. |
| **K1 authority discovery** | Bounded discovery only after B-1 lands. No post-hoc provider/list creation. |
| **Prospective G3 expected-disposition record** | Owner should record expected HOLD-with-extension/STOP under the profitability allocation before K results drive disposition. |
| **ATP retention economic rule** | Owner ratification required before it governs keep/cancel. |
| **SF1 sequencing exception** | Required before the NO-START census can precede GAPPER disposition. |
| **GAPPER purchase** | Owner decision only if one qualified dataset is identified; otherwise STOP-FOR-CYCLE. |
| **LOW-001 paper protocol + Strategy-8 reactivation** | Must be frozen/authorized in LOW track after the complete post-Amendment-8 proof chain **and after factor-system GREEN is confirmed** (§5.2.1). IDLE remains default. |
| **S8.6 check 2 SHA pin vs the deployed runtime** | **OPEN.** Check 2 pins `956e932`; the box runs `3f32c75b`. Needs an owner ruling before any S8.6 rerun is scheduled. |

**Resolved/removed from the owner list:** B3a artifact identity is no longer open (#683 / `07a9233…`); the artificial 08-31→09-14 activation deadline is removed; v1.0 document restructure is implemented by this final version.

---

## 12. What this final plan does NOT authorize

- A second Algo Trader Plus subscription.
- Any MDQ order or broker capability.
- Phase-B/WebSocket implementation without a strategy-backed G10 decision.
- Direct live-consumer reads from the immutable MDQ archive.
- SCAN/DISC/Opportunity candidate output becoming an order/risk/sizing signal.
- GAPPER Stage-0 execution against a corpus that fails its frozen data contract.
- Metadata fiction to satisfy a missing dataset contract.
- MR-002 continuation; any revival is a new prospective program.
- Profitability-Acceleration or reserve-strategy code before its NO-START/pre-registration gate.
- Reopening rejected strategies without a genuinely new prospective economic mechanism.
- Exploration output entering K1–K6 qualification.
- Revising frozen K criteria after corpus inspection.
- Exploratory holdout access before hypothesis pre-registration.
- DISC/Opportunity/MDQ/news/SIP signals entering LOW-001 Dynamic-PIT economics.
- Treating LOW-001 Dynamic PIT as permission to weaken static strategy registration elsewhere.
- Credential switching to recover a failed MDQ slot.
- Backfilling/salvaging/manufacturing a lost governed capture day.
- Treating freeze exit 0, health checks, or code identity alone as proof of successful governed capture/deployment.
- Relaxing universe, credential, readiness or evidence semantics to make a gate pass.
- Any Strategy-8 reactivation from this document alone.
- **Any factor-dependent strategy activation, factor-ranked book generation, or scheduled factor-driven rebalance while factor readiness is FAIL or factor publication is stale** (§5.2.1) — and equally, any *forced liquidation* of existing positions merely because factor readiness is RED.
- Counting a PASS from S8.6 checks 3, 4 or 8 toward an aggregate 12/12 while factor readiness is RED.

---

## 13. Final review disposition

**REVIEW 2 — FINAL: ACCEPTED AS THE v1.0 IMPLEMENTATION BASELINE.**

The final changes relative to v0.16 are deliberately narrow but load-bearing:

1. **#696 status updated** to the actual remote successor head `02bdae3…` and the newer `AuthorityRef` work is correctly labelled **local/unpushed**, not repository evidence.
2. **#696 A6 contract changed from over-specified implementation shape to enforceable invariants.** Boolean state cannot create authority; future governed K1 binding requires verifiable immutable provenance.
3. **B3a ambiguity closed:** PR #683 / merge `07a9233…` is the pinned artifact.
4. **LOW-001 timing corrected:** no invented 08-31/09-14 activation deadline; Strategy 8 remains IDLE until all activation gates close and the owner chooses reactivation.
5. **Historical S8.6 PASS preserved but scoped correctly:** a fresh post-Amendment-8 no-transition S8.6 is still required because the runtime changes.
6. **Profitability admission test remains controlling:** every active task serves a named strategy/economic decision or is the minimum required enabler.
7. **History removed from the execution surface:** v0.3–v0.16 material is preserved separately; developers execute from this current plan, not from layered state-sync history.

Future **state-only** updates should change a compact current-status block/subordinate task list without reincorporating historical narrative. A future change to strategy economics, qualification definitions, authority boundaries or the profitability queue requires an explicit successor design version or a separately governed strategy pre-registration.

**Developer rule:** if this plan conflicts with a frozen registration, sealed evidence record, accepted ADR, or explicit owner ruling, stop and use the higher-authority artifact. Do not reconcile the conflict by inference.
