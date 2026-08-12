"""Step 7 findings — mechanically derived facts, and the cross-checks that bind an operator narrative.

## Why this module exists

Step 7's package used to state its findings as prose constants: *"top five AXTI SNDK BE WDC MU —
UNCHANGED"*, *"regime margin +27.2576% -> +12.3491%"*, *"no excluded identity touches the July 27
decision"*. Those were true of the 2026-07-27 construction and false-by-default of every other one, and
nothing in the pipeline could tell the difference — a later construction would have published the
previous run's conclusions inside a well-formed supersession record.

The split this module enforces:

  DERIVED    facts that can be measured are measured, from the Step 4 and Step 5 artifacts the package
             already binds. The operator cannot override them; there is no input that reaches them.
  AUTHORED   conclusions that cannot be proven mechanically — why a security crossed a ranking
             boundary, whether a change is lineage correction or ordinary price movement, materiality
             — are supplied in a separate operator-analysis file and clearly labelled as human work.

The tool cannot prove a causal explanation is intellectually correct. It CAN prove the narrative refers
to this construction and does not contradict a measured fact, and it refuses when it does not.

⚠ A narrative copied forward from the previous construction fails on its bindings (session, corpus
manifest, Step 4/Step 5 digests) before any of its prose is read. That is the specific failure this is
built to catch.
"""

from __future__ import annotations

from typing import Any

ANALYSIS_SCHEMA_VERSION = "1.0"

#: Every binding the operator narrative must restate correctly. A stale file fails here first.
REQUIRED_ANALYSIS_BINDINGS = ("target_session", "corpus_manifest_sha256",
                              "step4_artifact_sha256", "step5_artifact_sha256")

REFUSAL_CODE = "STEP7_ANALYSIS_INCOMPLETE_OR_INCONSISTENT"


def _tickers(entries: Any) -> list[str]:
    """Ticker list from a top-five/ranked block, which holds dicts with a `ticker` key."""
    out = []
    for e in entries or []:
        out.append(e["ticker"] if isinstance(e, dict) else str(e))
    return out


class FindingsRefused(RuntimeError):
    """The artifacts do not describe one coherent construction."""


def derive_findings(step4: dict, step5: dict, recon: dict, session: str) -> dict:
    """Measure every fact the artifacts can support. Never consults the operator narrative."""
    # The three artifacts must describe the SAME session. A mismatch here means an artifact was
    # carried over from a previous construction, which no digest downstream would reveal.
    sessions = {"step4": step4["session"], "step5": step5["session"],
                "reconciliation": recon["session_date"], "requested": session}
    if len(set(sessions.values())) != 1:
        raise FindingsRefused(
            f"the bound artifacts disagree about the session: {sessions}. At least one was carried "
            f"over from a different construction.")

    reb = step4["rebuilt"]["result"]
    sup = step4["superseded"]["result"]
    reb_regime, sup_regime = reb["regime"], sup["regime"]

    prior_top, new_top = _tickers(sup["top_five"]), _tickers(reb["top_five"])
    derived: dict[str, Any] = {
        "session": step4["session"],
        "decision_comparison": {
            "prior_top_five": prior_top,
            "new_top_five": new_top,
            "top_five_unchanged": prior_top == new_top,
            "prior_ordering": prior_top,
            "new_ordering": new_top,
            "ordering_unchanged": prior_top == new_top,
            "prior_target_weights": sup["target_weights"],
            "new_target_weights": reb["target_weights"],
            "target_weights_unchanged": sup["target_weights"] == reb["target_weights"],
            "prior_regime_state": sup_regime["state"],
            "new_regime_state": reb_regime["state"],
            "regime_state_unchanged": sup_regime["state"] == reb_regime["state"],
            "prior_regime_gross": sup_regime["gross"],
            "new_regime_gross": reb_regime["gross"],
            "regime_gross_unchanged": sup_regime["gross"] == reb_regime["gross"],
            "prior_regime_rel_to_ma": sup_regime["rel_to_ma"],
            "new_regime_rel_to_ma": reb_regime["rel_to_ma"],
            "regime_margin_unchanged": sup_regime["rel_to_ma"] == reb_regime["rel_to_ma"],
        },
        "universe_comparison": {
            "prior_raw_scoring_universe": sup["raw_scoring_universe"],
            "new_raw_scoring_universe": reb["raw_scoring_universe"],
            "prior_scored_names": sup["scored_names"],
            "new_scored_names": reb["scored_names"],
            "prior_passing_floors": sup["passing_floors"],
            "new_passing_floors": reb["passing_floors"],
            "prior_proxy_basket": sup["proxy"]["basket_after_quarantine"],
            "new_proxy_basket": reb["proxy"]["basket_after_quarantine"],
            "prior_proxy_contributors": sup["proxy"]["final_contributors"],
            "new_proxy_contributors": reb["proxy"]["final_contributors"],
        },
        "exclusion_census": _exclusion_census(step5),
        "window": {"sessions": step5["window_sessions"], "span": step5["window"],
                   "exact": step5["exact_273_session_window"]},
        "reconciliation": {
            "verdict": recon["verdict"],
            "proven": recon["proven"],
            "checks_included": recon["checks_included"],
            "terminal_census": dict(recon["checks_by_status"]),
            "checks_by_verdict": dict(recon["checks_by_verdict"]),
            "unexplained_adjustment_count": recon["unexplained_adjustment_count"],
            "relevance_set_sha256": recon["relevance_set_sha256"],
            "window": recon["window"],
        },
    }
    derived["material_changes"] = _material_changes(derived)
    return derived


def _exclusion_census(step5: dict) -> dict:
    """Per-identity reach into the decision sets, straight from the Step 5 impact table."""
    census: dict[str, Any] = {"excluded": {}, "quarantined": {}, "touching_the_decision": []}
    for key, row in sorted(step5["summary"].items()):
        bucket = "quarantined" if row["category"] == "QUARANTINED" else "excluded"
        reach = {
            "class": row["exclusion_class"],
            "in_raw_scoring_universe": row["in_raw_scoring_universe"],
            "in_top_200_scoring_universe": row["in_top_200_scoring_universe"],
            "in_proxy_basket": row["in_proxy_basket"],
            "in_final_proxy_contributors": row["in_final_proxy_contributors"],
            "in_top_five": row["in_top_five"],
            "session_rank_unconditional": row["session_rank_unconditional"],
            "placing_would_be_a_finding": row["placing_would_be_a_finding"],
        }
        census[bucket][key] = reach
        if bucket == "excluded" and any(
                reach[k] for k in ("in_raw_scoring_universe", "in_top_200_scoring_universe",
                                   "in_proxy_basket", "in_final_proxy_contributors", "in_top_five")):
            census["touching_the_decision"].append(key)
    census["exclusions_cost_the_decision_nothing"] = not census["touching_the_decision"]
    return census


def _material_changes(derived: dict) -> list[dict]:
    """Every measured difference that a human must explain before the package may be emitted.

    Keyed, because the requirement is checkable: each key must be the `subject` of a causal finding.
    """
    d, u = derived["decision_comparison"], derived["universe_comparison"]
    changes = []
    for key, unchanged, prior, new in (
            ("top_five", d["top_five_unchanged"], d["prior_top_five"], d["new_top_five"]),
            ("ordering", d["ordering_unchanged"], d["prior_ordering"], d["new_ordering"]),
            ("target_weights", d["target_weights_unchanged"],
             d["prior_target_weights"], d["new_target_weights"]),
            ("regime_state", d["regime_state_unchanged"],
             d["prior_regime_state"], d["new_regime_state"]),
            ("regime_gross", d["regime_gross_unchanged"],
             d["prior_regime_gross"], d["new_regime_gross"]),
            ("regime_margin", d["regime_margin_unchanged"],
             d["prior_regime_rel_to_ma"], d["new_regime_rel_to_ma"]),
    ):
        if not unchanged:
            changes.append({"key": key, "prior": prior, "new": new})
    for key in ("raw_scoring_universe", "scored_names", "passing_floors",
                "proxy_basket", "proxy_contributors"):
        prior, new = u[f"prior_{key}"], u[f"new_{key}"]
        if prior != new:
            changes.append({"key": key, "prior": prior, "new": new})
    return changes


def cross_check(analysis: dict, derived: dict, bindings: dict) -> list[str]:
    """Validate the operator narrative against the construction. Returns violations; empty is clean."""
    v: list[str] = []

    if analysis.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION:
        v.append(f"analysis_schema_version must be {ANALYSIS_SCHEMA_VERSION}, got "
                 f"{analysis.get('analysis_schema_version')!r}")

    # 1-3, 8: bindings. A narrative copied from the previous construction dies here.
    for field in REQUIRED_ANALYSIS_BINDINGS:
        expected, actual = bindings.get(field), analysis.get(field)
        if actual != expected:
            v.append(f"{field}: narrative says {actual!r}, construction is {expected!r} — the "
                     f"narrative does not belong to this construction")

    findings = analysis.get("causal_findings") or []
    subjects = {f.get("subject") for f in findings}

    census = derived["exclusion_census"]
    known = set(census["excluded"]) | set(census["quarantined"])
    decision = derived["decision_comparison"]
    named_universe = known | set(decision["new_top_five"]) | set(decision["prior_top_five"]) \
        | {c["key"] for c in derived["material_changes"]}

    for f in findings:
        subject = f.get("subject")
        if not subject:
            v.append("a causal finding has no subject")
            continue
        if f.get("review_status") != "APPROVED":
            v.append(f"causal finding {subject!r} is not APPROVED "
                     f"(review_status={f.get('review_status')!r})")
        # 4: a named security must exist in the comparison artifacts.
        if subject not in named_universe:
            v.append(f"causal finding names {subject!r}, which is absent from the comparison "
                     f"artifacts and from the measured material changes")
        # 5: cannot claim 'unchanged' about something measured as changed.
        claim = (f.get("claim") or "").lower()
        changed_keys = {c["key"] for c in derived["material_changes"]}
        if "unchanged" in claim and subject in changed_keys:
            v.append(f"causal finding {subject!r} claims 'unchanged' but it was measured as changed")
        # 6: a claimed rank must match the measured rank.
        if (rank := f.get("claimed_session_rank")) is not None:
            measured = (census["excluded"].get(subject) or census["quarantined"].get(subject) or {}
                        ).get("session_rank_unconditional")
            if rank != measured:
                v.append(f"causal finding {subject!r} claims session rank {rank}, measured "
                         f"{measured}")
        # 7: an exclusion claim must not contradict the Step 5 impact table.
        if (reached := f.get("claimed_reached_decision")) is not None:
            actually = subject in census["touching_the_decision"]
            if bool(reached) != actually:
                v.append(f"causal finding {subject!r} claims reached_decision={reached}, Step 5 "
                         f"measured {actually}")

    # 9: every measured material change needs an explanation.
    for change in derived["material_changes"]:
        if change["key"] not in subjects:
            v.append(f"material change {change['key']!r} ({change['prior']} -> {change['new']}) has "
                     f"no causal finding")

    if not analysis.get("materiality_assessment"):
        v.append("materiality_assessment is required and must not be empty")
    return v


def unresolved_requirements(analysis: dict, derived: dict) -> list[str]:
    """Material changes still lacking an approved causal finding."""
    approved = {f.get("subject") for f in (analysis.get("causal_findings") or [])
                if f.get("review_status") == "APPROVED"}
    return [c["key"] for c in derived["material_changes"] if c["key"] not in approved]
