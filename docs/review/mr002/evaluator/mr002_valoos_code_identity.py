"""MR-002 validation/OOS evaluator — code identity + refusal layer (operational increment / P3).

Refuses with REFUSED_CODE_OR_DATA_IDENTITY on any commit / tree / module-blob / container mismatch
BEFORE any window is read. Complements `mr002_valoos_identity` (which pins the governing DATA
artifacts): this module pins the executing CODE.

Two properties the qualification turns on:

  * an UNBOUND module that is present on disk is a refusal, not a shrug — otherwise code could be
    added to the evaluator directory after the binding was accepted;
  * the binding must be supplied, not inferred. `bind_from_directory` exists to MINT a binding during
    qualification; it is explicitly not a verification path, and `require_code_identity` never falls
    back to it.
"""

from __future__ import annotations

import hashlib
import json
import os

REFUSED = "REFUSED_CODE_OR_DATA_IDENTITY"

# identity fields a §4 pre-access binding must carry (P5 resolves these; P3 enforces their shape)
REQUIRED_BINDING_FIELDS = ("commit", "tree", "container_image_digest", "modules")

PENDING_SENTINELS = frozenset({"", "PENDING_EVALUATOR_BIND", "PENDING", "TBD", "UNKNOWN", "N/A"})


class RefusedCodeIdentity(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — the executing code is not the bound code."""


def _refuse(detail: str):
    raise RefusedCodeIdentity(f"{REFUSED}:{detail}")


def sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def module_digests(directory: str, *, suffix: str = ".py",
                   exclude_prefixes: tuple = ("test_", "_gen_")) -> dict:
    """SHA-256 of every evaluator module in `directory` (tests and generators excluded)."""
    out = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(suffix) or name.startswith(exclude_prefixes):
            continue
        out[name] = sha_file(os.path.join(directory, name))
    return out


def bind_from_directory(directory: str, *, commit: str, tree: str,
                        container_image_digest: str) -> dict:
    """MINT a code-identity binding. Qualification-time only — never a verification fallback."""
    for label, value in (("commit", commit), ("tree", tree),
                         ("container_image_digest", container_image_digest)):
        if not value or str(value).strip().upper() in PENDING_SENTINELS:
            _refuse(f"binding_field_unresolved:{label}")
    return {"commit": commit, "tree": tree, "container_image_digest": container_image_digest,
            "modules": module_digests(directory)}


def verify_code_identity(directory: str, binding: dict, *,
                         observed_commit: str | None = None,
                         observed_tree: str | None = None,
                         observed_container_image_digest: str | None = None) -> dict:
    """Compare the on-disk evaluator against a supplied binding. Reports; does not raise."""
    problems = []
    for field in REQUIRED_BINDING_FIELDS:
        if field not in binding:
            problems.append({"kind": "binding_field_missing", "field": field})
        elif field != "modules" and str(binding[field]).strip().upper() in PENDING_SENTINELS:
            problems.append({"kind": "binding_field_unresolved", "field": field,
                             "value": binding[field]})

    bound_modules = binding.get("modules") or {}
    if not bound_modules:
        problems.append({"kind": "binding_field_unresolved", "field": "modules"})
    observed = module_digests(directory)
    for name, want in sorted(bound_modules.items()):
        got = observed.get(name)
        if got is None:
            problems.append({"kind": "module_missing", "module": name})
        elif got != want:
            problems.append({"kind": "module_drift", "module": name, "bound": want, "observed": got})
    for name in sorted(set(observed) - set(bound_modules)):
        problems.append({"kind": "module_unbound", "module": name, "observed": observed[name]})

    for field, got in (("commit", observed_commit), ("tree", observed_tree),
                       ("container_image_digest", observed_container_image_digest)):
        if got is not None and binding.get(field) != got:
            problems.append({"kind": "identity_mismatch", "field": field,
                             "bound": binding.get(field), "observed": got})

    return {"matches": not problems, "problems": problems,
            "bound_module_count": len(bound_modules), "observed_module_count": len(observed)}


def require_code_identity(directory: str, binding: dict, **observed) -> dict:
    """Fail-closed gate. MUST be called before any window read."""
    if not isinstance(binding, dict):
        _refuse("binding_absent")
    report = verify_code_identity(directory, binding, **observed)
    if not report["matches"]:
        kinds = sorted({p["kind"] for p in report["problems"]})
        _refuse(",".join(kinds))
    return report


def binding_sha256(binding: dict) -> str:
    return hashlib.sha256(
        json.dumps(binding, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
