"""The Layer 2 construction toolchain must never infer the session it is building for.

Every tool in this chain was written for exactly one session (2026-07-27) and carried that date as a
module constant. The failure mode that motivates these tests is specific and nasty: a tool that
silently defaults to the previous session produces a corpus, a manifest, an attestation and a readiness
receipt that all AGREE WITH ONE ANOTHER and are all wrong together. No digest catches it, because every
digest is computed over internally consistent inputs. The only defence is a refusal at the boundary.

So these tests assert refusals, not behaviour: that the session cannot be defaulted, that a narrative
cannot be carried forward, and that a human conclusion cannot contradict a measured fact.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
    session_date,
)
from scripts.forward_validation._step7_findings import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION,
    FindingsRefused,
    cross_check,
    derive_findings,
    unresolved_requirements,
)

#: ⚠ `build_normalized_corpus.py` is deliberately ABSENT from this list and from the repository.
#: Layer2_Corpus_Countersignature_and_Supersession_v1.0 keeps the reconstruction builder OUT of
#: any repository production tree: repository tooling may validate, inspect, package and verify,
#: but only the governed offline builder may create authoritative corpus and coverage records.
#: That is a trust-boundary decision, not a missing file. Its session/cutoff parameterization
#: lives on the preserved offline copy.
#: Tools that take a governed session, and the flag each one uses.
SESSION_TOOLS = [
    ("july27_exclusion_impact_check", "--session"),
    ("layer2_adjustment_reconciliation", "--session"),
    ("layer2_lineage_hole_census", "--session"),
    ("layer2_residual_relevance", "--session"),
    ("layer2_shop_tln_quarantine", "--session"),
    ("layer2_step4_july27_recompute", "--session"),
    ("layer2_step5_exclusion_impact_273", "--session"),
    ("layer2_tolerance_remeasurement", "--session"),
    ("layer2_step6_corpus_manifest", "--session"),
    ("layer2_step7_supersession_package", "--session"),
    ("layer2_complete_package", "--session"),
    ("extract_single_vintage", "--governed-cutoff"),
]

TOOL_DIR = BACKEND / "scripts" / "forward_validation"


@pytest.mark.parametrize(("tool", "flag"), SESSION_TOOLS)
def test_every_construction_tool_exposes_a_required_session_flag(tool: str, flag: str) -> None:
    """The flag exists and argparse marks it required — a default would be the whole defect."""
    out = subprocess.run(  # noqa: S603
        [sys.executable, str(TOOL_DIR / f"{tool}.py"), "--help"],
        capture_output=True, text=True, cwd=BACKEND,
        env={**_env(), "PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8"}, check=False)
    assert out.returncode == 0, out.stderr
    help_text = out.stdout
    assert flag in help_text, f"{tool} does not expose {flag}"
    # argparse lists required options in the usage line WITHOUT surrounding brackets.
    usage = help_text.split("options:")[0]
    assert f"[{flag}" not in usage, f"{tool}: {flag} is optional; a governed session must be required"


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()}


@pytest.mark.parametrize("tool", [t for t, _ in SESSION_TOOLS])
def test_no_tool_retains_a_hardcoded_session_constant(tool: str) -> None:
    """`SESSION = date(2026, 7, 27)` and `GOVERNED_CUTOFF = "..."` must not come back as constants."""
    src = (TOOL_DIR / f"{tool}.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "SESSION = date(" not in code, f"{tool} reintroduced a module-level SESSION constant"
    assert "GOVERNED_CUTOFF = " not in code, f"{tool} reintroduced a GOVERNED_CUTOFF constant"


def test_session_date_rejects_a_non_iso_value() -> None:
    """Strict parsing: a mistyped session must refuse, never resolve to a nearby date."""
    assert session_date("2026-07-28").isoformat() == "2026-07-28"
    for bad in ("28-07-2026", "2026/07/28", "July 28 2026", "2026-13-01", ""):
        with pytest.raises(argparse.ArgumentTypeError):
            session_date(bad)


def test_add_session_argument_has_no_default() -> None:
    ap = argparse.ArgumentParser()
    add_session_argument(ap)
    with pytest.raises(SystemExit):
        ap.parse_args([])


# --------------------------------------------------------------------------------------------------
# Step 7: derived facts, and the cross-checks that bind an operator narrative
# --------------------------------------------------------------------------------------------------

SESSION = "2026-07-28"


def _step4() -> dict:
    def result(top: list[str], regime: dict, floors: int, basket: int, contributors: int) -> dict:
        return {
            "top_five": [{"ticker": t, "rank": i + 1} for i, t in enumerate(top)],
            "target_weights": dict.fromkeys(top, 0.196),
            "regime": regime,
            "raw_scoring_universe": 200, "scored_names": 198, "passing_floors": floors,
            "proxy": {"basket_after_quarantine": basket, "final_contributors": contributors},
        }
    band = {"state": "ABOVE_BAND", "gross": 0.98, "rel_to_ma": 0.1234}
    return {
        "session": SESSION,
        "superseded": {"result": result(["AXTI", "SNDK", "BE", "WDC", "MU"], band, 46, 687, 661)},
        "rebuilt": {"result": result(["AXTI", "SNDK", "BE", "WDC", "MU"], band, 46, 687, 661)},
    }


def _step5() -> dict:
    def row(cat: str, cls: str, **over: object) -> dict:
        base = {
            "category": cat, "exclusion_class": cls,
            "in_raw_scoring_universe": False, "in_top_200_scoring_universe": False,
            "in_proxy_basket": False, "in_final_proxy_contributors": False, "in_top_five": False,
            "session_rank_unconditional": 4377, "placing_would_be_a_finding": True,
        }
        base.update(over)
        return base
    return {
        "session": SESSION,
        "window": ["2025-06-26", SESSION], "window_sessions": 273,
        "exact_273_session_window": True,
        "summary": {
            "OCCI": row("EXCLUDED", "EXCLUDED_NO_AUTHORITATIVE_SEP_PRICE_COVERAGE"),
            "SHOP": row("QUARANTINED", "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY",
                        in_raw_scoring_universe=True, in_top_200_scoring_universe=True,
                        in_proxy_basket=True, in_final_proxy_contributors=True, in_top_five=True,
                        session_rank_unconditional=119, placing_would_be_a_finding=False),
        },
    }


def _recon() -> dict:
    return {
        "session_date": SESSION, "verdict": "NOT_PROVEN_UNSUPPORTED_ACTION", "proven": False,
        "checks_included": 1791, "checks_by_status": {"PROVEN_REFLECTED": 1676},
        "checks_by_verdict": {"PROVEN": 1773}, "unexplained_adjustment_count": 4,
        "relevance_set_sha256": "a" * 64, "window": ["2025-06-26", SESSION, 273],
    }


BINDINGS = {"target_session": SESSION, "corpus_manifest_sha256": "b" * 64,
            "step4_artifact_sha256": "c" * 64, "step5_artifact_sha256": "d" * 64}


def _analysis(**over: object) -> dict:
    base = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        **BINDINGS,
        "causal_findings": [],
        "materiality_assessment": "the governed decision is unchanged",
    }
    base.update(over)
    return base


def test_derive_refuses_when_artifacts_disagree_about_the_session() -> None:
    """An artifact carried over from a previous construction is invisible to every downstream digest."""
    step4 = _step4()
    step4["session"] = "2026-07-27"
    with pytest.raises(FindingsRefused, match="disagree about the session"):
        derive_findings(step4, _step5(), _recon(), SESSION)


def test_derived_findings_are_measured_not_supplied() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    assert d["decision_comparison"]["top_five_unchanged"] is True
    assert d["decision_comparison"]["new_top_five"] == ["AXTI", "SNDK", "BE", "WDC", "MU"]
    assert d["exclusion_census"]["touching_the_decision"] == []
    assert d["exclusion_census"]["exclusions_cost_the_decision_nothing"] is True
    # SHOP reaches the decision but is QUARANTINED, not EXCLUDED — it must not be counted as an
    # exclusion touching the decision, and it must not be called decision-irrelevant either.
    assert d["exclusion_census"]["quarantined"]["SHOP"]["in_top_five"] is True
    assert d["material_changes"] == []


@pytest.mark.parametrize("field", list(BINDINGS))
def test_a_narrative_from_another_construction_is_refused(field: str) -> None:
    """The stale-copy case: every binding is checked before any prose is read."""
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    stale = _analysis(**{field: "2026-07-27" if field == "target_session" else "e" * 64})
    violations = cross_check(stale, d, BINDINGS)
    assert any(field in v for v in violations), violations


def test_clean_narrative_passes() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    assert cross_check(_analysis(), d, BINDINGS) == []
    assert unresolved_requirements(_analysis(), d) == []


def _changed() -> tuple[dict, dict]:
    """A construction whose top five genuinely moved — so a causal finding becomes mandatory."""
    step4 = copy.deepcopy(_step4())
    step4["rebuilt"]["result"]["top_five"] = [
        {"ticker": t} for t in ["AXTI", "SNDK", "BE", "WDC", "NVDA"]]
    return step4, derive_findings(step4, _step5(), _recon(), SESSION)


def test_a_material_change_without_a_causal_finding_is_refused() -> None:
    _, d = _changed()
    assert "top_five" in {c["key"] for c in d["material_changes"]}
    violations = cross_check(_analysis(), d, BINDINGS)
    assert any("no causal finding" in v for v in violations), violations
    assert "top_five" in unresolved_requirements(_analysis(), d)


def test_a_narrative_cannot_claim_unchanged_about_a_measured_change() -> None:
    _, d = _changed()
    analysis = _analysis(causal_findings=[
        {"subject": "top_five", "claim": "the top five is UNCHANGED",
         "review_status": "APPROVED"}])
    violations = cross_check(analysis, d, BINDINGS)
    assert any("claims 'unchanged'" in v for v in violations), violations


def test_an_unapproved_finding_does_not_satisfy_the_requirement() -> None:
    _, d = _changed()
    analysis = _analysis(causal_findings=[
        {"subject": "top_five", "claim": "NVDA entered on restored eligibility",
         "review_status": "DRAFT"}])
    assert any("not APPROVED" in v for v in cross_check(analysis, d, BINDINGS))
    assert "top_five" in unresolved_requirements(analysis, d)


def test_a_claimed_rank_must_match_the_measured_rank() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    analysis = _analysis(causal_findings=[
        {"subject": "SHOP", "claim": "ranked well inside the pool", "review_status": "APPROVED",
         "claimed_session_rank": 5}])
    violations = cross_check(analysis, d, BINDINGS)
    assert any("claims session rank 5, measured 119" in v for v in violations), violations


def test_an_exclusion_claim_cannot_contradict_the_step5_table() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    analysis = _analysis(causal_findings=[
        {"subject": "OCCI", "claim": "OCCI reached the proxy basket", "review_status": "APPROVED",
         "claimed_reached_decision": True}])
    violations = cross_check(analysis, d, BINDINGS)
    assert any("reached_decision=True" in v for v in violations), violations


def test_a_finding_about_an_unknown_security_is_refused() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    analysis = _analysis(causal_findings=[
        {"subject": "WIDGETCO", "claim": "displaced at the boundary", "review_status": "APPROVED"}])
    violations = cross_check(analysis, d, BINDINGS)
    assert any("WIDGETCO" in v and "absent" in v for v in violations), violations


def test_materiality_assessment_is_mandatory() -> None:
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    violations = cross_check(_analysis(materiality_assessment=""), d, BINDINGS)
    assert any("materiality_assessment" in v for v in violations), violations


def test_the_shipped_july27_narrative_validates_against_its_own_construction() -> None:
    """The contract is exercised against the real artifacts, where the answer is already known."""
    # Operator data location, never a hard-coded working-copy path: the ported tools removed those
    # deliberately, and a test that reintroduces one is unrunnable by anyone else.
    corpus = Path(os.environ.get("LAYER2_CORPUS_DIR", ""))
    if not corpus.name:
        pytest.skip("LAYER2_CORPUS_DIR is not set; operator corpus artifacts unavailable")
    if not (corpus / "step4_comparison.json").is_file():
        pytest.skip("operator corpus artifacts not present on this machine")
    import json
    step4 = json.loads((corpus / "step4_comparison.json").read_text(encoding="utf-8"))
    step5 = json.loads((corpus / "step5_exclusion_impact_273.json").read_text(encoding="utf-8"))
    recon = json.loads((corpus / "adjustment_reconciliation_final.json").read_text(encoding="utf-8"))
    analysis = json.loads((corpus / "step7_operator_analysis.json").read_text(encoding="utf-8"))
    derived = derive_findings(step4, step5, recon, "2026-07-27")

    # The facts the package used to state as prose constants, now measured.
    dc = derived["decision_comparison"]
    assert dc["new_top_five"] == ["AXTI", "SNDK", "BE", "WDC", "MU"]
    assert dc["top_five_unchanged"] and dc["ordering_unchanged"]
    assert dc["regime_state_unchanged"] and dc["regime_gross_unchanged"]
    assert dc["regime_margin_unchanged"] is False
    assert derived["exclusion_census"]["exclusions_cost_the_decision_nothing"] is True

    bindings = {"target_session": "2026-07-27",
                "corpus_manifest_sha256": analysis["corpus_manifest_sha256"],
                "step4_artifact_sha256": analysis["step4_artifact_sha256"],
                "step5_artifact_sha256": analysis["step5_artifact_sha256"]}
    assert cross_check(analysis, derived, bindings) == []
    assert unresolved_requirements(analysis, derived) == []


def test_the_july27_narrative_is_refused_for_a_later_session() -> None:
    """The same file, offered for the next construction, must fail on its bindings."""
    # Operator data location, never a hard-coded working-copy path: the ported tools removed those
    # deliberately, and a test that reintroduces one is unrunnable by anyone else.
    corpus = Path(os.environ.get("LAYER2_CORPUS_DIR", ""))
    if not corpus.name:
        pytest.skip("LAYER2_CORPUS_DIR is not set; operator corpus artifacts unavailable")
    if not (corpus / "step7_operator_analysis.json").is_file():
        pytest.skip("operator corpus artifacts not present on this machine")
    import json
    analysis = json.loads((corpus / "step7_operator_analysis.json").read_text(encoding="utf-8"))
    d = derive_findings(_step4(), _step5(), _recon(), SESSION)
    violations = cross_check(analysis, d, BINDINGS)
    assert any("target_session" in v for v in violations), violations


def test_findings_module_imports_cleanly_without_the_app_package() -> None:
    """Pure functions: the derivation must not drag in runtime state."""
    mod = importlib.import_module("scripts.forward_validation._step7_findings")
    assert mod.REFUSAL_CODE == "STEP7_ANALYSIS_INCOMPLETE_OR_INCONSISTENT"
