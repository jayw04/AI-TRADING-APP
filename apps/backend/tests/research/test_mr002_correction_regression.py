"""MR-002 — the correction's OWN regression guards (owner ruling §3).

Two implementation defects were found DURING the directed-rounding correction, and both produced
results that looked clean. Neither must be able to return silently.

  PRECISION-LOSS. An interval endpoint was converted through a default-precision `mpf` path, cutting
  a 336-bit value to 53 bits BEFORE anything reasoned about rounding it to 53 bits. Every serializer
  then agreed with every other and the sweep reported zero difference everywhere. A universal zero is
  not exact agreement — it is a broken instrument.

  PREDICATE-SCOPE. The reconciliation evaluated signed-gap qualification instead of the complete
  registered predicate (KKT AND signed-gap), and did not reconcile against the recorded HiGHS count.

So the counts themselves are pinned. A correction that finds NO disagreement anywhere now FAILS.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from mpmath import iv

from app.research.mr002.directed import (
    as_fraction,
    legacy_nearest_up,
    to_binary64_up,
)

EVIDENCE = pathlib.Path(__file__).resolve().parents[4] / "docs/implementation/evidence/mr_002"
iv.dps = 100


@pytest.fixture(scope="module")
def correction() -> dict:
    p = EVIDENCE / "MR002_DirectedRounding_Correction.json"
    if not p.exists():
        pytest.skip("correction artifact absent")
    return json.loads(p.read_text(encoding="utf-8"))


def test_the_serializer_preserves_FULL_PRECISION_to_the_final_conversion():
    """The precision-loss defect, pinned. A real interval endpoint must still carry hundreds of bits
    when it reaches the directed conversion — not 53."""
    third = iv.mpf(1) / iv.mpf(3)
    assert as_fraction(third.b).numerator.bit_length() > 300


def test_legacy_and_directed_rendering_DISAGREE_at_the_expected_rate():
    """If L and D agreed everywhere, the correction would be measuring nothing. On genuine
    high-precision endpoints they must disagree about half the time. A rate near 0 (or 100) means the
    precision is being destroyed before the comparison — which is exactly what the defect did."""
    disagree = sum(
        to_binary64_up(iv.mpf(1) / iv.mpf(2 * k + 1)) != legacy_nearest_up(iv.mpf(1) / iv.mpf(2 * k + 1))
        for k in range(1, 101)
    )
    assert 20 <= disagree <= 80, (
        f"L and D differed on {disagree}/100 endpoints — near 0 or 100 means the instrument is "
        f"broken, not that the rounding agrees")


def test_the_population_sweep_OBSERVED_a_nonzero_rendering_disagreement(correction):
    """The sweep itself must have SEEN the serializers disagree. `max |L - D| = 0 ulps` across a
    quarter-million records was the tell that the instrument was broken."""
    m = correction["margins"]["signed_gap_band"]["max_inward_rounding_error_ulps"]
    assert m >= 1, "the sweep observed NO L-vs-D difference anywhere — broken instrument, not a pass"


def test_the_COMPOSITE_verdict_is_what_was_counted_not_the_signed_gap_half(correction):
    """The predicate-scope defect, pinned. The registered verdict is KKT AND signed-gap. Counting only
    the signed-gap half gave HIGHS_QPASM = 454 against a recorded 592."""
    comp = {s: len(v) for s, v in correction["nonqualifications"]["D"].items()}
    gap = {s: len(v) for s, v in correction["signed_gap_gate_only_nonqualifications"].items()}
    assert comp["HIGHS_QPASM"] == 592, "the composite HiGHS count no longer reconciles"
    assert comp["QUADPROG_SQRT"] == 5
    assert len(correction["cascade_unresolved"]["D"]) == 0
    # the two views must DIFFER — if they ever coincide, the composite is not being evaluated
    assert comp != gap, "composite and gap-only counts are identical — the KKT half is not applied"
    assert gap["HIGHS_QPASM"] < comp["HIGHS_QPASM"]


def test_zero_verdict_flips_over_the_complete_population(correction):
    for path in ("L_vs_D", "N_vs_D", "D_vs_EXACT"):
        assert correction["verdict_changes"][path]["count"] == 0
    pop = correction["population"]
    assert pop["complete"] is True and pop["smoke_truncated"] is False
    assert pop["certificates_rebuilt"] + pop["solver_exceptions"] == pop["instance_solver_pairs"]
    assert pop["unclassified_records"] == 0 and pop["non_finite_corrections"] == 0
