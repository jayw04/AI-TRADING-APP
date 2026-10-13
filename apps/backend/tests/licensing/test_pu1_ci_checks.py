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

FIELD_TABLE = {
    "ast_enforced_market_data_names": ["market_value", "unrealized_pl", "current_price"],
    "kinds": {
        "position": {
            "fields": {
                "qty": {"class": "OWNER_RECORD"},
                "market_value": {"class": "MARKET_DATA"},
                "unrealized_pl": {"class": "MARKET_DATA"},
                "current_price": {"class": "MARKET_DATA"},
            }
        }
    },
}


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
        (tmp_path / "table.json").write_text(json.dumps(FIELD_TABLE), encoding="utf-8")
        base = {
            "hosts": [],
            "non_data_hosts": [],
            "mixed_hosts": [],
            "imports": [],
            "non_data_imports": [],
            "mixed_imports": [],
            "modules": [],
            "altdata_source_names": {},
            "broker_field_access": {"field_table": "table.json", "allowlist": []},
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


# --------------------------------------------------------------------------- mixed broker sources


def test_mixed_host_needs_a_field_table_registered_sources_and_the_mixed_label(
    source_check,
) -> None:
    body = 'U = "https://api.broker.example/v2/positions"\n'
    good = {
        "host": "broker.example",
        "classification": "MIXED",
        "field_classification": "table.json",
        "source_ids": ["alpaca_market_data"],
    }
    assert source_check({"src/a.py": body}, {"mixed_hosts": [good]}) == []
    missing_table = {**good, "field_classification": "nope.json"}
    assert any(
        "missing field table" in p
        for p in source_check({"src/a.py": body}, {"mixed_hosts": [missing_table]})
    )
    wrong_label = {**good, "classification": "NON_DATA"}
    assert any(
        "must have classification 'MIXED'" in p
        for p in source_check({"src/a.py": body}, {"mixed_hosts": [wrong_label]})
    )
    unregistered = {**good, "source_ids": ["ghost"]}
    assert any(
        "REGISTRY ROW MISSING" in p
        for p in source_check({"src/a.py": body}, {"mixed_hosts": [unregistered]})
    )


def test_real_broker_hosts_are_mixed_not_blanket_non_data() -> None:
    smap = json.loads((BACKEND / "ci" / "pu1_source_map.json").read_text(encoding="utf-8"))
    non_data = {e["host"] for e in smap["non_data_hosts"]}
    mixed = {e["host"]: e for e in smap["mixed_hosts"]}
    for host in ("api.alpaca.markets", "paper-api.alpaca.markets"):
        assert host not in non_data
        assert mixed[host]["classification"] == "MIXED"
        assert (REPO / mixed[host]["field_classification"]).is_file()
    assert {e["prefix"] for e in smap["mixed_imports"]} == {"alpaca.trading"}


# --------------------------------------------------------------------------- broker field access


def test_helper_names_match_the_script_and_the_module() -> None:
    from app.licensing import broker_fields

    mod = _load("check_pu1_registry_closure")
    assert mod.HELPER_NAMES == broker_fields.HELPER_NAMES


def test_unclassified_market_data_field_read_fails_the_build(source_check) -> None:
    body = "def f(p):\n    return p.market_value\n"
    problems = source_check({"src/a.py": body}, {})
    assert any("UNCLASSIFIED broker market-data field read in src/a.py" in p for p in problems)


@pytest.mark.parametrize(
    "body",
    [
        "def f(p):\n    return p.market_value\n",
        "def f(p):\n    return p['unrealized_pl']\n",
        "def f(p):\n    return p.get('current_price')\n",
        "def f(p):\n    return p.pop('market_value', None)\n",
    ],
    ids=["attribute", "subscript", "get", "pop"],
)
def test_every_access_form_is_detected(source_check, body) -> None:
    assert any("UNCLASSIFIED" in p for p in source_check({"src/a.py": body}, {}))


def test_calling_the_helper_satisfies_the_rule(source_check) -> None:
    via_name = (
        "from app.licensing.broker_fields import sources_of_fields\n"
        "def f(p):\n    sources_of_fields('position', ['market_value'])\n    return p.market_value\n"
    )
    assert source_check({"src/a.py": via_name}, {}) == []
    via_module = (
        "from app.licensing import broker_fields\n"
        "def f(p):\n    broker_fields.scope_of_fields('position', ['qty'])\n    return p.market_value\n"
    )
    assert source_check({"src/b.py": via_module}, {}) == []
    # an import with no call is NOT "going through the helper"
    imported_only = (
        "from app.licensing.broker_fields import sources_of_fields\n"
        "def f(p):\n    return p.market_value\n"
    )
    assert any("UNCLASSIFIED" in p for p in source_check({"src/c.py": imported_only}, {}))
    # a same-named local function is not the helper
    shadow = "def sources_of_fields(*a):\n    return a\ndef f(p):\n    sources_of_fields(1)\n    return p.market_value\n"
    assert any("UNCLASSIFIED" in p for p in source_check({"src/d.py": shadow}, {}))


def test_allowlist_needs_a_reason_names_its_fields_and_must_not_go_stale(source_check) -> None:
    body = "def f(p):\n    return p.market_value\n"
    ok = {"file": "src/a.py", "fields": ["market_value"], "reason": "order path, table only"}
    access = {"field_table": "table.json", "allowlist": [ok]}
    assert source_check({"src/a.py": body}, {"broker_field_access": access}) == []
    no_reason = {**ok, "reason": ""}
    assert any(
        "a reason is required" in p
        for p in source_check(
            {"src/a.py": body},
            {"broker_field_access": {"field_table": "table.json", "allowlist": [no_reason]}},
        )
    )
    unnamed = {**ok, "fields": ["unrealized_pl"]}
    assert any(
        "does not name" in p
        for p in source_check(
            {"src/a.py": body},
            {"broker_field_access": {"field_table": "table.json", "allowlist": [unnamed]}},
        )
    )
    stale = {"file": "src/gone.py", "fields": ["market_value"], "reason": "r"}
    assert any(
        "stale" in p
        for p in source_check(
            {"src/a.py": body},
            {
                "broker_field_access": {
                    "field_table": "table.json",
                    "allowlist": [ok, stale],
                }
            },
        )
    )
    no_longer = {"file": "src/b.py", "fields": ["market_value"], "reason": "r"}
    assert any(
        "no longer reads" in p
        for p in source_check(
            {"src/a.py": body, "src/b.py": "def g():\n    return 1\n"},
            {
                "broker_field_access": {
                    "field_table": "table.json",
                    "allowlist": [ok, no_longer],
                }
            },
        )
    )


def test_field_access_limits_are_documented_and_stay_undetected(source_check) -> None:
    """The AST rule does NOT see these. If this test starts failing the rule got stronger: update
    the module docstring and the ADR, then move the case to the detected list above."""
    dynamic_getattr = "def f(p):\n    return getattr(p, 'market_value')\n"
    built_key = "def f(p):\n    return p['market_' + 'value']\n"
    kwarg = "def f(p):\n    return make(market_value=1)\n"
    dict_literal = "def f():\n    return {'market_value': 1}\n"
    unenforced_name = "def f(a):\n    return a['equity']\n"
    for body in (dynamic_getattr, built_key, kwarg, dict_literal, unenforced_name):
        assert source_check({"src/a.py": body}, {}) == [], body


def test_field_table_must_agree_with_the_enforced_names(source_check, tmp_path) -> None:
    bad = {
        "ast_enforced_market_data_names": ["market_value"],
        "kinds": {"position": {"fields": {"market_value": {"class": "OWNER_RECORD"}}}},
    }
    source_check({}, {})  # creates the tmp tree
    (tmp_path / "table.json").write_text(json.dumps(bad), encoding="utf-8")
    mod = sys.modules["check_pu1_registry_closure"]
    problems = mod._check_broker_field_access({"field_table": "table.json", "allowlist": []})
    assert any("is OWNER_RECORD" in p for p in problems)
    unclassified = {"ast_enforced_market_data_names": ["ghost"], "kinds": {}}
    (tmp_path / "table.json").write_text(json.dumps(unclassified), encoding="utf-8")
    problems = mod._check_broker_field_access({"field_table": "table.json", "allowlist": []})
    assert any("not classified MARKET_DATA anywhere" in p for p in problems)


def test_real_tree_field_access_is_closed_and_every_allowlist_entry_is_reasoned() -> None:
    smap = json.loads((BACKEND / "ci" / "pu1_source_map.json").read_text(encoding="utf-8"))
    allow = smap["broker_field_access"]["allowlist"]
    assert allow and all(e["reason"].strip() and e["disposition"] for e in allow)
    # order-path / risk / broker modules are classified by table only, never wired
    for e in allow:
        if "/risk/" in e["file"] or "/brokers/" in e["file"]:
            assert e["disposition"] == "order_path_table_only", e["file"]
    assert _load("check_pu1_registry_closure").check() == []


# --------------------------------------------------------------------------- export bypass routes
#
# Each case below is either DETECTED (it must be reported UNREGISTERED) or NOT COVERED (documented
# in the script docstring and ADR 0057; the test asserts it is NOT detected, so a silent change in
# coverage fails the build and forces the documentation to be updated).

DETECTED_BYPASSES = {
    "variable_held_method": "def f(p):\n    w = p.write_text\n    w('x')\n",
    "partial_of_method": (
        "import functools\ndef f(df):\n    return functools.partial(df.to_csv, 'a.csv')\n"
    ),
    "getattr_literal": "def f(p):\n    getattr(p, 'write_text')('x')\n",
    "io_open": "import io\ndef f(p):\n    io.open(p, 'w').write('x')\n",
    "io_open_alias_import": ("from io import open as op\ndef f(p):\n    op(p, 'w').write('x')\n"),
    "io_open_alias_assign": "import io\nopener = io.open\ndef f(p):\n    opener(p, 'a')\n",
    "gzip_open": "import gzip\ndef f(p):\n    gzip.open(p, 'wt').write('x')\n",
    "open_dynamic_mode": "def f(p, m):\n    open(p, m).write('x')\n",
    "path_open_keyword_mode": "def f(p):\n    p.open(mode='w')\n",
    "subprocess_redirect": (
        "import subprocess\ndef f():\n    subprocess.run('echo x > report.txt', shell=True)\n"
    ),
    "os_system_redirect": "import os\ndef f():\n    os.system('cat a >> b.txt')\n",
    "subprocess_tee": (
        "import subprocess\ndef f():\n    subprocess.run(['sh', '-c', 'cmd | tee out.txt'])\n"
    ),
    "third_party_client_s3": ("def f(c):\n    c.put_object(Bucket='b', Key='k', Body=b'x')\n"),
    "third_party_client_getattr": "def f(c):\n    getattr(c, 'upload_file')('a', 'b', 'c')\n",
    "third_party_mail": "def f(s):\n    s.sendmail('a', 'b', 'x')\n",
    "importlib_literal": (
        "import importlib\ndef f():\n    return importlib.import_module('pptx')\n"
    ),
    "dunder_import_literal": "def f():\n    return __import__('matplotlib.pyplot')\n",
    "string_concat_path": "def f():\n    return 'out' + '/share/' + 'deck.pdf'\n",
    "fstring_constant_path": "def f():\n    return f'out/publish/deck.pdf'\n",
    "os_path_join_segment": ("import os\ndef f(n):\n    return os.path.join('out', 'export', n)\n"),
    "path_div_segment": (
        "from pathlib import Path\ndef f(n):\n    return Path('out') / 'presentations' / n\n"
    ),
    "joinpath_segment": "def f(p):\n    return p.joinpath('shared')\n",
}

UNCOVERED_BYPASSES = {
    # names that are not literals
    "getattr_variable_name": "def f(p, n):\n    getattr(p, n)('x')\n",
    "getattr_built_name": "def f(p):\n    getattr(p, 'write_' + 'text')('x')\n",
    "importlib_variable_name": (
        "import importlib\ndef f(n):\n    return importlib.import_module(n)\n"
    ),
    "path_from_variables": "def f(root, seg, n):\n    return root + seg + n\n",
    "subprocess_dynamic_command": (
        "import subprocess\ndef f(cmd):\n    subprocess.run(cmd, shell=True)\n"
    ),
    "writer_from_factory": "def f(make):\n    w = make()\n    w('x')\n",
    # a third-party client under a method name outside the egress list, and HTTP bodies
    "third_party_client_other_method": "def f(c):\n    c.store_blob('k', b'x')\n",
    "http_post_body": (
        "import requests\ndef f(b):\n    requests.post('https://x.example/u', data=b)\n"
    ),
    # reflection / code generation
    "exec_string": "def f():\n    exec(\"open('a','w').write('x')\")\n",
    # print to an already-open file object (the open() that created it is a separate, detected site)
    "print_to_file_object": "def f(fh):\n    print('x', file=fh)\n",
}


@pytest.mark.parametrize("body", list(DETECTED_BYPASSES.values()), ids=list(DETECTED_BYPASSES))
def test_bypass_route_is_detected(export_check, body) -> None:
    problems = export_check({"src/a.py": body}, entries=[])
    assert any("UNREGISTERED" in p for p in problems), body


@pytest.mark.parametrize("body", list(UNCOVERED_BYPASSES.values()), ids=list(UNCOVERED_BYPASSES))
def test_documented_uncovered_bypass_stays_undetected(export_check, body) -> None:
    """NOT PROVEN by the AST check. If this fails, coverage changed: update the script docstring
    and ADR 0057 (and move the case to DETECTED_BYPASSES) rather than deleting the test."""
    assert export_check({"src/a.py": body}, entries=[]) == [], body


def test_shell_redirection_outside_python_and_non_python_scripts_are_out_of_scope(
    export_check,
) -> None:
    """``python report.py > out.md`` and shell/PowerShell wrappers never reach the AST check; the
    only controls are the scope sidecar and the footer on the report itself."""
    assert export_check({"src/a.py": "def main():\n    print('report body')\n"}, entries=[]) == []


def test_filename_with_an_a_is_not_an_append_mode(export_check) -> None:
    # Path.open("data.txt") has a file name, not a mode, at position 0
    assert export_check({"src/a.py": "def f(p):\n    return p.open('data.txt')\n"}, []) == []


def test_documented_limits_appear_in_the_script_docstring_and_the_adr() -> None:
    doc = (BACKEND / "scripts" / "check_pu1_export_path_closure.py").read_text(encoding="utf-8")
    adr = (REPO / "docs" / "adr" / "0057-pu1-personal-use-presentation-gate.md").read_text(
        encoding="utf-8"
    )
    for needle in ("NOT PROVEN BY THIS CHECK", "getattr", "importlib", "subprocess"):
        assert needle in doc, needle
    for needle in ("does not prove", "getattr", "subprocess", "third-party"):
        assert needle in adr, needle
