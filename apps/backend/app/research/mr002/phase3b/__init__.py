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
