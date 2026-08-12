"""The executing closure is derived, complete, and proven by SET EQUALITY -- never by count.

The defect these tests exist to prevent: v2 bound 35 files and 35 files were imported, but they
were not the same 35. `spq1/__init__.py` supplies PHASE0_CENSUS_SHA256, PHASE0_OWNER_RULINGS_SHA256,
PHASE0_SCHEMA_SHA256 and PRODUCER_CODE_VERSION, all of which reach GOVERNING_IDENTITIES and so every
emitted record -- and it was bound by neither the supplement nor the runtime roster. A count check
would have passed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from app.research.mr002.phase3b import closure as C
from app.research.mr002.phase3b import roster as R

LAYER = os.path.dirname(os.path.abspath(C.__file__))
ROOT = C.package_root(LAYER)

# Files whose absence from the binding was the actual defect.
IDENTITY_CARRYING = "app/research/mr002/spq1/__init__.py"
PACKAGE_INITIALIZERS = (
    "app/__init__.py",
    "app/research/__init__.py",
    "app/research/mr002/__init__.py",
    "app/research/mr002/spq1/__init__.py",
    "app/research/mr002/spq1/phase2b/__init__.py",
    "app/research/mr002/spq1/adapters/__init__.py",
    "app/research/mr002/phase3b/__init__.py",
)


def _rel(paths):
    return {os.path.relpath(p, ROOT).replace(os.sep, "/") for p in paths}


def test_the_identity_carrying_initializer_is_in_the_closure():
    """The file that broke v2. Its constants reach every emitted record."""
    assert IDENTITY_CARRYING in _rel(C.static_closure(LAYER))


def test_every_executed_package_initializer_is_bound_even_when_empty():
    """A zero-byte __init__.py is still executed code; emptiness today is not an invariant."""
    got = _rel(C.static_closure(LAYER))
    assert set(PACKAGE_INITIALIZERS) <= got, sorted(set(PACKAGE_INITIALIZERS) - got)


def test_phase2b_initializer_is_import_reached_not_merely_governing():
    """It is the package initializer for phase2b.cutoff / sic_sector, so Python executes it."""
    assert "app/research/mr002/spq1/phase2b/__init__.py" in _rel(C.static_closure(LAYER))


def test_closure_is_not_vacuous_and_spans_both_packages():
    got = _rel(C.static_closure(LAYER))
    assert len(got) >= 40
    assert sum(1 for p in got if "/phase3b/" in p) >= 16
    assert sum(1 for p in got if "/spq1/" in p) >= 19


CLEAN_PROCESS = """
import json, sys
sys.path.insert(0, {backend!r})
from app.research.mr002.phase3b import closure as C
from app.research.mr002.phase3b import roster as R
import app.research.mr002.phase3b.entrypoint  # the REAL entry point, and nothing else
print(json.dumps({{
    "unpredicted": C.verify_static_covers_runtime(C.static_closure({layer!r}), C.runtime_closure({root!r})),
    "audit": R.audit_runtime_against(R.enumerate_closure()),
}}))
"""


def _clean_process_result():
    """Measure in a FRESH interpreter.

    sys.modules is process-global, so inside a pytest session it already holds every backend module
    some other test imported. Only a clean process reproduces what the container actually does:
    import the entry point and nothing else.
    """
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = CLEAN_PROCESS.format(backend=backend, layer=LAYER, root=ROOT)
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, cwd=backend)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_static_closure_predicts_everything_python_actually_executes():
    """Runtime is ground truth; the static binding must already cover it."""
    assert _clean_process_result()["unpredicted"] == []


def test_lazily_imported_modules_are_still_bound():
    """earnings_blackout is imported INSIDE functions, so an import-time scan would miss it.

    This is exactly why the static walk is the binding and runtime is only its audit.
    """
    assert "app/research/mr002/phase3b/earnings_blackout.py" in _rel(C.static_closure(LAYER))


def test_verify_proves_set_equality_not_count(tmp_path):
    """A binding with the right COUNT but the wrong MEMBERS must refuse. This is the v2 defect."""
    bound = R.enumerate_closure()
    swapped = dict(bound)
    swapped.pop(IDENTITY_CARRYING)
    swapped["app/research/mr002/spq1/NOT_A_REAL_FILE.py"] = "0" * 64
    assert len(swapped) == len(bound)  # same count...
    with pytest.raises(C.ClosureRefused) as exc:
        C.verify(swapped, LAYER)
    assert "bound but absent" in str(exc.value) and "NOT bound" in str(exc.value)


def test_verify_refuses_drift():
    bound = dict(R.enumerate_closure())
    bound[IDENTITY_CARRYING] = "f" * 64
    with pytest.raises(C.ClosureRefused, match="identity drift"):
        C.verify(bound, LAYER)


def test_verify_refuses_an_unbound_file_that_would_execute():
    bound = dict(R.enumerate_closure())
    bound.pop(IDENTITY_CARRYING)
    with pytest.raises(C.ClosureRefused, match="present and executing but NOT bound"):
        C.verify(bound, LAYER)


def test_verify_passes_on_the_real_tree():
    detail = C.verify(R.enumerate_closure(), LAYER)
    assert detail["set_equality_proven"] is True and detail["file_count"] >= 40


def test_runtime_audit_refuses_a_module_it_never_bound():
    with pytest.raises(R.RosterRefused, match="executed but NOT bound"):
        R.audit_runtime_against({"app/research/mr002/phase3b/gap.py": "0" * 64})


def test_runtime_audit_passes_against_the_derived_closure():
    audit = _clean_process_result()["audit"]
    assert audit["unpredicted"] == 0 and audit["drift"] == 0
    # Non-vacuity: a clean process really did execute the package, not zero modules.
    assert audit["runtime_modules_observed"] >= 30, audit


def test_roster_verify_now_covers_the_closure_group():
    assert "closure" in R.current_roster()
    detail = R.verify(R.current_roster())
    assert detail["closure_files"] >= 40


def test_an_unresolvable_intra_package_import_refuses(tmp_path):
    """A missing dependency must refuse, never be silently skipped."""
    stage = tmp_path / "app" / "research" / "mr002" / "phase3b"
    stage.mkdir(parents=True)
    for part in ("app", "app/research", "app/research/mr002"):
        (tmp_path / part / "__init__.py").write_text("")
    (stage / "__init__.py").write_text("")
    (stage / "m.py").write_text("from ..spq1.does_not_exist import Thing\n")
    with pytest.raises(C.ClosureRefused, match="unresolvable intra-package import"):
        C.static_closure(str(stage))


def test_closure_survives_being_mounted_at_a_different_path(tmp_path):
    """Bindings are repository-relative, so the same package verifies from any mount point."""
    dest = tmp_path / "mnt"
    shutil.copytree(os.path.join(ROOT, "app"), dest / "app")
    moved = C.verify(R.enumerate_closure(), str(dest / "app/research/mr002/phase3b"))
    assert moved["file_count"] == len(R.enumerate_closure())


def test_runtime_closure_reports_only_files_under_the_root():
    import app.research.mr002.phase3b.entrypoint  # noqa: F401

    for p in C.runtime_closure(ROOT):
        assert os.path.commonpath([p, ROOT]) == ROOT
    assert sys.modules  # sanity: the audit read a populated module table
