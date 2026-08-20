"""DISC-MDQ-001 Phase A — exploration policy (the pre-read embargo).

The point of these tests is not coverage of a decision table; it is to hold the
line that the holdout is quarantined *before* anything is opened.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.research.disc_mdq.policy import (
    MdqExplorationPolicy,
    PolicyError,
    ReviewWindow,
    check_period_holdout_claim,
    load_holdout_artifact,
)
from app.research.disc_mdq.spec import (
    HOLDOUT_SYMBOLS_SHA256,
    PERIOD_HOLDOUT_UNSTAMPED,
    PRE_STAMP_HOLDOUT_ARTIFACT_SHA256,
    REVIEW_D0,
    REVIEW_END_EXCLUSIVE,
    UNIVERSE_SYMBOLS_SHA256,
    Decision,
    ReadPurpose,
)

HOLDOUT = ["AMZN", "EFA", "KMLM", "MSTR", "NBIS", "NOW", "TSLA", "XLK", "XLV", "XOM"]
UNIVERSE = [*HOLDOUT, "AAPL", "GOOGL", "MSFT", "NVDA", "SPY", "QQQ", "AMD", "META"]

IN_WINDOW = date(2026, 8, 20)
HOLDOUT_DAY = date(2026, 10, 6)
LAST_HOLDOUT_DAY = date(2026, 10, 17)
BEFORE_D0 = date(2026, 8, 18)
AFTER_WINDOW = date(2026, 10, 18)


def make_policy(**kw: object) -> MdqExplorationPolicy:
    params: dict[str, object] = {
        "universe_symbols": UNIVERSE,
        "holdout_symbols": HOLDOUT,
        "window": ReviewWindow.governed(),
    }
    params.update(kw)
    return MdqExplorationPolicy(**params)  # type: ignore[arg-type]


# --- the governed window ----------------------------------------------------


def test_governed_window_matches_the_preregistered_dates() -> None:
    w = ReviewWindow.governed()
    assert w.d0 == REVIEW_D0 == date(2026, 8, 19)
    assert w.end_exclusive == REVIEW_END_EXCLUSIVE == date(2026, 10, 18)
    # Holdout = final 12 calendar days: 2026-10-06 .. 2026-10-17 inclusive.
    assert w.holdout_start == date(2026, 10, 6)
    assert w.holdout_end_exclusive == date(2026, 10, 18)
    assert (w.end_exclusive - w.d0).days == 60


def test_window_rejects_a_holdout_that_would_swallow_the_window() -> None:
    with pytest.raises(PolicyError, match="consume the whole"):
        ReviewWindow(d0=date(2026, 8, 19), end_exclusive=date(2026, 8, 29), period_holdout_days=12)


# --- symbol quarantine ------------------------------------------------------


@pytest.mark.parametrize("symbol", HOLDOUT)
def test_every_holdout_symbol_is_denied_on_an_ordinary_in_window_day(symbol: str) -> None:
    d = make_policy().can_read(symbol, IN_WINDOW, ReadPurpose.EXPLORATION)
    assert not d.allowed
    assert d.decision is Decision.DENIED_HOLDOUT_SYMBOL


def test_holdout_symbol_is_denied_on_every_date_including_outside_the_window() -> None:
    policy = make_policy()
    for d in (BEFORE_D0, IN_WINDOW, HOLDOUT_DAY, AFTER_WINDOW):
        assert policy.can_read("TSLA", d, ReadPurpose.EXPLORATION).decision is (
            Decision.DENIED_HOLDOUT_SYMBOL
        )


def test_holdout_check_is_case_insensitive() -> None:
    assert make_policy().can_read("tsla", IN_WINDOW, ReadPurpose.EXPLORATION).decision is (
        Decision.DENIED_HOLDOUT_SYMBOL
    )


# --- period quarantine ------------------------------------------------------


@pytest.mark.parametrize("day", [HOLDOUT_DAY, date(2026, 10, 12), LAST_HOLDOUT_DAY])
def test_non_holdout_symbol_is_denied_during_the_holdout_period(day: date) -> None:
    d = make_policy().can_read("AAPL", day, ReadPurpose.EXPLORATION)
    assert not d.allowed
    assert d.decision is Decision.DENIED_HOLDOUT_PERIOD


def test_the_day_before_the_period_holdout_is_still_allowed() -> None:
    d = make_policy().can_read("AAPL", date(2026, 10, 5), ReadPurpose.EXPLORATION)
    assert d.allowed


def test_dates_outside_the_review_window_are_denied() -> None:
    policy = make_policy()
    assert policy.can_read("AAPL", BEFORE_D0, ReadPurpose.EXPLORATION).decision is (
        Decision.DENIED_OUTSIDE_REVIEW_WINDOW
    )
    assert policy.can_read("AAPL", AFTER_WINDOW, ReadPurpose.EXPLORATION).decision is (
        Decision.DENIED_OUTSIDE_REVIEW_WINDOW
    )


def test_d0_itself_is_in_the_window() -> None:
    assert make_policy().can_read("AAPL", REVIEW_D0, ReadPurpose.EXPLORATION).allowed


# --- out-of-universe is NOT a demotion --------------------------------------


def test_symbol_outside_the_mdq_universe_reports_unavailable_not_denied() -> None:
    """A DISC candidate MDQ never observed stays a perfectly valid candidate."""
    d = make_policy().can_read("ZZZZ", IN_WINDOW, ReadPurpose.EXPLORATION)
    assert not d.allowed
    assert d.decision is Decision.UNAVAILABLE_NOT_IN_UNIVERSE
    assert d.decision.value == "unavailable_not_in_universe"


# --- purpose ----------------------------------------------------------------


def test_holdout_evaluation_is_not_a_read_purpose() -> None:
    """The graduating-hypothesis path is a separate explicit act, never a flag."""
    assert [p.value for p in ReadPurpose] == ["exploration"]


def test_an_unrecognised_purpose_fails_closed() -> None:
    with pytest.raises(PolicyError, match="unknown read purpose"):
        make_policy().can_read("AAPL", IN_WINDOW, "holdout_evaluation")  # type: ignore[arg-type]


# --- construction guards ----------------------------------------------------


def test_empty_holdout_is_refused() -> None:
    with pytest.raises(PolicyError, match="holdout"):
        make_policy(holdout_symbols=[])


def test_holdout_symbols_must_come_from_the_universe() -> None:
    with pytest.raises(PolicyError, match="not in the MDQ universe"):
        make_policy(universe_symbols=["AAPL", "MSFT"], holdout_symbols=["TSLA"])


# --- authorize() ------------------------------------------------------------


def test_authorize_excludes_holdout_symbols_and_dates_from_the_allow_set() -> None:
    policy = make_policy()
    scope = policy.authorize(
        symbols=["AAPL", "TSLA", "NVDA", "ZZZZ"],
        session_dates=[IN_WINDOW, HOLDOUT_DAY],
    )

    assert scope.pairs == {("AAPL", IN_WINDOW), ("NVDA", IN_WINDOW)}

    # Nothing holdout-flavoured survives, on any axis.
    assert all(sym != "TSLA" for sym, _ in scope.pairs)
    assert HOLDOUT_DAY not in scope.dates()

    counts = scope.denials_by_decision()
    assert counts["denied_holdout_symbol"] == 2  # TSLA on both dates
    assert counts["denied_holdout_period"] == 2  # AAPL + NVDA on the holdout day
    assert counts["unavailable_not_in_universe"] == 2  # ZZZZ on both dates


def test_authorize_records_every_denial_for_the_discovery_ledger() -> None:
    scope = make_policy().authorize(["AAPL", "TSLA"], [IN_WINDOW, HOLDOUT_DAY])
    assert len(scope.denials) + len(scope.pairs) == 4
    assert all(not d.allowed for d in scope.denials)


def test_scope_fingerprint_is_stable_and_scope_sensitive() -> None:
    policy = make_policy()
    a = policy.authorize(["AAPL"], [IN_WINDOW])
    b = policy.authorize(["AAPL"], [IN_WINDOW])
    c = policy.authorize(["AAPL", "NVDA"], [IN_WINDOW])
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()


def test_scope_for_a_holdout_only_request_is_empty() -> None:
    scope = make_policy().authorize(["TSLA", "XOM"], [IN_WINDOW])
    assert scope.is_empty
    assert scope.symbols_for(IN_WINDOW) == frozenset()


# --- the frozen artifacts ---------------------------------------------------


def repo_config(name: str) -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / name
        if candidate.exists():
            return candidate
    raise AssertionError(f"could not locate config/{name} from {here}")


def test_policy_builds_from_the_real_frozen_artifacts() -> None:
    policy = MdqExplorationPolicy.from_config(
        universe_symbols_path=repo_config("mdq_phase_a_universe_symbols.json"),
        holdout_path=repo_config("mdq_phase_a_holdout.json"),
    )
    assert len(policy.universe) == 50
    assert policy.holdout == frozenset(HOLDOUT)
    # 10/50 = the ratified 20% quarantine.
    assert len(policy.holdout) * 5 == len(policy.universe)
    assert policy.can_read("TSLA", IN_WINDOW, ReadPurpose.EXPLORATION).decision is (
        Decision.DENIED_HOLDOUT_SYMBOL
    )


def test_real_holdout_artifact_is_STAMPED_and_matches_the_frozen_rule() -> None:
    """The 2026-08-20 stamp (PX-4b), and the counterpart of the guard it replaced.

    This test previously asserted the artifact was *unstamped* and pinned that
    state deliberately, so that stamping it would fail CI by design and force
    the stamp and the test update into one commit. This is that commit: the
    assertion is inverted rather than deleted, so the transition is visible in
    the diff instead of silently disappearing.

    The bounds are named explicitly in the artifact because the
    inclusive/exclusive reading of a bare ``A..B`` range differs by a day at
    each end -- the defect registration section 8.2 ruling 4 exists to correct.
    """
    artifact = load_holdout_artifact(repo_config("mdq_phase_a_holdout.json"))
    claim = artifact["period_holdout_dates"]

    assert claim != PERIOD_HOLDOUT_UNSTAMPED, "the artifact should now be stamped"
    assert isinstance(claim, dict), "the stamp must name its bounds, not use a bare range"
    assert claim["start_inclusive"] == "2026-10-06"
    assert claim["end_inclusive"] == "2026-10-17"
    assert claim["end_exclusive"] == "2026-10-18"

    provenance = check_period_holdout_claim(artifact, ReviewWindow.governed())
    assert provenance == "artifact_stamped_and_matches_rule"

    # And the stamped bounds are the ones the policy actually enforces.
    w = ReviewWindow.governed()
    assert w.holdout_start == date.fromisoformat(claim["start_inclusive"])
    assert w.holdout_end_exclusive == date.fromisoformat(claim["end_exclusive"])


def test_the_stamp_did_NOT_change_the_governed_symbol_quarantine() -> None:
    """The invariant the stamp had to preserve.

    ``mdq_phase_a_holdout.json`` is a genuine holdout *because it was frozen
    before capture began* (registration section 8 item 17; committed 63c0c52 on
    2026-08-17, D0 = 2026-08-19). Editing it after D0 is therefore only safe if
    the ten quarantined symbols are provably untouched.

    The artifact's own file hash necessarily changes on any edit, so it cannot
    carry that guarantee -- hence a separate canonical hash over the symbol list
    alone, plus the retained pre-stamp identity.
    """
    artifact = load_holdout_artifact(repo_config("mdq_phase_a_holdout.json"))
    symbols = artifact["holdout_symbols"]

    # 1. The set and the ORDER are both unchanged.
    assert symbols == HOLDOUT
    assert sorted(symbols) == symbols, "artifact order is the sorted order"
    assert len(symbols) == 10

    # 2. The canonical symbol-list hash is the pre-stamp value.
    canonical = hashlib.sha256(",".join(symbols).encode("utf-8")).hexdigest()
    assert canonical == HOLDOUT_SYMBOLS_SHA256
    assert artifact["holdout_symbols_sha256"] == HOLDOUT_SYMBOLS_SHA256

    # 3. The pre-D0 identity is retained as evidence, not overwritten.
    assert artifact["pre_stamp_identity"]["sha256_lf"] == PRE_STAMP_HOLDOUT_ARTIFACT_SHA256

    # 4. The universe pin the holdout was drawn from is unchanged.
    assert artifact["universe_symbols_sha256"] == UNIVERSE_SYMBOLS_SHA256


def test_a_stamped_artifact_that_disagrees_with_the_rule_is_fatal(tmp_path: Path) -> None:
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": "2026-10-01..2026-10-18",
    }
    with pytest.raises(PolicyError, match="disagrees with the frozen rule"):
        check_period_holdout_claim(artifact, ReviewWindow.governed())


def test_a_stamped_artifact_matching_the_rule_is_accepted(tmp_path: Path) -> None:
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": "2026-10-06..2026-10-18",
    }
    assert (
        check_period_holdout_claim(artifact, ReviewWindow.governed())
        == "artifact_stamped_and_matches_rule"
    )


def test_universe_drift_from_the_holdout_pin_is_fatal(tmp_path: Path) -> None:
    """If the universe file changes, the ten quarantined names no longer
    describe a 20% draw of it — fail closed rather than quarantine the wrong
    names."""
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps(UNIVERSE), encoding="utf-8")
    hold = tmp_path / "holdout.json"
    hold.write_text(
        json.dumps(
            {
                "artifact": "MDQ001_EXPLORATION_HOLDOUT",
                "holdout_symbols": HOLDOUT,
                "period_holdout_dates": PERIOD_HOLDOUT_UNSTAMPED,
                "universe_symbols_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="drawn from a different universe file"):
        MdqExplorationPolicy.from_config(universe_symbols_path=uni, holdout_path=hold)


def test_universe_pin_is_defined_over_LF_NORMALISED_bytes_not_raw_bytes() -> None:
    """The governing identity is the LF form (the Git blob) — do not "simplify".

    The holdout rule states the pin literally as
    ``sha256(universe_symbols_file_LF)``. A Windows checkout stores this file
    with CRLF, so hashing raw bytes yields a *different* digest on the
    developer's laptop than on the Linux box: the control would pass on one and
    fail closed on the other.

    ⛔ If this test fails on a fresh checkout, the fix is NEVER to re-pin the
    artifact to the working-tree byte hash — that would pass locally and fail on
    the box, where the deployed file is LF. Normalise, don't re-pin.
    """
    path = repo_config("mdq_phase_a_universe_symbols.json")
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")

    pinned = json.loads(repo_config("mdq_phase_a_holdout.json").read_text(encoding="utf-8"))[
        "universe_symbols_sha256"
    ]

    assert hashlib.sha256(lf).hexdigest() == pinned
    assert pinned == UNIVERSE_SYMBOLS_SHA256

    # And the property that makes this test worth keeping: on a CRLF checkout
    # the raw-byte hash genuinely differs, so normalisation is load-bearing
    # rather than cosmetic.
    if raw != lf:
        assert hashlib.sha256(raw).hexdigest() != pinned


def test_from_config_accepts_the_stamped_artifact_end_to_end() -> None:
    """The whole path, not just the claim checker."""
    policy = MdqExplorationPolicy.from_config(
        universe_symbols_path=repo_config("mdq_phase_a_universe_symbols.json"),
        holdout_path=repo_config("mdq_phase_a_holdout.json"),
    )
    assert policy.period_holdout_provenance == "artifact_stamped_and_matches_rule"
    assert policy.window.holdout_start == date(2026, 10, 6)
    assert policy.window.holdout_end_exclusive == date(2026, 10, 18)
    # The last quarantined day is denied; the day before the window is allowed.
    assert policy.can_read("AAPL", date(2026, 10, 17), ReadPurpose.EXPLORATION).decision is (
        Decision.DENIED_HOLDOUT_PERIOD
    )
    assert policy.can_read("AAPL", date(2026, 10, 5), ReadPurpose.EXPLORATION).allowed


def test_a_stamped_period_that_is_internally_inconsistent_is_fatal() -> None:
    """end_inclusive must be exactly one day before end_exclusive."""
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": {
            "start_inclusive": "2026-10-06",
            "end_inclusive": "2026-10-18",  # off by one
            "end_exclusive": "2026-10-18",
        },
    }
    with pytest.raises(PolicyError, match="internally inconsistent"):
        check_period_holdout_claim(artifact, ReviewWindow.governed())


def test_a_stamped_dict_that_disagrees_with_the_rule_is_fatal() -> None:
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": {
            "start_inclusive": "2026-10-01",
            "end_exclusive": "2026-10-18",
        },
    }
    with pytest.raises(PolicyError, match="disagrees with the frozen rule"):
        check_period_holdout_claim(artifact, ReviewWindow.governed())


def test_a_malformed_stamp_refuses_to_guess() -> None:
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": {"start_inclusive": "2026-10-06"},  # no end
    }
    with pytest.raises(PolicyError, match="malformed"):
        check_period_holdout_claim(artifact, ReviewWindow.governed())


def test_the_unstamped_form_is_still_recognised_and_derives_from_the_rule() -> None:
    """Retained so a regression to the placeholder is detected, not silently
    re-derived as if nothing had changed."""
    artifact = {
        "artifact": "MDQ001_EXPLORATION_HOLDOUT",
        "holdout_symbols": HOLDOUT,
        "period_holdout_dates": PERIOD_HOLDOUT_UNSTAMPED,
    }
    assert (
        check_period_holdout_claim(artifact, ReviewWindow.governed())
        == "derived_from_governed_review_window_artifact_unstamped"
    )
