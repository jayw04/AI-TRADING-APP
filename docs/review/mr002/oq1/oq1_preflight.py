"""MR-002 OQ-1 — operational identity preflight (Component 3).

Runs BEFORE any evaluator/pipeline import. Verifies governance identities, evaluator file hashes,
environment lock, python/runtime, container digest, synthetic-fixture identity, output-directory
policy, network-disabled state, and sealed-path denial. A failed preflight prevents pipeline import.

Dispositions: PREFLIGHT_PASS | PREFLIGHT_REFUSED | PREFLIGHT_INTEGRITY_STOP.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVALUATOR = os.path.abspath(os.path.join(HERE, "..", "evaluator"))
GOV_DIR = os.path.abspath(os.path.join(HERE, ".."))


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run_preflight(*, container_digest: str = "n/a", expected_container_digest: str | None = None,
                  require_network_disabled: bool = True, output_dir: str | None = None) -> dict:
    checks, refused, stop = [], [], []

    def ck(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        return ok

    # 1. governance identity chain (registry edb7ff22 / resolution 860c8cde / prereg / ledger / census)
    sys.path.insert(0, EVALUATOR)
    try:
        import mr002_valoos_portfolio_identity as PID
        ident = PID.load_portfolio_identity(GOV_DIR)
        ck("governance_identity", ident["registry_sha256"].startswith("edb7ff22")
           and ident["resolution_sha256"].startswith("860c8cde"), "registry+resolution bound")
    except Exception as exc:                                  # noqa: BLE001 — fail closed on any identity error
        ck("governance_identity", False, type(exc).__name__)
        refused.append(f"REFUSED_CODE_OR_DATA_IDENTITY:{exc}")

    # 2. evaluator source file hashes vs the pinned OQ-1 manifest
    try:
        pinned = json.load(open(os.path.join(HERE, "oq1_evaluator_hashes.json"), encoding="utf-8"))
        for name, want in pinned["files"].items():
            got = _sha(os.path.join(EVALUATOR, name))
            if got != want:
                refused.append(f"REFUSED_CODE_OR_DATA_IDENTITY:EVALUATOR_HASH:{name}")
        ck("evaluator_file_hashes", not any("EVALUATOR_HASH" in r for r in refused),
           f"{len(pinned['files'])} files")
    except FileNotFoundError:
        ck("evaluator_file_hashes", False, "pinned manifest missing")
        stop.append("INTEGRITY_STOP:EVALUATOR_HASH_MANIFEST_MISSING")

    # 3. environment lock
    try:
        import oq1_environment as ENV
        ENV.verify_environment(os.path.join(HERE, "wheelhouse-manifest.json"))
        ck("environment_identity", True, "locked packages verified")
    except Exception as exc:                                  # noqa: BLE001
        ck("environment_identity", False, str(exc).split(":", 1)[-1][:60])
        refused.append(str(exc) if str(exc).startswith("REFUSED") else f"REFUSED_ENVIRONMENT_IDENTITY:{exc}")

    # 4. python / schema identity
    ck("python_identity", sys.version_info[:2] == (3, 13), ".".join(map(str, sys.version_info[:2])))

    # 5. base-image digest (pinned) + running container-image digest
    EXPECTED_BASE_INDEX = "sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91"
    EXPECTED_BASE_AMD64 = "sha256:afe189875f1d2f9b45e287834fb9f2c273a5d59d354ae4050ab9affbf0a6ba06"
    try:
        bid = json.load(open(os.path.join(HERE, "container-build-identity.json"), encoding="utf-8"))
        base_ok = (bid["base_image"]["index_digest"] == EXPECTED_BASE_INDEX
                   and bid["base_image"]["amd64_digest"] == EXPECTED_BASE_AMD64)
        ck("base_image_digest", base_ok, "digest-pinned base bound")
        if not base_ok:
            refused.append("REFUSED_ENVIRONMENT_IDENTITY:BASE_IMAGE_DIGEST")
        # container-image digest: the running image must match the build-identity's resulting digest
        if bid.get("resulting_image_digest") and bid["resulting_image_digest"] != "n/a":
            match = container_digest == bid["resulting_image_digest"]
            ck("container_image_digest", match, "running image bound to build identity")
            if not match:
                refused.append("REFUSED_ENVIRONMENT_IDENTITY:CONTAINER_IMAGE_DIGEST")
    except FileNotFoundError:
        ck("base_image_digest", False, "build-identity manifest missing")
        stop.append("INTEGRITY_STOP:BUILD_IDENTITY_MISSING")
    if expected_container_digest is not None and container_digest != expected_container_digest:
        refused.append("REFUSED_ENVIRONMENT_IDENTITY:CONTAINER_IMAGE_DIGEST")

    # 6. output-directory policy (must exist, be writable, and not be an input/evaluator/gov path)
    if output_dir is not None:
        import oq1_sealed_access as SA
        outreal = os.path.realpath(output_dir)
        bad = (SA.is_sealed_path(outreal) or outreal.startswith(os.path.realpath(EVALUATOR))
               or outreal.startswith(os.path.realpath(GOV_DIR + os.sep + "governing_sources")))
        ck("output_dir_policy", os.path.isdir(output_dir) and os.access(output_dir, os.W_OK) and not bad,
           os.path.basename(outreal))
        if bad:
            refused.append("REFUSED_PUBLICATION:OUTPUT_DIR_POLICY")

    # 7. sealed-path denial + no credentials
    try:
        import oq1_sealed_access as SA
        SA.assert_no_credentials()
        SA.assert_no_aws_credentials_files()
        SA.assert_no_forbidden_imports(set(sys.modules))
        ck("sealed_access_denied", True, "no creds / no forbidden imports")
    except Exception as exc:                                  # noqa: BLE001
        ck("sealed_access_denied", False, str(exc).split(":", 1)[-1][:60])
        refused.append(str(exc))

    # 8. network-disabled state (best-effort)
    if require_network_disabled:
        import oq1_sealed_access as SA
        try:
            SA.assert_network_disabled()
            ck("network_disabled", True, "outbound unreachable")
        except SA.SealedAccessRefused:
            ck("network_disabled", False, "network reachable")
            refused.append("REFUSED_SEALED_ACCESS:NETWORK_REACHABLE")

    if stop:
        disp = "PREFLIGHT_INTEGRITY_STOP"
    elif refused:
        disp = "PREFLIGHT_REFUSED"
    else:
        disp = "PREFLIGHT_PASS"
    return {"disposition": disp, "checks": checks, "refusals": refused, "stops": stop,
            "all_pass": disp == "PREFLIGHT_PASS"}
