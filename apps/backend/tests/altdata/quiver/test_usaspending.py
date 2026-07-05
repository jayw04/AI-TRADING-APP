"""USAspending cross-check reconciliation (EAD Phase 1 exit gate). Offline; httpx MockTransport."""

from __future__ import annotations

from datetime import date

import httpx

from app.altdata.quiver.usaspending import USAspendingClient, reconcile_event


def _client(results):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": results})
    return USAspendingClient(transport=httpx.MockTransport(handler))


def test_matches_recipient_agency_and_computes_lag():
    res = [{"Recipient Name": "LOCKHEED MARTIN CORPORATION",
            "Awarding Agency": "Department of Homeland Security",
            "Award Amount": 1.0, "Last Modified Date": "2026-07-09 12:00:00"}]
    with _client(res) as c:
        r = reconcile_event(ticker="LMT", company_name="Lockheed Martin",
                            agency="Department of Homeland Security",
                            action_date=date(2026, 7, 2), usa_client=c)
    assert r.matched and r.agency_matched and r.note == "ok"
    assert r.n_candidates == 1 and r.availability_lag_days == 7   # 07-09 − 07-02


def test_agency_stopwords_prevent_false_match():
    # "Department of Energy" vs "…Homeland Security" share only stopwords -> NOT an agency match
    res = [{"Recipient Name": "X", "Awarding Agency": "Department of Energy",
            "Last Modified Date": "2026-07-20"}]
    with _client(res) as c:
        r = reconcile_event(ticker="LMT", company_name="Lockheed",
                            agency="Department of Homeland Security",
                            action_date=date(2026, 7, 2), usa_client=c)
    assert r.matched and not r.agency_matched
    assert r.note == "recipient_matched_agency_mismatch" and r.availability_lag_days == 18


def test_no_official_award_is_unmatched():
    with _client([]) as c:
        r = reconcile_event(ticker="LMT", company_name="Nonexistent Co",
                            agency="X", action_date=date(2026, 7, 2), usa_client=c)
    assert not r.matched and r.n_candidates == 0
    assert r.note == "no_official_award_for_recipient_in_window"
