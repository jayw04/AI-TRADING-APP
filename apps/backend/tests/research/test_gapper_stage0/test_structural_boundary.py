"""Structural boundary: research-plane isolation of the Stage-0 prep harness.

AST-scans every module in ``app/research/gapper_stage0/`` (plus the census CLI
script) and asserts:

* no order-path / broker / risk imports (``app.orders``, ``app.risk``,
  ``app.brokers``), no Alpaca SDK, no LLM SDK, no AWS SDK;
* no HTTP client or raw-socket usage (``httpx``/``requests``/``aiohttp``/
  ``urllib``/``websockets``/``socket``) — the harness takes all data by
  injection;
* no runtime singletons (``get_settings`` / ``get_engine``).

Also asserts the imported package resolves inside THIS checkout — the worktree
editable-install gotcha: the venv can silently map ``app`` to a different
checkout, making every other test in this directory test the wrong code.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app.research.gapper_stage0 as gapper_stage0

PACKAGE_DIR = Path(gapper_stage0.__file__).resolve().parent
BACKEND_DIR = Path(__file__).resolve().parents[3]  # .../apps/backend
CLI_SCRIPT = BACKEND_DIR / "scripts" / "gapper_stage0_census.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "app.orders",
    "app.risk",
    "app.brokers",
    "alpaca",
    "alpaca_py",
    "anthropic",
    "boto3",
    "botocore",
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "socket",
    "http.client",
)
FORBIDDEN_CALL_NAMES = ("get_settings", "get_engine")


def _scanned_files() -> list[Path]:
    files = sorted(PACKAGE_DIR.glob("*.py"))
    assert files, f"no modules found under {PACKAGE_DIR}"
    assert CLI_SCRIPT.is_file(), f"CLI script missing: {CLI_SCRIPT}"
    return [*files, CLI_SCRIPT]


def _imports_of(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_package_resolves_inside_this_checkout() -> None:
    # The venv's editable install can map `app` to ANOTHER checkout (worktree
    # gotcha). The package under test must live in the same tree as this test.
    assert str(PACKAGE_DIR).startswith(str(BACKEND_DIR)), (
        f"app.research.gapper_stage0 resolved to {PACKAGE_DIR}, outside this "
        f"checkout {BACKEND_DIR} — set PYTHONPATH to this apps/backend first"
    )


def test_no_order_path_broker_llm_or_http_imports() -> None:
    for path in _scanned_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imports_of(tree):
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                assert not (name == prefix or name.startswith(prefix + ".")), (
                    f"{path.name} imports forbidden module {name!r} "
                    f"(matches {prefix!r}) — research-plane isolation violated"
                )


def test_no_settings_or_engine_singletons() -> None:
    for path in _scanned_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            called = None
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called = node.func.attr
            if called in FORBIDDEN_CALL_NAMES:
                raise AssertionError(
                    f"{path.name} calls {called}() — the harness must take all "
                    "inputs by injection, never runtime singletons"
                )


def test_package_does_not_import_bar_cache() -> None:
    # BarCache binds the Alpaca adapter; the harness reads injected frames /
    # local parquet only. (The CLI reads day files directly for the same reason.)
    for path in _scanned_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imports_of(tree):
            assert "bar_cache" not in name, f"{path.name} imports {name!r}"
