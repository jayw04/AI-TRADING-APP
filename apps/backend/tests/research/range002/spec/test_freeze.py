"""WP0.3 freeze tool + loader/view tests. Synthetic fixtures only; nothing real is frozen."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from app.research.range002.spec.loader import (
    SpecHashMismatchError,
    SpecSchemaError,
    SpecView,
    load_frozen,
)

from ._fixtures import SYNTH_MANIFEST_PATH, complete_payload, decision_block, set_path

BACKEND_DIR = Path(__file__).resolve().parents[4]
CLI_SCRIPT = BACKEND_DIR / "scripts" / "research" / "range002" / "freeze_spec.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("range002_freeze_spec_cli", CLI_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Cli:
    """The freeze tool with the synthetic manifest injected (production reads only the fixed
    committed path; the explicit ``manifest_path`` parameter exists for tests)."""

    def __init__(self, module, manifest_path):
        self._m = module
        self._manifest_path = manifest_path

    def main(self, argv):
        return self._m.main(argv, manifest_path=self._manifest_path)

    def freeze(self, draft, out, **kw):
        kw.setdefault("manifest_path", self._manifest_path)
        return self._m.freeze(draft, out, **kw)

    def __getattr__(self, name):
        return getattr(self._m, name)

    def __setattr__(self, name, value):  # monkeypatch.setattr(cli, "load_frozen", ...) patches
        if name in ("_m", "_manifest_path"):  # the real module, as before the proxy existed
            object.__setattr__(self, name, value)
        else:
            setattr(self._m, name, value)


raw_cli = _load_cli()
cli = _Cli(raw_cli, SYNTH_MANIFEST_PATH)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _freeze(tmp_path, payload=None) -> Path:
    draft = _write(tmp_path / "draft.json", payload or complete_payload())
    out = tmp_path / "frozen.json"
    assert cli.main([str(draft), "--out", str(out)]) == 0
    return out


def test_freeze_complete_decided_draft_round_trips(tmp_path, capsys):
    out = _freeze(tmp_path)
    view = load_frozen(out)
    assert view.has_run_decision and view.unusable_reasons == ()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["decision"]["spec_sha256"] == view.spec_sha256
    assert f"spec_sha256={view.spec_sha256}" in capsys.readouterr().out


def test_freeze_refuses_when_p0_fields_unset_and_names_them(tmp_path, capsys):
    payload = complete_payload()
    set_path(payload, "gates.win_rate", None)
    set_path(payload, "exits.selection.score", None)
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    err = capsys.readouterr().err
    assert rc == 2 and not out.exists()
    assert "gates.win_rate" in err and "exits.selection.score" in err


def test_freeze_refuses_without_a_decision_and_never_fabricates_one(tmp_path, capsys):
    payload = complete_payload(decided=False)
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    assert rc == 2 and not out.exists()
    assert "decision" in capsys.readouterr().err


@pytest.mark.parametrize("outcome", ["revise", "defer", "stop"])
def test_freeze_refuses_a_decision_that_is_not_approved(tmp_path, capsys, outcome):
    payload = complete_payload()
    payload["decision"]["decision"] = outcome
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    assert rc == 2 and not out.exists()
    assert "approved" in capsys.readouterr().err


def test_freeze_refuses_a_decision_without_run_scope(tmp_path, capsys):
    payload = complete_payload()
    payload["decision"] = decision_block(scope=["build"], partitions=[])
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    assert rc == 2 and not out.exists()
    assert "run" in capsys.readouterr().err


def test_freeze_refuses_minutes_file_that_does_not_exist(tmp_path, capsys):
    payload = complete_payload()
    payload["decision"]["minutes_path"] = "minutes/absent.md"
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    assert rc == 2 and not out.exists()
    assert "does not exist" in capsys.readouterr().err


def test_freeze_refuses_minutes_hash_mismatch(tmp_path, capsys):
    payload = complete_payload()
    payload["decision"]["minutes_sha256"] = "0" * 64
    out = tmp_path / "frozen.json"
    rc = cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)])
    assert rc == 2 and not out.exists()
    assert "changed after the decision" in capsys.readouterr().err


def test_freeze_refuses_stale_preset_hash(tmp_path, capsys):
    payload = complete_payload()
    payload["decision"]["spec_sha256"] = "0" * 64
    out = tmp_path / "frozen.json"
    assert cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(out)]) == 2
    assert "decision.spec_sha256" in capsys.readouterr().err


def test_freeze_accepts_a_correct_preset_hash_and_fills_nothing_else(tmp_path):
    from app.research.range002.spec.loader import load_draft, spec_sha256

    draft = _write(tmp_path / "d.json", complete_payload())
    digest = spec_sha256(load_draft(draft))
    payload = complete_payload()
    payload["decision"]["spec_sha256"] = digest
    out = tmp_path / "frozen.json"
    assert cli.main([str(_write(tmp_path / "d2.json", payload)), "--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))["decision"]
    assert written == {**complete_payload()["decision"], "spec_sha256": digest}


def test_freeze_never_overwrites_an_existing_frozen_file(tmp_path):
    out = _freeze(tmp_path)
    before = out.read_bytes()
    assert cli.main([str(tmp_path / "draft.json"), "--out", str(out)]) == 2
    assert out.read_bytes() == before


def test_freeze_refuses_unknown_keys(tmp_path):
    payload = complete_payload()
    payload["surprise"] = 1
    assert (
        cli.main([str(_write(tmp_path / "d.json", payload)), "--out", str(tmp_path / "f.json")])
        == 2
    )


def test_duplicate_json_keys_refused(tmp_path):
    text = json.dumps(complete_payload())
    dup = text[:-1] + ', "program": "RANGE-002"}'
    p = tmp_path / "d.json"
    p.write_text(dup, encoding="utf-8")
    assert cli.main([str(p), "--out", str(tmp_path / "f.json")]) == 2


def test_frozen_spec_with_no_decision_is_flagged_unusable(tmp_path):
    # Cannot be produced by the tool; hand-built to prove the loader still refuses to trust it.
    hand = _write(tmp_path / "hand.json", complete_payload(decided=False))
    view = load_frozen(hand)
    assert view.has_run_decision is False
    assert view.unusable_reasons == ("decision missing",)
    assert view.decision is None and view.minutes_path is None
    assert cli.main(["--verify", str(hand)]) == 2


def test_frozen_spec_with_decision_but_no_bound_hash_is_unusable(tmp_path):
    hand = _write(tmp_path / "hand.json", complete_payload())  # spec_sha256 not filled in
    view = load_frozen(hand)
    assert view.has_run_decision is False
    assert view.unusable_reasons == ("decision.spec_sha256 missing",)


def test_decision_edited_after_freeze_to_not_approved_is_unusable(tmp_path):
    out = _freeze(tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    data["decision"]["decision"] = "stop"
    out.write_text(json.dumps(data), encoding="utf-8")
    view = load_frozen(out)  # the decision block is outside the hash, so it loads, but unusable
    assert view.has_run_decision is False and view.decision == "stop"
    assert any("not 'approved'" in r for r in view.unusable_reasons)
    assert cli.main(["--verify", str(out)]) == 2


def test_editing_a_frozen_file_changes_the_hash_and_loader_refuses(tmp_path):
    out = _freeze(tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    data["risk"]["per_trade_pct"] = 0.99  # post-freeze tamper
    out.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SpecHashMismatchError) as ei:
        load_frozen(out)
    assert ei.value.recorded != ei.value.computed
    assert cli.main(["--verify", str(out)]) == 2


def test_reformatting_a_frozen_file_does_not_break_it(tmp_path):
    out = _freeze(tmp_path)
    view1 = load_frozen(out)
    out.write_text(json.dumps(json.loads(out.read_text(encoding="utf-8"))), encoding="utf-8")
    assert load_frozen(out).spec_sha256 == view1.spec_sha256


def test_frozen_file_with_unset_p0_is_not_loadable(tmp_path):
    from app.research.range002.spec.schema import UnsetP0FieldsError

    payload = complete_payload()
    set_path(payload, "stats.bootstrap.method", None)
    with pytest.raises(UnsetP0FieldsError, match="stats.bootstrap.method"):
        load_frozen(_write(tmp_path / "f.json", payload))


def test_malformed_file_is_a_schema_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(SpecSchemaError):
        load_frozen(p)
    nan = tmp_path / "nan.json"
    nan.write_text('{"program": NaN}', encoding="utf-8")
    with pytest.raises(SpecSchemaError):
        load_frozen(nan)


def test_emit_skeleton_is_all_null_and_loads_as_unfrozen(tmp_path, capsys):
    sk = tmp_path / "skeleton.json"
    assert cli.main(["--emit-skeleton", str(sk)]) == 0
    assert cli.main(["--emit-skeleton", str(sk)]) == 2  # no overwrite
    data = json.loads(sk.read_text(encoding="utf-8"))
    assert data["stats"]["bootstrap"]["method"] is None and data["gates"]["win_rate"] is None
    # freezing the skeleton must be refused: nothing decided, nothing signed
    assert cli.main([str(sk), "--out", str(tmp_path / "f.json")]) == 2
    assert not (tmp_path / "f.json").exists()


def test_cli_requires_draft_and_out(tmp_path):
    with pytest.raises(SystemExit):
        cli.main([])


def test_spec_view_shape(tmp_path):
    view = load_frozen(_freeze(tmp_path))
    assert isinstance(view, SpecView)
    assert set(view.partitions) == {
        "development_selection",
        "development_confirmation",
        "holdout",
    }
    assert view.partitions["holdout"] == (date(2022, 1, 1), date(2025, 12, 31))
    assert view.exposed_windows == ((date(2026, 1, 1), date(2026, 7, 31)),)
    assert view.p3_criteria == {"synthetic": True}
    assert [c["id"] for c in view.exits_candidates or ()] == ["X1", "X2", "X3"]
    assert view.exits_selection is not None and view.exits_selection["score"] == "synthetic_score"
    assert len(view.spec_sha256) == 64
    with pytest.raises(AttributeError):
        view.has_run_decision = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        view.partitions["holdout"] = (date(2000, 1, 1), date(2000, 1, 2))  # type: ignore[index]
