"""PU-1 Personal-Use Data Presentation Rule: registry, taint, gate, marking, export paths."""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app.licensing as lic
from app.licensing import registry as reg_mod
from app.licensing.scopes import LicenseScope, Scoped, combine_scopes, derive

REASON = "PU1_PERSONAL_SCOPE_BLOCKED"
FOOTER = "PERSONAL USE ONLY — not for presentation (PU-1)"

_OK_REGISTRY = {
    "schema_version": 1,
    "entries": [
        {
            "source_id": "alpaca_sip",
            "license_scope": "PERSONAL",
            "basis": {"document": "Alpaca terms", "date": "2026-10-12"},
            "owner_ruling_ref": "PU-1",
        },
        {
            "source_id": "vendor_ok",
            "license_scope": "COMMERCIAL_OK",
            "basis": {"document": "written vendor permission", "date": "2026-11-01"},
            "owner_ruling_ref": "minute 2026-11-05",
        },
        {
            "source_id": "vendor_unknown",
            "license_scope": "UNKNOWN",
            "basis": {"document": "contract not read", "date": None},
            "owner_ruling_ref": "none",
        },
    ],
}


@pytest.fixture
def commercial_registry(tmp_path, monkeypatch):
    """Swap in a registry that contains one COMMERCIAL_OK source (the in-repo one has none)."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_OK_REGISTRY), encoding="utf-8")
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", path)
    monkeypatch.setattr(reg_mod, "REGISTRY_SHA256", reg_mod.canonical_sha256(_OK_REGISTRY))
    return path


# --------------------------------------------------------------------------- registry + scopes


def test_in_repo_registry_is_hash_pinned_and_classifies_sources() -> None:
    reg = reg_mod.load_registry()
    assert reg.sha256 == reg_mod.REGISTRY_SHA256
    assert reg.scope_of_source("alpaca_sip") is LicenseScope.PERSONAL
    for src in ("sharadar", "fmp", "quiver"):
        assert reg.scope_of_source(src) is LicenseScope.UNKNOWN
    # nothing in the shipped registry is presentable
    assert all(e.license_scope.blocks_presentation for e in reg.entries.values())


def test_unregistered_source_is_unknown_and_blocked() -> None:
    assert reg_mod.load_registry().scope_of_source("some_new_vendor") is LicenseScope.UNKNOWN
    with pytest.raises(lic.PersonalScopeBlocked) as ei:
        lic.assert_presentable(sources=["some_new_vendor"])
    assert ei.value.reason_code == REASON
    assert ei.value.scope is LicenseScope.UNKNOWN


def test_scope_order_and_combination() -> None:
    assert LicenseScope.COMMERCIAL_OK < LicenseScope.UNKNOWN <= LicenseScope.PERSONAL
    assert combine_scopes("COMMERCIAL_OK", "UNKNOWN") is LicenseScope.UNKNOWN
    assert combine_scopes("UNKNOWN", "PERSONAL") is LicenseScope.PERSONAL
    assert combine_scopes("COMMERCIAL_OK", "COMMERCIAL_OK") is LicenseScope.COMMERCIAL_OK
    assert combine_scopes() is LicenseScope.UNKNOWN
    assert combine_scopes("garbage") is LicenseScope.UNKNOWN
    assert combine_scopes(None) is LicenseScope.UNKNOWN


def test_alpaca_feed_mapping() -> None:
    assert lic.alpaca_feed_source_id("SIP") == "alpaca_sip"
    assert reg_mod.load_registry().scope_of_source(lic.alpaca_feed_source_id("iex")) is (
        LicenseScope.UNKNOWN
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.write_text("{not json", encoding="utf-8"),
        lambda p: p.write_text("[]", encoding="utf-8"),
        lambda p: p.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8"),
        lambda p: p.unlink(),
    ],
    ids=["bad-json", "not-object", "no-entries", "missing-file"],
)
def test_malformed_or_unreadable_registry_fails_closed(commercial_registry, mutate) -> None:
    mutate(commercial_registry)
    with pytest.raises(reg_mod.LicenseRegistryError):
        reg_mod.load_registry()
    with pytest.raises(lic.PersonalScopeBlocked) as ei:
        lic.assert_presentable(sources=["vendor_ok"])
    assert ei.value.reason_code == REASON
    # marking is conservative too: even a "commercial" source is stamped when the registry is dead
    assert FOOTER in lic.stamp("body", sources=["vendor_ok"])


def test_tampered_registry_fails_pin(commercial_registry) -> None:
    doc = json.loads(commercial_registry.read_text(encoding="utf-8"))
    doc["entries"][0]["license_scope"] = "COMMERCIAL_OK"  # flip PERSONAL -> OK without re-pinning
    commercial_registry.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(reg_mod.LicenseRegistryError, match="pinned"):
        reg_mod.load_registry()
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok"])


@pytest.mark.parametrize(
    "entry",
    [
        {
            "source_id": "x",
            "license_scope": "MAYBE",
            "basis": {"document": "d", "date": None},
            "owner_ruling_ref": "r",
        },
        {
            "source_id": "x",
            "license_scope": "COMMERCIAL_OK",
            "basis": {"document": "d", "date": None},
            "owner_ruling_ref": "r",
        },
        {"source_id": "x", "license_scope": "PERSONAL", "basis": {"document": "d", "date": None}},
    ],
    ids=["bad-scope", "commercial-without-dated-permission", "no-ruling-ref"],
)
def test_schema_violations_rejected(entry) -> None:
    text = json.dumps({"schema_version": 1, "entries": [entry]})
    with pytest.raises(reg_mod.LicenseRegistryError):
        reg_mod.parse_registry_text(text, expected_sha256=None)


# --------------------------------------------------------------------------- gate


@pytest.mark.parametrize("source", ["alpaca_sip", "sharadar", "never_heard_of_it"])
def test_gate_blocks_personal_and_unknown_identically(source) -> None:
    with pytest.raises(lic.PersonalScopeBlocked) as ei:
        lic.assert_presentable(sources=[source], destination="deck")
    assert ei.value.reason_code == REASON
    assert REASON in str(ei.value)


def test_gate_blocks_empty_lineage() -> None:
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=[])


def test_commercial_ok_only_artifact_passes(commercial_registry) -> None:
    assert lic.assert_presentable(sources=["vendor_ok"]) is LicenseScope.COMMERCIAL_OK
    assert lic.stamp("body", sources=["vendor_ok"]) == "body"


def test_one_personal_input_taints_a_commercial_artifact(commercial_registry) -> None:
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok", "alpaca_sip"])
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok", "vendor_unknown"])


def test_producer_cannot_loosen_scope_by_declaration(commercial_registry) -> None:
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["alpaca_sip"], declared_scope="COMMERCIAL_OK")
    # and may only tighten
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok"], declared_scope="PERSONAL")


# --------------------------------------------------------------------------- taint propagation


def test_taint_propagates_through_join() -> None:
    bars = Scoped.of(pd.DataFrame({"sym": ["A", "B"], "close": [1.0, 2.0]}), ["alpaca_sip"])
    fundamentals = Scoped.of(pd.DataFrame({"sym": ["A", "B"], "eps": [3.0, 4.0]}), ["sharadar"])
    joined = derive(lambda a, b: a.merge(b, on="sym"), bars, fundamentals)
    assert joined.sources == {"alpaca_sip", "sharadar"}
    assert reg_mod.load_registry().scope_of(joined.sources) is LicenseScope.PERSONAL


def test_taint_propagates_through_resample() -> None:
    idx = pd.date_range("2026-01-02 09:30", periods=120, freq="min")
    minute = Scoped.of(pd.Series(np.arange(120.0), index=idx), ["alpaca_sip"])
    hourly = derive(lambda s: s.resample("1h").last(), minute)
    assert len(hourly.value) >= 2
    assert hourly.sources == {"alpaca_sip"}
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=hourly.sources)


def test_taint_propagates_through_real_backtest() -> None:
    from app.research.factor_lab.reproduction import backtest_cross_asset_sleeve

    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2023-01-02", periods=400)
    panel = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, (len(idx), 3)), axis=0)),
        index=idx,
        columns=["SPY", "TLT", "GLD"],
    )
    prices = Scoped.of(panel, ["alpaca_sip"])
    returns = derive(backtest_cross_asset_sleeve, prices)
    assert isinstance(returns.value, pd.Series) and len(returns.value) == len(idx)
    assert returns.sources == {"alpaca_sip"}
    stats = derive(lambda r: float(r.mean() / (r.std() or 1.0)), returns)  # a "Sharpe"
    assert stats.sources == {"alpaca_sip"}
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=stats.sources, destination="deck")


# --------------------------------------------------------------------------- envelope tagging


def test_tag_envelope_is_additive_and_ordered() -> None:
    env = {"run_id": "r1", "artifact_sha256": "ab" * 32, "rows": 3}
    tagged = lic.tag_envelope(env, ["Alpaca_SIP"])
    assert env == {"run_id": "r1", "artifact_sha256": "ab" * 32, "rows": 3}  # input untouched
    keys = list(tagged)
    assert keys.index("license_scope") == keys.index("artifact_sha256") + 1
    assert tagged["license_scope"] == "PERSONAL"
    assert tagged["license_sources"] == ["alpaca_sip"]
    assert tagged["rows"] == 3 and tagged["run_id"] == "r1"


def test_envelope_scope_untagged_and_forged() -> None:
    assert lic.envelope_scope({"artifact_sha256": "x"}) is LicenseScope.UNKNOWN
    forged = {"license_scope": "COMMERCIAL_OK", "license_sources": ["alpaca_sip"]}
    assert lic.envelope_scope(forged) is LicenseScope.PERSONAL


def test_sidecar_binds_digest_and_missing_sidecar_is_unknown(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert lic.scope_of_file(f) is LicenseScope.UNKNOWN  # no sidecar
    lic.write_sidecar(f, ["alpaca_sip"])
    assert lic.scope_of_file(f) is LicenseScope.PERSONAL
    f.write_text("tampered", encoding="utf-8")  # digest no longer matches
    assert lic.scope_of_file(f) is LicenseScope.UNKNOWN


# --------------------------------------------------------------------------- footer


def test_footer_text_is_exact_and_present_on_every_non_ok_render() -> None:
    assert lic.PERSONAL_FOOTER == FOOTER
    for fmt in ("markdown", "text", "html"):
        for scope in (LicenseScope.PERSONAL, LicenseScope.UNKNOWN):
            block = lic.footer_for(scope, fmt)
            assert block is not None and FOOTER in block
        assert lic.footer_for(LicenseScope.COMMERCIAL_OK, fmt) is None
    out = lic.stamp("# t", sources=["alpaca_sip"])
    assert out.rstrip().endswith(f"**{FOOTER}**")
    assert lic.stamp(out, sources=["alpaca_sip"]) == out  # idempotent
    assert FOOTER in lic.stamp("<p>x</p>", sources=["sharadar"], fmt="html")


_SUPPRESS = re.compile(
    r"suppress|hide|skip|override|force|bypass|disable|no_footer|footer|allow|ignore|unsafe|quiet",
    re.I,
)


def test_no_public_callable_has_a_suppression_or_override_parameter() -> None:
    offenders = []
    for name in lic.__all__:
        obj = getattr(lic, name)
        if not callable(obj) or inspect.isclass(obj):
            continue
        for p in inspect.signature(obj).parameters:
            if _SUPPRESS.search(p):
                offenders.append(f"{name}({p})")
    for cls in (lic.PersonalScopeBlocked,):
        for p in inspect.signature(cls.__init__).parameters:
            if _SUPPRESS.search(p):
                offenders.append(f"{cls.__name__}({p})")
    assert offenders == []


def test_footer_cannot_be_suppressed_by_env_or_registry_swap(monkeypatch) -> None:
    for var in ("PU1_SUPPRESS_FOOTER", "PU1_OVERRIDE", "WORKBENCH_ALLOW_PERSONAL_EXPORT"):
        monkeypatch.setenv(var, "1")
    assert FOOTER in lic.stamp("x", sources=["alpaca_sip"])
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["alpaca_sip"])


# --------------------------------------------------------------------------- export seam


def test_export_for_external_use_blocks_personal_and_writes_nothing(tmp_path) -> None:
    dest = tmp_path / "outbound" / "deck.html"
    for src in (["alpaca_sip"], ["sharadar"], ["unregistered"], []):
        with pytest.raises(lic.PersonalScopeBlocked) as ei:
            lic.export_for_external_use(dest, "<html/>", sources=src, destination="deck")
        assert ei.value.reason_code == REASON
    assert not dest.exists() and not dest.parent.exists()


def test_export_for_external_use_allows_commercial_ok(tmp_path, commercial_registry) -> None:
    dest = tmp_path / "outbound" / "deck.html"
    lic.export_for_external_use(dest, "<html>ok</html>", sources=["vendor_ok"])
    assert dest.read_text(encoding="utf-8") == "<html>ok</html>"  # no footer: it is COMMERCIAL_OK
    assert lic.scope_of_file(dest) is LicenseScope.COMMERCIAL_OK
    copy = tmp_path / "share" / "deck.html"
    lic.export_file_for_external_use(dest, copy)
    assert copy.exists()


def test_export_file_blocks_personal_unknown_and_unlabelled_files(tmp_path) -> None:
    personal = tmp_path / "p.md"
    lic.write_internal_report(personal, "# r", sources=["alpaca_sip"])
    unknown = tmp_path / "u.md"
    lic.write_internal_report(unknown, "# r", sources=["sharadar"])
    unlabelled = tmp_path / "n.md"
    unlabelled.write_text("# r", encoding="utf-8")
    for f in (personal, unknown, unlabelled):
        with pytest.raises(lic.PersonalScopeBlocked) as ei:
            lic.export_file_for_external_use(f, tmp_path / "share" / f.name)
        assert ei.value.reason_code == REASON
    assert not (tmp_path / "share").exists()


def test_write_internal_report_stamps_and_tags(tmp_path) -> None:
    f = tmp_path / "r.md"
    lic.write_internal_report(f, "# r", sources=["alpaca_sip"])
    assert FOOTER in f.read_text(encoding="utf-8")
    side = json.loads((tmp_path / "r.md.license.json").read_text(encoding="utf-8"))
    assert side["license_scope"] == "PERSONAL"


# --------------------------------------------------------------------------- commercial-safe path


def test_commercial_safe_omits_rather_than_substitutes(commercial_registry) -> None:
    calls: list[tuple[str, ...]] = []

    def build(sources: tuple[str, ...]) -> str:
        calls.append(sources)
        return "SECTION " + ",".join(sources)

    omitted = lic.commercial_safe_section(
        "Momentum backtest",
        candidate_source_sets=[["alpaca_sip"], ["vendor_unknown"]],
        build=build,
    )
    assert calls == []  # the builder never saw a personal/unknown source set
    assert "ANALYSIS OMITTED" in omitted and "Momentum backtest" in omitted
    assert omitted == lic.omission_notice("Momentum backtest")
    assert not re.search(r"\d", omitted.replace("PU-1", ""))  # no number leaks into the notice

    built = lic.commercial_safe_section(
        "Momentum backtest",
        candidate_source_sets=[["alpaca_sip"], ["vendor_ok"]],
        build=build,
    )
    assert built == "SECTION vendor_ok" and calls == [("vendor_ok",)]


def test_commercial_safe_with_dead_registry_omits(commercial_registry) -> None:
    commercial_registry.write_text("garbage", encoding="utf-8")
    out = lic.commercial_safe_section(
        "X", candidate_source_sets=[["vendor_ok"]], build=lambda s: "SHOULD NOT BUILD"
    )
    assert out == lic.omission_notice("X")


# --------------------------------------------------------------------------- wired report paths


def test_research_dashboard_render_and_write_are_marked(tmp_path) -> None:
    from app.research.dashboard import render_dashboard, write_dashboard
    from app.research.registry import DatasetRecord, ResearchStore

    store = ResearchStore(db_path=str(tmp_path / "r.duckdb"))
    try:
        store.record_dataset(DatasetRecord(dataset_id="d1", provider="alpaca_sip", version="1"))
        md = render_dashboard(store)
        assert md.rstrip().endswith(f"**{FOOTER}**")
        out = write_dashboard(store, str(tmp_path / "out" / "dash.md"))
        assert FOOTER in Path(out).read_text(encoding="utf-8")
        assert lic.scope_of_file(Path(out)) is LicenseScope.PERSONAL
        with pytest.raises(lic.PersonalScopeBlocked):
            lic.export_file_for_external_use(Path(out), tmp_path / "share" / "dash.md")
    finally:
        store.close()


def test_research_dashboard_with_no_datasets_is_unknown_and_marked(tmp_path) -> None:
    from app.research.dashboard import render_dashboard
    from app.research.registry import ResearchStore

    store = ResearchStore(db_path=str(tmp_path / "r.duckdb"))
    try:
        assert FOOTER in render_dashboard(store)
    finally:
        store.close()


def _load_script(name: str, rel: str):
    root = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(name, root / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_morning_opportunities_report_is_marked(tmp_path, monkeypatch, capsys) -> None:
    mod = _load_script("pu1_morning_opps", "scripts/reports/morning_opportunities.py")
    record = {
        "asof": "2026-10-12",
        "funnel": {"gappers_in": 1, "candidate_count": 1},
        "candidates": [{"symbol": "ABC", "gap_pct": 5.0}],
        "stale": False,
    }
    (tmp_path / "premarket_scan_2026-10-12.json").write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["morning_opportunities.py", "--evidence-dir", str(tmp_path)])
    mod.main()
    out = capsys.readouterr().out
    assert "Morning Opportunities" in out and FOOTER in out


async def test_evidence_summary_declares_personal_scope(client) -> None:
    resp = await client.get("/api/v1/evidence/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["license_scope"] == "PERSONAL"
    assert "alpaca_sip" in body["license_sources"]
    assert body["license_footer"] == FOOTER
