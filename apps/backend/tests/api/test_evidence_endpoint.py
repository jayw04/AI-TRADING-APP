"""P13 — GET /api/v1/evidence/summary shape + the research-program registry."""

from __future__ import annotations

from app.research.programs import RESEARCH_PROGRAMS, list_programs, status_counts


async def test_evidence_summary_shape(client) -> None:
    resp = await client.get("/api/v1/evidence/summary")
    assert resp.status_code == 200
    body = resp.json()
    # confidence score envelope
    assert 0 <= body["confidence"]["score"] <= 100
    assert set(body["confidence"]["components"]) == {
        "verifiability", "safety", "maturity", "operational"}
    # KPI scorecard
    assert "rows" in body["kpis"] and "summary" in body["kpis"]
    assert {r["key"] for r in body["kpis"]["rows"]} >= {
        "reconciliation_success", "replay_consistency", "fill_success"}
    # research programs + strategies present
    ids = {p["id"] for p in body["research_programs"]}
    assert {"MOM-001", "RNG-001", "MF-001", "SEC-001"}.issubset(ids)
    assert isinstance(body["strategies"], list)


def test_research_programs_catalog():
    progs = list_programs()
    assert len(progs) == len(RESEARCH_PROGRAMS)
    by_id = {p["id"]: p for p in progs}
    assert by_id["MOM-001"]["status"] == "validated" and by_id["MOM-001"]["color"] == "green"
    assert by_id["RNG-001"]["status"] == "rejected" and by_id["RNG-001"]["color"] == "red"
    assert by_id["MF-001"]["status"] == "inconclusive" and by_id["MF-001"]["color"] == "amber"
    assert by_id["SEC-001"]["status"] == "inconclusive" and by_id["SEC-001"]["color"] == "amber"
    # every program carries a philosophy + headline
    assert all(p["philosophy"] and p["headline"] for p in progs)


def test_status_counts_sum_to_total():
    assert sum(status_counts().values()) == len(RESEARCH_PROGRAMS)
