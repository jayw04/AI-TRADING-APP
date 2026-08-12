"""Register the twelve InputIdentityRegistry slots for the validation window.

Phase 2B populated seven of these with opaque development labels -- ``dev-spy``, ``dev-sec``,
``dev-map``, ``dev-sic``, ``dev-cross``, ``dev-earn`` -- which established neither reproducibility
nor a transferable identity. They satisfied the registry's SHAPE during development and nothing
more, so they are recorded here as PHASE2B_INPUT_IDENTITY_PLACEHOLDERS -- NONTRANSFERABLE. Reusing
them would stamp development provenance onto validation records; inventing ``val-*`` would be the
same failure with a different prefix.

What must stay continuous is each slot's MEANING. The SPY slot still identifies the SPY input, the
PIT sector slot still identifies the sector source, the crosswalk slot still identifies the security
lineage source. Replacing an opaque label with a deterministic provenance identity is an
identity-quality correction, not an economic change.

Each window-dependent slot binds TWO things:

    slot_identity = H(source_object_identity || interpretation_identity)

Source alone is not enough: two different extraction rules over the same object would otherwise
receive the same identity, and the slot means "the SPY total-return series", not "some table
containing SPY". Interpretation alone is not enough either. Both, or the slot is not an identity.

Source identities come from the ALREADY-REGISTERED commitments -- the sealed-store upload manifest
for window objects, the P11 reference-layer registration for reference objects. No sealed object is
opened to compute them, so the opening stays unspent.

Interpretation identities are the git blob digests of the frozen modules that perform each
extraction, taken from the executing-closure binding. Blob bytes, never worktree bytes.

``price_return_adjustment_policy`` carries ``"v3"`` unchanged: it names the frozen price-series
policy, not a window-specific dataset instance.

Zero-data instrument: reads governed records and git objects. No AWS call, no sealed object, no
credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
GOV = "docs/review/mr002/phase3bc"
BACKEND = "apps/backend"

UPLOAD = f"{GOV}/MR002_SealedStoreUploadManifest_v1.0.json"
P11 = f"{GOV}/MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json"
WINDOW = "validation"

PLACEHOLDERS = {
    "spy_total_return_series": "dev-spy",
    "sector_etf_source_series": "dev-sec",
    "sector_etf_proxy_mapping_table": "dev-map",
    "pit_sector_source": "dev-sic",
    "pit_identity_registry": "dev-cross",
    "eligibility_evidence_sources": "dev-earn",
}
FORBIDDEN_PREFIXES = ("dev-", "val-", "obs-", "id-", "test-")

# Each window-dependent slot: its source objects and the frozen modules that interpret them.
SLOTS = {
    "spy_total_return_series": {
        "meaning": "the SPY total-return series used as the market factor",
        "sources": [("window", "etf_prices")],
        "interpretation_modules": [
            "app/research/mr002/phase3b/assembly.py",
            "app/research/mr002/spq1/returns.py",
        ],
        "rule": "SPY selected from the registered ETF series by the frozen proxy ticker; "
                "total-return semantics per the registered price-return adjustment policy v3",
    },
    "sector_etf_source_series": {
        "meaning": "the sector-ETF proxy series used as the sector factor",
        "sources": [("window", "etf_prices")],
        "interpretation_modules": [
            "app/research/mr002/phase3b/assembly.py",
            "app/research/mr002/spq1/sector_factor.py",
        ],
        "rule": "sector-ETF source-series extraction over the same registered ETF object; a "
                "DIFFERENT rule over the SAME object, which is why source alone cannot identify it",
    },
    "sector_etf_proxy_mapping_table": {
        "meaning": "the SIC-range to research-sector and sector-proxy mapping",
        "sources": [("reference", "sic_mapping")],
        "interpretation_modules": ["app/research/mr002/spq1/phase2b/sic_sector.py"],
        "rule": "registered mapping-table semantics: SIC range bounds with effective dates to "
                "research_sector and sector_etf",
    },
    "pit_sector_source": {
        "meaning": "the point-in-time SIC observation source",
        "sources": [("window", "sic_observations")],
        "interpretation_modules": [
            "app/research/mr002/spq1/sector_pit.py",
            "app/research/mr002/spq1/phase2b/cutoff.py",
        ],
        "rule": "PIT acceptance-timestamp and close-t cutoff semantics; no forward fill before the "
                "first observation",
    },
    "pit_identity_registry": {
        "meaning": "the point-in-time security lineage source",
        "sources": [("reference", "crosswalk")],
        "interpretation_modules": [
            "app/research/mr002/spq1/security_identity.py",
            "app/research/mr002/phase3b/candidates.py",
        ],
        "rule": "registered interval/lineage interpretation: permaticker/ticker effective intervals "
                "and relationship types mapped to corporate-action continuity",
    },
}

# The eligibility composite is enumerated mechanically below rather than assumed.
ELIGIBILITY = {
    "meaning": "the complete governed source set capable of changing the eligibility evidence trail",
    "trail_producing_sources": [("window", "anchors")],
    "population_determining_sources": [("window", "universe")],
    "interpretation_modules": [
        "app/research/mr002/phase3b/earnings_blackout.py",
        "app/research/mr002/spq1/eligibility.py",
        "app/research/mr002/spq1/constants.py",
        "app/research/mr002/phase3b/candidates.py",
    ],
    "rule": "the two frozen earnings controls (70-calendar-day stale-anchor blackout, two-session "
            "post-release cooling) evaluated under the fixed precedence taxonomy",
}

POLICY_SLOT = ("price_return_adjustment_policy", "v3")

_ = sys  # module is a CLI; sys is used in main


class IdentityRegistrationRefused(Exception):
    """A slot cannot be derived from a governed authority. Nothing is emitted."""


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _compact(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("ascii")


def _read(rel: str) -> dict:
    path = os.path.join(_REPO, rel)
    if not os.path.exists(path):
        raise IdentityRegistrationRefused(f"governing artifact absent: {rel}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _blob_sha(commit: str, rel: str) -> str:
    proc = subprocess.run(
        ["git", "-C", _REPO, "show", f"{commit}:{BACKEND}/{rel}"], capture_output=True
    )
    if proc.returncode != 0:
        raise IdentityRegistrationRefused(f"module absent at {commit[:7]}: {rel}")
    return hashlib.sha256(proc.stdout).hexdigest()


def source_identity(kind: str, table: str) -> dict:
    """Registered object identity, taken from an existing commitment. No sealed read."""
    if kind == "window":
        objects = _read(UPLOAD).get("objects") or {}
        key = f"{WINDOW}/{table}.parquet"
        meta = objects.get(key)
        if not meta or not meta.get("sha256"):
            raise IdentityRegistrationRefused(f"{key}: no registered sha256 in the upload manifest")
        return {"kind": "window", "table": table, "object_key": key,
                "sha256": meta["sha256"], "version_id": meta.get("version_id"),
                "authority": UPLOAD}
    if kind == "reference":
        tables = _read(P11)["reference_layer"]["tables"]
        meta = tables.get(table)
        if not meta:
            raise IdentityRegistrationRefused(f"{table}: not in the P11 reference registration")
        return {"kind": "reference", "table": table, "object_key": meta["object_key"],
                "sha256": meta["object_sha256"], "content_sha256": meta["content_sha256"],
                "version_id": meta["version_id"], "authority": P11}
    raise IdentityRegistrationRefused(f"unknown source kind {kind!r}")


def interpretation_identity(commit: str, modules: list[str], rule: str) -> dict:
    digests = {m: _blob_sha(commit, m) for m in sorted(modules)}
    return {
        "modules": digests,
        "rule": rule,
        "identity": hashlib.sha256(_compact({"modules": digests, "rule": rule})).hexdigest(),
        "digest_source": "git blob bytes at the bound commit, never worktree bytes",
    }


def _slot(name: str, sources: list[dict], interp: dict) -> dict:
    src_ids = [s["sha256"] for s in sources]
    composite = hashlib.sha256(
        _compact({"sources": sorted(src_ids), "interpretation": interp["identity"]})
    ).hexdigest()
    if any(composite.startswith(p) for p in FORBIDDEN_PREFIXES):
        raise IdentityRegistrationRefused(f"{name}: derived identity looks like an opaque label")
    return {
        "identity": composite,
        "constituents": {"source_identities": sorted(src_ids),
                         "interpretation_identity": interp["identity"]},
        "construction": "sha256(compact_json({sources: sorted[source_sha256], "
                        "interpretation: interpretation_identity}))",
        "sources": sources,
        "interpretation": interp,
    }


def build(commit: str) -> dict:
    remote = subprocess.run(
        ["git", "-C", _REPO, "rev-parse", "origin/research/mr002-preregistration"],
        capture_output=True,
    ).stdout.decode().strip()
    if remote != commit:
        raise IdentityRegistrationRefused(
            f"remote head {remote[:12]} is not {commit[:12]}; identities must bind pushed bytes"
        )

    slots, registry = {}, {}
    for name, spec in SLOTS.items():
        sources = [source_identity(k, t) for k, t in spec["sources"]]
        interp = interpretation_identity(commit, spec["interpretation_modules"], spec["rule"])
        slots[name] = {"meaning": spec["meaning"], **_slot(name, sources, interp)}
        registry[name] = slots[name]["identity"]

    trail = [source_identity(k, t) for k, t in ELIGIBILITY["trail_producing_sources"]]
    population = [source_identity(k, t) for k, t in ELIGIBILITY["population_determining_sources"]]
    elig_interp = interpretation_identity(
        commit, ELIGIBILITY["interpretation_modules"], ELIGIBILITY["rule"]
    )
    elig = _slot("eligibility_evidence_sources", trail + population, elig_interp)
    elig.update({
        "meaning": ELIGIBILITY["meaning"],
        "enumeration": {
            "method": "mechanical: every module constructing an ExclusionCheck was located, and "
                      "each mapped to the governed source it reads",
            "trail_producing": {
                "sources": [s["table"] for s in trail],
                "producer": "app/research/mr002/phase3b/earnings_blackout.py - the ONLY module in "
                            "the executing closure that constructs ExclusionCheck",
            },
            "population_determining": {
                "sources": [s["table"] for s in population],
                "mechanism": "universe decides which (symbol, session) units exist, so it changes "
                             "which trails are produced even though it emits no ExclusionCheck",
            },
            "excluded_with_reason": {
                "liquidity / prices": "liquidity.py raises typed REFUSALS, not ExclusionChecks; "
                                      "precedence rank 5 has no producer in the executing closure",
                "sic_observations / sic_mapping": "feed the sector factor regression and the PIT "
                                                  "sector assignment, not the eligibility trail",
                "crosswalk": "feeds security lineage, not the eligibility trail",
                "actions / etf_prices": "feed the execution seam and the factor series",
            },
            "closure_rule": "zero missing, zero extra - the identity covers exactly the sources "
                            "capable of changing the eligibility evidence trail",
        },
    })
    slots["eligibility_evidence_sources"] = elig
    registry["eligibility_evidence_sources"] = elig["identity"]

    registry[POLICY_SLOT[0]] = POLICY_SLOT[1]
    slots[POLICY_SLOT[0]] = {
        "meaning": "the frozen price-series adjustment policy",
        "identity": POLICY_SLOT[1],
        "carried_unchanged": True,
        "rationale": "names the frozen policy, not a window-specific dataset instance, so it is "
                     "window-independent and is NOT re-derived",
    }

    for name, value in registry.items():
        if any(str(value).startswith(p) for p in FORBIDDEN_PREFIXES):
            raise IdentityRegistrationRefused(
                f"{name}={value!r} is an opaque label; refusing to register a non-derived identity"
            )
    if set(registry) != set(PLACEHOLDERS) | {POLICY_SLOT[0]}:
        raise IdentityRegistrationRefused(
            f"registered slots {sorted(registry)} != the seven this artifact exists to close"
        )

    return {
        "record_type": "MR002_Phase3B_ValidationInputIdentityRegistration",
        "version": "1.0",
        "artifact_kind": "INPUT_IDENTITY_REGISTRATION",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "window": WINDOW,
        "commit": commit,
        "purpose": (
            "Register the seven InputIdentityRegistry slots Phase 2B left as opaque development "
            "labels, as deterministic identities derived from already-frozen validation sources "
            "and frozen interpretation rules."
        ),
        "phase2b_disposition": {
            "status": "PHASE2B_INPUT_IDENTITY_PLACEHOLDERS - NONTRANSFERABLE",
            "values": PLACEHOLDERS,
            "evidence": "app/research/mr002/spq1/phase2b/orchestrator.py::_OBS_IDS",
            "finding": "labels, not registered content identities; they established neither "
                       "reproducibility nor a transferable validation identity",
            "continuity_preserved": "each slot's MEANING is unchanged; only the identity quality "
                                    "improves, so this is not an economic change",
        },
        "construction_rule": (
            "slot_identity = H(source_object_identity || interpretation_identity). Source alone "
            "would give two different extraction rules over the same object the same identity."
        ),
        "no_sealed_read": (
            "source identities come from the registered upload and P11 commitments, so no sealed "
            "object is opened and the single validation opening remains UNSPENT"
        ),
        "slots": slots,
        "registry": registry,
        "registry_identity_sha256": hashlib.sha256(_compact(registry)).hexdigest(),
        "boundary": "Zero-data. No AWS call, no sealed object, no credential.",
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _gen_validation_input_identities.py <commit-sha>")
    record = build(sys.argv[1])
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()

    out = os.path.join(_HERE, "MR002_Phase3B_ValidationInputIdentityRegistration_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    reg = os.path.join(_HERE, "MR002_Phase3B_ValidationInputIdentityRegistry_v1.0.json")
    with open(reg, "wb") as fh:
        fh.write(_canonical(record["registry"]))

    print(f"wrote {out}")
    print(f"wrote {reg}")
    print(f"record identity   {record['record_identity_sha256']}")
    print(f"registry identity {record['registry_identity_sha256']}")
    for k, v in sorted(record["registry"].items()):
        print(f"  {k:32s} {v}")


if __name__ == "__main__":
    main()
