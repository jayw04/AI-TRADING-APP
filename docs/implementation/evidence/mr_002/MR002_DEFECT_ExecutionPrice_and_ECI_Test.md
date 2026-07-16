# MR-002 v1.1 — TWO IMPLEMENTATION DEFECTS THAT INVALIDATE THE DEVELOPMENT RUN

**Date:** 2026-07-12 · **Status:** 🛑 **DEVELOPMENT RUN INVALID — DISCARD. Separate adjudication
required.**

Raised under the Full Development-Run Authorization: *"Any later implementation defect must be
documented and adjudicated separately."*

| Bound artifact | SHA-256 |
|---|---|
| Pre-Registration v1.1 rev 3 | `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Structural adjudication | `ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e` |
| Stage-3 retry erratum (countersigned) | `9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb` |

---

## 0. Bottom line

The 1,700-session A/B/C run **completed with zero `INVALID_RUN`**, and the Stage-3 cascade worked exactly
as registered (4 rescues across A/B/C, all passing every original-coordinate check). **But the harness
suppressed trading on 61–81% of sessions for two spurious reasons.** The performance figures it produced
are **artifacts of the defects, not evidence about MR-002**, and they must not anchor any decision.

**Performance was inspected** — that was authorized once the clean run completed, and the development
window is not blind. **But the numbers are void.** They are recorded below only to show the *magnitude of
the distortion*, never as a research result.

**Validation and sealed OOS remain SEALED AND UNREAD.**

---

## 1. The signal that something was wrong

| | Structural slice (124 sessions) | **Full run, config A (1,700)** |
|---|---|---|
| `EXECUTION_CONSTRAINED_INFEASIBLE` | 3 (2.4%) | **1,371 (81%)** |

An 81% infeasibility rate is not a market condition. The 124-session slice never surfaced it because the
book was still nearly empty in the first six months — **the slice was too short to exercise the
held-position path at all.** That is itself a lesson about the structural gate.

---

## 2. DEFECT A — execution prices for HELD positions are drawn from the ENTRY-eligibility funnel

`dataset.py` builds `open_next` **only** for `members = self._uni_at(d)` — the day's PIT ranking universe
— and then `continue`s past any member with a **non-finite z** or an **unresolved sector**.

Those are **entry** criteria. They are being used to decide whether an **already-open position can
trade**. A position whose symbol leaves the top-250/top-150 universe, or whose z is momentarily
non-finite, or whose sector is unresolved on that day, silently loses its execution price.

### Measured (config A, 1,700 sessions)

| | Count | |
|---|---|---|
| Held-position days | **3,048** | |
| Marked `NO_EXECUTABLE_OPEN` (non-tradable) | **1,389** | **45.6%** of all held-position days |
| …of which **a valid price bar EXISTS in the frozen store** | **948** | **68.3% of them are SPURIOUS** |
| …genuinely missing bar (legitimate) | 441 | 31.7% |

**Two-thirds of every "no executable open" classification is false.** The market traded, the open price is
sitting in the frozen store, and the harness refused to use it.

### Why one spurious fixed position destroys an entire session

A fixed exposure `f` is a **constant** in the constraint system. Evaluate the coupling rows at `y = 0,
x = 0`: the book is *only* that position, so

```
sector_gross_k / G  =  f / f  =  1.00   >   0.20
```

**Any single fixed position breaches the 20% sector-gross cap on its own.** So one spuriously-fixed
holding is enough to classify the whole day `EXECUTION_CONSTRAINED_INFEASIBLE` and cancel every new entry.

**It also blocks exits.** The runner's exit path takes `px = inp.open_next.get(...)`; with no price the
exit "stays PENDING". Positions that should have closed on the 5-session limit stayed open, compounding
the problem on subsequent days.

### The fix (implementation, non-economic)

Execution prices for **held** positions must come from the **price store**, not from the entry funnel. A
position is `NO_EXECUTABLE_OPEN` **only when the market genuinely has no open bar for it** — a halt or a
delisting — never because it fell out of the ranking universe or momentarily lacked a z-score.

*Eligibility governs what may be ENTERED. It must never govern what may be EXITED or REDUCED.*

---

## 3. DEFECT B — the ECI test asks the wrong question

Registered wording (v1.1 §7 / Appendix A): *"Fixed exposures (`f`) violate a coupling constraint … **even
with all `y = 0` and all `x = 0`**."*

I implemented that literally: probe the coupling rows at `z = 0`; if they breach, declare
`EXECUTION_CONSTRAINED_INFEASIBLE`.

**That is not a test of infeasibility.** `z = 0` being infeasible does **not** imply the LP is infeasible.
New orders `x` **dilute** a fixed exposure — they *increase* `G`, which *lowers* every ratio. A book that
breaches at `z = 0` can be perfectly feasible at `z > 0`. This is the exact scale-invariance that
invalidated v1.0, reappearing in the infeasibility *test* rather than in the construction.

### Measured

Of the **1,371** sessions my probe declared `EXECUTION_CONSTRAINED_INFEASIBLE` in config A, HiGHS finds
the Stage-3 LP region **actually feasible** on **261** of them.

**261 sessions were falsely suppressed even granting the spurious fixed positions of Defect A.**

*(The other 1,110 are genuinely infeasible LPs — but overwhelmingly because Defect A manufactured the
fixed positions in the first place. A single unhedged fixed position at 1.5% of NAV requires `G ≥ 20 × f =
30% of NAV` to satisfy the 5%-of-gross sector-net cap; the book's median gross is **0.14%**. So a spurious
fixed position is close to unsurvivable.)*

### The fix (implementation, non-economic — but it touches registered TEXT)

The correct test of *"no `(y, x)` can satisfy the coupling constraints"* is **LP infeasibility**, which
Stage 1 already determines: `EXECUTION_CONSTRAINED_INFEASIBLE` ⇔ **the Stage-1 LP returns status 2
(infeasible)**.

This matches the **intent** of the registered definition — fixed exposures make the combined book
infeasible and *nothing can cure it* — while replacing a test that is not equivalent to that intent.

> **⚠️ This one requires the owner's ruling, because it corrects registered TEXT, not merely my code.**
> The phrase *"even with all y = 0 and all x = 0"* encodes a check that is neither necessary nor
> sufficient for infeasibility. I am not changing a registered definition unilaterally.

---

## 4. The void figures (magnitude of distortion ONLY — not a result)

> **These are NOT a research result and must not anchor any decision.** They are the output of a harness
> that suppressed 61–81% of sessions and blocked exits. Recorded solely to show how badly the defects
> distorted the run.

| | A (z=1.75) | **B (z=2.00, verdict cfg)** | C (z=2.25) |
|---|---|---|---|
| ECI sessions | 1,371 (81%) | 1,032 (61%) | 897 (53%) |
| Feasible entry sessions | 59 | 47 | 6 |
| Trades | 668 | 397 | 67 |
| Median gross | 0.144% | 0.120% | 0.020% |

**No verdict may be drawn from these.** MR-002 has still never been tested on an economically valid
portfolio path.

---

## 5. What DID work (retained)

The countersigned Stage-3 cascade behaved exactly as registered, on the full window:

| | A | B | C |
|---|---|---|---|
| Raw solves | 272 | 525 | 474 |
| **`SCALED_RESCUE`** | **3** | **0** | **1** |
| `INVALID_RUN` | **0** | **0** | **0** |
| Max KKT residual | 1.46e-11 | 1.80e-12 | 8.31e-12 |
| Max homogeneous violation | 3.42e-16 | 2.86e-16 | 1.90e-16 |
| LP statuses | {0} | {0} | {0} |
| Session determinism hashes | 1700/1700 | 1700/1700 | 1700/1700 |
| Funnel reconciliation | 1700/1700, 0 unclassified | ✓ | ✓ |

**43 fixtures pass. All 124 structural-slice decision hashes are unchanged. The erratum is sound.** The
defects reported here are upstream of the solver, in the data plumbing and in the ECI test.

---

## 6. Requested adjudication

1. **Defect A** — approve the execution-price fix (held positions price from the store; `NO_EXECUTABLE_OPEN`
   means a genuinely absent bar). *Implementation-only; no economic rule changes.*
2. **Defect B** — approve replacing the `z = 0` probe with **Stage-1 LP infeasibility** as the definition of
   `EXECUTION_CONSTRAINED_INFEASIBLE`. **This corrects registered text and needs your explicit ruling.**
3. **Discard the completed development run** and re-run clean from session 1 after both fixes.
4. Consider whether the **structural gate should be lengthened** — the 124-session slice could not
   surface either defect because the book was still nearly empty.

**Nothing further runs until you rule. Validation and sealed OOS remain sealed and unread.**
