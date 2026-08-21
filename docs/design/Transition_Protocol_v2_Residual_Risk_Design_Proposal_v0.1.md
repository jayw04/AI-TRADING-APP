# Transition Protocol v2 — Residual-Risk Continuation Policy

**Design proposal v0.1 — DRAFT FOR OWNER DECISION**
Account 7 / Strategy 9 (combined-book v1.4.0, C40) · 2026-08-21
Author: development session 2026-08-21 · Requested by owner ruling 2026-08-21

---

## 0. Status and scope

> **SUPERSEDED 2026-08-21 by [ADR 0054 — Transition Residual-Risk Continuation Policy](../adr/0054-transition-residual-risk-continuation-policy.md).**
> The owner accepted Candidate C and ruled every open threshold; the policy is implemented,
> tested (246 assertions across six suites) and sealed. This document is retained as the
> evidence and reasoning that produced the decision. Two things it says are now out of date:
> §0 states nothing is implemented, and §9 lists open items that have since been ruled —
> except the concentration-on-`A_exits` question, which the ADR carries forward as the one
> live open item.

**This was a proposal. Nothing here was implemented at the time of writing.** The executor stack on `ec2-paper` is
byte-unchanged: planner v5 `4d0f6ca5…`, executor v7 `c0b35ff0…`, core v2 `2aa66c95…`,
identity latch `0da221e8…`, frozen limits v5 `ed5873d5…`.

Per the owner's separation of concerns:

> Today: design → implement → test → evidence. Next eligible session: fresh manifest under
> the amended, frozen protocol → approval → execution.

Account 7 is frozen: 51-position reconciled book, Strategy 9 IDLE, gross cap $100,000, no
reload, no `/start`, no C40 epoch, no manual sale of residual names, no new execution manifest.

**What this document does not do:** it does not select thresholds. Section 6 presents the
decision surface; the numbers stay open until the owner rules, precisely so that the choice is
not reverse-engineered from the $757.28 residual we are trying to get past.

---

## 1. ⚠ Correction to the record — only TWO names aborted on 2026-08-20, not four

Building the replay against the sealed residual ledger
(`OTR-20260820T164912Z-S9.residual.v3.jsonl`) contradicted the working account of the
2026-08-20 halt, which I had carried into this morning's step-5 report. The ledger is
authoritative and the earlier reading was wrong.

| | recorded account (08-20 → this morning) | what the sealed ledger shows |
|---|---|---|
| names that aborted | MS, PH, **EBAY, FN** | **MS and PH only** |
| abort records | 4 | 4 |
| failing **orders** | 4 | **2** |
| EBAY / FN | "aborted; stdout never flushed" | **never attempted** — the stage halted at seq 34; EBAY is seq 35, FN is seq 36 |

The live journal touches sequences 1–34 and stops. `order_disposition` records exist for 34
orders: 32 `FILLED`, and **2** `EXHAUSTED_GATE` — MS (seq 20, residual $123.5852) and PH
(seq 34, residual $133.6848). The four abort records are **two orders × K=2 attempts**.

**Consequences for the framing of yesterday's NO-GO.** The claim that today's Stage A contains
"the same four stale-prone names" is not supported by evidence:

- **MS, PH** — demonstrated `stale_reference` failure under live conditions. Real evidence.
- **EBAY, FN** — no evidence either way. They are still held because the stage stopped before
  reaching them, not because they failed.
- **DDOG** — new exit; it left the top 40 on the 2026-08-20 factor data.

The escalation conclusion is unaffected — the protocol still needs amendment — but the reason
is sharper than "four stale names keep recurring", and one of the three defects below was
invisible under the old reading.

---

## 2. Diagnosis — three distinct defects, not one

### D1 — The abort stop condition mixes units (attempts in the numerator, orders in the denominator)

`v13_transition_executor_v7.py:499–506`:

```python
stats  = self.ledger.attempt_opportunities(stage=stage)
aborts = stats["pre_submission_gate_aborts"]      # counts ATTEMPT records
if aborts > 3: ...
if stage_order_count and aborts > 0.10 * stage_order_count: ...   # ORDER count
```

`ResidualLedger.attempt_opportunities()` counts attempt records, and `attempt_policy.max_attempts`
is **K = 2**. So one failing order contributes **2** to `aborts`.

The practical effect of `aborts > 3` is therefore **"more than 1.5 failing orders"** — i.e.
**two failing orders halt any stage of any size**, whether the stage has 6 orders or 80. That
is what actually stopped the 2026-08-20 run: 2 of 34 attempted orders (5.9%) failed.

It also makes a dry run structurally incapable of predicting the live decision. Dry mode calls
`core.gate()` **once** per order and writes nothing to the residual ledger, so a dry run records
**1** abort per failing order where live records **2**. The replay shows this directly: the same
stage, same orders, same two cheap failures → `CONTINUE` in dry accounting, `HALT` in live
accounting (§5, C1 vs C2 at k=2).

### D2 — Stage-denominator collapse (the finding of 2026-08-20, confirmed 2026-08-21)

The `> 10% of the stage's order count` rule is denominated on the current manifest's stage size.
After a partial transition the re-plan shrinks the stage, and the tolerance shrinks with it.
A_exits went 36 → 4 → 5 orders; at 5 orders, 10% = 0.5, so the first failing order is 20% and
stage-fatal. Waiting a day for fresh data added one name and restored zero tolerance.

### D3 — Small stages inherit zero tolerance by integer arithmetic, not by policy

`B_cross_asset` is structurally 6 orders. 6 × 10% = 0.6 < 1, so it has always tolerated zero
aborts. That may well be the correct risk policy for a jointly-constructed sleeve — but it is
currently an accident of arithmetic rather than a declared rule, and nothing in the frozen limits
says so. §7 answers this on evidence.

### What is *not* broken

The order-level gates. The 300 s stale-reference rule, the 10 s cross-asset quote age, the 25 bps
half-spread cap, the 1.5 % manifest-drift gate, the K=2 / 120 s attempt policy, the identity latch,
the risk engine and the broker-terminality precondition all did exactly their job. MS and PH were
correctly refused. **No candidate below touches any of them, and no candidate ever force-submits a
refused order.**

### The conflation to fix

The protocol currently answers one question where there are two:

1. *Is this individual order safe enough to submit?* — the order-level gates. Working.
2. *Does the failure of this individual order make continuing the whole transition unsafe?* —
   currently answered by counting aborts. Not working.

A thin single name can correctly fail (1) without making $24 k of cross-asset construction unsafe.

---

## 3. What already exists and should be built on

The frozen limits **already carry an economic residual rule** that is closer to what is wanted
than the count rule is:

```
residual_policy.unified_rule        ONE residual-exposure ledger. Aborted, rejected, expired,
                                   cancelled and unfilled-partial quantities ALL enter it.
residual_policy.residual_valuation  broker-confirmed remaining qty x current governed valuation
residual_policy.tolerance_usd_per_stage   250.0
residual_policy.stage_outcome_rule  within tolerance -> stage COMPLETE with the residual
                                   disclosed as operational debt; beyond -> HALTED_REQUIRES_REVIEW
```

This is already checked in `check_stop_conditions`, but **third**, after the two count clauses —
so it has never been the binding clause. On 2026-08-20 the residual reached $257.27 against a
$250.00 tolerance, i.e. the economic rule would also have halted the run, by $7.27, and was never
reached.

The amendment is therefore mostly a matter of **promoting the rule that measures economics,
correcting the units of the rule that counts, and declaring per-stage policy explicitly** — not of
inventing a new risk framework.

---

## 4. Candidate policies

All three keep every order-level gate unchanged, never force-submit a refused order, always record
residuals to the unified ledger, and never silently drop a residual name from the target book.

### Candidate A — unit-corrected count rule with an explicit floor

```
HALT if  failed_ORDERS > max(FLOOR, floor(PCT x stage_orders))
HALT if  stage_residual > TOLERANCE          (unchanged)
```

Fixes D1 (count orders, not attempt records) and D2 (the floor stops the denominator collapsing).
Minimal diff; easiest to test. Still count-based: it cannot tell a $174 SPY failure from a
$15,931 UUP failure, so it does not fix D3.

### Candidate B — residual-risk budget with an absolute backstop

```
HALT immediately if the failure class is HARD/system
        (risk refusal, identity mismatch, broker error, unknown state,
         terminality unestablished, reconciliation mismatch)
HALT if  stage_residual > max(R_ABS, R_PCT x equity)
HALT if  failed_ORDERS  > N_BACKSTOP
```

This is the owner's stated conceptual design. Continuation is decided on the economic exposure
left behind; the absolute backstop stops dozens of tiny stale names passing merely because the
total notional is small; hard failures never get a budget at all.

Additional continuation conditions to be enforced alongside the budget (not exercised by this
replay, since every observed failure was `stale_reference`):

- post-continuation projected gross and net exposure remain inside `risk_limits`;
- no residual name is economically in conflict with the incoming construction;
- every residual is written to the ledger and to a cleanup obligation.

The conflict test matters across manifests, not within one: a name that fails to exit today and
re-enters the top 40 tomorrow silently converts a residual into an intended holding. TSM is the
worked example — exited 2026-08-20 (seq 3, filled), bought 2026-08-21 (seq 42).

Candidate B under-protects `B_cross_asset`: see §7.

### Candidate C — per-stage declared policy, governed in the manifest ✅ recommended

Each stage declares its own continuation rule **inside the hashed manifest body**, so the owner
approves the rule together with the orders it will govern.

| stage | declared policy | rationale |
|---|---|---|
| `A_exits` | Candidate B budget | exits are de-risking; what is left behind is measurable legacy exposure |
| `B_cross_asset` | **completeness required** — any failure halts — triggered by a declared concentration test on the largest single order | the sleeve is a joint construction; a partial sleeve is a different allocation, not a smaller one |
| `C_equity` | Candidate A count rule **and** the Candidate B budget | many small, individually unimportant entries |

Global: hard/system failure halts immediately in every stage.

The concentration test is what makes Stage B's 6/6 a *rule* rather than an arithmetic accident:
when the largest single order is ≥ `CONCENTRATION` of stage notional, the stage is all-or-nothing
by declaration. Today UUP is 65.3 % of Stage B.

---

## 5. Replay evidence

Harness `v13_residual_policy_replay_v1.py` sha `cad33c04…` — read-only, imports nothing from
`app.orders` / `app.risk` / `app.brokers`, places no orders. Every case is built from a sealed
artifact; provenance SHA-256s are recorded in the evidence JSON.

Parameters used for the observed replay: `TOLERANCE = R_ABS = $250` (the existing frozen value),
`FLOOR = 2`, `PCT = 10 %`, `R_PCT = 0.25 %`, `N_BACKSTOP = 3`, `CONCENTRATION = 50 %`.

### 5.1 Observed failure sets — the three real runs

| case | stage | orders | failing **orders** | abort records | residual | P0 (current) | A | B | C |
|---|---|---|---|---|---|---|---|---|---|
| **C1** 08-20 **live** (45082b68) | A | 36 planned / 34 attempted | **2** — MS, PH | 4 | **$257.27** (0.2552 % of equity) | **HALT** `aborts>3` | **HALT** residual | **HALT** residual | **HALT** residual |
| **C2** 08-20 **dry** (same manifest, 23 min earlier) | A | 36 | **1** — FSLR | 1 | $191.13 imputed | CONTINUE | CONTINUE | CONTINUE | CONTINUE |
| **C3** 08-20 dry (30a53127) | C | 38 | **1** — ALAB | 1 | $65.07 | CONTINUE | CONTINUE | CONTINUE | CONTINUE |

**Reading C1 — the most important result in this document.** The actual halt of 2026-08-20 halts
under **every** candidate, including the purely economic ones. $257.27 exceeded the $250 budget on
its own. **No proposed amendment retroactively permits the run that was stopped.** Whatever is
adopted, the historical decision stands.

**Reading C3.** Manifest `30a53127` was retired over a single ALAB abort worth $65.07. No policy
here — nor the current one — would have halted on it. That retirement came from an owner
authorization stricter than the executor ("require every frozen gate to PASS"), not from the
protocol. That standing question is separate from this amendment and is flagged in §9.

### 5.2 Counterfactual sweep — where the candidates actually diverge

`k` = number of failing orders; *cheapest-k* and *dearest-k* bracket the real range.

**C4 — 2026-08-21 Stage A (5 orders, $757.28, largest order 22.4 % of stage)**

| k | cheapest set | residual | P0 | A | B | C |
|---|---|---|---|---|---|---|
| 1 | MS | $124.47 | **HALT** | CONTINUE | CONTINUE | CONTINUE |
| 1 | EBAY (dearest) | $169.58 | **HALT** | CONTINUE | CONTINUE | CONTINUE |
| 2 | MS, PH | $257.04 | HALT | HALT | HALT | HALT |
| 3 | MS, PH, FN | $422.27 | HALT | HALT | HALT | HALT |

The entire divergence between the current rule and every candidate is **the single-failure case**.
That is the denominator collapse, isolated: today one failing order out of five stops $27,941 of
construction over $124–$170 of residual.

**C5 — 2026-08-21 Stage B (6 orders, $24,381.68, largest order UUP 65.3 % of stage)**

| k | set | residual | P0 | A | B | C |
|---|---|---|---|---|---|---|
| 1 | SPY (cheapest) | $173.96 | HALT | **CONTINUE** ⚠ | **CONTINUE** ⚠ | **HALT** |
| 1 | UUP (dearest) | $15,931.10 | HALT | HALT | HALT | HALT |
| 2 | KMLM, UUP | $21,928.42 | HALT | HALT | HALT | HALT |

**This is the case that decides between the candidates.** A and B both continue after losing SPY,
because $174 is economically trivial. It is not structurally trivial: the sleeve would then be
built at the wrong weights. Only Candidate C — which declares Stage B all-or-nothing via the
concentration test — gets this right.

**C6 — 2026-08-21 Stage C (36 orders, $3,559.88, largest order TSM 6.9 %)**

| k | cheapest set | residual | P0 | A | B | C |
|---|---|---|---|---|---|---|
| 2 | GLW, CIEN | $108.46 | **HALT** | CONTINUE | CONTINUE | CONTINUE |
| 3 | GLW, CIEN, ASML | $165.88 | **HALT** | CONTINUE | CONTINUE | CONTINUE |
| 4 | GLW, CIEN, ASML, GOOGL | $224.94 | HALT | HALT | HALT | HALT |
| 2 | STM, TSM (dearest) | $389.04 | HALT | HALT | HALT | HALT |

Here the current rule **over-halts**: two trivially small entries stop the run over $108.46.
The k = 4 row shows the backstop earning its place — $224.94 is still *inside* the budget, and
B/C halt anyway because four failing orders exceed `N_BACKSTOP`. That is exactly the "dozens of
tiny stale names" case the owner asked to be protected against.

**C1 vs C2 at k = 2 — the unit mismatch, isolated.** Identical stage, identical orders, identical
two cheap failures ($212.16): P0 says **HALT** in the live case (4 abort records) and **CONTINUE**
in the dry case (2 abort records). Same failures, different verdict, solely because live retries.

---

## 6. Threshold sensitivity — the decision surface

Sweep `v13_residual_policy_sweep_v1.py` sha `fb622df4…`. Cell = smallest `k` at which the stage
halts under Candidate C. Higher = more permissive. Current rule for reference: C1 halts at k ≥ 2,
C4 at k ≥ 1, C5 at k ≥ 1, C6 at k ≥ 2.

**`R_ABS = $250`, `N_BACKSTOP = 2`** (the most conservative combination swept):

| case | 0.05 % | 0.10 % | 0.25 % | 0.50 % | 1.00 % | ← `R_PCT` of equity |
|---|---|---|---|---|---|---|
| C1 08-20 Stage A, cheapest | k≥3 | k≥3 | k≥3 | k≥3 | k≥3 |
| C1 08-20 Stage A, dearest | k≥2 | k≥2 | k≥2 | k≥3 | k≥3 |
| C4 08-21 Stage A | k≥2 | k≥2 | k≥2 | k≥3 | k≥3 |
| **C5 08-21 Stage B** | **k≥1** | **k≥1** | **k≥1** | **k≥1** | **k≥1** |
| C6 08-21 Stage C, cheapest | k≥3 | k≥3 | k≥3 | k≥3 | k≥3 |
| C6 08-21 Stage C, dearest | k≥2 | k≥2 | k≥2 | k≥2 | k≥2 |

Stage B is invariant at k ≥ 1 across **every** cell of the whole sweep — the concentration
declaration, not the budget, is what governs it.

Loosening is visibly dangerous at the top of the grid: at `R_ABS = $1000`, `N_BACKSTOP = 5`,
today's Stage A **never halts** — the whole stage is only $757.28, so the budget can never bind
and the backstop never trips. That combination should be excluded on its face.

### Derivation anchors — where a defensible `R_ABS` comes from

| anchor | value | provenance |
|---|---|---|
| frozen `tolerance_usd_per_stage` | **$250** | limits v5, ratified 2026-07-29 |
| modelled worst-stage residual at K=2 | ~$127 | `v13_reattempt_simulation.json`; $250 ≈ 2× |
| 5 % of account 7 `max_daily_loss` | **$250** | `risk_limits` id 9: $5,000 |

Two unrelated derivations land on $250. That is the argument for keeping $250 as `R_ABS` — it
predates this incident by three weeks and is not read off either residual. `R_PCT` has no such
pedigree yet and needs either an owner ruling or a calibration run (§9).

---

## 7. The Stage B question, answered

> Is Stage B intended to require 6/6 executable orders, or is that merely an arithmetic side effect
> of a generic percentage rule?

**Today it is an arithmetic side effect. It should be kept as policy, but re-derived and declared.**

The evidence:

- Stage B is structurally 6 orders. `6 × 10 % = 0.6 < 1`, so zero tolerance falls out of integer
  arithmetic. Nothing in limits v5 states the intent; the rule cannot be reviewed because it is
  not written down.
- The economic case for 6/6 is real but is **not** a size argument. C5 shows the failure: an
  economic budget alone continues after losing SPY at $173.96, and the resulting sleeve is built
  at wrong weights. The sleeve is a joint construction — a partial sleeve is a different
  allocation, not a smaller one.
- UUP is $15,931.10 = **65.3 %** of the stage. A stage in which one order is two-thirds of the
  notional is all-or-nothing by nature, and a *concentration* test says so in a way that survives
  the stage changing size.

So: keep 6/6, but reach it through a declared `completeness_required` flag triggered by a
concentration threshold, recorded in the manifest and approved with it. Then if the sleeve ever
grows to 12 names with no dominant leg, the policy adapts on its stated reason instead of
silently flipping when `12 × 10 % ≥ 1`.

The corollary — already an owner ruling of 2026-08-20 and unchanged here — is that **if UUP aborts,
the correct outcome is an aborted transition, not a relaxed gate.** Candidate C makes that outcome
follow from a written rule.

---

## 8. Recommendation

**Adopt Candidate C**, parameterised as:

| parameter | proposed | basis |
|---|---|---|
| `R_ABS` | **$250** | frozen limits v5; ≈ 2× modelled worst case; = 5 % of the daily-loss limit |
| `R_PCT` | **owner decision** — 0.05 %–0.25 % is the conservative band | no pedigree yet; §9 |
| `N_BACKSTOP` | **2 failing orders** | most conservative swept; preserves the "many tiny names" backstop |
| `FLOOR` (Stage C) | **2 orders** | stops denominator collapse without becoming permissive |
| `PCT` (Stage C) | **10 %** | unchanged from v1 |
| `CONCENTRATION` | **50 %** of stage notional | owner decision; UUP is 65.3 %, so 50 % is not a fitted value |

Properties of this parameterisation, all evidenced above:

- the 2026-08-20 halt still halts (§5.1, C1) — the amendment is not retroactive permission;
- Stage B stays 6/6, by declaration (§7);
- today's Stage A tolerates exactly one failing order and halts at two (§5.2, C4);
- the dry-run/live divergence caused by K=2 disappears, because the count is order-level;
- nothing that currently continues starts halting.

⚠ **One interaction to rule on.** `N_BACKSTOP` and Stage C's count rule overlap. At
`N_BACKSTOP = 2`, Stage C's `max(FLOOR, PCT × 36) = 3` never binds first — the backstop halts at
3 failing orders before the count rule reaches 4. At `N_BACKSTOP = 3` the two agree and Stage C
halts at 4. Either is defensible; the choice should be explicit rather than emergent. If the
backstop is meant as a *global* sanity limit rather than a per-stage tolerance, declaring it per
stage (2 for A and B, 3–4 for C) keeps both rules meaningful.

**What it explicitly does not do:** it does not change the 10 % denominator as a point fix, does
not reorder stages, does not exclude any name, does not extend the 300 s threshold, and does not
force downstream buys. All five remain forbidden.

---

## 9. Open items requiring an owner decision

1. **`R_PCT`.** No defensible derivation exists yet. Options: (a) rule it directly; (b) set
   `R_PCT = 0` and rely on `R_ABS` alone, which is fully defensible today and can be revisited
   when the account is materially larger; (c) commission a calibration deriving it from the
   adverse 1-day move distribution on residual-prone names, in the style of
   `v13_reference_age_calibration`.
2. **`CONCENTRATION` threshold.** 50 % is proposed as a round number well below the observed
   65.3 %, deliberately not fitted. Alternative: declare `completeness_required` per stage by hand
   at manifest generation, with concentration only as a warning.
3. **Residual cleanup obligation.** Where does a disclosed residual go — a follow-up manifest, the
   strategy's own next scheduled rebalance, or an explicit operator task? "Do not silently drop
   residual names" needs a named destination.
4. **The "every gate must pass" authorization (C3).** Independent of this amendment: as written it
   burns a manifest on any single stale name out of ~80 orders. Keep, or align with the protocol's
   own tolerance?
5. **Whether this becomes an ADR.** It changes a governed execution invariant, which by CLAUDE.md
   convention is ADR territory.

---

## 10. Implementation and test plan — not started

Deliberately not begun, per the owner's separation of concerns. Proposed shape:

1. Extend limits v5 → **v6**: add `continuation_policy` per stage (`mode`, `R_ABS`, `R_PCT`,
   `N_BACKSTOP`, `FLOOR`, `PCT`, `completeness_required`, `concentration_trigger`). Every numeric
   order-level gate byte-identical to v5.
2. Planner: embed the per-stage continuation policy in the hashed manifest body, and compute
   `largest_order_share_of_stage` per stage so the concentration trigger is reviewable pre-approval.
3. Executor `check_stop_conditions`: count **orders**, not attempt records; evaluate hard-failure →
   budget → backstop in that order; keep the residual ledger as the single source of residual truth.
4. Failure-class taxonomy in `execute_logical_order`: tag each abort HARD vs EXECUTABILITY.
5. Tests: extend `test_v13_executor_v7.py` (46/46 today) with the six replay cases as fixtures, so
   every case in §5 becomes a regression test — including the assertion that C1 still halts.
6. Re-conformance of all five suites, then re-seal the stack SHAs.

---

## 11. Artifacts

| artifact | path | SHA-256 |
|---|---|---|
| replay harness | `data/ops/acct7/v13_residual_policy_replay_v1.py` | `cad33c04de590779eed9795e4202079e69db388bcb78a721018f07213ff8d147` |
| sweep harness | `data/ops/acct7/v13_residual_policy_sweep_v1.py` | `fb622df47852313398c3f8b0baed45c7a898dc3620f16a9ec7d1e985b43ae0e2` |
| replay evidence | `data/v13_transition/PROTOCOL_V2_POLICY_REPLAY_20260821.json` | `955ca9cdb82a912226ae07e59bb100145dbab9299601f3fe9ef733e7b497ad02` |
| sweep evidence | `data/v13_transition/PROTOCOL_V2_THRESHOLD_SWEEP_20260821.json` | `0f9a224cc9aa8dd871662fccc777f55cc95bb9392910daafad15462243a18e20` |
| disposition of `0a0079d4…` | `data/v13_transition/DISPOSITION_OTR-20260821T140319Z-S9.json` | file `0846a860ec75ae2a37848c8ffbfd86dd4aa3bf70980567def2bca193f05d1c2a` · body-self `05cece8468101e59d341506bd52eb53bc2cc51496c1e5c12fc34527bb4fee50e` |

Paths are relative to `/opt/workbench/` on `ec2-paper`. All evidence files are mode 0444.

Source artifacts replayed (provenance SHA-256s recorded inside the evidence JSON):
`OTR-20260820T164912Z-S9.json` · `.residual.v3.jsonl` · `.execution.v3.dryrun.jsonl` ·
`OTR-20260820T162605Z-S9.json` · `.execution.v3.dryrun.jsonl` · `OTR-20260821T140319Z-S9.json`.
