"""MR-002 Phase 3B mounted execution layer.

Governed by MR002_Phase3B_RunSpecification_v1.0 (identity 2a1fb775...) under the prospective
execution-boundary clarification (5f54d85b...): this package is hash-bound independently of the
evaluator image and executes INSIDE that image, mounted read-only, under the P10-bound numeric
runtime. The evaluator image identity is unchanged.

It performs no research choice. Configurations, gates, estimators, windows, folds, costs and the
trial count are all frozen elsewhere and are cited and verified here, never selected.
"""

from __future__ import annotations

RUN_ID = "MR002-SPQ1-P3B-VALIDATION-V1"
WINDOW = "validation"
RUNSPEC_IDENTITY = "2a1fb7755a57b97f9831cf257c6e60c8bd5baf77eab39541b75ae88c27cb5b43"
CLARIFICATION_IDENTITY = "5f54d85b1ff9193ddefdc5a7639d02e8406e28089248e92d211f47c1f300d88f"
GOVERNED_IMAGE = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"

# ---------------------------------------------------------------------------------------------
# The frozen authorities the run checks its CONFIGURATION against.
#
# These exist so that the expected side of a check has provenance independent of the side being
# checked. Until v3.4 the entrypoint supplied `contract_identities` and `config_mapping` to BOTH
# sides of their comparisons, so `_verify_contract_identity` and `_bind_config` compared the
# configuration against itself and could not fail -- the same defect that let a stale configuration
# execute undetected and spend a governed opening on 2026-08-14.
#
# A module constant is the right authority precisely because it is INSIDE the hash-bound execution
# closure: it cannot be altered without altering `code_identity`, which the S1 closure check now
# enforces against the live mount. The configuration, by contrast, is staged as a separate file and
# is exactly the artifact that drifted.
#
# `run_specification` and `execution_boundary_clarification` are deliberately expressed as the
# constants above rather than restated, so a future edit cannot leave the two copies disagreeing.
# ---------------------------------------------------------------------------------------------

#: The A/B/C entry-threshold mapping, frozen by MR002_Phase3B_RunSpecification_v1.0.
FROZEN_CONFIG_MAPPING: dict[str, float] = {"A": 1.75, "B": 2.00, "C": 2.25}

#: The eight contract identities the run specification and its governing chain fix.
FROZEN_CONTRACT_IDENTITIES: dict[str, str] = {
    "corrected_development_reconciliation":
        "5904e04b24bab2320cd773e82d8803870d0188ec4408cc0cf88c0ab7913d70bc",
    "earnings_control_census":
        "d132684aea4e97e31294d647ea10fd929e229b516100d861a529474329a509c1",
    "execution_boundary_clarification": CLARIFICATION_IDENTITY,
    "p12_authorization_grant":
        "440e96e15bda2f8c4eaf991ce8e45190392607bb16bc3ff803f0e6bdac9137f5",
    "reference_manifest":
        "22166af451536b3c2f027addccfbbc5b18d7b6f1892bf4f64faa84f2d21860d9",
    "registered_session_list":
        "d11d3561e0b814d3a2fc5e5baeeb3fb76274dbf647cbb4ae177d9c21ad45dbdc",
    "run_specification": RUNSPEC_IDENTITY,
    "validation_input_identity_registration":
        "8578707bc94084c7ed30c9f30b3a001c47b6144c0fcafb9c03639424f779ca56",
}
