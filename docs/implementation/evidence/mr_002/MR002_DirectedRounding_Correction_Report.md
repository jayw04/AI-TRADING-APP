# MR-002 v1.1 — Directed-Rounding Correction and Full-Population No-Verdict-Flip Proof

**Status:** CORRECTION **PASS** · zero verdict changes over the complete affected population · not
countersigned
**Authorization:** owner ruling 2026-07-14, directed-rounding correction §1–§9
**Commit:** `347f398d73648f33f18d2145d747b4c91b001624` (declared before execution)
**Image:** `mr002-research@sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`

**Performance: NOT COMPUTED. Validation and sealed OOS: SEALED AND UNREAD. Preflight and the
development run: STOPPED. Erratum: UNDRAFTED.**

---

## 1. Outcome (§4, §9)

```
affected verdicts evaluated  = 27,265   (= the complete affected population)
corrected verdict changes    = 0
unclassified records         = 0
non-finite corrections       = 0
```

| | |
|---|---|
| instances (registered corpus, hash verified) | 3,895 |
| solvers | 7 |
| (instance, solver) pairs | **27,265** |
| certificates rebuilt | 26,455 |
| solver exceptions (no value ever serialized) | 810 |
| serialized field records | **264,550** |
| verdict flips `L → D` | **0** |
| verdict flips `N → D` | **0** |
| verdict flips `D → EXACT` | **0** |

`26,455 + 810 = 27,265`. Every pair is accounted for.

## 2. Why three serializers, not one comparison

The defective nearest-rounding serializer **was never committed** — it existed only in a working
tree. Git therefore cannot establish which of the 2026-07-13 artifacts it produced, and guessing
would put an assumption underneath the proof.

So the archaeology was made unnecessary. The corpus is frozen and the solvers are deterministic, so
every certificate any past run could have produced is reproducible. Each is recomputed under every
serializer that has existed in this program, and zero flips are required under **every** pairing:

| | serializer | status |
|---|---|---|
| **L** | `float(x)` — round to NEAREST | **the defect.** Not a bound in either direction. |
| **N** | `nextafter(float(x), ±inf)` | rigorous but 1–2 ulps loose; maps an exact `0` lower endpoint to `-5e-324`. |
| **D** | correctly directed | **the correction.** The tightest double on the correct side. |
| **EXACT** | pure rational, no binary64 | **the authority** all three are judged against. |

If no verdict differs between L, N and D, the retained Booleans are unaffected *regardless of which
serializer wrote them*.

## 3. The registered verdict, not half of it

The first pass evaluated only the **signed-gap half** of the gate and reported it as the verdict. It
returned zero flips, and its load-bearing numbers matched the record exactly (`QUADPROG_SQRT` = 5,
cascade unresolved = 0) — so it would have been easy to ship.

It did not reconcile. `HIGHS_QPASM` came out **454** against a recorded **592**.

The registered verdict is `canonical_qualify` = **(no KKT limit violated) AND (signed-gap gate
passes)**. The KKT half never touches the serializer, so it cannot flip under rounding and the
conclusion was never in doubt — but §4 asks for the corrected result of the *registered gate*, and a
proof about a sub-component is not a proof about the gate. Both halves are now evaluated, and the
gap-only view is recorded separately (`signed_gap_gate_only_nonqualifications`) so the two can never
be confused again.

A notable by-product: the primary solver's gap-only nonqualification count is **0**. All five of its
registered nonqualifications are **KKT-limit failures**, not signed-gap failures.

## 4. Reconciliation against the predecessors (§6)

Recomputed **registered** verdicts (D), against every retained artifact carrying verdicts:

| solver | D (now) | gap-only | `ComplementaryCoverage` | `R2_RegressionSampleA` | `RepairSizingSample` |
|---|---|---|---|---|---|
| QUADPROG_SQRT *(cascade primary)* | **5** | 0 | 5 | 5 | 5 |
| PIQP_P2 *(cascade fallback)* | 51 | 2 | 50 | 51 | 51 |
| PIQP_P1 | 59 | 2 | 58 | 59 | 59 |
| QUADPROG_RAW | 70 | 7 | 70 | 70 | 70 |
| QUADPROG_TSCALED | 185 | 0 | 185 | 185 | 185 |
| CLARABEL | 29 | 20 | **9** | 29 | 29 |
| HIGHS_QPASM | 592 | 7 | 592 | 592 | 592 |
| **cascade unresolved** | **0** | — | 0 | 0 | 0 |

The recomputation matches `R2_RegressionSampleA` and `RepairSizingSample` on **all seven solvers**,
and matches all three on the load-bearing figures.

`MR002_ComplementaryCoverage.json` differs on CLARABEL / PIQP_P1 / PIQP_P2 — **and it also disagrees
with the other two retained artifacts** (CLARABEL 9 vs 29). It therefore predates a code correction,
not a rounding difference: `certificate.py` records that "a hand-rolled Clarabel dual mapping
produced a false verdict earlier in this program," and the mapping was subsequently fixed and
centralised. This is a known, already-corrected defect. It is **not** attributable to serialization —
rounding is proven to flip nothing (§1).

### Disposition per predecessor (§6) — no predecessor is edited

| artifact | sha256 | serialized bounds | Boolean verdict |
|---|---|---|---|
| `MR002_ComplementaryCoverage_Certified.json` | `47215cd2…` | **defective** (superseded) | **unaffected by rounding.** Already superseded on its own terms (nonnegative-gap rule invalidated; gate FAIL; retained immutable). |
| `MR002_ComplementaryCoverage.json` | `790002c0…` | **defective** | **unaffected by rounding.** Its CLARABEL/PIQP counts predate the Clarabel dual-mapping fix and are superseded on that separate ground. |
| `MR002_R2_RegressionSampleA.json` | `2719e354…` | **defective** | **unaffected.** Verdicts reproduce exactly. |
| `MR002_RepairSizingSample.json` | `aa0f4cf1…` | **defective** | **unaffected.** Verdicts reproduce exactly. |

Prior Boolean conclusions may stand. **The old serialized endpoints are superseded.**

## 5. Margins (§5) — explanatory only; §1 is the proof

| gate | records | max \|L − D\| | min authoritative margin | min corrected margin | within 1 ulp | within 10 ulps | capable of flipping |
|---|---|---|---|---|---|---|---|
| signed-gap band | 52,910 | **1 ulp** | −4.116754e-06 | −4.116754e-06 | **0** | **0** | **0** |
| interval-width limit | 52,910 | 0 ulp | 1.000000e-30 | 1.000000e-30 | **0** | **0** | **0** |
| dual_lower (reused as a downstream input) | 26,455 | **1 ulp** | — | — | **0** | **0** | **0** |

The serialization error is bounded at **1 ulp**, and **not one record in the population lies within
10 ulps of any threshold**. That is a per-record count on the IEEE-754 bit pattern, not a margin
argument — the negative minimum margin is simply a genuinely nonqualifying certificate, which fails
under every serializer alike.

## 6. A defect found in the correction itself, by measurement

The first serializer reported `max |L − D| = 0 ulps` **everywhere**. Nearest and directed rounding
never once disagreed.

That would have been written up as "the correction is a no-op." It was a broken instrument.

`iv.mpf(...).b` returns an **`ivmpf`**, not an `mpf`. `as_fraction` fell through to `mpf(v)`, which
converts at the **current `mp` precision — 15 decimal digits by default**. A 336-bit interval
endpoint was being rounded to 53 bits *before* anything reasoned about how to round it to 53 bits.
Every serializer then trivially agreed with every other.

**The zero was the tell.** On genuine high-precision endpoints, nearest and directed rounding *must*
disagree roughly half the time. After the fix: `max |L − D| = 1 ulp`, as it has to be.

The fixtures missed it because they fed the serializer `mpf` and `Fraction` values, while production
hands it an `ivmpf` — the suite tested a type the call site never uses. It now tests the real call
site and **pins the disagreement rate** (20–80 per 100): a rate near 0 *or* 100 now fails, because
either means precision is being destroyed rather than rounding agreeing.

## 7. Also corrected: `_width` was a bound in diagnostic's clothing

`_width` gates (`fw <= 1e-30`) but rounded to **nearest**, so it could report a width *below* the
true one and admit an interval wider than the limit allows. It reads like a diagnostic. It is a
bound. Now rounded up.

## 8. Fixtures (§8) — 37, all required cases present

Positive upper endpoint that nearest rounds **down**; negative lower endpoint that nearest rounds
**up**; exactly-representable endpoints; halfway cases (including at the 1e-10 gate scale); positive
and negative subnormals; subnormal-to-subnormal gaps; signed zero (`+0.0` bit-exact, and the
`-5e-324` spurious-negative regression); overflow and non-finite **refusal** (`+inf` is a formally
valid upper bound and a useless one); the largest finite double and one ulp past it; **real interval
endpoints** at full precision; refusal to serialize a whole interval; soundness **and tightness**
against the exact rational across nine scales.

Two negative controls, without which the suite could pass trivially:
* nearest rounding **demonstrably produces non-bounds** (else the premise of this correction is
  false);
* L and D **disagree on 20–80 of 100** real interval endpoints (else the precision is being
  destroyed).

An artificial near-boundary verdict that flips under inward rounding is covered by the
`capable_of_flipping` counter, which is **0** in the population and is reconciled against the
observed flip count of **0**.

## 9. Provenance (§7)

Run from the declared commit, with in-container source hashes:

| file | sha256 |
|---|---|
| `app/research/mr002/directed.py` | `7f8d44d252512f76…` |
| `app/research/mr002/certificate.py` | `c679eb39bcabd900…` |
| `app/research/mr002/joint_portfolio.py` | `4efd57393e2d99e0…` |
| `scripts/mr002_directed_rounding_correction.py` | `60010457ecfbc393…` |
| `scripts/mr002_coverage_signed_gap.py` | `66118bc787bb8590…` |
| `scripts/mr002_solver_intersection.py` | `ee1aacf37c1a81ec…` |
| `tests/research/test_mr002_directed_rounding.py` | `31039480dac0f447…` |

*(the correction artifact records the full 64-hex digests; the run's own hashes are recomputed inside
the container from the files `import` resolved, not from the host)*

| artifact | sha256 |
|---|---|
| `MR002_DirectedRounding_Correction.json` | `93666948d3a0156833ce7dcf399640915a4283b2269ae65e465b2f10d46bd822` |
| `MR002_DirectedRounding_Inventory.jsonl.gz` (264,550 records) | `7d9ae937e62330b7dc0fe5703d01b585cdf7c8e9e270ea29ff8788536c88987c` |

Corpus reproduced exactly: `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
Wall-clock 627s.

Reproduce:

```
docker run --rm -e MR002_COMMIT_SHA=347f398 -e MR002_IMAGE_DIGEST=sha256:aa930021… \
  -v <repo>:/work -v <out>:/out mr002-research:v1.4 \
  python /work/apps/backend/scripts/mr002_directed_rounding_correction.py
```

## 10. §9 outcome rule

```
complete population evaluated        27,265 / 27,265   ✓
zero corrected verdict changes       0                 ✓
zero unclassified                    0                 ✓
zero non-finite corrections          0                 ✓
provenance + fixture gates pass                        ✓
-> directed-rounding correction CLOSES; proceed to Sample A
```

Nothing else was changed: no solver profile, no cascade order, no signed-gap tolerance, no repair
formulation, no agreement gate, no economic specification.
