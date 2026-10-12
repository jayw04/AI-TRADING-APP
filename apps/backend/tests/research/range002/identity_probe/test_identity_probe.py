"""Identity probe harness on SYNTHETIC fixtures, with negative controls that must fail closed.

Nothing here is vendor data. The probe is never executed on real data from this repository state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import identity_probe as ip  # noqa: E402


def T(p: str, tick: str, first: str, last: str | None = None, delisted: str = "N") -> dict:  # type: ignore[type-arg]
    return {
        "permaticker": p,
        "ticker": tick,
        "firstpricedate": first,
        "lastpricedate": last,
        "isdelisted": delisted,
    }


def A(day: str, action: str, ticker: str, contra: str = "") -> dict:  # type: ignore[type-arg]
    return {"date": day, "action": action, "ticker": ticker, "contraticker": contra}


def clean(n: int) -> list[dict]:  # type: ignore[type-arg]
    return [T(f"C{i}", f"CLN{i}", "2010-01-04") for i in range(n)]


def good_sample() -> dict:  # type: ignore[type-arg]
    rows = clean(7)
    # ticker changes whose intervals are present (two rows, own intervals)
    for i in range(3):
        rows += [
            T(f"R{i}", f"OLD{i}", "2010-01-04", "2015-06-30", "N"),
            T(f"R{i}", f"NEW{i}", "2015-07-01"),
        ]
    # successor identity: one ticker string, two issuers, non-overlapping intervals
    rows += [T("S1", "REUSE", "2010-01-04", "2012-01-03", "Y"), T("S2", "REUSE", "2016-01-04")]
    actions = [A("2015-07-01", "tickerchangefrom", f"NEW{i}", f"OLD{i}") for i in range(3)]
    return {"tickers": rows, "actions": actions}


def label_of(payload: dict, issuer: str) -> str:  # type: ignore[type-arg]
    pre = ip.load_preregistration()
    rows, acts, _ = ip.parse_input(payload)
    return ip.classify(rows, acts, pre)[issuer]


# --- pre-registration is frozen ---------------------------------------------------------------


def test_preregistration_is_pinned_and_a_changed_copy_is_refused(tmp_path: Path) -> None:
    raw = ip.PREREGISTRATION_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ip.PREREGISTRATION_SHA256
    pre = ip.load_preregistration()
    assert pre.decision_labels == ("RETAIN_RAW_INTERVALS", "SCOPE_AMENDMENT")
    assert (pre.min_issuers, pre.min_change_cases, pre.gap_days) == (10, 3, 7)
    changed = tmp_path / "pre.json"
    changed.write_bytes(
        raw.replace(b'"min_identity_change_cases": 3', b'"min_identity_change_cases": 0')
    )
    with pytest.raises(ip.PreregistrationError):
        ip.load_preregistration(changed)
    with pytest.raises(ip.PreregistrationError):
        ip.load_preregistration(tmp_path / "missing.json")


# --- labels on the five required fixture classes -----------------------------------------------


def test_clean_history_and_ticker_change_with_intervals() -> None:
    p = good_sample()
    assert label_of(p, "C0") == "CLEAN_SINGLE_INTERVAL"
    assert label_of(p, "R0") == "TICKER_CHANGE_INTERVALS_PRESENT"


def test_successor_identity_is_resolved_only_with_non_overlapping_dated_intervals() -> None:
    p = good_sample()
    assert label_of(p, "S1") == label_of(p, "S2") == "SUCCESSOR_IDENTITY_RESOLVED"


def test_a_change_evidenced_only_by_actions_is_current_only() -> None:
    p = {
        "tickers": [T("X", "NEWX", "2010-01-04")],  # one row: no historical interval
        "actions": [A("2015-07-01", "tickerchangefrom", "NEWX", "OLDX")],
    }
    assert label_of(p, "X") == "TICKER_CHANGE_CURRENT_ONLY"


def test_gap_is_explained_only_by_an_action_inside_it() -> None:
    rows = [T("G", "AAA", "2010-01-04", "2012-01-03", "Y"), T("G", "AAA", "2013-01-04")]
    assert label_of({"tickers": rows, "actions": []}, "G") == "INTERVAL_GAP_UNEXPLAINED"
    inside = {"tickers": rows, "actions": [A("2012-06-01", "listed", "AAA")]}
    assert label_of(inside, "G") == "INTERVAL_GAP_EXPLAINED"
    outside = {"tickers": rows, "actions": [A("2014-06-01", "listed", "AAA")]}
    assert label_of(outside, "G") == "INTERVAL_GAP_UNEXPLAINED"


def test_overlapping_mapping_is_ambiguous_in_both_directions() -> None:
    same_issuer = [T("M", "AAA", "2010-01-04", "2015-12-31"), T("M", "BBB", "2015-01-01")]
    assert label_of({"tickers": same_issuer, "actions": []}, "M") == "AMBIGUOUS_MAPPING"
    same_ticker = [T("P", "ZZZ", "2010-01-04"), T("Q", "ZZZ", "2012-01-04")]
    p = {"tickers": same_ticker, "actions": []}
    assert label_of(p, "P") == label_of(p, "Q") == "AMBIGUOUS_MAPPING"


def test_invalid_records_are_labelled_not_dropped() -> None:
    inverted = {"tickers": [T("I", "AAA", "2015-01-01", "2010-01-01", "Y")], "actions": []}
    assert label_of(inverted, "I") == "INVALID_RECORD"
    delisted_no_end = {"tickers": [T("J", "AAA", "2010-01-04", None, "Y")], "actions": []}
    assert label_of(delisted_no_end, "J") == "INVALID_RECORD"


# --- the decision and its negative controls ---------------------------------------------------


def test_a_demonstrating_sample_retains_raw_intervals() -> None:
    r = ip.run_probe(good_sample())
    assert r.decision == "RETAIN_RAW_INTERVALS" and r.reasons == ()
    assert r.issuers >= 10 and r.identity_change_cases >= 3 and r.blocking_cases == 0


@pytest.mark.parametrize(
    ("name", "mutate", "reason"),
    [
        ("empty response", lambda p: {"tickers": [], "actions": []}, "INSUFFICIENT_SAMPLE"),
        (
            "too small",
            lambda p: {"tickers": p["tickers"][:6], "actions": p["actions"]},
            "INSUFFICIENT_SAMPLE",
        ),
        (
            "vacuous: nothing but clean issuers",
            lambda p: {"tickers": clean(30), "actions": []},
            "TOO_FEW_IDENTITY_CHANGE_CASES",
        ),
        (
            "one current-only change among many good ones",
            lambda p: {
                "tickers": p["tickers"] + [T("Z", "NEWZ", "2010-01-04")],
                "actions": p["actions"] + [A("2014-01-01", "tickerchangefrom", "NEWZ", "OLDZ")],
            },
            "BLOCKING_LABELS_PRESENT",
        ),
        (
            "one ambiguous overlap",
            lambda p: {
                "tickers": p["tickers"]
                + [T("O1", "DUP", "2010-01-04"), T("O2", "DUP", "2011-01-04")],
                "actions": p["actions"],
            },
            "BLOCKING_LABELS_PRESENT",
        ),
        (
            "one unexplained gap",
            lambda p: {
                "tickers": p["tickers"]
                + [T("GG", "GAP", "2010-01-04", "2011-01-04", "Y"), T("GG", "GAP", "2013-01-04")],
                "actions": p["actions"],
            },
            "BLOCKING_LABELS_PRESENT",
        ),
        (
            "one invalid record",
            lambda p: {
                "tickers": p["tickers"] + [T("", "NOID", "2010-01-04")],
                "actions": p["actions"],
            },
            "BLOCKING_LABELS_PRESENT",
        ),
        (
            "a row that cannot be parsed",
            lambda p: {
                "tickers": p["tickers"] + [{"firstpricedate": "not-a-date"}],
                "actions": p["actions"],
            },
            "STRUCTURAL_DEFECTS",
        ),
    ],
)
def test_negative_controls_fail_closed_to_scope_amendment(name, mutate, reason) -> None:  # type: ignore[no-untyped-def]
    r = ip.run_probe(mutate(good_sample()))
    assert r.decision == "SCOPE_AMENDMENT", name
    assert reason in r.reasons, (name, r.reasons)


def test_malformed_input_is_refused_not_decided() -> None:
    for bad in (None, [], {"tickers": "x"}, {"actions": []}):
        with pytest.raises(ip.ProbeInputError):
            ip.run_probe(bad)


def test_a_label_outside_the_preregistered_set_is_a_harness_defect(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(ip, "classify", lambda rows, acts, pre: {"X": "SOMETHING_NEW"})
    with pytest.raises(ip.PreregistrationError):
        ip.run_probe(good_sample())


def test_output_carries_labels_and_counts_only() -> None:
    fields = set(ip.ProbeResult.__dataclass_fields__)
    assert not {f for f in fields if any(w in f for w in ("price", "return", "volume", "pnl"))}
    assert "RETAIN_RAW_INTERVALS" in ip.load_preregistration().decision_labels


# --- the CLI cannot run without an owner authorization record ----------------------------------


def test_cli_refuses_without_an_authorization_record(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    data = tmp_path / "in.json"
    data.write_text(json.dumps(good_sample()), encoding="utf-8")
    missing = tmp_path / "none.json"
    assert ip.main(["x", "--authorization-record", str(missing), "--input", str(data)]) == 2
    deny = tmp_path / "deny.json"
    deny.write_text(
        json.dumps({"record_type": "range002.identity_probe_authorization.v1", "decision": "DENY"})
    )
    assert ip.main(["x", "--authorization-record", str(deny), "--input", str(data)]) == 2
    assert "REFUSED" in capsys.readouterr().out
    allow = tmp_path / "allow.json"
    allow.write_text(
        json.dumps(
            {
                "record_type": "range002.identity_probe_authorization.v1",
                "decision": "ALLOW",
                "owner_record_ref": "synthetic/test-only.md",
            }
        )
    )
    assert ip.main(["x", "--authorization-record", str(allow), "--input", str(data)]) == 0


def test_the_preregistration_file_is_a_committed_artifact() -> None:
    assert ip.PREREGISTRATION_PATH.is_file()
    assert shutil.which is not None  # keeps the import used on all platforms
