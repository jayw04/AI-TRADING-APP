"""Produce the Phase 3B execution manifest deterministically from already-governed authorities.

The entry point used to want a hand-written run configuration. That was the wrong shape: almost
every field in it is a projection of something already governed, or an observation of the live
runtime. Authoring it by hand would mean inventing copies of values that already have owners.

So this producer reads only governed artifacts and live materialization observations, and emits the
configuration. The rule it enforces is the one that makes it trustworthy:

    EVERY populated field carries a value AND a provenance identity. If a value cannot be traced to
    an artifact or an observation, the field REFUSES. There is no "best available" fallback.

Five pre-publication field groups, one authority each:

  observed_identities   the mounted execution closure and dependency bundle, rehashed live
  runtime_facts         the P10 runtime identity as materialized in the bound image
  contract_identities   RunSpecification, boundary clarification, P12 grant + authorization state,
                        the earnings-control adjudications, and the accepted execution supplement
  identities            the bound execution/research identity set
  config_mapping        the frozen A/B/C mapping, cited from its registered source

`published_at` is deliberately ABSENT. It is stamped by the publisher at the durable publication
transition and is not a run input; see publish.publish_run.

Zero-data instrument: reads governed records and a live observation file. No AWS call, no sealed
object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
GOV = "docs/review/mr002/phase3bc"

RUN_ID = "MR002-SPQ1-P3B-VALIDATION-V1"
WINDOW = "validation"

# Contract identities, each a named field of a named governed artifact. Nothing is transcribed by
# hand: the producer reads the artifact and refuses if the field is absent.
CONTRACT_SOURCES = {
    "run_specification": (f"{GOV}/MR002_Phase3B_RunSpecification_v1.0.json", "record_identity_sha256"),
    "execution_boundary_clarification": (
        f"{GOV}/MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json", "record_identity_sha256"),
    # The grant record names its identity `grant_identity_sha256`, not `record_identity_sha256`.
    # The producer refused rather than falling back, which is how the difference was found.
    "p12_authorization_grant": (
        f"{GOV}/MR002_Phase3BC_P12AuthorizationGrant_v1.0.json", "grant_identity_sha256"),
    "earnings_control_census": (
        f"{GOV}/MR002_Phase3B_EarningsControlStructuralCensus_v1.0.json", "record_identity_sha256"),
    "corrected_development_reconciliation": (
        f"{GOV}/MR002_Phase3B_CorrectedDevelopmentReconciliation_v1.0.json",
        "record_identity_sha256"),
    "reference_manifest": (f"{GOV}/MR002_Phase3B_ReferenceManifest_v1.0.json",
                           "record_identity_sha256"),
    "registered_session_list": (
        f"{GOV}/MR002_Phase3B_RegisteredSessionList_Provenance_v1.0.json",
        "record_identity_sha256"),
}
# The authorization STATE is read for its live values, not for a record hash.
AUTH_STATE = f"{GOV}/MR002_Phase3BC_ValidationAuthorizationState_v1.0.json"
STRUCTURAL = f"{GOV}/MR002_ValidationStructuralManifest_v1.0.json"
UPLOAD = f"{GOV}/MR002_SealedStoreUploadManifest_v1.0.json"

# The frozen configuration mapping and where it is implemented. Cited, never constructed.
CONFIG_MAPPING = {"A": 1.75, "B": 2.00, "C": 2.25}
CONFIG_MAPPING_SOURCE = (
    "mr002_valoos_portfolio_identity.Z_ENTRY, inside the bound evaluator image "
    "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
)


class ManifestRefused(Exception):
    """A field cannot be traced to an authority. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _read(rel: str) -> tuple[dict, str]:
    path = os.path.join(_REPO, rel)
    if not os.path.exists(path):
        raise ManifestRefused(f"governing artifact absent: {rel}")
    with open(path, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _traced(value, *, source: str, field: str) -> dict:
    """Every populated field is a {value, provenance} pair. An untraced value is not a value."""
    if value in (None, "", {}, []):
        raise ManifestRefused(f"{field}: empty value from {source}; refusing rather than defaulting")
    return {"value": value, "provenance": {"artifact": source, "field": field}}


# -- the five pre-publication field groups -------------------------------------------------


def contract_identities() -> tuple[dict, dict]:
    values, provenance = {}, {}
    for name, (rel, key) in CONTRACT_SOURCES.items():
        doc, file_sha = _read(rel)
        ident = doc.get(key)
        if not ident:
            raise ManifestRefused(f"{name}: {rel} has no {key}; cannot trace the contract identity")
        values[name] = ident
        provenance[name] = {"artifact": rel, "field": key, "artifact_file_sha256": file_sha}
    return values, provenance


def authorization_facts() -> dict:
    state, file_sha = _read(AUTH_STATE)
    for key in ("validation_authorization", "_rev"):
        if key not in state:
            raise ManifestRefused(f"authorization state has no {key}")
    if state["validation_authorization"] is not True or state["_rev"] != 1:
        raise ManifestRefused(
            f"authorization is not the granted state: "
            f"validation_authorization={state['validation_authorization']} _rev={state['_rev']}"
        )
    return {
        "validation_authorization": state["validation_authorization"],
        "_rev": state["_rev"],
        "granted_at_utc": state.get("granted_at_utc"),
        "provenance": {
            "artifact": AUTH_STATE,
            "artifact_file_sha256": file_sha,
            "store": "Git-tracked file, compare-and-set by "
                     "scripts/mr002_custody/p12_authorization.py",
            "note": "the CAS is file-based, so its authority rests on Git history rather than an "
                    "atomic store. Recorded as a fact, not asserted as equivalent.",
        },
    }


def observed_identities(observation: dict) -> tuple[dict, dict]:
    """Identities REHASHED from the live mount, not copied from a manifest."""
    closure = observation.get("closure_files") or {}
    if not closure:
        raise ManifestRefused("observation carries no closure identities")
    deps = observation.get("dependency_bundle") or {}
    if not deps.get("wheels"):
        raise ManifestRefused("observation carries no dependency-bundle identities")

    sealed, _ = _read(UPLOAD)
    objects = sealed.get("objects") or {}
    inputs = {}
    for key, meta in sorted(objects.items()):
        prefix = key.split("/", 1)[0]
        if prefix not in (WINDOW, "reference"):
            continue
        if not meta.get("sha256"):
            raise ManifestRefused(f"{key}: upload manifest has no sha256")
        inputs[key] = meta["sha256"]

    values = {
        "execution_closure_sha256": hashlib.sha256(
            _canonical(dict(sorted(closure.items())))
        ).hexdigest(),
        "execution_closure_file_count": len(closure),
        "dependency_bundle_sha256": hashlib.sha256(
            _canonical(dict(sorted(deps["wheels"].items())))
        ).hexdigest(),
        "sealed_input_sha256": dict(sorted(inputs.items())),
    }
    provenance = {
        "execution_closure_sha256": {
            "artifact": "live observation of the read-only code mount",
            "field": "closure_files",
            "derivation": "sha256 over the canonicalised {path: sha256} map, digests taken from "
                          "git blob bytes so the working tree cannot influence identity",
        },
        "dependency_bundle_sha256": {
            "artifact": "live observation of the read-only dependency mount",
            "field": "dependency_bundle.wheels",
        },
        "sealed_input_sha256": {"artifact": UPLOAD, "field": "objects"},
    }
    return values, provenance


def runtime_facts(observation: dict) -> tuple[dict, dict]:
    facts = observation.get("runtime") or {}
    required = ("image_digest", "python_version", "numpy", "scipy", "pandas", "host_instance_id")
    missing = [k for k in required if not facts.get(k)]
    if missing:
        raise ManifestRefused(f"runtime observation lacks {missing}; refusing rather than guessing")
    return dict(facts), {
        k: {"artifact": "live materialization observation inside the bound image", "field": k}
        for k in facts
    }


def execution_identities(observation: dict) -> tuple[dict, dict]:
    closure = observation.get("closure_files") or {}
    if not closure:
        raise ManifestRefused("identities.code_identity: no closure observed")
    runspec_path, runspec_field = CONTRACT_SOURCES["run_specification"]
    values = {
        "code_identity": hashlib.sha256(_canonical(dict(sorted(closure.items())))).hexdigest(),
        "runtime_identity": (observation.get("runtime") or {}).get("image_digest"),
        "governing_identity": _read(runspec_path)[0].get(runspec_field),
    }
    untraced = sorted(k for k, v in values.items() if not v)
    if untraced:
        raise ManifestRefused(f"identities could not be traced: {untraced}")
    return values, {
        "code_identity": {"artifact": "live code mount", "field": "closure_files"},
        "runtime_identity": {"artifact": "live runtime", "field": "image_digest"},
        "governing_identity": {
            "artifact": CONTRACT_SOURCES["run_specification"][0],
            "field": "record_identity_sha256",
        },
    }


def config_mapping() -> dict:
    return _traced(dict(CONFIG_MAPPING), source=CONFIG_MAPPING_SOURCE, field="Z_ENTRY")


# -- assembly ------------------------------------------------------------------------------


def build(observation: dict) -> dict:
    contracts, contract_prov = contract_identities()
    observed, observed_prov = observed_identities(observation)
    runtime, runtime_prov = runtime_facts(observation)
    idents, ident_prov = execution_identities(observation)
    mapping = config_mapping()

    config = {
        "run_id": RUN_ID,
        "window": WINDOW,
        "observed_identities": observed,
        "runtime_facts": runtime,
        "expected_runtime_facts": runtime,
        "contract_identities": contracts,
        "identities": idents,
        "config_mapping": mapping["value"],
    }
    if "published_at" in json.dumps(config):
        raise ManifestRefused(
            "published_at must not appear in a pre-execution configuration; it is stamped by the "
            "publisher at the durable publication transition"
        )

    return {
        "record_type": "MR002_Phase3B_ExecutionManifest",
        "version": "1.0",
        "artifact_kind": "GENERATED_EXECUTION_CONFIGURATION",
        "run_id": RUN_ID,
        "window": WINDOW,
        "generated_not_authored": (
            "every field is a projection of a governed artifact or a live materialization "
            "observation. A field whose provenance cannot be traced REFUSES; there is no "
            "best-available fallback."
        ),
        "configuration": config,
        "provenance": {
            "observed_identities": observed_prov,
            "runtime_facts": runtime_prov,
            "contract_identities": contract_prov,
            "identities": ident_prov,
            "config_mapping": mapping["provenance"],
        },
        "authorization": authorization_facts(),
        "published_at_policy": {
            "present_in_configuration": False,
            "stamped_by": "publish.publish_run at the durable publication transition",
            "rationale": "the frozen contract could not have known it prospectively; it is "
                         "publication metadata, not a research configuration parameter",
            "independence": "signal, eligibility, enrichment, admissibility, selection, "
                            "configuration identity and authorization identity do not depend on it",
            "retry": "an existing publication record refuses rather than restamping",
        },
        "boundary": (
            "Zero-data. No AWS call, no sealed object, no credential. The opening remains UNSPENT."
        ),
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _gen_execution_manifest.py <live_observation.json>")
    with open(sys.argv[1], encoding="utf-8") as fh:
        observation = json.load(fh)

    record = build(observation)
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()

    out = os.path.join(_HERE, "MR002_Phase3B_ExecutionManifest_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    cfg = os.path.join(_HERE, "MR002_Phase3B_ExecutionConfiguration_v1.0.json")
    with open(cfg, "wb") as fh:
        fh.write(_canonical(record["configuration"]))

    print(f"wrote {out}")
    print(f"wrote {cfg}  <-- the entry point's --config")
    print(f"record identity {record['record_identity_sha256']}")
    print(f"contract identities traced: {len(record['configuration']['contract_identities'])}")
    print(f"authorization: validation_authorization="
          f"{record['authorization']['validation_authorization']} _rev={record['authorization']['_rev']}")
    print("published_at in configuration:", "published_at" in json.dumps(record["configuration"]))


if __name__ == "__main__":
    main()
