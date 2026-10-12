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
            "source_id": "alpaca_market_data",
            "license_scope": "PERSONAL",
            "basis": {"document": "Alpaca terms", "date": "2026-10-12"},
            "owner_ruling_ref": "PU-1",
        },
        {
            "source_id": "vendor_ok",
            "license_scope": "COMMERCIAL_OK",
            "basis": {
                "document": "written vendor permission",
                "date": "2026-11-01",
                "documents": [{"name": "vendor licence", "sha256": "ab" * 32}],
            },
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
    assert reg.scope_of_source("alpaca_market_data") is LicenseScope.PERSONAL
    for src in ("sharadar", "fmp", "quiver"):
        assert reg.scope_of_source(src) is LicenseScope.UNKNOWN
    # The ONLY presentable source in the shipped registry is the owner's own operational records.
    presentable = {k for k, e in reg.entries.items() if not e.license_scope.blocks_presentation}
    assert presentable == {"owner_generated_records"}
    assert "alpaca_sip" not in reg.entries  # renamed: one source covers every Alpaca feed


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


@pytest.mark.parametrize("feed", ["sip", "SIP", "iex", "delayed_sip", "otc", "boats", "", None])
def test_every_alpaca_feed_maps_to_the_one_personal_source(feed) -> None:
    sid = lic.alpaca_feed_source_id(feed)
    assert sid == "alpaca_market_data"
    assert reg_mod.load_registry().scope_of_source(sid) is LicenseScope.PERSONAL


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


def _entry(scope: str, **basis) -> dict:
    return {
        "source_id": "x",
        "license_scope": scope,
        "basis": {"document": "d", "date": "2026-10-12", **basis},
        "owner_ruling_ref": "r",
    }


def _parse(entry: dict) -> reg_mod.LicenseRegistry:
    text = json.dumps({"schema_version": 1, "entries": [entry]})
    return reg_mod.parse_registry_text(text, expected_sha256=None)


def test_document_hash_may_be_null_for_personal_and_unknown_only() -> None:
    pending = {"name": "T&C", "sha256": None, "sha256_status": "PENDING_OWNER_SUPPLIED_AS_FETCHED"}
    for scope in ("PERSONAL", "UNKNOWN"):
        reg = _parse(_entry(scope, documents=[pending]))
        assert reg.entries["x"].documents[0].sha256 is None
    with pytest.raises(reg_mod.LicenseRegistryError, match="sha256"):
        _parse(_entry("COMMERCIAL_OK", documents=[pending]))
    # one hashed + one missing is still refused
    good = {"name": "A", "sha256": "0f" * 32}
    with pytest.raises(reg_mod.LicenseRegistryError, match="sha256"):
        _parse(_entry("COMMERCIAL_OK", documents=[good, pending]))
    assert _parse(_entry("COMMERCIAL_OK", documents=[good])).entries["x"].license_scope == (
        LicenseScope.COMMERCIAL_OK
    )


@pytest.mark.parametrize(
    "doc",
    [
        {"name": "T&C", "sha256": None},  # null without a pending status
        {"name": "T&C", "sha256": "not-hex", "sha256_status": "x"},
        {"name": "T&C", "sha256": "AB" * 32},  # must be lowercase hex
    ],
)
def test_malformed_document_hash_rejected(doc) -> None:
    with pytest.raises(reg_mod.LicenseRegistryError):
        _parse(_entry("PERSONAL", documents=[doc]))


def test_commercial_ok_needs_dated_basis_ruling_and_documents_or_explicit_none() -> None:
    with pytest.raises(reg_mod.LicenseRegistryError):  # no dated basis
        _parse(_entry("COMMERCIAL_OK", date=None, no_vendor_documents="owner records"))
    with pytest.raises(reg_mod.LicenseRegistryError):  # neither hashed documents nor a statement
        _parse(_entry("COMMERCIAL_OK"))
    ok = _parse(_entry("COMMERCIAL_OK", no_vendor_documents="owner-generated records"))
    assert ok.entries["x"].license_scope is LicenseScope.COMMERCIAL_OK
    broken = _entry("COMMERCIAL_OK", no_vendor_documents="owner-generated records")
    del broken["owner_ruling_ref"]
    with pytest.raises(reg_mod.LicenseRegistryError):
        _parse(broken)


def test_alpaca_market_data_entry_records_the_owners_reading_as_structured_data() -> None:
    e = reg_mod.load_registry().entries["alpaca_market_data"]
    assert e.license_scope is LicenseScope.PERSONAL
    assert e.owner_ruling_ref == "PU-1 ruling 2026-10-12 (Jay Wang)"
    names = [d.name for d in e.documents]
    assert names == [
        "Alpaca Terms & Conditions",
        "NYSE Market Data Display Services Agreement",
    ]
    for d in e.documents:  # never a fabricated hash
        assert d.sha256 is None
        assert d.sha256_status == "PENDING_OWNER_SUPPLIED_AS_FETCHED_2026-10-12"
    assert e.reading == (
        "local storage permitted for personal use; no retention limit; "
        "no deletion required on cancel"
    )
    assert e.recheck_triggers == (
        "either document hash changes",
        "use becomes commercial",
        "any account trading on these signals moves to an entity",
    )
    assert "weekly-minute" not in e.owner_ruling_ref


def test_owner_generated_records_is_the_first_commercial_ok_entry() -> None:
    reg = reg_mod.load_registry()
    e = reg.entries["owner_generated_records"]
    assert e.license_scope is LicenseScope.COMMERCIAL_OK
    assert e.basis_date == "2026-10-12"
    assert e.basis_document == "owner-generated operational records; contains no vendor market data"
    assert e.owner_ruling_ref == "PU-1 ruling 2026-10-12 (Jay Wang)"
    assert [k for k, v in reg.entries.items() if not v.license_scope.blocks_presentation] == [
        "owner_generated_records"
    ]


def test_owner_generated_records_alone_passes_the_gate_and_carries_no_footer() -> None:
    assert lic.assert_presentable(sources=["owner_generated_records"]) is (
        LicenseScope.COMMERCIAL_OK
    )
    assert lic.stamp("body", sources=["owner_generated_records"]) == "body"


def test_market_data_touching_metric_stays_personal_by_taint_propagation() -> None:
    """Slippage against quotes / fill quality / P&L marked to market combines the owner's own
    records with Alpaca market data; the combination is PERSONAL and blocked."""
    orders = Scoped.of(pd.DataFrame({"px": [10.0, 11.0]}), ["owner_generated_records"])
    quotes = Scoped.of(pd.DataFrame({"mid": [10.1, 10.9]}), ["alpaca_market_data"])
    slippage = derive(lambda o, q: (o["px"] - q["mid"]).mean(), orders, quotes)
    assert slippage.sources == {"owner_generated_records", "alpaca_market_data"}
    reg = reg_mod.load_registry()
    assert reg.scope_of(slippage.sources) is LicenseScope.PERSONAL
    with pytest.raises(lic.PersonalScopeBlocked) as ei:
        lic.assert_presentable(sources=slippage.sources, destination="deck")
    assert ei.value.reason_code == REASON
    assert FOOTER in lic.stamp("slippage", sources=slippage.sources)


def test_sidecar_governs_over_an_envelope_that_claims_commercial_ok(tmp_path) -> None:
    """A pinned envelope cannot be re-serialised, so its scope lives in a sidecar. If the envelope
    itself carries a (stale or forged) COMMERCIAL_OK label, the sidecar still decides, and writing
    the sidecar never touches the artifact's bytes (its pinned digest is unchanged)."""
    art = tmp_path / "receipt.json"
    envelope = {
        "artifact_sha256": "cd" * 32,
        "license_scope": "COMMERCIAL_OK",
        "license_sources": ["owner_generated_records"],
        "rows": 3,
    }
    art.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    before = art.read_bytes()
    assert lic.scope_of_file(art) is LicenseScope.UNKNOWN  # no sidecar: the envelope is not trusted
    lic.write_sidecar(art, ["owner_generated_records", "alpaca_market_data"])
    assert art.read_bytes() == before
    assert lic.scope_of_file(art) is LicenseScope.PERSONAL  # sidecar wins over the envelope label
    with pytest.raises(lic.PersonalScopeBlocked) as ei:
        lic.export_file_for_external_use(art, tmp_path / "share" / "receipt.json")
    assert ei.value.reason_code == REASON
    assert not (tmp_path / "share").exists()


def test_sidecar_over_envelope_commercial_ok_sidecar_passes(tmp_path) -> None:
    art = tmp_path / "ops.json"
    art.write_text(json.dumps({"artifact_sha256": "ef" * 32, "license_scope": "PERSONAL"}))
    lic.write_sidecar(art, ["owner_generated_records"])
    # the sidecar is derived from SOURCES, not from the envelope's own (more restrictive) label
    assert lic.scope_of_file(art) is LicenseScope.COMMERCIAL_OK


# --------------------------------------------------------------------------- gate


@pytest.mark.parametrize("source", ["alpaca_market_data", "sharadar", "never_heard_of_it"])
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
        lic.assert_presentable(sources=["vendor_ok", "alpaca_market_data"])
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok", "vendor_unknown"])


def test_producer_cannot_loosen_scope_by_declaration(commercial_registry) -> None:
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["alpaca_market_data"], declared_scope="COMMERCIAL_OK")
    # and may only tighten
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["vendor_ok"], declared_scope="PERSONAL")


# --------------------------------------------------------------------------- taint propagation


def test_taint_propagates_through_join() -> None:
    bars = Scoped.of(pd.DataFrame({"sym": ["A", "B"], "close": [1.0, 2.0]}), ["alpaca_market_data"])
    fundamentals = Scoped.of(pd.DataFrame({"sym": ["A", "B"], "eps": [3.0, 4.0]}), ["sharadar"])
    joined = derive(lambda a, b: a.merge(b, on="sym"), bars, fundamentals)
    assert joined.sources == {"alpaca_market_data", "sharadar"}
    assert reg_mod.load_registry().scope_of(joined.sources) is LicenseScope.PERSONAL


def test_taint_propagates_through_resample() -> None:
    idx = pd.date_range("2026-01-02 09:30", periods=120, freq="min")
    minute = Scoped.of(pd.Series(np.arange(120.0), index=idx), ["alpaca_market_data"])
    hourly = derive(lambda s: s.resample("1h").last(), minute)
    assert len(hourly.value) >= 2
    assert hourly.sources == {"alpaca_market_data"}
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
    prices = Scoped.of(panel, ["alpaca_market_data"])
    returns = derive(backtest_cross_asset_sleeve, prices)
    assert isinstance(returns.value, pd.Series) and len(returns.value) == len(idx)
    assert returns.sources == {"alpaca_market_data"}
    stats = derive(lambda r: float(r.mean() / (r.std() or 1.0)), returns)  # a "Sharpe"
    assert stats.sources == {"alpaca_market_data"}
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=stats.sources, destination="deck")


# --------------------------------------------------------------------------- envelope tagging


def test_tag_envelope_is_additive_and_ordered() -> None:
    env = {"run_id": "r1", "artifact_sha256": "ab" * 32, "rows": 3}
    tagged = lic.tag_envelope(env, ["Alpaca_Market_Data"])
    assert env == {"run_id": "r1", "artifact_sha256": "ab" * 32, "rows": 3}  # input untouched
    keys = list(tagged)
    assert keys.index("license_scope") == keys.index("artifact_sha256") + 1
    assert tagged["license_scope"] == "PERSONAL"
    assert tagged["license_sources"] == ["alpaca_market_data"]
    assert tagged["rows"] == 3 and tagged["run_id"] == "r1"


def test_envelope_scope_untagged_and_forged() -> None:
    assert lic.envelope_scope({"artifact_sha256": "x"}) is LicenseScope.UNKNOWN
    forged = {"license_scope": "COMMERCIAL_OK", "license_sources": ["alpaca_market_data"]}
    assert lic.envelope_scope(forged) is LicenseScope.PERSONAL


def test_sidecar_binds_digest_and_missing_sidecar_is_unknown(tmp_path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert lic.scope_of_file(f) is LicenseScope.UNKNOWN  # no sidecar
    lic.write_sidecar(f, ["alpaca_market_data"])
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
    out = lic.stamp("# t", sources=["alpaca_market_data"])
    assert out.rstrip().endswith(f"**{FOOTER}**")
    assert lic.stamp(out, sources=["alpaca_market_data"]) == out  # idempotent
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
    assert FOOTER in lic.stamp("x", sources=["alpaca_market_data"])
    with pytest.raises(lic.PersonalScopeBlocked):
        lic.assert_presentable(sources=["alpaca_market_data"])


# --------------------------------------------------------------------------- export seam


def test_export_for_external_use_blocks_personal_and_writes_nothing(tmp_path) -> None:
    dest = tmp_path / "outbound" / "deck.html"
    for src in (["alpaca_market_data"], ["sharadar"], ["unregistered"], []):
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
    lic.write_internal_report(personal, "# r", sources=["alpaca_market_data"])
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
    lic.write_internal_report(f, "# r", sources=["alpaca_market_data"])
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
        candidate_source_sets=[["alpaca_market_data"], ["vendor_unknown"]],
        build=build,
    )
    assert calls == []  # the builder never saw a personal/unknown source set
    assert "ANALYSIS OMITTED" in omitted and "Momentum backtest" in omitted
    assert omitted == lic.omission_notice("Momentum backtest")
    assert not re.search(r"\d", omitted.replace("PU-1", ""))  # no number leaks into the notice

    built = lic.commercial_safe_section(
        "Momentum backtest",
        candidate_source_sets=[["alpaca_market_data"], ["vendor_ok"]],
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
        store.record_dataset(
            DatasetRecord(dataset_id="d1", provider="alpaca_market_data", version="1")
        )
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


async def test_evidence_summary_declares_per_panel_scope(client) -> None:
    resp = await client.get("/api/v1/evidence/summary")
    assert resp.status_code == 200
    body = resp.json()
    # top level: combined most-restrictive scope
    assert body["license_scope"] == "PERSONAL"
    assert "alpaca_market_data" in body["license_sources"]
    assert body["license_footer"] == FOOTER
    panels = body["panels"]
    assert set(panels) == {
        "confidence",
        "kpis",
        "research_programs",
        "research_status_counts",
        "strategies",
    }
    # built only from the owner's records: presentable, no footer
    for name in ("confidence", "kpis", "strategies"):
        assert panels[name]["license_scope"] == "COMMERCIAL_OK", name
        assert panels[name]["license_sources"] == ["owner_generated_records"]
        assert panels[name]["license_footer"] is None
    # built on backtests over vendor data: blocked, footer present
    for name in ("research_programs", "research_status_counts"):
        assert panels[name]["license_scope"] == "PERSONAL", name
        assert "alpaca_market_data" in panels[name]["license_sources"]
        assert panels[name]["license_footer"] == FOOTER
    # every KPI row carries its own scope
    assert all(r["license_scope"] == "COMMERCIAL_OK" for r in body["kpis"]["rows"])
    assert all(r["license_sources"] == ["owner_generated_records"] for r in body["kpis"]["rows"])


def test_evidence_license_block_fails_closed_and_every_kpi_row_is_classified() -> None:
    from app.api.v1 import evidence as ev
    from app.ops.kpis import KpiInputs, build_scorecard

    assert ev._license_block(())["license_scope"] == "UNKNOWN"
    assert ev._license_block(())["license_footer"] == FOOTER
    assert ev._license_block(("owner_generated_records",))["license_footer"] is None
    mixed = ev._license_block(("owner_generated_records", "alpaca_market_data"))
    assert mixed["license_scope"] == "PERSONAL"
    zero = KpiInputs(
        reconciliation_runs=0,
        reconciliation_passes=0,
        reconciliation_discrepancies=0,
        replay_checked=0,
        replay_matched=0,
        orders_risk_passed=0,
        orders_rejected_by_risk=0,
        orders_rejected_by_broker=0,
        breaker_trips=0,
        breaker_resets=0,
        breaker_recovery_minutes=None,
        orders_submitted=0,
        fills_ingested=0,
        expected_snapshot_days=0,
        actual_snapshot_days=0,
    )
    assert {r["key"] for r in build_scorecard(zero)} <= set(ev._KPI_ROW_SOURCES)


def test_dashboard_maps_any_alpaca_provider_to_the_single_market_data_source(tmp_path) -> None:
    from app.research.dashboard.render import dashboard_sources
    from app.research.registry import DatasetRecord, ResearchStore

    store = ResearchStore(db_path=str(tmp_path / "r.duckdb"))
    try:
        store.record_dataset(DatasetRecord(dataset_id="d1", provider="alpaca", version="1"))
        store.record_dataset(DatasetRecord(dataset_id="d2", provider="alpaca_iex", version="1"))
        store.record_dataset(DatasetRecord(dataset_id="d3", provider="sharadar", version="1"))
        assert dashboard_sources(store) == ["alpaca_market_data", "sharadar"]
    finally:
        store.close()
