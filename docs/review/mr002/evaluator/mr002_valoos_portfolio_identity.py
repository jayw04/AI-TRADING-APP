"""MR-002 Increment 3 — identity-bound portfolio-rule loader (synthetic only).

Hash-binds the implementation-binding rule registry (MR002_Increment3_RuleRegistry_v1.0) + the
Phase-0 resolution (MR002_Increment3_Phase0_Resolution_v1.0) + the governing sources. Any divergence
between these bytes and their pinned SHA-256 raises RefusedPortfolioIdentity
(REFUSED_CODE_OR_DATA_IDENTITY). Also owns the single NAV-identity rule (RC-4): construction NAV and
execution NAV must be the same value within an order cycle, else NAV_IDENTITY_MISMATCH.

No data read; no performance; no signal/residual/sigma computation.
"""

from __future__ import annotations

import hashlib
import json
import os

REGISTRY = "MR002_Increment3_RuleRegistry_v1.0.json"
RESOLUTION = "MR002_Increment3_Phase0_Resolution_v1.0.json"

REGISTRY_SHA = "edb7ff22b5215f815b15e64166111604d2b99da91a545729b6c9796928d3b91a"
RESOLUTION_SHA = "860c8cdeb995fadea21359ede189dad27378ab2c553e5a24122bbbd2d2546740"

# governing sources the registry/resolution bind (verified transitively)
SOURCE_SHAS = {
    "MR002_ValidationOOS_Preregistration_v1.0.4.json": "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c",
    "MR002_DSR_TrialLedger_v1.0.json": "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b",
    "MR002_Portfolio_Rule_Census_v1.0.json": "91eec2626c584b0f4dd0b184feae9f1f5dc80e5245a823be72a321b5d5f9417e",
}

# frozen economic constants (mirrored from the binding registry / prereg exposure_limits_frozen)
POSITION_CAP_NAV = 0.015          # PR-08 per-name 1.5% NAV
SECTOR_NET_MAX = 0.05             # PR-09 net per sector / gross
SECTOR_GROSS_MAX = 0.20          # PR-09 gross per sector / gross
BETA_MAX = 0.10                  # PR-10 |Sum w_i beta_i| / gross
GROSS_MAX = 1.00                # PR-01 gross <= 100% NAV
NET_DRIFT_BAND = 0.05           # PR-15 net dollar / gross drift band
SIDE_GROSS_CAP = 0.50           # PR-06 per-side <= 50% NAV
Z_ENTRY = {"A": 1.75, "B": 2.00, "C": 2.25}     # PR-20 A/B/C differ ONLY in Z_entry


class RefusedPortfolioIdentity(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — a governing artifact or NAV identity failed validation."""


def _refuse(detail: str):
    raise RefusedPortfolioIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:{detail}")


def _check(gov_dir: str, name: str, want: str) -> dict:
    if os.path.basename(name) != name:
        _refuse(f"NON_BASENAME:{name}")
    p = os.path.join(gov_dir, name)
    if os.path.islink(p):
        _refuse(f"SYMLINK:{name}")
    if not os.path.isfile(p):
        _refuse(f"MISSING:{name}")
    raw = open(p, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != want:
        _refuse(f"HASH_MISMATCH:{name}:{got}")
    return json.loads(raw.decode("utf-8"))


def load_portfolio_identity(gov_dir: str) -> dict:
    """Validate the binding registry + resolution + governing sources; return the bound identities and
    frozen constants. Fail-closed on any hash or cross-binding divergence."""
    registry = _check(gov_dir, REGISTRY, REGISTRY_SHA)
    resolution = _check(gov_dir, RESOLUTION, RESOLUTION_SHA)
    for name, sha in SOURCE_SHAS.items():
        _check(gov_dir, name, sha)

    if registry.get("record_status") != "IMPLEMENTATION_BINDING":
        _refuse(f"REGISTRY_NOT_BINDING:{registry.get('record_status')}")
    if registry.get("bound_identities", {}).get("phase0_resolution_v1.0") != RESOLUTION_SHA:
        _refuse("REGISTRY_RESOLUTION_UNBOUND")
    if resolution.get("record_type") != "MR002_INCREMENT3_PHASE0_RESOLUTION":
        _refuse("RESOLUTION_RECORD_TYPE")
    if resolution.get("bound_identities", {}).get("registry_draft_v1.0") != registry.get("bound_identities", {}).get("census_v1.0") and \
       resolution.get("bound_identities", {}).get("census_v1.0") != SOURCE_SHAS["MR002_Portfolio_Rule_Census_v1.0.json"]:
        _refuse("RESOLUTION_CENSUS_UNBOUND")

    return {
        "registry_sha256": REGISTRY_SHA, "resolution_sha256": RESOLUTION_SHA,
        "source_shas": dict(SOURCE_SHAS),
        "constants": {"POSITION_CAP_NAV": POSITION_CAP_NAV, "SECTOR_NET_MAX": SECTOR_NET_MAX,
                      "SECTOR_GROSS_MAX": SECTOR_GROSS_MAX, "BETA_MAX": BETA_MAX,
                      "GROSS_MAX": GROSS_MAX, "NET_DRIFT_BAND": NET_DRIFT_BAND,
                      "SIDE_GROSS_CAP": SIDE_GROSS_CAP, "Z_ENTRY": dict(Z_ENTRY)},
    }


def assert_nav_identity(construction_nav: float, execution_nav: float) -> float:
    """RC-4: construction and execution must use one common NAV within the order cycle."""
    if float(construction_nav) != float(execution_nav):
        _refuse(f"NAV_IDENTITY_MISMATCH:{construction_nav}!={execution_nav}")
    return float(construction_nav)
