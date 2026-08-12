"""Activate the separately bound execution-dependency mount without perturbing the P10 stack.

The bound evaluator image has no parquet decoder and no S3 client, and rebuilding it to add them
would churn the evaluator identity for infrastructure outside evaluator economics. So they arrive on
their own read-only, hash-bound mount. The whole safety argument for doing that rests on one claim:

    adding this mount does not move the numeric stack P10 qualified.

This module refuses to take that on trust. It photographs numpy, scipy and pandas -- resolved file
AND version -- before the mount is added and again afterwards, and refuses if anything moved. It
also refuses before adding the path at all if the bundle shares a single top-level name with
something the image already provides, because a shadow is exactly how a numeric package moves
without anyone naming it.

A dependency that requires replacing numpy, scipy, pandas, BLAS or the interpreter is out of scope
by construction: at that point the correct route is a new image and a fresh P10/P12 chain, not a
bundle.
"""

from __future__ import annotations

import importlib
import importlib.util  # explicit: `importlib` alone does NOT bind .util in a clean interpreter
import os
import sys

# The packages P10 qualified numerically. If any of these move, the qualification is void.
P10_CRITICAL = ("numpy", "scipy", "pandas")

# Everything the bundle is permitted to contain. Anything else is unbound code on the path.
PERMITTED_TOP_LEVEL = frozenset(
    {"boto3", "botocore", "jmespath", "pyarrow", "s3transfer", "urllib3"}
)

# What the Phase 3B package actually needs from the bundle.
REQUIRED_IMPORTS = ("pyarrow", "boto3")


class DependencyRefused(Exception):
    """The dependency mount cannot be activated safely. The run must not proceed."""


def _snapshot() -> dict[str, tuple[str | None, str | None]]:
    """Resolved file and version of each P10-critical package, as currently importable."""
    out: dict[str, tuple[str | None, str | None]] = {}
    for name in P10_CRITICAL:
        try:
            mod = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - absence is itself a fact worth recording
            out[name] = (None, None)
            continue
        out[name] = (getattr(mod, "__file__", None), getattr(mod, "__version__", None))
    return out


def _top_level_names(bundle_path: str) -> set[str]:
    names = set()
    for entry in os.listdir(bundle_path):
        if entry in ("bin", "__pycache__") or entry.endswith(".dist-info"):
            continue
        names.add(entry[:-3] if entry.endswith(".py") else entry)
    return names


def _is_read_only(path: str) -> bool:
    """Probe by attempting a write, then removing it. A writable mount is a mutable runtime."""
    probe = os.path.join(path, ".write-probe")
    try:
        with open(probe, "w") as fh:
            fh.write("x")
    except OSError:
        return True
    os.remove(probe)
    return False


def activate(bundle_path: str, *, require_read_only: bool = True) -> dict[str, object]:
    """Add the bundle to sys.path, proving the P10 stack is untouched on both sides of the move."""
    bundle_path = os.path.abspath(bundle_path)
    if not os.path.isdir(bundle_path):
        raise DependencyRefused(f"dependency mount absent: {bundle_path}")

    if require_read_only and not _is_read_only(bundle_path):
        raise DependencyRefused(
            f"{bundle_path} is writable; a mutable dependency mount defeats the hash binding"
        )

    names = _top_level_names(bundle_path)
    if not names:
        raise DependencyRefused("dependency mount is empty")
    unexpected = sorted(names - PERMITTED_TOP_LEVEL)
    if unexpected:
        raise DependencyRefused(f"unbound packages on the dependency mount: {unexpected}")

    # A shadow is how a numeric package moves without anyone naming it. Refuse BEFORE pathing.
    already = {n for n in names if importlib.util.find_spec(n) is not None}
    if already:
        raise DependencyRefused(
            f"the bundle would shadow packages the runtime already provides: {sorted(already)}"
        )

    before = _snapshot()
    if bundle_path not in sys.path:
        sys.path.append(bundle_path)  # append: the image's own packages keep precedence
    try:
        for name in REQUIRED_IMPORTS:
            importlib.import_module(name)
    except Exception as exc:
        raise DependencyRefused(f"the bundle does not satisfy {REQUIRED_IMPORTS}: {exc}") from exc
    after = _snapshot()

    moved = sorted(n for n in P10_CRITICAL if before[n] != after[n])
    if moved:
        raise DependencyRefused(
            f"the P10 numeric stack MOVED when the bundle was added: {moved}. A bundle that "
            "changes numpy/scipy/pandas is not a supplement - a new image and a fresh P10/P12 "
            "chain is the correct route."
        )

    return {
        "bundle_path": bundle_path,
        "read_only": require_read_only,
        "top_level": sorted(names),
        "p10_critical_before": {k: list(v) for k, v in before.items()},
        "p10_critical_after": {k: list(v) for k, v in after.items()},
        "p10_stack_unchanged": True,
        "sys_path_position": "appended after the image site-packages",
        "imports_satisfied": list(REQUIRED_IMPORTS),
    }
