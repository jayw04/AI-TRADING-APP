"""R5e-2 structural invariants over EVERY production Python surface.

The R5e-2 review made these load-bearing. The disclosed residual — `ForwardSessionRunner` still accepts
the three witness legs as independent optional fields — is acceptable ONLY while these hold, because
what makes the gate real is not that the runner refuses bad wiring but that no production entry point
ever wires it.

Two weaknesses in the first attempt are fixed here.

**Surface.** The original scans looked only under `app/`. `scripts/` is equally a production entry
point — the forward-validation CLI lives there — so a script constructing a runtime would have passed
silently. Both trees are scanned now, and exclusions (tests, generated artifacts, vendored code,
virtualenvs) are named explicitly rather than achieved by scanning less.

**Method.** The original scans were substring matches on source text, which a comment, a string, an
`import ... as` alias, or a call split across lines defeats. Detection is AST-based: calls are resolved
through the module's own import bindings, so `from x import SessionRuntime as SR; SR(...)` is caught
and the words appearing in a docstring are not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

# Every production Python surface. Not "app/ because that is where the interesting code is" — a
# production entry point is anything the deployment can execute.
PRODUCTION_TREES = ("app", "scripts")

# Explicit exclusions. Named so that adding one is a visible decision rather than a silent narrowing.
EXCLUDED_DIR_NAMES = frozenset({
    "tests", "test", "__pycache__", ".venv", "venv", "site-packages", "node_modules",
    "alembic",            # generated migrations
    "research",           # scripts/research: exploratory one-off reproductions, never deployed
})


def _production_files() -> list[Path]:
    out: list[Path] = []
    for tree in PRODUCTION_TREES:
        root = BACKEND / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if EXCLUDED_DIR_NAMES.intersection(path.relative_to(BACKEND).parts):
                continue
            out.append(path)
    return sorted(out)


def _local_names_for(tree: ast.Module, target_module_suffix: str, target_name: str) -> set[str]:
    """Every local binding in this module that refers to `target_name`, honouring `as` aliases."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(target_module_suffix):
            for alias in node.names:
                if alias.name == target_name:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(target_module_suffix):
                    names.add(f"{alias.asname or alias.name}.{target_name}")
    return names


def _callee_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        cur: ast.expr = func.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _call_sites(module_suffix: str, name: str) -> dict[str, list[int]]:
    """Files (repo-relative POSIX) → line numbers where `name` is CALLED, resolved through imports."""
    found: dict[str, list[int]] = {}
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover - a broken file fails elsewhere
            continue
        bound = _local_names_for(tree, module_suffix, name)
        if not bound:
            continue
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and _callee_name(n) in bound]
        if hits:
            found[path.relative_to(BACKEND).as_posix()] = sorted(hits)
    return found


def _imported_names(module_suffix: str, name: str) -> list[str]:
    """Files that so much as IMPORT `name`, whether or not they call it."""
    out: list[str] = []
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        if _local_names_for(tree, module_suffix, name):
            out.append(path.relative_to(BACKEND).as_posix())
    return sorted(out)


# ── the scanner itself must be trustworthy ───────────────────────────────────────────────────────────

def test_the_scan_actually_covers_both_production_trees():
    """A structural test that silently scanned nothing would pass forever."""
    files = {p.relative_to(BACKEND).as_posix() for p in _production_files()}
    assert any(f.startswith("app/") for f in files)
    assert any(f.startswith("scripts/") for f in files)
    assert "app/validation/session_composition.py" in files
    assert "scripts/run_forward_validation_session.py" in files
    assert not any("/tests/" in f or f.startswith("tests/") for f in files)


def test_the_scanner_resolves_aliases_and_ignores_text(tmp_path):
    """Pins the AST method against the substring method it replaced: an aliased import is a real call
    site, and the same words in a comment or string are not."""
    source = (
        "from app.validation.session_orchestration import SessionRuntime as SR\n"
        "# SessionRuntime( in a comment\n"
        "DOC = 'SessionRuntime('\n"
        "x = SR(store=None)\n"
    )
    tree = ast.parse(source)
    bound = _local_names_for(tree, "session_orchestration", "SessionRuntime")
    assert bound == {"SR"}
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _callee_name(n) in bound]
    assert hits == [4], "the alias call must be found, and comment/string text must not"


# ── the invariants ───────────────────────────────────────────────────────────────────────────────────

def test_one_production_session_runtime_construction_site():
    sites = _call_sites("session_orchestration", "SessionRuntime")
    assert list(sites) == ["app/validation/session_composition.py"], (
        f"SessionRuntime is constructed in production outside the composition root: {sites}")


def test_one_production_run_production_session_invocation():
    sites = _call_sites("session_orchestration", "run_production_session")
    assert list(sites) == ["scripts/run_forward_validation_session.py"], (
        f"run_production_session is invoked from an unexpected production path: {sites}")


def test_one_production_forward_session_runner_construction_site():
    """The DISCLOSED RESIDUAL is bounded by exactly this: the runner still takes its three witness legs
    independently, so the only thing standing between that and an unwitnessed record is that precisely
    one production path builds it — the one that goes through the enforced SessionRuntime."""
    sites = _call_sites("forward_session_runner", "ForwardSessionRunner")
    assert list(sites) == ["app/validation/session_orchestration.py"], (
        f"a second production path constructs the runner: {sites}; it would bypass the enforced witness")


def test_no_production_module_assigns_the_witness_legs_independently():
    """The legs may be READ (the SessionRuntime properties do) but never SET outside the runner
    construction that the composition path owns."""
    legs = {"anchor_signer", "anchor_verifier", "external_anchor_sink"}
    offenders: dict[str, list[int]] = {}
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel in ("app/validation/session_orchestration.py",
                   "app/validation/forward_session_runner.py"):
            continue                               # the sanctioned construction and the definition
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.keyword) and n.arg in legs]
        hits += [t.attr for t in ast.walk(tree)                     # type: ignore[misc]
                 if isinstance(t, ast.Attribute) and isinstance(t.ctx, ast.Store) and t.attr in legs]
        if hits:
            offenders[rel] = hits                                    # type: ignore[assignment]
    assert offenders == {}, f"production code wires witness legs independently: {offenders}"


def test_production_witness_is_constructed_only_inside_the_enforcement_module():
    sites = _call_sites("witness_enforcement", "ProductionWitness")
    assert sites == {}, (
        f"ProductionWitness is constructed outside witness_enforcement.py: {sites}; only the gate may "
        f"build the carrier")


def test_no_production_module_reaches_for_the_issuance_internals():
    """`_mark_enforced` and `_ISSUANCE_SENTINEL` mint an enforced witness without any gate. Nothing in
    production may import them — the thing production wants is `enforce_production_witness`."""
    for private in ("_mark_enforced", "_ISSUANCE_SENTINEL", "_ISSUANCE_ATTR"):
        importers = [f for f in _imported_names("witness_enforcement", private)
                     if not f.endswith("witness_enforcement.py")]
        assert importers == [], f"production modules import {private}: {importers}"


@pytest.mark.parametrize("name", ["enforce_production_witness"])
def test_the_gate_is_reachable_where_it_should_be(name):
    """The mirror of the refusals above: the sanctioned entry point IS used, so these tests cannot all
    be passing because nothing is wired at all."""
    importers = _imported_names("witness_enforcement", name)
    assert "app/validation/session_composition.py" in importers
    assert "scripts/run_forward_validation_session.py" in importers


# ── A4: exactly one authoritative completion path ────────────────────────────────────────────────────
#
# The coverage row, the completed ingest run and the artifact binding are the three facts a consumer
# treats as source authority. If any other production code could write them, "authoritative" would mean
# "someone asserted it" again — the exact weakness the governed protocol exists to remove.

_FINALIZER_FILE = "app/factor_data/store.py"


def test_only_the_store_finalizer_writes_dataset_coverage():
    """No production module outside the finalizer may INSERT/UPDATE/DELETE `dataset_coverage`."""
    offenders: dict[str, list[str]] = {}
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel == _FINALIZER_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [line.strip() for line in text.splitlines()
                if "dataset_coverage" in line
                and any(verb in line.upper() for verb in ("INSERT", "UPDATE", "DELETE"))]
        if hits:
            offenders[rel] = hits
    assert offenders == {}, f"production code writes dataset_coverage outside the finalizer: {offenders}"


def test_no_completed_actions_ingest_run_is_recorded_outside_the_finalizer():
    """Scoped to the ACTIONS dataset deliberately, and the reason matters.

    Other datasets (`sep`, `sf1`, `vix`) have long-standing ingest scripts that record completed runs,
    and those are fine: source authority requires a coverage row AND a linked completed run, and only
    the finalizer writes coverage rows — which the test above pins. A completed run alone confers
    nothing, so a blanket ban would be governance theatre and would drag unrelated scripts into this
    change.

    What must not exist is a second way to mark an ACTIONS ingest complete, because that is the dataset
    whose authority the forward validation rests on.
    """
    offenders: dict[str, list[int]] = {}
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel == _FINALIZER_FILE:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        hits: list[int] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and _callee_name(node).endswith("record_ingest_run")):
                continue
            names_actions = any(
                (isinstance(a, ast.Constant) and a.value == "actions")
                or (isinstance(a, ast.Name) and a.id.endswith("ACTIONS_DATASET"))
                or (isinstance(a, ast.Attribute) and a.attr.endswith("ACTIONS_DATASET"))
                for a in node.args)
            completed = any(isinstance(a, ast.Constant) and a.value == "ok" for a in node.args)
            if names_actions and completed:
                hits.append(node.lineno)
        if hits:
            offenders[rel] = hits
    assert offenders == {}, (
        f"production code marks an ACTIONS ingest complete outside the finalizer: {offenders}")


def test_exactly_one_production_actions_finalization_call_site():
    """The governed ACTIONS ingest is the single production caller of the finalizer."""
    sites = _call_sites("factor_data.store", "finalize_dataset_ingest")
    assert sites == {}, (
        f"finalize_dataset_ingest is called from production code outside the store: {sites}; the "
        f"governed ACTIONS path is store.ingest_actions_from_artifact")

    store = (BACKEND / _FINALIZER_FILE).read_text(encoding="utf-8")
    assert store.count("def _finalize_within_transaction(") == 1
    assert store.count("_finalize_within_transaction(") == 3, (
        "expected exactly the definition plus two callers (finalize_dataset_ingest and the governed "
        "ACTIONS ingest); a third caller is a new completion path")


def _code_only(path: Path) -> str:
    """Source with comments AND string literals removed.

    A name scan over raw text cannot tell a live code path from a comment explaining why that path was
    REMOVED — and this module's own removal notes name the retired fields deliberately. Tokenizing and
    dropping comments and strings makes the guard search semantics rather than prose.
    """
    import io
    import tokenize

    kept: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            kept.append(tok.string)
    except (tokenize.TokenError, IndentationError):   # pragma: no cover - a broken file fails elsewhere
        return ""
    return " ".join(kept)


# ── ADR 0045: no v1 or reference-algorithm path survives in PRODUCTION code ──────────────────────────
#
# These scan PRODUCTION trees only (`app/` and `scripts/`). A guard that also scanned the test tree
# would be satisfied by test code and would miss the thing that matters — what the deployment runs.

def test_no_production_module_pins_the_reference_algorithm():
    """`ALGORITHM_ED25519` is a REFERENCE identifier. Production may name it in an allowlist definition
    or refuse it, but no production module may select it as the pinned production algorithm."""
    offenders: dict[str, list[str]] = {}
    allowed = {"app/validation/witness_protocol.py",      # defines the identifier and the allowlists
               "app/validation/chain_witness.py",         # the reference signer/verifier themselves
               "app/validation/witness_enforcement.py"}   # refuses it / defaults the reference verifier
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel in allowed:
            continue
        if "ALGORITHM_ED25519" in _code_only(path):
            offenders[rel] = ["ALGORITHM_ED25519"]
    assert offenders == {}, f"production code outside the protocol/reference modules pins Ed25519: {offenders}"


def test_no_v1_receipt_parser_or_compatibility_path_remains():
    """Protocol v1 is retired without migration (ADR 0045 clause 7). Nothing may parse, upgrade or fall
    back to it."""
    banned = ("signature_b64", "public_key_id", "PROTOCOL_VERSION_1", "protocol_version == 1",
              "protocol_version=1", "from_v1", "upgrade_receipt")
    offenders: dict[str, list[str]] = {}
    for path in _production_files():
        code = _code_only(path)
        hits = [token for token in banned if token in code]
        if hits:
            offenders[path.relative_to(BACKEND).as_posix()] = hits
    assert offenders == {}, f"a retired v1 receipt path survives in production code: {offenders}"


def test_no_retired_witness_projection_field_is_read_or_written_in_production():
    """The three-field projection is gone. `witness_identity` is NOT retired — it is a v2 receipt
    field — so only the two genuinely retired names are banned."""
    offenders: dict[str, list[str]] = {}
    for path in _production_files():
        code = _code_only(path)
        hits = [t for t in ("witness_signature", "witness_public_key_id") if t in code]
        if hits:
            offenders[path.relative_to(BACKEND).as_posix()] = hits
    assert offenders == {}, f"retired witness projection fields survive in production: {offenders}"


def test_every_production_signed_receipt_construction_supplies_all_eight_fields():
    """A partially-constructed receipt would rely on defaults that do not exist — and if they ever did,
    the stored evidence would be missing what the in-memory object had."""
    required = {"protocol_version", "algorithm", "key_id", "public_key_fingerprint",
                "message_digest", "signature", "signed_at", "witness_identity"}
    offenders: dict[str, list[int]] = {}
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        bound = _local_names_for(tree, "witness_protocol", "SignedReceipt")
        if not bound:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee_name(node) in bound:
                supplied = {kw.arg for kw in node.keywords if kw.arg}
                if not required.issubset(supplied):
                    offenders.setdefault(path.relative_to(BACKEND).as_posix(), []).append(node.lineno)
    assert offenders == {}, f"a production SignedReceipt is built without all eight fields: {offenders}"


def test_only_the_protocol_serializer_crosses_the_persistence_boundary():
    """Storage must not enumerate receipt fields or reach for `asdict`: a layer that builds its own
    mapping can bypass the strict parse on the way back in."""
    offenders: dict[str, list[str]] = {}
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel == "app/validation/witness_protocol.py":
            continue
        code = _code_only(path)
        if "witness_receipt" not in code:
            continue
        hits = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if "asdict(" in line and "receipt" in line.lower()
                and not line.strip().startswith("#")]
        if hits:
            offenders[rel] = hits
    assert offenders == {}, f"a persistence layer serializes a receipt itself: {offenders}"


# ── the witness exception hierarchy is one rooted tree (fail-closed boundaries) ──────────────────────

def test_the_witness_error_hierarchy_has_one_root_under_integrity_stop():
    """`WitnessProtocolError` was once a SIBLING of `WitnessError`, so a protocol failure could slip
    past `except WitnessError` boundaries and change rollback behaviour silently. Both relationships
    are pinned so that cannot recur."""
    from app.validation.forward_window import IntegrityStop
    from app.validation.witness_config import WitnessConfigError
    from app.validation.witness_protocol import (
        WitnessError,
        WitnessPersistenceError,
        WitnessProtocolError,
        WitnessVerificationError,
    )

    for subclass in (WitnessProtocolError, WitnessVerificationError, WitnessPersistenceError,
                     WitnessConfigError):
        assert issubclass(subclass, WitnessError), subclass
        assert issubclass(subclass, IntegrityStop), subclass


def test_an_existing_integrity_stop_boundary_still_catches_a_configuration_error():
    """Behavioural, not just structural: reparenting `WitnessConfigError` under `WitnessError` must not
    have changed how an existing `except IntegrityStop` control path behaves."""
    from app.validation.forward_window import IntegrityStop
    from app.validation.witness_config import WitnessConfigError

    caught = None
    try:
        raise WitnessConfigError("declaration incomplete", code="WITNESS_CONFIG_INCOMPLETE")
    except IntegrityStop as exc:                   # the historical boundary
        caught = exc
    assert isinstance(caught, WitnessConfigError)
    assert caught.code == "WITNESS_CONFIG_INCOMPLETE"


def test_structural_parsing_precedes_policy_checks_in_configuration_load():
    """A malformed value and a prohibited value are different findings. Reporting the policy error
    first would mask the malformed one, which is what happened before this ordering was fixed."""
    from app.validation.witness_config import WitnessConfigError, load_witness_config

    # PRODUCTION profile, missing algorithm/key_id (a policy fault) AND a malformed signer options
    # block (a structural fault). The STRUCTURAL error must be the one reported.
    with pytest.raises(WitnessConfigError) as exc:
        load_witness_config({
            "profile": "PRODUCTION",
            "public_key_path": "/etc/workbench/witness.pub",
            "signer": {"factory": "deployment.witness:build_signer", "identity": "kms://x",
                       "options": "not-an-object"},
            "sink": {"factory": "deployment.witness:build_sink", "identity": "s3://y"},
        })
    assert "options must be an object" in str(exc.value)
