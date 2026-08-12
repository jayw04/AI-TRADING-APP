"""The dependency mount may not perturb the stack P10 qualified.

These run against synthetic mounts, because the real bundle (pyarrow + the AWS client stack) is a
Linux/cp313 artifact that only materialises inside the bound image. What is qualified here is the
GUARD: that it refuses shadowing, refuses unbound packages, refuses a writable mount, and refuses
if numpy/scipy/pandas move.

Note the development venv already provides boto3 and pyarrow -- so the guard refuses them here, by
design. That is itself the reason the real bundle can only be qualified inside the image, where
they are genuinely absent. To exercise the guard's logic we use names no environment supplies.
"""

from __future__ import annotations

import sys

import pytest

from app.research.mr002.phase3b import deps as D

FAKE = ("mr002_fake_arrow", "mr002_fake_boto")


@pytest.fixture
def fake_bundle(monkeypatch):
    monkeypatch.setattr(D, "PERMITTED_TOP_LEVEL", frozenset(FAKE))
    monkeypatch.setattr(D, "REQUIRED_IMPORTS", FAKE)
    saved = list(sys.path)
    yield
    sys.path[:] = saved
    for name in FAKE:
        sys.modules.pop(name, None)


def _mount(tmp_path, packages, *, body="VALUE = 1\n"):
    root = tmp_path / "deps"
    root.mkdir(exist_ok=True)
    for name in packages:
        pkg = root / name
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").write_text(body)
    return str(root)


def test_refuses_a_package_that_would_shadow_the_runtime(tmp_path):
    """A shadow is how a numeric package moves without anyone naming it."""
    with pytest.raises(D.DependencyRefused, match="unbound packages"):
        D.activate(_mount(tmp_path, ["json"]), require_read_only=False)


def test_refuses_a_permitted_name_that_is_already_importable(tmp_path, monkeypatch):
    """Even a PERMITTED name must not already resolve; that would be a silent override."""
    monkeypatch.setattr(D, "PERMITTED_TOP_LEVEL", frozenset({"json"}))
    with pytest.raises(D.DependencyRefused, match="would shadow"):
        D.activate(_mount(tmp_path, ["json"]), require_read_only=False)


def test_the_real_bundle_names_are_refused_when_the_runtime_already_has_them(tmp_path):
    """Concretely: boto3/pyarrow exist in the dev venv, so activation there must refuse."""
    with pytest.raises(D.DependencyRefused, match="would shadow"):
        D.activate(_mount(tmp_path, ["pyarrow", "boto3"]), require_read_only=False)


def test_refuses_an_unbound_package_on_the_mount(tmp_path):
    with pytest.raises(D.DependencyRefused, match="unbound packages"):
        D.activate(_mount(tmp_path, ["totally_unexpected_pkg"]), require_read_only=False)


def test_refuses_an_empty_mount(tmp_path):
    (tmp_path / "deps").mkdir()
    with pytest.raises(D.DependencyRefused, match="empty"):
        D.activate(str(tmp_path / "deps"), require_read_only=False)


def test_refuses_an_absent_mount(tmp_path):
    with pytest.raises(D.DependencyRefused, match="absent"):
        D.activate(str(tmp_path / "nope"), require_read_only=False)


def test_refuses_a_writable_mount(tmp_path, fake_bundle):
    """A writable dependency mount is a mutable runtime, which defeats the hash binding."""
    with pytest.raises(D.DependencyRefused, match="writable"):
        D.activate(_mount(tmp_path, list(FAKE)), require_read_only=True)


def test_refuses_when_the_bundle_does_not_satisfy_the_required_imports(tmp_path, fake_bundle):
    """Present-but-broken must fail as loudly as absent."""
    path = _mount(tmp_path, list(FAKE))
    (tmp_path / "deps" / FAKE[0] / "__init__.py").write_text("raise RuntimeError('broken')\n")
    with pytest.raises(D.DependencyRefused, match="does not satisfy"):
        D.activate(path, require_read_only=False)


def test_refuses_if_the_p10_numeric_stack_moves(tmp_path, monkeypatch, fake_bundle):
    """The single claim the whole bundle architecture rests on."""
    calls = iter(
        [
            {"numpy": ("/img/numpy.py", "2.2.6"), "scipy": (None, None), "pandas": (None, None)},
            {"numpy": ("/bundle/numpy.py", "2.9.9"), "scipy": (None, None), "pandas": (None, None)},
        ]
    )
    monkeypatch.setattr(D, "_snapshot", lambda: next(calls))
    with pytest.raises(D.DependencyRefused, match="P10 numeric stack MOVED"):
        D.activate(_mount(tmp_path, list(FAKE)), require_read_only=False)


def test_activation_succeeds_and_reports_the_stack_unchanged(tmp_path, fake_bundle):
    detail = D.activate(_mount(tmp_path, list(FAKE)), require_read_only=False)
    assert detail["p10_stack_unchanged"] is True
    assert sorted(detail["top_level"]) == sorted(FAKE)
    # Non-vacuity: the snapshot observed the real numpy, not an empty record.
    assert detail["p10_critical_before"]["numpy"][0] is not None
    assert detail["p10_critical_before"] == detail["p10_critical_after"]


def test_the_bundle_is_appended_never_prepended(tmp_path, fake_bundle):
    """Precedence stays with the image, so no ordering accident can shadow it."""
    path = D.activate(_mount(tmp_path, list(FAKE)), require_read_only=False)["bundle_path"]
    assert sys.path[-1] == path


def test_p10_critical_set_is_the_numeric_stack():
    assert set(D.P10_CRITICAL) == {"numpy", "scipy", "pandas"}


def test_permitted_set_contains_no_numeric_or_image_package():
    assert not (D.PERMITTED_TOP_LEVEL & {"numpy", "scipy", "pandas", "six", "dateutil", "pytest"})
