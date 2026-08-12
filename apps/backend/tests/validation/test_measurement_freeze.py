"""The measurement-instrument freeze — expected identity held OUTSIDE the tree it pins.

Two defects are pinned here, both structural:

  * the in-tree constant was an unsolvable FIXED POINT — a constant cannot name the commit that
    contains it, so the binding was guaranteed to drift and did (28 authorized commits);
  * `build_forward_context` DEFAULTED the actual commit to the expected constant, so the clause
    compared a constant to itself and could not fail.

The replacement is only meaningful if the expected and actual values can genuinely disagree, so most
of these tests are refusals.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import date
from pathlib import Path

import pytest

from app.validation import forward_window as fw
from app.validation.measurement_freeze import (
    MEASURED_PATHS,
    SUPPORTED_SCHEMA_VERSIONS,
    MeasurementFreezeError,
    load_measurement_freeze,
    validation_tree_digest,
    verify_deployment,
)
from app.validation.production_bindings import build_forward_context

RATIFIED = "d13310a32227c67163250566eca719d5f734dd53"
SUPERSEDED = "764883b58cb96936f23e49182dd02b70d969501b"
DESCENDANT = "f" * 40


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())
    return root


@pytest.fixture
def runtime(tmp_path):
    return _tree(tmp_path / "rt", {"app/validation/a.py": "A\n", "app/validation/sub/b.py": "B\n"})


def _manifest(tmp_path, **over) -> Path:
    d = {
        "manifest_schema_version": "1.0",
        "measurement_commit": RATIFIED,
        "validation_tree_sha256": "0" * 64,
        "supersedes_measurement_commit": SUPERSEDED,
        "ratified_increment_inventory_sha256": "1" * 64,
        "amendment_sha256": "2" * 64,
        "measured_paths": list(MEASURED_PATHS),
        "validation_tree_identity_algorithm": "PATH_SORTED_SHA256_CRLF_TO_LF_V1",
        "byte_manifest_sha256": "3" * 64,
    }
    d.update(over)
    p = tmp_path / "measurement_freeze.json"
    p.write_bytes(json.dumps(d, sort_keys=True, indent=2).encode())
    return p


# ---- the digest itself --------------------------------------------------------------------------

def test_the_digest_covers_content_and_path_not_mtime_or_order(runtime, tmp_path):
    first = validation_tree_digest(runtime)
    (runtime / "app/validation/a.py").touch()
    assert validation_tree_digest(runtime) == first, "mtime must not change the identity"

    moved = _tree(tmp_path / "rt2", {"app/validation/sub/b.py": "B\n", "app/validation/a.py": "A\n"})
    assert validation_tree_digest(moved) == first, "walk order must not change the identity"


def test_any_content_change_moves_the_digest(runtime):
    before = validation_tree_digest(runtime)
    (runtime / "app/validation/a.py").write_bytes(b"A CHANGED\n")
    assert validation_tree_digest(runtime) != before


def test_a_new_measurement_module_moves_the_digest(runtime):
    before = validation_tree_digest(runtime)
    (runtime / "app/validation/c.py").write_bytes(b"C\n")
    assert validation_tree_digest(runtime) != before, "adding a module is a governed change"


def test_line_endings_do_not_change_the_IDENTITY(runtime):
    """Git stores LF; a Windows checkout with core.autocrlf=true materializes CRLF. The same source
    must not have two identities, or no single manifest could describe both."""
    before = validation_tree_digest(runtime)
    (runtime / "app/validation/a.py").write_bytes(b"A\r\n")
    assert validation_tree_digest(runtime) == before


def test_a_CRLF_converted_build_passes_IDENTITY_but_fails_TRANSPORT(tmp_path, runtime):
    """★ The two questions, separated. `git archive` under core.autocrlf=true rewrote 581 of 592
    deployed .py files: the SOURCE was ratified, the BYTES were not. Identity must still hold — the
    code is the ratified code — while the transport check reports the alteration."""
    from app.validation.measurement_freeze import byte_manifest, measured_entries

    fz = _freeze(tmp_path, runtime)
    committed = byte_manifest(measured_entries(runtime))
    assert verify_deployment(fz, actual_commit=RATIFIED, runtime_root=runtime,
                             expected_bytes=committed) == []

    (runtime / "app/validation/a.py").write_bytes(b"A\r\n")
    fails = verify_deployment(fz, actual_commit=RATIFIED, runtime_root=runtime,
                              expected_bytes=committed)
    assert any("bytes differ" in f for f in fails), "the transport check must report it"
    assert not any("not the ratified content" in f for f in fails), (
        "identity is newline-canonical, so the SOURCE claim still holds")


def test_pycache_is_ignored(runtime):
    before = validation_tree_digest(runtime)
    (runtime / "app/validation/__pycache__").mkdir()
    (runtime / "app/validation/__pycache__/x.py").write_bytes(b"junk\n")
    assert validation_tree_digest(runtime) == before


def test_a_runtime_missing_the_measured_path_refuses(tmp_path):
    with pytest.raises(MeasurementFreezeError, match="is absent under"):
        validation_tree_digest(tmp_path / "empty")


# ---- the manifest -------------------------------------------------------------------------------

def test_a_superseded_schema_version_refuses(tmp_path):
    """★ REQUIRED CASE: superseded manifest versions refuse."""
    p = _manifest(tmp_path, manifest_schema_version="0.9")
    with pytest.raises(MeasurementFreezeError, match="not supported"):
        load_measurement_freeze(p)
    assert "0.9" not in SUPPORTED_SCHEMA_VERSIONS


@pytest.mark.parametrize("field", ["measurement_commit", "validation_tree_sha256",
                                   "supersedes_measurement_commit",
                                   "ratified_increment_inventory_sha256", "amendment_sha256"])
def test_a_manifest_missing_any_required_binding_refuses(tmp_path, field):
    with pytest.raises(MeasurementFreezeError, match=f"carries no.*{field}"):
        load_measurement_freeze(_manifest(tmp_path, **{field: ""}))


def test_a_manifest_measuring_a_different_path_set_refuses(tmp_path):
    with pytest.raises(MeasurementFreezeError, match="do not describe the same executable content"):
        load_measurement_freeze(_manifest(tmp_path, measured_paths=["app"]))


def test_an_absent_or_unreadable_manifest_refuses(tmp_path):
    with pytest.raises(MeasurementFreezeError, match="is absent"):
        load_measurement_freeze(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    with pytest.raises(MeasurementFreezeError, match="not readable JSON"):
        load_measurement_freeze(bad)


def test_the_manifest_records_its_own_digest(tmp_path):
    p = _manifest(tmp_path)
    assert load_measurement_freeze(p).manifest_sha256 == hashlib.sha256(p.read_bytes()).hexdigest()


# ---- verify_deployment: the four required outcomes ----------------------------------------------

def _freeze(tmp_path, runtime, **over):
    return load_measurement_freeze(
        _manifest(tmp_path, validation_tree_sha256=validation_tree_digest(runtime), **over))


def test_correct_head_and_tree_digest_passes(tmp_path, runtime):
    """★ REQUIRED CASE: correct HEAD and tree digest passes."""
    fz = _freeze(tmp_path, runtime)
    assert verify_deployment(fz, actual_commit=RATIFIED, runtime_root=runtime) == []


def test_correct_head_with_wrong_tree_digest_refuses(tmp_path, runtime):
    """★ REQUIRED CASE: the CONTROLLING identity is executable content, not the commit."""
    fz = _freeze(tmp_path, runtime)
    (runtime / "app/validation/a.py").write_bytes(b"TAMPERED\n")
    fails = verify_deployment(fz, actual_commit=RATIFIED, runtime_root=runtime)
    assert any("not the ratified content" in f for f in fails)


def test_wrong_actual_head_refuses_when_ancestry_cannot_be_shown(tmp_path, runtime):
    """★ REQUIRED CASE: wrong actual HEAD refuses. With no git and no attestation it FAILS CLOSED
    rather than assuming the deployment descends from ratified history."""
    fz = _freeze(tmp_path, runtime)
    fails = verify_deployment(fz, actual_commit=DESCENDANT, runtime_root=runtime)
    assert any("could not be verified" in f for f in fails)


def test_a_missing_actual_commit_refuses(tmp_path, runtime):
    """★ REQUIRED CASE: omitted commit identity is a fail-closed error, never an assumption."""
    fz = _freeze(tmp_path, runtime)
    for missing in ("", "   "):
        fails = verify_deployment(fz, actual_commit=missing, runtime_root=runtime)
        assert any("measurement identity of the running code is unknown" in f for f in fails)


def test_a_deploy_time_ancestry_attestation_admits_a_descendant(tmp_path, runtime):
    fz = _freeze(tmp_path, runtime)
    marker = tmp_path / "ancestry.json"
    marker.write_bytes(json.dumps({"measurement_commit": RATIFIED, "deployed_head": DESCENDANT,
                                   "is_ancestor": True}).encode())
    assert verify_deployment(fz, actual_commit=DESCENDANT, runtime_root=runtime,
                             ancestry_marker=marker) == []


@pytest.mark.parametrize("bad", [
    {"measurement_commit": "x" * 40, "deployed_head": DESCENDANT, "is_ancestor": True},
    {"measurement_commit": RATIFIED, "deployed_head": "y" * 40, "is_ancestor": True},
    {"measurement_commit": RATIFIED, "deployed_head": DESCENDANT, "is_ancestor": False},
    {"measurement_commit": RATIFIED, "deployed_head": DESCENDANT},
])
def test_an_ancestry_attestation_that_does_not_name_both_commits_refuses(tmp_path, runtime, bad):
    fz = _freeze(tmp_path, runtime)
    marker = tmp_path / "ancestry.json"
    marker.write_bytes(json.dumps(bad).encode())
    fails = verify_deployment(fz, actual_commit=DESCENDANT, runtime_root=runtime,
                              ancestry_marker=marker)
    assert fails, "a marker that does not name both commits is not an attestation"


# ---- the vacuous default is gone ----------------------------------------------------------------

def test_code_commit_has_no_default_and_cannot_be_omitted():
    """★ REQUIRED CASE: omitted code_commit cannot reach preflight."""
    sig = inspect.signature(build_forward_context)
    assert sig.parameters["code_commit"].default is inspect.Parameter.empty
    with pytest.raises(TypeError, match="code_commit"):
        build_forward_context(date(2026, 7, 27), dgs3mo_path=Path("x"),  # type: ignore[call-arg]
                              trial_ledger_path=Path("y"), ledger_account_id=99,
                              measurement_freeze=None, runtime_root=Path("."))


def test_no_wrapper_defaults_the_actual_commit_to_the_expected_value():
    """★ REQUIRED CASE: passing the manifest's EXPECTED commit as the ACTUAL one must not happen
    through any wrapper. Checked at the source: no caller may bind the expected constant to
    `code_commit`."""
    from app.validation import session_composition

    for mod in (session_composition, __import__("app.validation.production_bindings",
                                                fromlist=["x"])):
        src = inspect.getsource(mod)
        assert "code_commit=VALIDATION_MEASUREMENT_COMMIT" not in src
        assert "code_commit: str = VALIDATION_MEASUREMENT_COMMIT" not in src


def test_the_superseded_constant_is_marked_and_unused_as_a_binding():
    """The original freeze is PRESERVED AS HISTORY. It must never be re-read as a live check."""
    assert fw.SUPERSEDED_VALIDATION_MEASUREMENT_COMMIT == SUPERSEDED
    src = inspect.getsource(fw.preflight)
    assert "VALIDATION_MEASUREMENT_COMMIT" not in src, (
        "preflight must bind the governed manifest, never the superseded in-tree constant")


# ---- preflight refuses without a freeze ---------------------------------------------------------

def test_preflight_refuses_when_no_freeze_is_supplied(tmp_path):
    ctx = fw.ForwardRunContext(
        session_date=date(2026, 7, 27), is_nyse_trading_session=True, code_commit=RATIFIED,
        benchmark_commits=dict(fw.BENCHMARK_COMMITS), dgs3mo_path=tmp_path / "d",
        dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF, trial_ledger_path=tmp_path / "t",
        effective_dsr_trial_count=fw.EFFECTIVE_DSR_TRIAL_COUNT, config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=99, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False)
    with pytest.raises(fw.IntegrityStop, match="no measurement-freeze manifest"):
        fw.preflight(ctx)


def test_preflight_refuses_an_empty_actual_commit(tmp_path, runtime):
    ctx = fw.ForwardRunContext(
        session_date=date(2026, 7, 27), is_nyse_trading_session=True, code_commit="",
        benchmark_commits=dict(fw.BENCHMARK_COMMITS), dgs3mo_path=tmp_path / "d",
        dgs3mo_cutoff=fw.DGS3MO_OBSERVATION_CUTOFF, trial_ledger_path=tmp_path / "t",
        effective_dsr_trial_count=fw.EFFECTIVE_DSR_TRIAL_COUNT, config=dict(fw.FROZEN_CONFIG),
        ledger_account_id=99, ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False, references_retired_baseline=False,
        measurement_freeze=_freeze(tmp_path, runtime), runtime_root=runtime)
    with pytest.raises(fw.IntegrityStop, match="measurement identity is unknown"):
        fw.preflight(ctx)


# ---- the named canonicalization contract --------------------------------------------------------
#
# PATH_SORTED_SHA256_CRLF_TO_LF_V1. Every rule is pinned, because "normalize line endings" is exactly
# the kind of phrase that quietly grows to mean "and trim whitespace, and strip the BOM".

from app.validation.measurement_freeze import (  # noqa: E402
    TREE_IDENTITY_ALGORITHM,
    byte_manifest,
    canonicalize,
    measured_entries,
    tree_identity,
    verify_deployment_bytes,
)


def test_the_algorithm_is_named_and_versioned():
    assert TREE_IDENTITY_ALGORITHM == "PATH_SORTED_SHA256_CRLF_TO_LF_V1"


def test_only_CRLF_is_normalized(runtime):
    assert canonicalize(b"a\r\nb\n", "x.py") == b"a\nb\n"


def test_a_lone_CR_is_REFUSED_not_normalized():
    """★ Normalizing a lone CR would give two different sources the same identity."""
    with pytest.raises(MeasurementFreezeError, match="lone CR"):
        canonicalize(b"a\rb\n", "x.py")


def test_undecodable_text_is_REFUSED_not_replaced():
    """★ `errors='replace'` would map many distinct byte sequences onto one identity."""
    with pytest.raises(MeasurementFreezeError, match="not decodable UTF-8"):
        canonicalize(b"\xff\xfe not utf-8\n", "x.py")


def test_whitespace_is_NOT_trimmed():
    assert canonicalize(b"a   \n", "x.py") != canonicalize(b"a\n", "x.py")
    assert canonicalize(b"\n\na\n", "x.py") != canonicalize(b"a\n", "x.py")


def test_unicode_is_NOT_normalized():
    """NFC and NFD forms of the same glyph are different content."""
    nfc, nfd = "é\n".encode(), "é\n".encode()
    assert canonicalize(nfc, "x.py") != canonicalize(nfd, "x.py")


def test_a_BOM_is_content_and_is_NOT_stripped():
    assert canonicalize(b"\xef\xbb\xbfa\n", "x.py") != canonicalize(b"a\n", "x.py")


def test_final_newline_presence_is_preserved():
    assert canonicalize(b"a\n", "x.py") != canonicalize(b"a", "x.py")


def test_the_path_is_bound_so_a_rename_moves_the_identity():
    assert tree_identity([("a.py", b"X\n")]) != tree_identity([("b.py", b"X\n")])


def test_membership_is_bound_so_adding_or_removing_a_file_moves_the_identity():
    one = tree_identity([("a.py", b"X\n")])
    assert tree_identity([("a.py", b"X\n"), ("b.py", b"Y\n")]) != one
    assert tree_identity([]) if False else True
    with pytest.raises(MeasurementFreezeError, match="no measured content"):
        tree_identity([])


def test_ordering_of_the_input_does_not_affect_the_identity():
    a = tree_identity([("a.py", b"X\n"), ("b.py", b"Y\n")])
    b = tree_identity([("b.py", b"Y\n"), ("a.py", b"X\n")])
    assert a == b


# ---- transport integrity is a BYTE comparison, not a CR scan ------------------------------------

def test_byte_integrity_compares_against_the_authoritative_bytes(runtime):
    """★ REQUIRED: catches ANY deployment transformation, not only CRLF."""
    expected = byte_manifest(measured_entries(runtime))
    assert verify_deployment_bytes(runtime, expected) == []

    (runtime / "app/validation/a.py").write_bytes(b"A\r\n")          # CRLF conversion
    assert any("bytes differ" in f for f in verify_deployment_bytes(runtime, expected))


@pytest.mark.parametrize("altered", [
    b"\xef\xbb\xbfA\n",          # BOM inserted by a re-encoding build
    b"A",                        # final newline stripped
    b"A \n",                     # trailing whitespace introduced
])
def test_byte_integrity_catches_transformations_a_CR_scan_would_miss(runtime, altered):
    expected = byte_manifest(measured_entries(runtime))
    (runtime / "app/validation/a.py").write_bytes(altered)
    assert any("bytes differ" in f for f in verify_deployment_bytes(runtime, expected))


def test_byte_integrity_catches_added_and_removed_files(runtime):
    expected = byte_manifest(measured_entries(runtime))
    (runtime / "app/validation/extra.py").write_bytes(b"E\n")
    assert any("not in the byte manifest" in f for f in verify_deployment_bytes(runtime, expected))
    (runtime / "app/validation/extra.py").unlink()
    (runtime / "app/validation/a.py").unlink()
    assert any("absent from the deployment" in f
               for f in verify_deployment_bytes(runtime, expected))


def test_a_manifest_naming_a_different_algorithm_refuses(tmp_path):
    with pytest.raises(MeasurementFreezeError, match="identity algorithm"):
        load_measurement_freeze(_manifest(tmp_path,
                                          validation_tree_identity_algorithm="SOMETHING_ELSE_V2"))


def test_the_committed_manifest_was_produced_by_THIS_implementation():
    """★ REQUIRED: the committed digest must come from the versioned implementation under test, not
    from a separate one-off command. Re-derived here from the working tree."""
    root = Path(__file__).resolve().parents[2]           # apps/backend
    manifest = load_measurement_freeze(
        root.parents[1] / "manifests/forward/measurement_freeze.json")
    assert manifest.validation_tree_identity_algorithm == TREE_IDENTITY_ALGORITHM
    assert manifest.validation_tree_sha256 == validation_tree_digest(root), (
        "the committed manifest does not describe the committed measurement content")


# ---- every call site supplies the required identity, on EVERY platform ---------------------------
#
# ★ This test exists because CI caught what this machine could not. The `scripts/` CLI called
# `build_forward_context` without the new required arguments; the tests that would have caught it are
# POSIX-gated (a PRODUCTION witness needs POSIX ownership guarantees), so on Windows all 16 are
# SKIPPED and the local suite was green while CI was red.
#
# An AST check over the call sites runs everywhere. It converts a platform-gated runtime failure into
# a portable static one, which is the only kind this developer machine can catch.

def test_every_call_site_supplies_the_required_identity_arguments():
    import ast

    required = {"code_commit", "measurement_freeze", "runtime_root"}
    backend = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for src in [*(backend / "app").rglob("*.py"), *(backend / "scripts").rglob("*.py")]:
        try:
            tree = ast.parse(src.read_text(encoding="utf-8"))
        except SyntaxError:                                  # pragma: no cover - not our file
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "build_forward_context":
                continue
            supplied = {k.arg for k in node.keywords if k.arg} | (
                required if any(k.arg is None for k in node.keywords) else set())
            missing = required - supplied
            if missing:
                offenders.append(f"{src.relative_to(backend)}:{node.lineno} missing {sorted(missing)}")
    assert not offenders, (
        "a caller omits the deployment identity — it would fail only where the POSIX-gated tests "
        f"run: {offenders}")
