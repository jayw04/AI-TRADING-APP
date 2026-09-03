"""Load the frozen MR-002 classification spine, and prove where it came from.

``app`` is a regular package on the research host, so putting the frozen source on
``PYTHONPATH`` is not enough — ``app.altdata.mr002`` resolves to whatever the host checkout
contains, not to the frozen tree. The modules therefore have to be loaded explicitly by
file location and grafted onto their parent packages.

The reason this is its own module, rather than three lines inside the driver, is trap #2 of
2026-08-24: an editable install hard-mapped ``app`` to the full checkout and overrode a
``sys.path.insert``, so an isolation proof executed all 84 files of the working tree while
appearing to pass. Every import succeeded. Only an assertion on ``module.__file__`` caught
it.

So: **a successful import is not evidence of provenance.** ``load_spine`` refuses to return
modules whose ``__file__`` does not sit under the frozen root, and it re-checks after the
graft rather than before, because the graft is what a stale ``sys.modules`` entry would
subvert.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

#: Packages loaded from the frozen tree, as ``(parent package, submodule)``.
FROZEN_PACKAGES: tuple[tuple[str, str], ...] = (
    ("app.altdata", "mr002"),
    ("app.research", "mr002"),
)


class SpineProvenanceError(RuntimeError):
    """A spine module did not come from the frozen tree."""


@dataclass(frozen=True)
class Spine:
    """The frozen modules the crawl uses, with their proven origins."""

    sic_history: ModuleType
    crosswalk: ModuleType
    frozen_root: Path

    @property
    def origins(self) -> dict[str, str]:
        return {
            "sic_history": str(self.sic_history.__file__),
            "crosswalk": str(self.crosswalk.__file__),
        }


def _graft(parent_name: str, sub: str, frozen_root: Path) -> ModuleType:
    pkg_dir = frozen_root / parent_name.replace(".", "/") / sub
    init = pkg_dir / "__init__.py"
    if not init.exists():
        raise SpineProvenanceError(f"frozen package missing: {init}")

    full = f"{parent_name}.{sub}"
    parent = importlib.import_module(parent_name)
    spec = importlib.util.spec_from_file_location(
        full, str(init), submodule_search_locations=[str(pkg_dir)]
    )
    if spec is None or spec.loader is None:
        raise SpineProvenanceError(f"could not build a spec for {full} at {init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    setattr(parent, sub, module)
    return module


def _assert_origin(module: ModuleType, frozen_root: Path) -> None:
    origin = getattr(module, "__file__", None)
    if not origin:
        raise SpineProvenanceError(f"{module.__name__} has no __file__ to verify")
    if not Path(origin).resolve().is_relative_to(frozen_root.resolve()):
        raise SpineProvenanceError(
            f"{module.__name__} loaded from {origin}, which is outside the frozen root "
            f"{frozen_root}. A successful import is not proof of provenance — this is the "
            f"editable-install shadowing failure, not a path typo."
        )


def load_spine(frozen_root: Path) -> Spine:
    """Load and verify the frozen spine. Raises rather than returning a suspect module."""
    frozen_root = Path(frozen_root)
    if not frozen_root.is_dir():
        raise SpineProvenanceError(f"frozen root does not exist: {frozen_root}")

    for parent, sub in FROZEN_PACKAGES:
        _graft(parent, sub, frozen_root)

    sic_history = importlib.import_module("app.altdata.mr002.sic_history")
    crosswalk = importlib.import_module("app.altdata.mr002.crosswalk")

    # Verified after the graft, not before: a stale sys.modules entry is exactly what
    # would make a pre-graft check pass and the actual import wrong.
    for module in (sic_history, crosswalk):
        _assert_origin(module, frozen_root)

    return Spine(sic_history=sic_history, crosswalk=crosswalk, frozen_root=frozen_root)
