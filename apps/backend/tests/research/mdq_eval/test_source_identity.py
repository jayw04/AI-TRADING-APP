"""B2 — the runtime source identity, and every state it must refuse.

These are adversarial by design. Each test puts the runtime into a state that a naive check would
wave through, and asserts a refusal. The one PASS case exists so the refusals are not vacuously
true — a gate that refuses everything proves nothing either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research.mdq_eval import source_identity as si
from app.research.mdq_eval.source_identity import (
    GOVERNED_SOURCE_PATHS,
    ApprovedComputationIdentity,
    MeasuredSourceIdentity,
    SourceIdentityRefused,
    compare_source_identity,
    measure_source_identity,
)

# Byte literals built from ordinals so no escape sequence appears in this file -- the
# governed-source contract is LF-only and this module is itself checked against it.
CR_BYTE = bytes([13])
LF_BYTE = bytes([10])
CRLF_BODY = b"x = 1" + CR_BYTE + LF_BYTE + b"y = 2" + CR_BYTE + LF_BYTE
LF_BODY = b"x = 1" + LF_BYTE + b"y = 2" + LF_BYTE

APPROVED_COMMIT = "a" * 40
GOOD_BLOBS = {rel: f"{i:064d}" for i, rel in enumerate(GOVERNED_SOURCE_PATHS)}
AUTHORITY = ApprovedComputationIdentity(review_commit=APPROVED_COMMIT, blobs=GOOD_BLOBS)


def _measured(**over) -> MeasuredSourceIdentity:
    kw = {
        "commit": APPROVED_COMMIT,
        "dirty_governed_paths": (),
        "blobs": dict(GOOD_BLOBS),
        "problems": (),
    }
    kw.update(over)
    return MeasuredSourceIdentity(**kw)  # type: ignore[arg-type]


@pytest.fixture
def measured(monkeypatch):
    def _install(m: MeasuredSourceIdentity):
        monkeypatch.setattr(si, "measure_source_identity", lambda *a, **k: m)

    return _install


class TestAuthorityIsExternalToTheSourceItApproves:
    """★ The anti-circularity property. This is the defect the previous design had."""

    def test_the_authority_record_is_not_in_the_governed_surface(self):
        """If it were, writing the approval would change the very blob it approves.

        The previous design put the approved identity in a module constant inside
        ``source_identity.py``, which is itself a governed path. Setting it changed that file's
        blob and produced a new commit, so the verifier would refuse the runtime the designation
        was meant to authorize — a fixed point, not something CI can resolve.
        """
        assert si.AUTHORITY_RECORD_PATH.as_posix() not in GOVERNED_SOURCE_PATHS
        assert not any(si.AUTHORITY_RECORD_PATH.as_posix() in p for p in GOVERNED_SOURCE_PATHS)

    def test_no_in_source_approved_identity_constant_survives(self):
        """The constant must be gone, not merely unused — or the cycle can be reintroduced."""
        assert not hasattr(si, "APPROVED_COMPUTATION_IDENTITY")

    def test_setting_the_authority_does_not_change_any_governed_blob(self, tmp_path):
        """Writing an approval must leave the approved surface byte-identical."""

        for rel in GOVERNED_SOURCE_PATHS:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x = 1" + LF_BYTE)
        before = measure_source_identity(backend_root=tmp_path).blobs

        rec = tmp_path / si.AUTHORITY_RECORD_PATH
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(
            json.dumps(
                {
                    "schema": si.AUTHORITY_RECORD_SCHEMA,
                    "approved_review_commit": "c" * 40,
                    "approved_governed_source_blobs": dict(before),
                }
            ),
            encoding="utf-8",
        )
        after = measure_source_identity(backend_root=tmp_path).blobs
        assert before == after, "writing the approval perturbed the approved surface"


class TestExternalAuthorityRecord:
    def _seed(self, root, *, schema=None, commit="c" * 40, blobs=None, body=b"x = 1"):
        for rel in GOVERNED_SOURCE_PATHS:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body + LF_BYTE)
        measured = measure_source_identity(backend_root=root)
        rec = root / si.AUTHORITY_RECORD_PATH
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(
            json.dumps(
                {
                    "schema": si.AUTHORITY_RECORD_SCHEMA if schema is None else schema,
                    "approved_review_commit": commit,
                    "approved_governed_source_blobs": (
                        dict(measured.blobs) if blobs is None else blobs
                    ),
                }
            ),
            encoding="utf-8",
        )
        return measured

    def test_an_absent_record_means_no_designation(self, tmp_path):
        """⛔ Missing must never read as permission."""
        identity, problems = si.load_computation_authority(backend_root=tmp_path)
        assert identity is None
        assert problems == []
        with pytest.raises(SourceIdentityRefused, match="no successor governed"):
            si.verify_governed_source_identity(backend_root=tmp_path)

    def test_an_unrecognised_schema_is_refused(self, tmp_path):
        self._seed(tmp_path, schema="something-else/9")
        identity, problems = si.load_computation_authority(backend_root=tmp_path)
        assert identity is None
        assert any("schema" in p for p in problems)

    def test_a_partial_pin_is_refused(self, tmp_path):
        """An unpinned governed file would be free to change."""
        self._seed(tmp_path, blobs={"app/research/mdq_eval/gate.py": "a" * 64})
        identity, problems = si.load_computation_authority(backend_root=tmp_path)
        assert identity is None
        assert any("does not pin every governed source path" in p for p in problems)

    def test_a_malformed_record_is_refused(self, tmp_path):
        rec = tmp_path / si.AUTHORITY_RECORD_PATH
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text("{not json", encoding="utf-8")
        identity, problems = si.load_computation_authority(backend_root=tmp_path)
        assert identity is None
        assert any("unreadable" in p for p in problems)

    def test_a_well_formed_record_loads_every_governed_path(self, tmp_path):
        measured = self._seed(tmp_path)
        identity, problems = si.load_computation_authority(backend_root=tmp_path)
        assert problems == []
        assert identity is not None
        assert set(identity.blobs) == set(GOVERNED_SOURCE_PATHS)
        # The blobs the record pins are exactly the ones measured; the commit legs still
        # refuse here because a tmp dir is not a repository, which is itself correct.
        assert all(identity.blobs[rel] == measured.blobs[rel] for rel in GOVERNED_SOURCE_PATHS)
        assert not any(
            "MIXED source state" in r for r in compare_source_identity(measured, identity)
        )

    def test_the_authority_path_is_not_injectable(self):
        """backend_root relocates the runtime; it cannot name a different authority file."""
        import inspect

        params = set(inspect.signature(si.load_computation_authority).parameters)
        assert params == {"backend_root"}


class TestComparisonRefusals:
    """Pure comparator — the only surface that accepts an expected identity. Mints nothing."""

    def test_a_dirty_governed_path_refuses(self):
        m = _measured(dirty_governed_paths=("app/research/mdq_eval/gate.py",))
        assert any("dirty" in r for r in compare_source_identity(m, AUTHORITY))

    def test_an_unmeasurable_identity_refuses(self):
        m = _measured(commit=None, problems=("git unavailable",))
        assert any("git unavailable" in r for r in compare_source_identity(m, AUTHORITY))

    def test_a_later_runtime_commit_is_NOT_by_itself_a_refusal(self):
        """★ The commit-level twin of the source-level cycle.

        Committing the external authority record necessarily advances HEAD past the reviewed
        commit. Requiring whole-repository HEAD equality would therefore refuse every runtime the
        designation was meant to authorize. The governed identity is the ten-file surface; the
        runtime commit is provenance, and equivalence over that surface is checked separately by
        `governed_paths_changed_since`, which needs git.
        """
        m = _measured(commit="b" * 40)  # a later custody commit, governed blobs unchanged
        assert compare_source_identity(m, AUTHORITY) == []

    def test_a_mixed_source_state_refuses(self):
        """★ The commit matches but the BYTES do not — what a commit-only check misses."""
        blobs = dict(GOOD_BLOBS)
        blobs["app/research/mdq_eval/gate.py"] = "f" * 64
        m = _measured(blobs=blobs)
        assert any("MIXED source state" in r for r in compare_source_identity(m, AUTHORITY))

    def test_a_missing_governed_file_refuses(self):
        m = _measured(problems=("governed source path missing from the runtime: x",))
        assert any("missing" in r for r in compare_source_identity(m, AUTHORITY))

    def test_exact_identity_with_matching_blobs_passes(self):
        """The refusals above are only meaningful if this one succeeds."""
        assert compare_source_identity(_measured(), AUTHORITY) == []


class TestGovernedSurfaceEquivalence:
    """HEAD may advance ONLY through changes outside GOVERNED_SOURCE_PATHS."""

    def test_an_unresolvable_review_commit_is_refused(self, tmp_path):
        """A commit not present in this runtime cannot be compared against."""
        changed, problems = si.governed_paths_changed_since("d" * 40, backend_root=tmp_path)
        assert changed is None
        assert any("cannot determine whether the governed surface changed" in p for p in problems)

    def test_the_real_repo_reports_no_governed_delta_against_its_own_head(self):
        """Sanity: HEAD vs HEAD must be empty, or the check would refuse everything."""
        root = Path(si.__file__).resolve().parents[3]
        head = si._git(["rev-parse", "HEAD"], root)
        if head is None:
            pytest.skip("not a git checkout")
        changed, problems = si.governed_paths_changed_since(head, backend_root=root)
        assert problems == []
        assert changed == []


class TestAncestryIsRequiredNotInferred:
    """git diff compares ENDPOINTS; it says nothing about lineage."""

    def _repo(self, root: Path):
        import subprocess

        def g(*a):
            return subprocess.run(
                ["git", *a], cwd=str(root), capture_output=True, text=True, check=False
            )

        root.mkdir(parents=True, exist_ok=True)
        g("init", "-q")
        g("config", "user.email", "t@example.com")
        g("config", "user.name", "t")
        return g

    def test_a_non_ancestor_review_commit_is_refused(self, tmp_path):
        """A divergent history carrying identical governed files must NOT be accepted."""
        g = self._repo(tmp_path)
        (tmp_path / "a.txt").write_text("one", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "base")
        base = g("rev-parse", "HEAD").stdout.strip()

        g("checkout", "-q", "--orphan", "other")
        (tmp_path / "b.txt").write_text("two", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "unrelated")

        ok, problems = si.review_commit_is_ancestor(base, backend_root=tmp_path)
        assert ok is False
        assert any("NOT an ancestor" in p for p in problems)

    def test_an_ancestor_with_a_later_non_governed_commit_passes(self, tmp_path):
        """★ The intended custody shape: HEAD advanced, governed surface untouched."""
        g = self._repo(tmp_path)
        for rel in GOVERNED_SOURCE_PATHS:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x = 1" + LF_BYTE)
        g("add", "-A")
        g("commit", "-qm", "reviewed")
        review = g("rev-parse", "HEAD").stdout.strip()

        rec = tmp_path / si.AUTHORITY_RECORD_PATH
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text("{}", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "custody the authority record")

        ok, problems = si.review_commit_is_ancestor(review, backend_root=tmp_path)
        assert ok is True and problems == []
        changed, delta_problems = si.governed_paths_changed_since(review, backend_root=tmp_path)
        assert delta_problems == []
        assert changed == [], "the custody commit must not touch the governed surface"

    def test_a_later_commit_that_DOES_touch_the_surface_is_caught(self, tmp_path):
        """★ THE falsifiability guard, and deliberately synthetic.

        It proves the delta check is not inert -- a check that could never report a change would
        look identical to a passing one. It builds its own repository rather than reasoning about
        this one's history, because `actions/checkout` defaults to a SHALLOW clone: an earlier
        version compared against `rev-list --max-parents=0 HEAD`, which resolves to HEAD itself at
        depth 1, so the delta was empty and the guard failed in CI while passing locally on a full
        clone. ⛔ Do not reintroduce a history-dependent form of this test.

        It also shows ancestry alone must not be mistaken for equivalence: the commit below IS an
        ancestor-descendant pair, yet the governed surface moved.
        """
        g = self._repo(tmp_path)
        for rel in GOVERNED_SOURCE_PATHS:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x = 1" + LF_BYTE)
        g("add", "-A")
        g("commit", "-qm", "reviewed")
        review = g("rev-parse", "HEAD").stdout.strip()

        (tmp_path / GOVERNED_SOURCE_PATHS[0]).write_bytes(b"x = 2" + LF_BYTE)
        g("add", "-A")
        g("commit", "-qm", "touches the governed surface")

        ok, _ = si.review_commit_is_ancestor(review, backend_root=tmp_path)
        assert ok is True  # still an ancestor ...
        changed, _ = si.governed_paths_changed_since(review, backend_root=tmp_path)
        assert changed == [GOVERNED_SOURCE_PATHS[0]]  # ... but the surface moved

    def test_an_unmeasurable_ancestry_refuses(self, tmp_path):
        ok, problems = si.review_commit_is_ancestor("e" * 40, backend_root=tmp_path)
        assert ok is None
        assert any("cannot establish whether" in p for p in problems)


class TestCrIsAFailureNotNormalised:
    """⛔ Never widen the identity check to tolerate a deployment quirk."""

    def test_a_cr_byte_in_a_governed_file_is_refused(self, tmp_path):
        for rel in GOVERNED_SOURCE_PATHS:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(CRLF_BODY)
        m = measure_source_identity(backend_root=tmp_path)
        assert any("CR bytes" in prob for prob in m.problems)
        assert m.measurable is False

    def test_an_lf_only_file_is_hashed_raw(self, tmp_path):
        """Raw bytes for a conforming file ARE the git blob bytes."""
        import hashlib

        body = LF_BODY
        for rel in GOVERNED_SOURCE_PATHS:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        m = measure_source_identity(backend_root=tmp_path)
        assert not any("CR bytes" in prob for prob in m.problems)
        assert m.blobs["app/research/mdq_eval/gate.py"] == hashlib.sha256(body).hexdigest()

    def test_this_very_module_set_is_cr_free(self):
        """The governed files must satisfy their own contract."""
        root = Path(si.__file__).resolve().parents[3]
        offenders = [
            rel
            for rel in GOVERNED_SOURCE_PATHS
            if (root / rel).exists() and CR_BYTE in (root / rel).read_bytes()
        ]
        assert offenders == []


def _code_without_docstrings(mod) -> str:
    """Module source with every docstring removed.

    Needed because the modules *name* the forbidden flags in prose in order to say they do not
    exist. Scanning raw source would fail on the very sentence that documents the guarantee, so the
    test would be measuring the documentation rather than the code.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


class TestNoOperatorAssertion:
    """An identity a caller can state is a claim about one, not an identity."""

    def test_the_b2_surface_has_no_operator_override(self):
        code = _code_without_docstrings(si)
        for forbidden in ("--source-sha", "--approved-sha", "--assume-clean", "getenv", "environ"):
            assert forbidden not in code, f"{forbidden} must not exist in the B2 code path"

    def test_the_cli_exposes_no_identity_flag(self):
        import scripts.mdq_evaluate_k as cli

        code = _code_without_docstrings(cli)
        for forbidden in ("--source-sha", "--approved-sha", "--assume-clean", "--blob"):
            assert forbidden not in code

    def test_the_scan_is_falsifiable(self):
        """★ Guard against the scan silently matching nothing: a real token IS found."""
        code = _code_without_docstrings(si)
        assert "AUTHORITY_RECORD_PATH" in code


class TestRealMeasurement:
    def test_a_non_repository_is_unmeasurable_not_assumed_clean(self, tmp_path):
        """A deployed tarball has no .git. That must read as UNMEASURABLE, never as 'fine'."""
        m = measure_source_identity(backend_root=tmp_path)
        assert m.commit is None
        assert m.measurable is False
        assert any("UNMEASURABLE" in p for p in m.problems)

    def test_measurement_reports_missing_governed_files(self, tmp_path):
        m = measure_source_identity(backend_root=tmp_path)
        assert any("governed source path missing" in p for p in m.problems)

    def test_the_governed_surface_is_explicit_and_nonempty(self):
        assert len(GOVERNED_SOURCE_PATHS) >= 8
        assert "app/research/mdq_eval/gate.py" in GOVERNED_SOURCE_PATHS
        assert "scripts/mdq_evaluate_k.py" in GOVERNED_SOURCE_PATHS


class TestB1aCannotBeRescuedByB1b:
    def test_invariance_does_not_make_a_bad_manifest_admissible(self, tmp_path, adjudication):
        """B1b is evidence about repository revisions; it cannot repair a partition-level failure."""
        from app.research.mdq_eval import gate
        from tests.research.mdq_eval.conftest import write_governed_manifests

        write_governed_manifests(tmp_path, __import__("datetime").date(2026, 8, 19))
        session = __import__("datetime").date(2026, 8, 19)
        mp = tmp_path / "iex" / session.isoformat() / "manifest.json"
        import json as _json

        m = _json.loads(mp.read_text(encoding="utf-8"))
        m["collector_version"] = "mdq-collector/9.9.9"
        mp.write_text(_json.dumps(m), encoding="utf-8")

        native = gate.verify_manifest_native_identity(tmp_path, session)
        # invariance still holds and still reports True ...
        assert native["collector_implementation_invariance_verified"] is True
        # ... and the partition is STILL refused.
        assert native["manifest_collector_version_verified"] is False
        with pytest.raises(gate.NotAdmissible):
            gate.require_admissible(tmp_path, session, session_close_utc=None)

    def test_historical_binding_stays_explicit_and_never_becomes_pass(self, tmp_path):
        from app.research.mdq_eval import gate
        from tests.research.mdq_eval.conftest import write_governed_manifests

        session = __import__("datetime").date(2026, 8, 19)
        write_governed_manifests(tmp_path, session)
        native = gate.verify_manifest_native_identity(tmp_path, session)
        assert native["per_partition_full_source_tuple_verified"] is False
        assert native["per_partition_full_source_tuple_status"] == "HISTORICAL_BINDING_UNAVAILABLE"
        # A fully passing partition must NOT silently upgrade the unavailable binding.
        assert native["manifest_collector_version_verified"] is True
        assert native["per_partition_full_source_tuple_verified"] is False


def test_governed_paths_exist_in_this_checkout():
    """The surface must name real files, or the identity binds nothing."""
    root = Path(si.__file__).resolve().parents[3]
    missing = [rel for rel in GOVERNED_SOURCE_PATHS if not (root / rel).exists()]
    assert missing == []
