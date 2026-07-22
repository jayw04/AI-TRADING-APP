"""MR-002 evaluator — SS4 pre-access binding qualification (prerequisite P5).

Produces the AUTHORITATIVE evaluator binding prospectively: enumerate the then-current directory
mechanically, classify every file under the registered inclusion/exclusion rule, qualify the
inventory fail-closed, and only then emit a binding.

`PENDING_EVALUATOR_BIND` is preserved, per leg, until that leg genuinely resolves. A binding whose
container image does not exist is `PARTIALLY_RESOLVED`, never quietly complete — an unresolved leg
must read as unresolved at the point of use, not be discovered at run time.

Nothing here reads a dataset, opens a partition, or infers a binding from a historical registry.
"""

from __future__ import annotations

import hashlib
import json
import os

REFUSED = "REFUSED_EVALUATOR_BINDING"
PENDING = "PENDING_EVALUATOR_BIND"

# registered SS4 inclusion / exclusion rule
INCLUDED_MODULE = "INCLUDED_MODULE"
EXCLUDED_TEST = "EXCLUDED_TEST"
EXCLUDED_GENERATOR = "EXCLUDED_GENERATOR"
EXCLUDED_NON_EVALUATOR = "EXCLUDED_NON_EVALUATOR"
EXCLUDED_CACHE = "EXCLUDED_CACHE"
CLASSES = (INCLUDED_MODULE, EXCLUDED_TEST, EXCLUDED_GENERATOR, EXCLUDED_NON_EVALUATOR,
           EXCLUDED_CACHE)

TEST_PREFIX = "test_"
GENERATOR_PREFIX = "_gen_"

# the SS4 element roster; every element is RESOLVED with an identity or explicitly UNRESOLVED
SECTION4_ELEMENTS = ("source_commit", "source_tree", "container_image_digest",
                     "dependency_lock", "data_manifest_identity", "benchmark_impl",
                     "cost_model_impl", "metric_impl", "bootstrap_impl", "pbo_dsr_impl",
                     "report_schema", "expected_output_paths")


class BindingRefused(Exception):
    """REFUSED_EVALUATOR_BINDING — qualification or verification failed; no binding is emitted."""


def _refuse(detail: str):
    raise BindingRefused(f"{REFUSED}:{detail}")


def sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def classify(name: str, *, is_dir: bool = False) -> str:
    """Classify one directory entry under the registered rule. Every entry gets a class."""
    if is_dir or name == "__pycache__":
        return EXCLUDED_CACHE
    if not name.endswith(".py"):
        return EXCLUDED_NON_EVALUATOR
    if name.startswith(TEST_PREFIX):
        return EXCLUDED_TEST
    if name.startswith(GENERATOR_PREFIX):
        return EXCLUDED_GENERATOR
    return INCLUDED_MODULE


def enumerate_inventory(directory: str) -> dict:
    """Mechanically enumerate and classify EVERY entry. Nothing is silently skipped."""
    included, excluded = {}, []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        cls = classify(name, is_dir=os.path.isdir(path))
        if cls == INCLUDED_MODULE:
            included[name] = sha_file(path)
        else:
            excluded.append({"path": name, "class": cls,
                             "sha256": None if cls == EXCLUDED_CACHE else sha_file(path)})
    counts = {c: sum(1 for e in excluded if e["class"] == c) for c in CLASSES}
    counts[INCLUDED_MODULE] = len(included)
    return {"included_modules": included, "excluded": excluded, "counts": counts,
            "entry_count": len(included) + len(excluded)}


def qualify_inventory(directory: str, *, previous_binding: dict | None = None) -> dict:
    """Fail-closed qualification of the then-current inventory.

    Refuses on duplicate module content (ambiguous identity) and, when a previous binding is
    supplied, on drift, missing, renamed, or unbound modules.
    """
    inv = enumerate_inventory(directory)
    included = inv["included_modules"]
    if not included:
        _refuse("empty_inventory")

    problems = []

    by_hash: dict = {}
    for name, digest in included.items():
        by_hash.setdefault(digest, []).append(name)
    for digest, names in sorted(by_hash.items()):
        if len(names) > 1:
            problems.append({"kind": "duplicate_module_content", "modules": sorted(names),
                             "sha256": digest})

    if previous_binding is not None:
        bound = previous_binding.get("included_modules") or {}
        bound_by_hash = {d: n for n, d in bound.items()}
        for name, digest in sorted(bound.items()):
            if name in included:
                if included[name] != digest:
                    problems.append({"kind": "module_drift", "module": name,
                                     "bound": digest, "observed": included[name]})
            elif digest in by_hash:
                problems.append({"kind": "module_renamed", "bound_module": name,
                                 "now_named": sorted(by_hash[digest]), "sha256": digest})
            else:
                problems.append({"kind": "module_missing", "module": name})
        for name, digest in sorted(included.items()):
            if name not in bound:
                kind = "module_unbound"
                if digest in bound_by_hash:
                    kind = "module_renamed_target"
                problems.append({"kind": kind, "module": name, "sha256": digest,
                                 **({"was_named": bound_by_hash[digest]}
                                    if kind == "module_renamed_target" else {})})

    return {"inventory": inv, "problems": problems, "qualified": not problems,
            "included_module_count": len(included)}


def require_qualified(directory: str, *, previous_binding: dict | None = None) -> dict:
    report = qualify_inventory(directory, previous_binding=previous_binding)
    if not report["qualified"]:
        _refuse(",".join(sorted({p["kind"] for p in report["problems"]})))
    return report


def build_binding(directory: str, *, source_commit: str, source_tree: str,
                  dependency_lock: str, dependency_lock_sha256: str,
                  data_manifest_identity: dict, expected_output_paths: list,
                  element_modules: dict, container_image_digest: str | None = None,
                  previous_binding: dict | None = None) -> dict:
    """Emit the authoritative SS4 binding. Refuses unless qualification passes first.

    `container_image_digest=None` leaves that leg PENDING — a bound image must actually exist.
    """
    for label, value in (("source_commit", source_commit), ("source_tree", source_tree),
                         ("dependency_lock_sha256", dependency_lock_sha256)):
        if not value or str(value).strip().upper() in {"", PENDING, "TBD", "PENDING", "UNKNOWN"}:
            _refuse(f"unresolved_required_field:{label}")

    report = require_qualified(directory, previous_binding=previous_binding)
    inv = report["inventory"]
    included = inv["included_modules"]

    for element, module in sorted(element_modules.items()):
        if module not in included:
            _refuse(f"section4_element_module_not_in_inventory:{element}:{module}")

    elements = {
        "source_commit": {"status": "RESOLVED", "value": source_commit},
        "source_tree": {"status": "RESOLVED", "value": source_tree},
        "container_image_digest": ({"status": "RESOLVED", "value": container_image_digest}
                                   if container_image_digest else
                                   {"status": "UNRESOLVED", "value": PENDING,
                                    "producer": "runtime producer (P10 / deployment)",
                                    "reason": "no qualifying bound image exists"}),
        "dependency_lock": {"status": "RESOLVED", "file": dependency_lock,
                            "sha256": dependency_lock_sha256},
        "data_manifest_identity": {"status": "RESOLVED_BY_REGISTERED_IDENTITY",
                                   **data_manifest_identity,
                                   "note": "bound from the registered preregistration identity; the "
                                           "physical artifact is verified at run time under the "
                                           "access boundary, never opened here"},
        "expected_output_paths": {"status": "RESOLVED", "value": expected_output_paths},
    }
    for element, module in sorted(element_modules.items()):
        elements[element] = {"status": "RESOLVED", "module": module, "sha256": included[module]}

    missing_elements = [e for e in SECTION4_ELEMENTS if e not in elements]
    if missing_elements:
        _refuse(f"section4_elements_unaccounted:{','.join(missing_elements)}")

    unresolved = sorted(e for e, v in elements.items() if v["status"] == "UNRESOLVED")
    return {
        "record_type": "MR002_EvaluatorBinding", "version": "1.0",
        "binding_state": "RESOLVED" if not unresolved else "PARTIALLY_RESOLVED",
        "unresolved_elements": unresolved,
        "pending_evaluator_bind": PENDING if unresolved else None,
        "inclusion_rule": {
            "included": "*.py excluding the test and generator prefixes",
            "test_prefix": TEST_PREFIX, "generator_prefix": GENERATOR_PREFIX,
            "excluded_classes": [c for c in CLASSES if c != INCLUDED_MODULE],
            "derivation": "mechanically enumerated at qualification time; the count is NOT an "
                          "adjudicated constant and must be re-derived on any tree change"},
        "included_modules": included,
        "included_module_count": len(included),
        "excluded": inv["excluded"],
        "inventory_counts": inv["counts"],
        "entry_count": inv["entry_count"],
        "inventory_digest": hashlib.sha256(
            json.dumps(included, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest(),
        "section4_elements": elements,
        "verification_rule": "a run is refused unless (a) every included module reproduces its bound "
                             "digest in the THEN-current tree, (b) no unbound module is present, "
                             "(c) no module is missing, renamed, duplicated, or drifted, and (d) no "
                             "element remains UNRESOLVED",
        "authorizes": "NOTHING - this is an identity binding; it grants no data access, releases no "
                      "credentials, and computes no performance",
    }


def verify_binding(directory: str, binding: dict) -> dict:
    """Fail-closed verification of the then-current tree against a binding."""
    if not isinstance(binding, dict) or binding.get("record_type") != "MR002_EvaluatorBinding":
        _refuse("binding_absent_or_wrong_type")
    report = qualify_inventory(directory, previous_binding=binding)
    unresolved = binding.get("unresolved_elements") or []
    ok = report["qualified"] and not unresolved
    return {"matches": ok, "problems": report["problems"],
            "unresolved_elements": unresolved,
            "binding_state": binding.get("binding_state"),
            "included_module_count": report["included_module_count"]}


def require_binding(directory: str, binding: dict) -> dict:
    """The gate a run must pass BEFORE any window read."""
    report = verify_binding(directory, binding)
    if report["problems"]:
        _refuse(",".join(sorted({p["kind"] for p in report["problems"]})))
    if report["unresolved_elements"]:
        _refuse(f"unresolved_section4_elements:{','.join(report['unresolved_elements'])}")
    return report
