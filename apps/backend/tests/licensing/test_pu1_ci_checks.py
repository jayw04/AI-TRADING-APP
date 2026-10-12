"""PU-1 CI checks: export-path closure and licence-registry closure behave as specified.

The scripts are run against throw-away trees (monkeypatched REPO/registry paths) so each rule is
shown to FAIL on a violation, not merely to pass on the real tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- export-path closure


@pytest.fixture
def export_check(tmp_path, monkeypatch):
    mod = _load("check_pu1_export_path_closure")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "REGISTRY", tmp_path / "reg.json")
    monkeypatch.setattr(mod, "SCAN_ROOTS", ("src",))
    (tmp_path / "src").mkdir()

    def setup(files: dict[str, str], entries: list[dict], frontend=None) -> list[str]:
        for rel, body in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        (tmp_path / "reg.json").write_text(
            json.dumps({"schema": 1, "entries": entries, "frontend_entries": frontend or []}),
            encoding="utf-8",
        )
        return mod.check()

    return setup


def _internal(file: str, funcs="*") -> dict:
    return {"file": file, "functions": funcs, "classification": "INTERNAL_ONLY", "reason": "r"}


def _gated(file: str, funcs) -> dict:
    return {"file": file, "functions": funcs, "classification": "GATED", "reason": "r"}


def test_real_tree_is_closed() -> None:
    mod = _load("check_pu1_export_path_closure")
    assert mod.check() == []


def test_unregistered_writer_fails(export_check) -> None:
    problems = export_check({"src/a.py": "def out(p):\n    p.write_text('x')\n"}, entries=[])
    assert any("UNREGISTERED" in p and "a.py::out" in p for p in problems)


@pytest.mark.parametrize(
    "body",
    [
        "def f(df):\n    df.to_csv('x.csv')\n",
        "def f():\n    open('x', 'w').write('1')\n",
        "def f(p):\n    p.open('ab')\n",
        "import json\ndef f(o, fh):\n    json.dump(o, fh)\n",
        "import shutil\ndef f(a, b):\n    shutil.copyfile(a, b)\n",
        "def f(fig):\n    fig.savefig('a.png')\n",
        "def f():\n    return 'out/outbound/deck.pdf'\n",  # outbound-named path, no writer
        "import matplotlib.pyplot as plt\n",  # rendering library
    ],
    ids=[
        "to_csv",
        "open_w",
        "path_open",
        "json_dump",
        "shutil",
        "savefig",
        "outbound",
        "render_lib",
    ],
)
def test_every_entry_kind_is_detected(export_check, body) -> None:
    problems = export_check({"src/a.py": body}, entries=[])
    assert any("UNREGISTERED" in p for p in problems), body


def test_reading_and_console_output_are_not_entries(export_check) -> None:
    body = (
        "def f(p):\n    print('hi')\n    return open(p).read() + p.read_text()\n"
        "def g(p):\n    return open(p, 'r').read()\n"
    )
    assert export_check({"src/a.py": body}, entries=[]) == []


def test_internal_only_writer_passes_but_outbound_target_does_not(export_check) -> None:
    ok = export_check(
        {"src/a.py": "def out(p):\n    p.write_text('x')\n"}, entries=[_internal("src/a.py")]
    )
    assert ok == []
    bad = export_check(
        {
            "src/a.py": "def out(p):\n    (p / 'share' / 'deck.html').write_text('x')\n"
            "    return 'x/share/y.html'\n"
        },
        entries=[_internal("src/a.py")],
    )
    assert any("INTERNAL_ONLY but carries" in p for p in bad)


def test_gated_entry_must_call_the_gate_before_writing(export_check) -> None:
    ungated = "def out(p):\n    p.write_text('x')\n"
    assert any(
        "calls no gate API" in p
        for p in export_check({"src/a.py": ungated}, entries=[_gated("src/a.py", ["out"])])
    )
    late = "def out(p):\n    p.write_text('x')\n    stamp('x', sources=[])\n"
    assert any(
        "before the first gate call" in p
        for p in export_check({"src/a.py": late}, entries=[_gated("src/a.py", ["out"])])
    )
    good = "def out(p):\n    stamp('x', sources=[])\n    p.write_text('x')\n"
    assert export_check({"src/a.py": good}, entries=[_gated("src/a.py", ["out"])]) == []


def test_stale_and_duplicate_registry_entries_fail(export_check) -> None:
    body = "def out(p):\n    p.write_text('x')\n"
    stale = export_check(
        {"src/a.py": body}, entries=[_internal("src/a.py"), _internal("src/gone.py")]
    )
    assert any("stale" in p for p in stale)
    undefined = export_check({"src/a.py": body}, entries=[_internal("src/a.py", ["out", "nope"])])
    assert any("'nope' is not defined" in p for p in undefined)
    dup = export_check({"src/a.py": body}, entries=[_internal("src/a.py"), _internal("src/a.py")])
    assert any("duplicate" in p for p in dup)
    no_reason = export_check(
        {"src/a.py": body},
        entries=[{"file": "src/a.py", "functions": "*", "classification": "INTERNAL_ONLY"}],
    )
    assert any("reason" in p for p in no_reason)


def test_frontend_print_trigger_must_be_registered_and_gated(export_check) -> None:
    page = "src_fe/page.tsx"
    files = {page: "const x = () => window.print();\n"}
    # FRONTEND_ROOT is repo-relative; point it at the throw-away tree
    mod = sys.modules["check_pu1_export_path_closure"]
    mod.FRONTEND_ROOT = "src_fe"
    unregistered = export_check(files, entries=[])
    assert any("UNREGISTERED frontend" in p for p in unregistered)
    entry = {"file": page, "must_contain": ["COMMERCIAL_OK"], "reason": "r"}
    assert any("COMMERCIAL_OK" in p for p in export_check(files, [], frontend=[entry]))
    files[page] += "// COMMERCIAL_OK gate\n"
    assert export_check(files, [], frontend=[entry]) == []


def test_licensing_seam_export_functions_gate_before_writing() -> None:
    """The seam itself is verified, not exempted: export_* must reference the gate first."""
    mod = _load("check_pu1_export_path_closure")
    import ast

    tree = ast.parse((BACKEND / "app" / "licensing" / "output.py").read_text(encoding="utf-8"))
    infos = mod.analyse(tree)
    for name in ("export_for_external_use", "export_file_for_external_use"):
        fi = infos[name]
        assert fi.seam_lines, name
        if fi.first_write is not None:
            assert min(fi.seam_lines) < fi.first_write


# --------------------------------------------------------------------------- registry closure


@pytest.fixture
def source_check(tmp_path, monkeypatch):
    mod = _load("check_pu1_registry_closure")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "SOURCE_MAP", tmp_path / "map.json")
    monkeypatch.setattr(mod, "REGISTRY_JSON", tmp_path / "registry.json")
    monkeypatch.setattr(mod, "ALTDATA_REGISTRY", tmp_path / "altdata.py")
    monkeypatch.setattr(mod, "SCAN_ROOTS", ("src",))
    (tmp_path / "src").mkdir()

    def setup(
        files: dict[str, str], smap: dict, registered=("alpaca_market_data",), altdata=""
    ) -> list[str]:
        for rel, body in files.items():
            (tmp_path / rel).write_text(body, encoding="utf-8")
        (tmp_path / "altdata.py").write_text(altdata, encoding="utf-8")
        (tmp_path / "registry.json").write_text(
            json.dumps({"entries": [{"source_id": s} for s in registered]}), encoding="utf-8"
        )
        base = {
            "hosts": [],
            "non_data_hosts": [],
            "imports": [],
            "non_data_imports": [],
            "modules": [],
            "altdata_source_names": {},
        }
        (tmp_path / "map.json").write_text(json.dumps({**base, **smap}), encoding="utf-8")
        return mod.check()

    return setup


def test_real_source_map_is_closed_against_the_real_registry() -> None:
    assert _load("check_pu1_registry_closure").check() == []


def test_new_data_host_without_mapping_fails_the_build(source_check) -> None:
    body = 'BASE = "https://api.newvendor.example/v1"\n'
    problems = source_check({"src/ingest.py": body}, {})
    assert any("UNMAPPED data host 'api.newvendor.example'" in p for p in problems)


def test_mapped_host_whose_source_has_no_registry_row_fails(source_check) -> None:
    body = 'BASE = "https://api.newvendor.example/v1"\n'
    smap = {"hosts": [{"host": "newvendor.example", "source_id": "newvendor"}]}
    problems = source_check({"src/ingest.py": body}, smap)
    assert any("REGISTRY ROW MISSING" in p and "newvendor" in p for p in problems)
    assert source_check({"src/ingest.py": body}, smap, registered=("newvendor",)) == []


def test_unmapped_alpaca_sdk_namespace_fails(source_check) -> None:
    body = "from alpaca.data.historical import StockHistoricalDataClient\n"
    assert any("UNMAPPED vendor SDK import" in p for p in source_check({"src/m.py": body}, {}))
    smap = {"imports": [{"prefix": "alpaca.data", "source_id": "alpaca_market_data"}]}
    assert source_check({"src/m.py": body}, smap) == []
    other = "from alpaca.newapi import X\n"
    assert any("UNMAPPED vendor SDK import" in p for p in source_check({"src/m.py": other}, smap))


def test_new_altdata_source_name_must_be_mapped(source_check) -> None:
    alt = 'X = DataSource(source_name="newfeed", provider="p")\n'
    problems = source_check({}, {}, altdata=alt)
    assert any("UNMAPPED altdata source_name 'newfeed'" in p for p in problems)
    ok = source_check({}, {"altdata_source_names": {"newfeed": "alpaca_market_data"}}, altdata=alt)
    assert ok == []


def test_non_data_host_requires_a_reason(source_check) -> None:
    body = 'U = "https://infra.example/x"\n'
    smap = {"non_data_hosts": [{"host": "infra.example"}]}
    assert any("without a reason" in p for p in source_check({"src/a.py": body}, smap))


# --------------------------------------------------------------------------- the gate script


def test_pu1_gate_script_and_ci_wiring_exist() -> None:
    assert (BACKEND / "scripts" / "check_pu1_presentation_gate.sh").is_file()
    ci_path = REPO / ".github" / "workflows" / "ci.yml"
    if not ci_path.is_file():  # an image/sdist without the repo root
        pytest.skip("repository root not present")
    ci = ci_path.read_text(encoding="utf-8")
    for needle in (
        "check_pu1_presentation_gate.sh",
        "check_pu1_export_path_closure.py",
        "check_pu1_registry_closure.py",
        "pu1_required_tests.json",
    ):
        assert needle in ci, needle
