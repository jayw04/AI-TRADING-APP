"""USAspending cross-check reconciliation (EAD Phase 1 exit gate). Offline; httpx MockTransport."""

from __future__ import annotations

from datetime import date

import httpx

from app.altdata.quiver.usaspending import (
    OPERATIONAL_OUTCOMES,
    ReconcileOutcome,
    USAspendingClient,
    reconcile_event,
)


def _client(results):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": results})
    return USAspendingClient(transport=httpx.MockTransport(handler))


_HIT = [{"Recipient Name": "X", "Awarding Agency": "Department of Energy",
         "Last Modified Date": "2026-07-09"}]


def _seq_client(status_seq, **kw):
    """Return a client whose handler yields the given status codes in order (200 -> _HIT results,
    429 -> Retry-After:0, 5xx -> empty, or raises for TIMEOUT/NETWORK)."""
    it = iter(status_seq)

    def handler(_req: httpx.Request) -> httpx.Response:
        st = next(it)
        if st == "timeout":
            raise httpx.ConnectTimeout("t")
        if st == "network":
            raise httpx.ConnectError("n")
        if st == 200:
            return httpx.Response(200, json={"results": _HIT})
        if st == 429:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(st)
    return USAspendingClient(transport=httpx.MockTransport(handler), sleep=lambda _s: None, **kw)


def _recon(client):
    return reconcile_event(ticker="T", company_name="X", agency="Department of Energy",
                           action_date=date(2026, 7, 2), usa_client=client)


def test_transient_429_is_retried_then_reconciles():
    r = _recon(_seq_client([429, 429, 200]))
    assert r.outcome is ReconcileOutcome.RECONCILED
    assert r.matched and r.attempts == 3


def test_persistent_429_is_operational_not_unreconciled():
    r = _recon(_seq_client([429, 429, 429], max_attempts=3))
    assert r.outcome is ReconcileOutcome.HTTP_429
    assert r.outcome in OPERATIONAL_OUTCOMES
    assert r.outcome is not ReconcileOutcome.VALID_NON_RECONCILIATION  # the whole point
    assert r.attempts == 3 and not r.matched


def test_timeout_and_5xx_are_operational():
    assert _recon(_seq_client(["timeout", "timeout"], max_attempts=2)).outcome is ReconcileOutcome.TIMEOUT
    assert _recon(_seq_client([503, 503], max_attempts=2)).outcome is ReconcileOutcome.HTTP_5XX


def test_empty_result_is_valid_non_reconciliation_not_operational():
    # a genuine empty official record is a SEMANTIC outcome, not an operational failure
    c = USAspendingClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"results": []})))
    r = _recon(c)
    assert r.outcome is ReconcileOutcome.VALID_NON_RECONCILIATION
    assert r.outcome not in OPERATIONAL_OUTCOMES


def test_rate_gate_and_callbacks_fire_per_attempt():
    events: list[str] = []
    c = _seq_client([429, 200], rate_gate=lambda: events.append("gate"),
                    on_429=lambda: events.append("429"), on_success=lambda: events.append("ok"))
    r = _recon(c)
    assert r.outcome is ReconcileOutcome.RECONCILED
    assert events.count("gate") == 2 and "429" in events and "ok" in events


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
