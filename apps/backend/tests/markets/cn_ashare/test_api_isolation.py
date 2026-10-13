"""Market-scoped API contract, and the import isolation of the markets package in both directions."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.markets.cn_ashare import crosscheck, ingest, research
from app.markets.cn_ashare.providers import synthetic as syn
from app.markets.cn_ashare.providers.baostock import BaostockProvider
from app.markets.cn_ashare.providers.tushare import TushareProvider
from app.markets.cn_ashare.store import CnAshareStore
from app.markets.registry import UnsupportedMarket
from app.markets.registry import resolve as resolve_market

APP = Path(__file__).resolve().parents[3] / "app"
PKG = APP / "markets"
BASE = "/api/v1/markets"
TS, BS = "cn_synthetic:tushare_shape", "cn_synthetic:baostock_shape"

#: Modules the markets package must never import: the order path, risk, brokers, US strategies,
#: schedulers/jobs, US services and US market/factor data, the app DB, and the LLM SDK.
FORBIDDEN = (
    "app.orders", "app.risk", "app.brokers", "app.strategies", "app.jobs", "app.services",
    "app.factor_data", "app.market_data", "app.db", "alpaca", "anthropic",
)  # fmt: skip
#: The only module outside ``app.markets`` allowed to import it.
ALLOWED_IMPORTERS = {APP / "api" / "v1" / "markets.py"}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_markets_package_imports_nothing_from_the_order_path() -> None:
    bad = []
    for path in PKG.rglob("*.py"):
        for name in _imports(path):
            if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                bad.append(f"{path.relative_to(APP)}: {name}")
    assert not bad, bad


def test_only_the_read_only_router_imports_the_markets_package() -> None:
    bad = []
    for path in APP.rglob("*.py"):
        if PKG in path.parents or path in ALLOWED_IMPORTERS:
            continue
        if any(n == "app.markets" or n.startswith("app.markets.") for n in _imports(path)):
            bad.append(str(path.relative_to(APP)))
    assert not bad, bad


def test_router_has_only_get_routes() -> None:
    from app.api.v1.markets import router

    assert router.routes and all(set(r.methods) == {"GET"} for r in router.routes)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "raw", ["", "US_EQUITY", "us", "cn", "CN_ASHARE", "jp_equity", " cn_ashare"]
)
def test_market_ids_match_exactly(raw: str) -> None:
    with pytest.raises(UnsupportedMarket):
        resolve_market(raw)
    assert resolve_market("cn_ashare").currency == "CNY"
    assert resolve_market("us_equity").timezone == "America/New_York"


@pytest.fixture
def cn_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.config import get_settings

    monkeypatch.setenv("WORKBENCH_CN_ASHARE_DB_PATH", str(tmp_path / "cn_ashare_api.duckdb"))
    monkeypatch.setenv("WORKBENCH_CN_ASHARE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("WORKBENCH_CN_ASHARE_TUSHARE_TOKEN_PATH", str(tmp_path / "no_token"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_market_list(client: AsyncClient) -> None:
    body = (await client.get(BASE)).json()
    by_id = {m["market"]: m for m in body["markets"]}
    assert set(by_id) == {"us_equity", "cn_ashare"}
    assert by_id["cn_ashare"]["currency_label"] == "RMB" and by_id["cn_ashare"]["research_only"]
    assert not by_id["us_equity"]["scoped_api"]


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["data-status", "strategies", "results"])
async def test_unsupported_and_unscoped_markets_are_refused(
    cn_paths: Path, client: AsyncClient, view: str
) -> None:
    r = await client.get(f"{BASE}/jp_equity/{view}")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "UNSUPPORTED_MARKET"
    r = await client.get(f"{BASE}/CN_ASHARE/{view}")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "UNSUPPORTED_MARKET"
    r = await client.get(f"{BASE}/us_equity/{view}")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MARKET_NOT_SCOPED"


@pytest.mark.asyncio
async def test_views_without_a_store(cn_paths: Path, client: AsyncClient) -> None:
    body = (await client.get(f"{BASE}/cn_ashare/data-status")).json()
    assert (
        body["market"] == "cn_ashare"
        and body["currency"] == "CNY"
        and body["timezone"] == "Asia/Shanghai"
    )
    assert body["store"] == "NO_STORE"
    kinds = {i["kind"] for i in body["issues"]}
    assert {"NO_STORE", "TUSHARE_TOKEN_ABSENT"} <= kinds
    assert {p["source_id"] for p in body["providers"]} == {"tushare_pro", "baostock"}
    assert (await client.get(f"{BASE}/cn_ashare/results")).json()["runs"] == []
    cands = (await client.get(f"{BASE}/cn_ashare/strategies")).json()["candidates"]
    assert {c["candidate_id"] for c in cands} == {"CN-MOM-20D", "CN-REV-5D"}
    assert all(c["status"] == "CANDIDATE" and c["last_run"] is None for c in cands)


@pytest.mark.asyncio
async def test_views_read_the_store(cn_paths: Path, client: AsyncClient) -> None:
    truth = syn.build_truth()
    start, end = truth.calendar[0], truth.calendar[-1]
    with CnAshareStore(cn_paths / "cn_ashare_api.duckdb", cn_paths / "cache") as store:
        ts = TushareProvider(syn.FakeTusharePro(truth), source_id=TS)
        bs = BaostockProvider(syn.FakeBaostock(truth, inject_price_mismatch=True), source_id=BS)
        syms = sorted(truth.names)
        for p in (ts, bs):
            ingest.ingest_sample(
                store, p, [*syms, "999999.SH"], start, end, sample_label=ingest.SYNTHETIC_SAMPLE
            )
        store.record_crosscheck(
            crosscheck.compare(
                TS, store.daily(TS), store.factors(TS), BS, store.daily(BS), store.factors(BS)
            )
        )
        rep = research.run_descriptive(
            "CN-MOM-20D", provider=BS, open_days=store.open_days(BS), daily=store.daily(BS),
            factors=store.factors(BS), securities=store.securities(BS), sample_label=ingest.SYNTHETIC_SAMPLE,
        )  # fmt: skip
        from app.markets.cn_ashare import context
        from app.markets.context import PriceBasis

        run_id = store.record_run(
            candidate_id="CN-MOM-20D", ctx=context(exchange="SSE+SZSE", provider=BS, price_basis=PriceBasis.HFQ),
            sample_label=ingest.SYNTHETIC_SAMPLE, ingest_ids=[], report=rep,
        )  # fmt: skip
    (cn_paths / "no_token").write_text("secret-value")

    status = (await client.get(f"{BASE}/cn_ashare/data-status")).json()
    assert status["store"] == "PRESENT" and "secret-value" not in str(status)
    tushare = next(p for p in status["providers"] if p["source_id"] == "tushare_pro")
    assert tushare["credential"] == "PRESENT"
    synth = next(p for p in status["providers"] if p["source_id"] == BS)
    assert synth["presentation"] == "SYNTHETIC_OK" and synth["last_update_utc"]
    daily = next(d for d in synth["datasets"] if d["dataset"] == "daily")
    assert daily["symbols"] == len(syms)
    assert status["calendar"] and status["calendar"][0]["open_days"] == len(truth.calendar)
    kinds = [i["kind"] for i in status["issues"]]
    assert "CROSSCHECK_PRICE_MISMATCH" in kinds and "SYMBOL_NOT_IN_SECURITY_LIST" in kinds
    assert "SYNTHETIC_ONLY" in kinds and status["crosscheck"]["all_explained"] is False

    cands = (await client.get(f"{BASE}/cn_ashare/strategies")).json()["candidates"]
    mom = next(c for c in cands if c["candidate_id"] == "CN-MOM-20D")
    assert mom["run_count"] == 1 and mom["last_run"]["run_id"] == run_id

    res = (await client.get(f"{BASE}/cn_ashare/results")).json()
    run = res["runs"][0]
    assert run["market_context"]["currency"] == "CNY"
    assert set(run["result"]["costs_cny"]) == {
        "commission", "stamp_duty", "transfer_fee", "handling_fee", "regulatory_fee", "total",
    }  # fmt: skip
    assert run["result"]["risk"]["volatility_annualized"] > 0
    assert run["limitations"]["not_modelled"] and run["limitations"]["rules"]
