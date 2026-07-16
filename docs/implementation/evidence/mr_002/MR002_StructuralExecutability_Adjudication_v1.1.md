# MR-002 v1.1 — STRUCTURAL-EXECUTABILITY ADJUDICATION PACKAGE

**Date:** 2026-07-12 · **Status:** ⏸ **STOPPED FOR OWNER ADJUDICATION — no performance has been
inspected.**

Pre-Registration v1.1 rev 3, countersigned 2026-07-12, artifact sha256
`311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5`.

The authorized sequence is complete through step 5. **P&L, returns, Sharpe, hit rate, drawdown and
configuration comparisons have NOT been computed, printed or persisted. Validation and sealed OOS
remain sealed and unread.**

---

## The finding

**v1.1 is structurally executable. The joint LP/QP construction produces 138 orders across 17 of the
same 124 sessions on which v1.0 produced zero.** Every registered constraint holds, every solver check
passes, and the run is byte-identical on repetition.

| | v1.0 (invalidated) | **v1.1** |
|---|---|---|
| Orders, same 124 sessions | **0** | **138** |
| Sessions with orders | 0 | **17** |
| Sessions with material gross | 0 | **18** |
| Fixtures passing | 8/8 (of a design that could not trade) | **27/27** |

---

## 1. Frozen runtime (Appendix B.6)

Linux/amd64 standalone offline image. No live database, no broker connection, no market-data websocket;
the research store is mounted read-only. **No structural or determinism evidence was produced on
Windows.**

| Field | Value |
|---|---|
| Image | `mr002-research:v1.1` · digest `sha256:1b0939e563d010ea96df50c7f07c5a5015c96c8e521352f3a0aa862a25212758` |
| Base | `python@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7` |
| OS | Debian GNU/Linux 12 (bookworm), glibc 2.36, x86_64 |
| Python / NumPy / SciPy | 3.13.14 / 2.2.6 / 1.18.0 |
| **HiGHS** | **1.12.0** (vendored by SciPy) |
| quadprog | 0.1.13 · **Linux artifact sha256 `cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff`** |
| Dependency lockfile | sha256 `f593604200fa681b8ab51988c7f14a8b04e514cc2cd13a78de4400f07d6dddc8` (generated **inside** the image) |
| Thread pins | all five **asserted**, not merely set |
| Manifest verdict | **VALID** |

**Tolerance contract VERIFIED, not assumed.** SciPy never echoes the applied tolerance back, so the
manifest verifies it discriminatively: `1e-10` is accepted **silently** (proof it reached HiGHS) while
`1e-11` **warns** and, under the frozen fatal-warning policy, **raises**. Verdict: **HONORED**.

Artifacts: `runtime/MR002_SolverRuntimeManifest.json`, `runtime/MR002_StructuralSlice_v1.1.json`.

---

## 2. The 27 fixtures — **27/27 PASS inside the frozen image**

All three rev-3 fixtures pass, including the two that pin the owner's rulings:

- **D1 (fixture 25):** a holding at 2.0% of NAV, sector-neutral within XLK and with new candidates in
  six disjoint sectors, is **retained in full at 2.0%** — *not trimmed to 1.5%*. The 1.5% limit is a
  **new-entry sizing cap**, exactly as ruled. The converse (25b) confirms an over-cap holding **is**
  reduced when a *coupling* constraint requires it — never for the cap itself.
- **D2 (fixture 26):** the silent-fallback path is demonstrated to be real (a below-floor tolerance is
  rejected while `linprog` still returns `success=True`), and the fatal-warning policy stops it.
- **D3 (fixture 27):** a below-floor exposure is carried as fixed `BELOW_NUMERICAL_INCLUSION_FLOOR`,
  stays in gross/sector/net/beta accounting, and never enters the Hessian.

---

## 3. Structural slice — 124 sessions, config B

### Executability

| Metric | Value |
|---|---|
| Sessions | 124 (2013-01-02 → 2013-06-28) |
| **New orders** | **138** across **17** sessions |
| Reductions | 126 |
| Exits | 105 |
| `VALID_ZERO_ENTRY_OUTCOME` days | 103 |
| `EXECUTION_CONSTRAINED_INFEASIBLE` days | **3** (2013-05-14, -15, -16) |
| `INVALID_RUN` | **0** |

### Gross (registered as an intended consequence)

Material-gross sessions: **18**. Min **0.004%**, median **4.52%**, max **7.08%** of NAV. **Low gross is
registered as an intended consequence of retaining the risk limits, not a defect.**

### Sector topology

Active sectors on material-gross days: **min 6, max 9** — consistent with the registered arithmetic that
**≥ 5 sectors are required for any positive feasible portfolio**.

### Constraint compliance — the **division-free** registered measure

**`max_homogeneous_violation = 1.34e-16`** against a limit of **1e-9**, taken as the maximum over every
homogeneous coupling row re-evaluated on the *realized* allocation.

Ratios, computed **only** on material-gross days, sit exactly on their caps — the constraints are
binding, which is what a correctly-specified LP should do:

| | Observed | Cap |
|---|---|---|
| Sector gross | 0.20000000000001 | 0.20 |
| Sector net | 0.05000000000004 | 0.05 |
| Beta | 0.10000000000000 | 0.10 |
| Net drift | 0.05000000000000 | 0.05 |

### Solver

| | Observed | Limit |
|---|---|---|
| Max KKT residual | **1.14e-12** | 1e-8 |
| Max `hessian_condition_number` κ(H) | **40,679** | 1e10 |
| LP statuses observed | **{0}** only | 0 |

### Determinism

The slice was run twice in the same image: the report is **byte-identical**
(`cf27ee15351cb96ad8c65749404256f955f2ae0b43c4d7f395649d86f2eb6b6b`). 115 per-day determinism hashes
recorded.

### Diagnostics

`EXISTING_POSITION_OVER_ENTRY_CAP`: **0 days** (no holding drifted above 1.5% in this slice, so the D1
ruling is untested by the *data* — it is tested by fixtures 25/25b). Below-floor excluded mass:
**1.6e-8** existing, **0** candidate — economically nil, and never removed from the accounting.

---

## 4. Defects found and fixed during development (disclosed)

Per the Implementation-Freeze standard — *"a defect found during development may be fixed; a change
intended to improve expected performance may not."* **Neither of these changes any economic rule.**

### Defect 1 — the lexicographic band audit was tighter than the registered residual policy

**Symptom:** `INVALID_RUN` on 2013-02-28 — `R = R* − 1e-8` failed the band audit by ~2e-19.

**Cause:** Stage 3 legitimately spends the full registered ε of retention slack (that is precisely what
`R ≥ R* − ε_retention` permits), landing **on** the boundary. That constraint is a **row of the primal
system**, so it is satisfied to the registered `primal_residual ≤ 1e-9` — not exactly. My audit
re-checked it with **zero** tolerance, contradicting the registered acceptance rule and failing on
floating-point noise.

**Fix:** the band audit now allows `ε + PRIMAL_RESIDUAL_MAX`, consistent with the registered residual
policy. No economic quantity changes; ε is $0.10 on a $10M book.

### Defect 2 — the structural **report** re-introduced division by G

**Symptom:** the first report showed `max_sector_gross_ratio = 16.0`, `beta = 22.2`, `net = 31.0` —
absurd values far above the caps.

**Cause:** those are `value / G` **ratios**, and on economically-empty sessions `G` is solver dust
(~1e-17 NAV weight) left by reductions that did not land on exactly zero. Dividing by dust manufactures
meaningless numbers. **This is the very pathology the homogeneous constraint form was adopted to
eliminate — and I had re-introduced it in the reporting layer.** The *constraints themselves* were never
violated (`max_homogeneous_violation = 1.3e-16`).

**Fix:** compliance is now attested by the **division-free** `max_homogeneous_violation`, which is
well-defined at `G = 0`. Ratios are emitted only when gross exceeds the frozen 1e-6 reporting threshold,
and are explicitly labelled as reporting-only. **The corrected ratios sit exactly on their caps.**

*Lesson, for the record: a division-free constraint formulation protects the solver but not the report.
The pathology can re-enter anywhere a ratio is displayed.*

---

## 5. What this evidence does and does not establish

**It establishes:** the registered v1.1 design is **implementable and executable**; it trades; every
registered risk limit binds correctly; the solver is numerically sound and byte-reproducible; the three
day-outcome classes all occur and are correctly distinguished.

**It does NOT establish — and must not be read as — anything about profitability.** No P&L, return,
Sharpe, hit rate, drawdown or configuration comparison has been computed. **Whether MR-002 has an edge
is entirely unknown and remains unknown until the development run is authorized.**

Two properties are worth the owner's attention *as structural facts*, not as performance signals:

1. **Orders occur on 17 of 124 sessions (14%)** and gross peaks at 7.1% of NAV. Capital deployment is
   sparse and slow. This is the **registered intended consequence** of the sector-net limit against
   sparse residual signals. If the eventual development run fails the ≥500-trade / ≥100-long /
   ≥100-short breadth gates on this basis, **that is a legitimate research result** and no gate moves.
2. **Three consecutive `EXECUTION_CONSTRAINED_INFEASIBLE` days** (2013-05-14/15/16) — fixed
   non-tradable exposure made the coupling constraints unsatisfiable. Correctly classified, correctly
   distinguished from solver failure and from a valid `Q*=0`, and correctly resumed afterward.

---

## 6. Requested adjudication

**Is structural executability ACCEPTED?**

- **If accepted:** the prohibition on performance inspection lifts, and the full A/B/C development run
  over the 1,700-session development window proceeds, followed by the Implementation-Freeze review.
- **If not accepted:** state the deficiency. Per §11, *no further economic-design change will be made
  merely because gross, feasible-day count or order count is lower than hoped* — **only an
  implementation or mathematical defect may reopen v1.1.**

**Nothing further will be run until you rule.**
