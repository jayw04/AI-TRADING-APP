#!/usr/bin/env python3
"""PU-1 licence-registry closure tripwire (CI check b of the PU-1 presentation gate; mini-ADR 0057).

WHAT THIS CLOSES. The runtime gate already treats an unregistered source as ``UNKNOWN`` (blocked).
That fails SAFE but late: a new ingestion source would be silently "UNKNOWN" forever and nobody
would have read its terms. This check moves the question to BUILD time: every data source that
ingestion code reaches must resolve, through the checked-in map
``apps/backend/ci/pu1_source_map.json``, to a ``source_id`` that has a row in the licence registry
``app/licensing/data_license_registry.json``. An unmapped source, or a mapped source with no
registry row, fails the build. (Registering a source as UNKNOWN passes: the point is that someone
had to name it and the registry has a row, not that it is presentable.)

WHAT COUNTS AS AN INGESTION SOURCE REFERENCE (deterministic; Python AST, tests excluded):

  host     a string literal containing ``http(s)://<host>`` -> ``hosts`` (exact host or a dotted
           suffix) must map it to a source_id, or ``non_data_hosts`` must list it with a reason.
  import   an ``import`` / ``from`` of a vendor SDK namespace (``alpaca``) -> ``imports`` (module
           prefix -> source_id) or ``non_data_imports`` (prefix or exact name, with reason).
  module   a non-network source consumed from a frozen snapshot (e.g. the FRED T-bill file) is
           declared per file in ``modules`` (file -> source_id).
  altdata  every ``DataSource.source_name`` in ``app/altdata/source_registry.py`` must appear in
           ``altdata_source_names`` and map to a registered source_id.

Every mapping target must exist in the registry (rule: REGISTRY ROW MISSING). Shell scripts are not
scanned (their only external hosts are infrastructure: docker, github, ntfy, IMDS).

MIXED SOURCES. The Alpaca broker/trading API (``api.alpaca.markets``, ``paper-api.alpaca.markets``,
the ``alpaca.trading`` SDK) returns the owner's own transaction/account records AND marked-to-market
market-data fields in one response, so it is neither a data host nor a non-data host. It is listed
under ``mixed_hosts`` / ``mixed_imports`` with a pointer to the per-field table
(``app/licensing/broker_field_classification.json``) and the registered source ids it can carry.

BROKER FIELD ACCESS (``broker_field_access`` in the map). A Python module that READS one of the
table's AST-enforced market-data field names -- an attribute load (``p.market_value``), a string
subscript (``r["market_value"]``) or ``.get/.pop/.setdefault("market_value")`` -- must CALL a
helper from ``app.licensing.broker_fields`` or be listed in the allowlist with a reason. LIMITS
(documented, tested): ``getattr(o, name)`` and constructed keys, keyword arguments and dict-literal
keys, values reached through ``model_dump()`` of a third-party object, and a name that is not in the
enforced list (e.g. ``equity``) are NOT caught; a helper call anywhere in the module satisfies the
rule for the module, it does not prove each individual access is routed through it.

Run from the repository root. Exit 0 = closed. Exit 1 = violation(s). Exit 2 = unusable input.
Disabling this check requires an ADR.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCE_MAP = REPO / "apps" / "backend" / "ci" / "pu1_source_map.json"
REGISTRY_JSON = REPO / "apps" / "backend" / "app" / "licensing" / "data_license_registry.json"
ALTDATA_REGISTRY = REPO / "apps" / "backend" / "app" / "altdata" / "source_registry.py"

SCAN_ROOTS = (
    "apps/backend/app",
    "apps/backend/scripts",
    "scripts",
    "deploy",
    "apps/mcp-server",
    "apps/mcp-workbench",
    "apps/agent",
)
SKIP_PARTS = {"tests", "test", ".venv", "node_modules", "__pycache__", "alembic", "site-packages"}
VENDOR_SDK_ROOTS = ("alpaca",)
# Names exported by app/licensing/broker_fields.py that count as "going through the helper"
# (tests assert this set equals broker_fields.HELPER_NAMES).
HELPER_NAMES = frozenset(
    {
        "classify_field",
        "sources_of_fields",
        "scope_of_fields",
        "subset_with_lineage",
        "taint_from_fields",
        "field_license_block",
        "market_data_field_names",
    }
)
HELPER_MODULE_PARENT = "app.licensing"
HELPER_MODULE = "app.licensing.broker_fields"
LICENSING_DIR = "apps/backend/app/licensing/"
_URL = re.compile(r"https?://([A-Za-z0-9.\-_]+)")


def _load_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"PU-1 registry closure: {what} unusable ({exc})", file=sys.stderr)
        raise SystemExit(2) from exc
    if not isinstance(data, dict):
        print(f"PU-1 registry closure: {what} is not an object", file=sys.stderr)
        raise SystemExit(2)
    return data


def _host_matches(host: str, pattern: str) -> bool:
    h, p = host.lower(), pattern.lower()
    return h == p or h.endswith("." + p)


def _prefix_matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _altdata_source_names() -> list[str]:
    """``source_name="..."`` keywords of the DataSource instances in the EAD registry (AST)."""
    try:
        tree = ast.parse(ALTDATA_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "source_name"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    names.append(kw.value.value)
    return names


def _field_reads(tree: ast.AST, names: frozenset[str]) -> dict[str, int]:
    """Market-data field names READ in ``tree`` (see the module docstring for what counts)."""
    hits: dict[str, int] = {}

    def hit(name: str) -> None:
        hits[name] = hits.get(name, 0) + 1

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in names:
            if isinstance(node.ctx, ast.Load):
                hit(node.attr)
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
            and node.slice.value in names
        ):
            if isinstance(node.ctx, ast.Load):
                hit(node.slice.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "pop", "setdefault")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value in names
        ):
            hit(node.args[0].value)
    return hits


def _calls_helper(tree: ast.AST) -> bool:
    """True if the module imports from ``app.licensing[.broker_fields]`` and CALLS a helper."""
    bound: set[str] = set()  # local names bound to helper functions
    module_aliases: set[str] = set()  # local names bound to the broker_fields module
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == HELPER_MODULE:
                bound.update((a.asname or a.name) for a in node.names if a.name in HELPER_NAMES)
            elif node.module == HELPER_MODULE_PARENT:
                bound.update((a.asname or a.name) for a in node.names if a.name in HELPER_NAMES)
                module_aliases.update(
                    (a.asname or a.name) for a in node.names if a.name == "broker_fields"
                )
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == HELPER_MODULE:
                    module_aliases.add(a.asname or a.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in bound:
                return True
            if isinstance(f, ast.Attribute) and f.attr in HELPER_NAMES:
                base = f.value
                if isinstance(base, ast.Name) and base.id in module_aliases:
                    return True
                if isinstance(base, ast.Attribute) and ast.unparse(base) == HELPER_MODULE:
                    return True
    return False


def _py_files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if base.is_dir():
            out.extend(
                p
                for p in sorted(base.rglob("*.py"))
                if not SKIP_PARTS & set(p.relative_to(REPO).parts)
            )
    return out


def check() -> list[str]:
    smap = _load_json(SOURCE_MAP, "source map")
    reg = _load_json(REGISTRY_JSON, "licence registry")
    registered = {
        str(e.get("source_id", "")).strip().lower()
        for e in reg.get("entries", [])
        if isinstance(e, dict)
    }
    hosts = [e for e in smap.get("hosts", []) if isinstance(e, dict)]
    non_data_hosts = [e for e in smap.get("non_data_hosts", []) if isinstance(e, dict)]
    mixed_hosts = [e for e in smap.get("mixed_hosts", []) if isinstance(e, dict)]
    mixed_imports = [e for e in smap.get("mixed_imports", []) if isinstance(e, dict)]
    access = smap.get("broker_field_access")
    imports = [e for e in smap.get("imports", []) if isinstance(e, dict)]
    non_data_imports = [e for e in smap.get("non_data_imports", []) if isinstance(e, dict)]
    modules = [e for e in smap.get("modules", []) if isinstance(e, dict)]
    altdata = smap.get("altdata_source_names", {})
    problems: list[str] = []

    # Every mapping must name a registered source, and every non-data entry must say why.
    def need_registered(kind: str, key: str, sid: object) -> None:
        if not isinstance(sid, str) or sid.strip().lower() not in registered:
            problems.append(
                f"REGISTRY ROW MISSING: {kind} {key!r} maps to {sid!r}, which has no row in "
                "app/licensing/data_license_registry.json"
            )

    for e in hosts:
        need_registered("host", str(e.get("host")), e.get("source_id"))
    for e in imports:
        need_registered("import", str(e.get("prefix")), e.get("source_id"))
    for e in modules:
        need_registered("module", str(e.get("file")), e.get("source_id"))
        if not (REPO / str(e.get("file", ""))).is_file():
            problems.append(f"module mapping names a missing file: {e.get('file')!r} (stale)")
    if isinstance(altdata, dict):
        for name, sid in altdata.items():
            need_registered("altdata source_name", str(name), sid)
    for e in [*non_data_hosts, *non_data_imports]:
        if not str(e.get("reason", "")).strip():
            problems.append(f"non-data mapping without a reason: {e}")
    for e in [*mixed_hosts, *mixed_imports]:
        key = str(e.get("host") or e.get("prefix"))
        if e.get("classification") != "MIXED":
            problems.append(f"MIXED mapping {key!r} must have classification 'MIXED'")
        table = e.get("field_classification")
        if not isinstance(table, str) or not (REPO / table).is_file():
            problems.append(f"MIXED mapping {key!r} points at a missing field table: {table!r}")
        ids = e.get("source_ids")
        if not isinstance(ids, list) or not ids:
            problems.append(f"MIXED mapping {key!r} must list the source_ids it can carry")
        else:
            for sid in ids:
                need_registered("mixed source", key, sid)

    for name in _altdata_source_names():
        if not isinstance(altdata, dict) or name not in altdata:
            problems.append(
                f"UNMAPPED altdata source_name {name!r} in app/altdata/source_registry.py "
                "(add it to altdata_source_names and give it a licence-registry row)"
            )

    for path in _py_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: cannot parse ({exc})")
            continue
        seen_hosts: set[str] = set()
        seen_imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                seen_hosts.update(m.group(1) for m in _URL.finditer(node.value))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in VENDOR_SDK_ROOTS:
                    seen_imports.add(node.module)
            elif isinstance(node, ast.Import):
                seen_imports.update(
                    a.name for a in node.names if a.name.split(".")[0] in VENDOR_SDK_ROOTS
                )
        for host in sorted(seen_hosts):
            ok = any(
                _host_matches(host, str(e.get("host", "")))
                for e in hosts + non_data_hosts + mixed_hosts
            )
            if not ok:
                problems.append(
                    f"UNMAPPED data host {host!r} in {rel}: map it to a licence-registry "
                    "source_id (hosts) or declare it non-data with a reason (non_data_hosts) in "
                    "apps/backend/ci/pu1_source_map.json, and register the source"
                )
        for mod in sorted(seen_imports):
            ok = any(
                _prefix_matches(mod, str(e.get("prefix", ""))) for e in imports + mixed_imports
            ) or any(
                _prefix_matches(mod, str(e.get("prefix", ""))) or mod == e.get("exact")
                for e in non_data_imports
            )
            if not ok:
                problems.append(
                    f"UNMAPPED vendor SDK import {mod!r} in {rel}: add it to imports "
                    "(with a registered source_id) or non_data_imports (with a reason)"
                )
    problems.extend(_check_broker_field_access(access))
    return problems


def _check_broker_field_access(access: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(access, dict):
        return ["broker_field_access section missing from the source map"]
    table_rel = access.get("field_table")
    table_path = REPO / str(table_rel)
    try:
        table = json.loads(table_path.read_text(encoding="utf-8"))
        enforced = frozenset(str(n).lower() for n in table["ast_enforced_market_data_names"])
        kinds = table["kinds"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"broker field table unusable ({table_rel!r}): {exc}"]
    # Table sanity: an enforced name must never be classified OWNER_RECORD in any response kind,
    # and must be MARKET_DATA somewhere (otherwise the enforcement list contradicts the table).
    seen_md: set[str] = set()
    for kind, body in kinds.items():
        for fname, spec in body.get("fields", {}).items():
            cls = spec.get("class")
            if fname.lower() in enforced:
                if cls == "OWNER_RECORD":
                    problems.append(
                        f"field table: enforced market-data name {fname!r} is OWNER_RECORD in "
                        f"kind {kind!r}"
                    )
                else:
                    seen_md.add(fname.lower())
    for n in sorted(enforced - seen_md):
        problems.append(f"field table: enforced name {n!r} is not classified MARKET_DATA anywhere")

    allow: dict[str, dict] = {}
    for i, e in enumerate(access.get("allowlist", [])):
        if not isinstance(e, dict) or not isinstance(e.get("file"), str):
            problems.append(f"broker_field_access.allowlist[{i}]: needs a 'file'")
            continue
        if not str(e.get("reason", "")).strip():
            problems.append(f"broker_field_access.allowlist[{i}] {e['file']}: a reason is required")
        if e["file"] in allow:
            problems.append(f"broker_field_access.allowlist: duplicate entry for {e['file']}")
        allow[e["file"]] = e

    reads_by_file: dict[str, dict[str, int]] = {}
    helper_files: set[str] = set()
    for path in _py_files():
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(LICENSING_DIR):
            continue  # the helper and lineage modules themselves
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue  # already reported by the host/import pass
        reads = _field_reads(tree, enforced)
        if not reads:
            continue
        reads_by_file[rel] = reads
        if _calls_helper(tree):
            helper_files.add(rel)
    for rel, reads in sorted(reads_by_file.items()):
        if rel in helper_files:
            continue
        entry = allow.get(rel)
        if entry is None:
            problems.append(
                f"UNCLASSIFIED broker market-data field read in {rel}: {sorted(reads)} -- go "
                "through app.licensing.broker_fields (sources_of_fields / scope_of_fields / "
                "subset_with_lineage / taint_from_fields) or list the module in "
                "broker_field_access.allowlist with a reason"
            )
            continue
        listed = {str(x).lower() for x in entry.get("fields", [])}
        extra = sorted(set(reads) - listed)
        if extra:
            problems.append(
                f"{rel}: reads market-data field(s) {extra} that its allowlist entry does not name"
            )
    for rel in sorted(allow):
        if not (REPO / rel).is_file():
            problems.append(f"broker_field_access allowlist names a missing file: {rel} (stale)")
        elif rel not in reads_by_file:
            problems.append(
                f"broker_field_access allowlist entry {rel} no longer reads any enforced field "
                "(stale)"
            )
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("PU-1 REGISTRY CLOSURE VIOLATION(S):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("PU-1 registry closure OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
