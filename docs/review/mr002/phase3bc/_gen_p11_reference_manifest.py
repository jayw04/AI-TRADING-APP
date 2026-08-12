"""Generate the Phase 3B reference manifest as a projection of the P11 reference registration.

The reference layer registers FOUR objects. Phase 3B consumes TWO. Those are different statements
and the manifest keeps them apart:

  registered reference universe        4 - sic_mapping, crosswalk, predecessor_overrides,
                                           security_sector_overrides
  Phase 3B consumed reference set      2 - sic_mapping, crosswalk
  registered but NOT consumed          2 - the two override tables, each named and justified

Pulling the overrides into Phase 3B would ADD an execution dependency, not preserve one. The
production precedent is explicit: Phase 2B's orchestrator loads `sic_mapping` raw and its identity
adapter loads `crosswalk` raw, neither applying overrides. The override-aware resolver lives in
`app/research/mr002/dataset.py`, a research-analysis path outside the Phase 2B production chain and
outside the Phase 3B import closure. Consuming them in validation would therefore BREAK continuity
with the development window rather than preserve it.

Every value is a projection with one hop to its authority. Nothing here is chosen:

  MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json  ->  object key, version id, sha256, rows
  MR002_ValidationStructuralManifest_v1.0.json          ->  registered column order per table

The generator refuses if a registered object is absent, if any identity differs, if an unregistered
reference object appears, or if the consumed set is not a subset of the registered universe. It
refuses outright if a validation-partition object is ever named.

Zero-data instrument: reads governed records. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os

P11 = "docs/review/mr002/phase3bc/MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json"
P9 = "docs/review/mr002/phase3bc/MR002_ValidationStructuralManifest_v1.0.json"

CONSUMED = ("crosswalk", "sic_mapping")
REGISTERED_UNIVERSE = ("crosswalk", "predecessor_overrides", "security_sector_overrides",
                       "sic_mapping")

# Why each registered object is excluded. An exclusion with no reason is not an exclusion.
EXCLUSIONS = {
    "predecessor_overrides": {
        "status": "REGISTERED_NOT_CONSUMED",
        "reason": "not part of Phase 2B production semantics",
        "evidence_consumer": "app/research/mr002/dataset.py::sector_resolver - splits CIK "
                             "intervals at the countersigned predecessor event date",
        "evidence_non_consumer": "app/research/mr002/spq1/adapters/identity_adapter.py::"
                                 "load_identity_registry - Phase 2B reads `crosswalk` RAW",
        "consequence_if_consumed": "Phase 3B would apply override semantics the development "
                                   "window never applied, breaking R-PROD continuity",
    },
    "security_sector_overrides": {
        "status": "REGISTERED_NOT_CONSUMED",
        "reason": "not part of Phase 2B production semantics",
        "evidence_consumer": "app/research/mr002/dataset.py::sector_resolver - passed into "
                             "SectorResolver",
        "evidence_non_consumer": "app/research/mr002/spq1/phase2b/orchestrator.py::"
                                 "_guarded_load_sic_map - Phase 2B reads `sic_mapping` RAW",
        "consequence_if_consumed": "Phase 3B would resolve sectors differently from development",
    },
}
DISPOSITION = (
    "The two override tables remain GOVERNED reference artifacts. They are not de-registered, not "
    "deleted, and may be used by other MR-002 analysis paths. They are simply not part of Phase 3B "
    "execution semantics, and Phase 3B does not activate override semantics."
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))


class ReferenceManifestRefused(Exception):
    """The reference manifest cannot be produced truthfully. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _read(rel: str) -> dict:
    with open(os.path.join(_REPO, rel), encoding="utf-8") as fh:
        return json.load(fh)


def build() -> dict:
    registration = _read(P11)["reference_layer"]["tables"]
    schemas = _read(P9)["schema_identity"]["tables"]

    registered = tuple(sorted(registration))
    if registered != REGISTERED_UNIVERSE:
        raise ReferenceManifestRefused(
            f"the registered reference universe changed: {registered} != {REGISTERED_UNIVERSE}. An "
            "unregistered reference object must never be projected into an execution manifest."
        )
    if not set(CONSUMED) <= set(registered):
        raise ReferenceManifestRefused("consumed set is not a subset of the registered universe")
    if set(EXCLUSIONS) != set(registered) - set(CONSUMED):
        raise ReferenceManifestRefused("every excluded object must be named and justified")

    structure, schema_out, objects = {}, {}, {}
    for table in CONSUMED:
        reg = registration[table]
        if table not in schemas:
            raise ReferenceManifestRefused(f"{table}: no registered column order in P9")
        if reg["object_key"].split("/", 1)[0] != "reference":
            raise ReferenceManifestRefused(
                f"{table}: {reg['object_key']} is not a reference object. A validation-partition "
                "object must never enter the reference manifest."
            )
        for field in ("object_sha256", "version_id", "row_count", "content_sha256"):
            if not reg.get(field):
                raise ReferenceManifestRefused(f"{table}: registration lacks {field}")
        structure[table] = {"row_count": int(reg["row_count"])}
        schema_out[table] = schemas[table]
        objects[reg["object_key"]] = {
            "sha256": reg["object_sha256"],
            "version_id": reg["version_id"],
            "content_sha256": reg["content_sha256"],
            "row_count": int(reg["row_count"]),
        }

    return {
        "record_type": "MR002_Phase3B_ReferenceManifest",
        "version": "1.0",
        "artifact_kind": "EXECUTION_INPUT_BINDING",
        "window": "validation",
        "prefix": "reference",
        "sealed": False,
        "derived_not_chosen": (
            "every value is a one-hop projection of the P11 reference registration and the P9 "
            "registered column order. The generator selects nothing."
        ),
        "authority": {
            "objects_and_identities": P11 + " -> reference_layer.tables",
            "column_order": P9 + " -> schema_identity.tables",
        },
        # decode_all / TableCommitment read these two keys.
        "structure": structure,
        "schema_identity": {"tables": schema_out},
        "objects": objects,
        "reference_scope": {
            "registered_reference_universe": list(REGISTERED_UNIVERSE),
            "phase3b_consumed_reference_set": list(CONSUMED),
            "registered_not_consumed": EXCLUSIONS,
            "subset_rule": "consumed set is a strict subset of the registered universe; every "
                           "exclusion is named with its reason and evidence",
            "fetch_rule": (
                "the entry point fetches EXACTLY the objects this manifest declares - never every "
                "object sharing the reference/ prefix. Sharing a prefix is not a reason to fetch."
            ),
            "invariant": "fetched == decoded == consumed == manifest_consumed_set",
            "disposition_of_excluded": DISPOSITION,
            "classification": "reference-scope clarification, NOT a research-semantic change",
        },
        "consumers": {
            "sic_mapping": "candidates.sic_map_from - registered SIC range to research sector and "
                           "sector proxy, with effective dates",
            "crosswalk": "candidates.cik_by_symbol_from and candidates.lineage_from - CIK "
                         "resolution and PIT security lineage",
        },
        "boundary": (
            "Reference objects are interval-valid registries: not part of any sealed partition and "
            "not under the OOS DENY. Zero-data. No AWS call, no sealed object, no credential."
        ),
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_ReferenceManifest_v1.0.json")
    payload = _canonical(record)
    with open(out, "wb") as fh:
        fh.write(payload)
    file_sha = hashlib.sha256(payload).hexdigest()
    print(f"wrote {out}")
    print(f"record identity {record['record_identity_sha256']}")
    print(f"FILE sha256     {file_sha}   <-- bind THIS in the entry point")
    print(f"consumed        {list(CONSUMED)}")
    print(f"excluded        {sorted(EXCLUSIONS)} (REGISTERED_NOT_CONSUMED)")


if __name__ == "__main__":
    main()
