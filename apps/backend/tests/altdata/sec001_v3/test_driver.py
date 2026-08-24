"""End-to-end crawl behaviour: output containment, resumability, halt handling.

Runs the real MR-002 spine against a mocked EDGAR, so the test exercises the actual call
path — ``collect_sic_observations`` -> ``fetch_header_text`` -> ``PolicyFetcher`` — rather
than a stand-in for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.altdata.mr002 import crosswalk as real_crosswalk
from app.altdata.mr002 import sic_history as real_sic_history
from app.altdata.sec001_v3 import policy
from app.altdata.sec001_v3.driver import (
    CrawlDriver,
    OutputPathError,
    PopulationSchemaError,
    assert_output_allowed,
    load_work_units,
    open_evidence_log,
)
from app.altdata.sec001_v3.fetch import CrawlHalt, PolicyFetcher
from app.altdata.sec001_v3.spine import Spine
from app.altdata.sec001_v3.state import CrawlState, WorkUnit

FILINGS = {
    320193: [("10-K", "0000320193-23-000106", "2023-11-03", "3571")],
    789019: [
        ("10-K", "0000789019-22-000078", "2022-07-28", "7372"),
        ("10-Q", "0000789019-23-000012", "2023-01-24", "7372"),
        ("20-F", "0000789019-24-000005", "2024-02-01", "7373"),
    ],
}


def edgar_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/submissions/" in url:
        cik = int(url.rsplit("CIK", 1)[1].split(".")[0])
        rows = FILINGS[cik]
        return httpx.Response(200, json={"filings": {"recent": {
            "form": [r[0] for r in rows],
            "accessionNumber": [r[1] for r in rows],
            "filingDate": [r[2] for r in rows],
            "acceptanceDateTime": [f"{r[2]}T16:30:00.000Z" for r in rows],
        }, "files": []}})
    for rows in FILINGS.values():
        for _form, accession, _date, sic in rows:
            if accession.replace("-", "") in url or accession in url:
                return httpx.Response(
                    200,
                    text=f"<SEC-HEADER>\nSTANDARD INDUSTRIAL CLASSIFICATION: THINGS [{sic}]\n",
                )
    return httpx.Response(404)


@pytest.fixture
def spine() -> Spine:
    return Spine(
        sic_history=real_sic_history,
        crosswalk=real_crosswalk,
        frozen_root=Path(real_sic_history.__file__).parent,
    )


def build_driver(tmp_path: Path, spine: Spine, handler=edgar_handler) -> CrawlDriver:
    out_root = tmp_path / "out"
    fetcher = PolicyFetcher(
        evidence=open_evidence_log(out_root),
        transport=httpx.MockTransport(handler),
        sleep=lambda d: None,
        monotonic=lambda: 0.0,
    )
    return CrawlDriver(
        spine=spine,
        out_root=out_root,
        fetcher=fetcher,
        state=CrawlState.load(tmp_path / "state"),
    )


UNITS = [WorkUnit(cik=320193, ticker="AAPL"), WorkUnit(cik=789019, ticker="MSFT")]


# --- output containment ---------------------------------------------------------------


def test_outputs_land_only_under_the_two_declared_prefixes(tmp_path, spine) -> None:
    driver = build_driver(tmp_path, spine)
    driver.run(UNITS)

    out_root = tmp_path / "out"
    written = sorted(p.relative_to(out_root).as_posix()
                     for p in out_root.rglob("*") if p.is_file())
    assert written, "the crawl produced no output"
    for rel in written:
        assert rel.startswith(policy.RAW_PREFIX) or rel.startswith(policy.BUILD_PREFIX), rel
    assert f"{policy.RAW_PREFIX}/observations/0000320193.jsonl" in written
    assert f"{policy.BUILD_PREFIX}/segments/0000789019.jsonl" in written
    assert f"{policy.RAW_PREFIX}/source_evidence.jsonl" in written


def test_writes_outside_the_prefixes_are_refused(tmp_path) -> None:
    root = tmp_path / "out"
    assert_output_allowed(root / policy.RAW_PREFIX / "x.jsonl", root)
    assert_output_allowed(root / policy.BUILD_PREFIX / "x.jsonl", root)

    for bad in ("sealed/factor_data.duckdb", "manifests/s3/docs.json", "build/source/repo.tar.gz"):
        with pytest.raises(OutputPathError):
            assert_output_allowed(root / bad, root)


def test_path_traversal_cannot_escape_the_output_root(tmp_path) -> None:
    """Checked on the resolved path — ``sealed/`` is under a COMPLIANCE lock to 2033."""
    root = tmp_path / "out"
    with pytest.raises(OutputPathError):
        assert_output_allowed(root / policy.RAW_PREFIX / ".." / ".." / ".." / "sealed" / "x", root)


# --- facts, not coverage --------------------------------------------------------------


def test_emitted_records_carry_no_coverage_quantity(tmp_path, spine) -> None:
    from app.altdata.sec001_v3.forbidden import FORBIDDEN_COVERAGE_FIELDS

    driver = build_driver(tmp_path, spine)
    driver.run(UNITS)

    for path in (tmp_path / "out").rglob("*.json*"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert not (set(json.loads(line)) & FORBIDDEN_COVERAGE_FIELDS), path


def test_observations_and_segments_reflect_the_filings(tmp_path, spine) -> None:
    driver = build_driver(tmp_path, spine)
    outcome = driver.run(UNITS)

    assert outcome.units_crawled_this_run == 2
    assert outcome.halted is False
    assert outcome.requests_issued > 0

    obs_path = tmp_path / "out" / policy.RAW_PREFIX / "observations" / "0000789019.jsonl"
    observations = [json.loads(x) for x in obs_path.read_text(encoding="utf-8").splitlines()]
    assert len(observations) == 3
    assert {o["form"] for o in observations} == {"10-K", "10-Q", "20-F"}
    assert {o["sic"] for o in observations} == {"7372", "7373"}

    seg_path = tmp_path / "out" / policy.BUILD_PREFIX / "segments" / "0000789019.jsonl"
    segments = [json.loads(x) for x in seg_path.read_text(encoding="utf-8").splitlines()]
    assert [s["sic"] for s in segments] == ["7372", "7373"]
    assert segments[0]["effective_to"] is not None
    assert segments[1]["effective_to"] is None


def test_twenty_f_is_actually_requested(tmp_path, spine) -> None:
    """The registered form widening reaches the wire, through the spine's existing
    ``forms=`` parameter — no MR-002 file is modified."""
    driver = build_driver(tmp_path, spine)
    driver.run(UNITS)

    evidence = tmp_path / "out" / policy.RAW_PREFIX / "source_evidence.jsonl"
    forms = {json.loads(x).get("form") for x in evidence.read_text(encoding="utf-8").splitlines()}
    assert "20-F" in forms
    assert real_sic_history.DEFAULT_FORMS == ("10-K", "10-K/A", "10-Q", "10-Q/A"), \
        "the spine's own default must remain untouched"


# --- resumability ---------------------------------------------------------------------


def test_second_run_recrawls_nothing(tmp_path, spine) -> None:
    first = build_driver(tmp_path, spine)
    first.run(UNITS)
    issued = first.fetcher.requests_issued

    second = build_driver(tmp_path, spine)
    outcome = second.run(UNITS)
    assert outcome.units_crawled_this_run == 0
    assert second.fetcher.requests_issued == 0
    assert issued > 0


def test_partial_run_resumes_where_it_stopped(tmp_path, spine) -> None:
    first = build_driver(tmp_path, spine)
    first.run(UNITS, limit=1)

    second = build_driver(tmp_path, spine)
    outcome = second.run(UNITS)
    assert outcome.units_crawled_this_run == 1
    assert outcome.units_completed == 2


# --- halt ------------------------------------------------------------------------------


def test_403_halts_records_state_and_refuses_a_bare_restart(tmp_path, spine) -> None:
    def blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    driver = build_driver(tmp_path, spine, blocked)
    with pytest.raises(CrawlHalt):
        driver.run(UNITS)

    state = CrawlState.load(tmp_path / "state")
    assert state.is_halted
    assert state.halt["http_status"] == 403

    # A restart without an explicit, cooled-down resume must not reach SEC again.
    calls: list[str] = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    restarted = build_driver(tmp_path, spine, counting)
    with pytest.raises(CrawlHalt, match="resume refused"):
        restarted.run(UNITS)
    assert calls == []


def test_outcome_is_written_even_when_halted(tmp_path, spine) -> None:
    driver = build_driver(tmp_path, spine, lambda r: httpx.Response(403))
    with pytest.raises(CrawlHalt):
        driver.run(UNITS)

    outcome_path = tmp_path / "out" / policy.BUILD_PREFIX / "crawl_outcome.json"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["halted"] is True
    assert outcome["crawl_id"] == policy.CRAWL_ID


# --- population loading ----------------------------------------------------------------


def test_population_loads_and_is_deduplicated(tmp_path) -> None:
    path = tmp_path / "pit200_union.json"
    path.write_text(json.dumps({"identities": [
        {"cik": 789019, "ticker": "msft", "permaticker": 111},
        {"cik": 320193, "ticker": "AAPL", "permaticker": 222},
        {"cik": 320193, "ticker": "AAPL", "permaticker": 222},
    ]}), encoding="utf-8")

    units = load_work_units(path)
    assert [u.ticker for u in units] == ["AAPL", "MSFT"]
    assert units[0].cik == 320193


def test_population_without_cik_fails_loudly(tmp_path) -> None:
    """Never infer a CIK. The diagnostic names the keys that were present."""
    path = tmp_path / "pit200_union.json"
    path.write_text(json.dumps([{"ticker": "AAPL", "permaticker": 222}]), encoding="utf-8")

    with pytest.raises(PopulationSchemaError, match="permaticker"):
        load_work_units(path)


def test_empty_population_is_an_error(tmp_path) -> None:
    path = tmp_path / "pit200_union.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(PopulationSchemaError, match="empty"):
        load_work_units(path)
