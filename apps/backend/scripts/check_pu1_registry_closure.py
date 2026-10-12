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
            ok = any(_host_matches(host, str(e.get("host", ""))) for e in hosts + non_data_hosts)
            if not ok:
                problems.append(
                    f"UNMAPPED data host {host!r} in {rel}: map it to a licence-registry "
                    "source_id (hosts) or declare it non-data with a reason (non_data_hosts) in "
                    "apps/backend/ci/pu1_source_map.json, and register the source"
                )
        for mod in sorted(seen_imports):
            ok = any(_prefix_matches(mod, str(e.get("prefix", ""))) for e in imports) or any(
                _prefix_matches(mod, str(e.get("prefix", ""))) or mod == e.get("exact")
                for e in non_data_imports
            )
            if not ok:
                problems.append(
                    f"UNMAPPED vendor SDK import {mod!r} in {rel}: add it to imports "
                    "(with a registered source_id) or non_data_imports (with a reason)"
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
