"""Corporate-action adjustment verifier (R5b) + the widened R5a seam.

Pins the arithmetic on BOTH governed factor systems, the composition rules, the default-deny
applicability classifier, duplicate canonicalization, and — the load-bearing ones — that

  * a declared action suppresses the series signal only for the FACTOR it actually reconciled, and
  * an EMPTY action table cannot yield a proven verdict when either factor visibly moves.

## Every fixture here is SYNTHETIC, and models SHARADAR's column semantics explicitly

    closeunadj   the price actually traded that day
    close        the SPLIT-ADJUSTED price (the whole history is restated on each split)
    closeadj     the split-AND-distribution adjusted (total-return) price

so the two factors are `S = close/closeunadj` (split) and `D = closeadj/close` (dividend). The previous
fixtures left `closeunadj` untouched while moving `close`, which encoded the OLD, WRONG assumption that
`close` is the traded price — under it, a correctly reflected split reads as a conflict. The split
helpers below restate `close` across the whole history, which is what the vendor actually does.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.adjustment_verifier import (
    NAMED_APPLICABILITY_RULES,
    REASON_ACQUIRER_CONTINUES,
    REASON_ADR_RATIO_REFLECTED,
    REASON_DIVIDEND_REFLECTED,
    REASON_INITIAL_LISTING_METADATA,
    REASON_INITIAL_LISTING_NO_HISTORY,
    REASON_LINEAGE_EVENT_NO_ADJUSTMENT,
    REASON_MA_DISCLOSED_NONDECISION,
    REASON_RELATIONSHIP_METADATA,
    REASON_SPINOFF_AND_SPLIT_REFLECTED,
    REASON_SPINOFF_REFLECTED,
    REASON_SPLIT_AND_CASH_REFLECTED,
    REASON_SPLIT_REFLECTED,
    REASON_TICKER_CHANGE_SAME_LINEAGE,
    SATISFIES_READINESS,
    ActionApplicability,
    ActionClass,
    ActionSourceDeclaration,
    ActionStatus,
    AdjustmentVerdict,
    AdjustmentVerificationError,
    DuplicateDisposition,
    FactorKind,
    NonDecisionMADisclosure,
    SourceRowIndex,
    Tolerance,
    classify_action,
    relevance_digest,
    source_row_key,
    verify_adjustments,
)

WINDOW_START = date(2026, 6, 1)
SESSION = date(2026, 6, 30)
PRE_START = date(2026, 5, 20)

#: AAA/BBB/CCC carry history BEFORE the window, so an action on the window's first session still has a
#: prior mark. NEWCO begins exactly at `WINDOW_START` and therefore has none — the two cases the
#: one-session-before scan must keep distinct.
TICKERS = ["AAA", "BBB", "CCC"]
NEWCO = "NEWCO"
ALL_TICKERS = [*TICKERS, NEWCO]

#: Permanent identities. Deliberately NOT equal to the symbols: the explained sets are keyed by these,
#: and a test that used the symbol as its own identity could not catch a ticker-keyed regression.
PERMATICKERS = {"AAA": "100001", "BBB": "100002", "CCC": "100003", NEWCO: "100004", "NA": "100005"}

SOURCE = ActionSourceDeclaration(identity="sharadar/ACTIONS@test", authoritative=True,
                                 coverage_start=date(2020, 1, 1), coverage_end=date(2026, 12, 31))


def _sessions(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


PRE_SESSIONS = _sessions(PRE_START, WINDOW_START - timedelta(days=1))
SESSIONS = _sessions(WINDOW_START, SESSION)

EX_DATE = SESSIONS[10]
PREV = SESSIONS[9]
FIRST = SESSIONS[0]
BASE = 100.0


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _rows_for(ticker: str, sessions: list[date]) -> list[dict]:
    return [{"ticker": ticker, "date": d, "open": BASE, "high": BASE, "low": BASE, "close": BASE,
             "volume": 1_000_000, "closeadj": BASE, "closeunadj": BASE, "lastupdated": d}
            for d in sessions]


@pytest.fixture
def store(tmp_path):
    """Flat $100 across all three price series, so both factors are identically 1.0 and no adjustment
    event exists anywhere — each test then introduces exactly the one it is about."""
    st = FactorDataStore(db_path=str(tmp_path / "adj.duckdb"))
    rows: list[dict] = []
    for t in TICKERS:
        rows += _rows_for(t, PRE_SESSIONS + SESSIONS)
    rows += _rows_for(NEWCO, SESSIONS)                 # no pre-window history, by construction
    st.ingest_sep(_frame(rows))
    st.ingest_tickers(_frame([
        {"ticker": t, "permaticker": PERMATICKERS[t], "name": f"{t} CORP", "exchange": "NYSE",
         "category": "Domestic Common Stock", "sector": "Technology", "industry": "Software",
         "isdelisted": False, "firstpricedate": PRE_START, "lastpricedate": SESSION,
         "lastupdated": SESSION}
        for t in ALL_TICKERS]))
    st.record_ingest_run("actions", datetime(2026, 6, 30, 22, 0), datetime(2026, 6, 30, 22, 1),
                         0, "ok")
    yield st
    st.close()


# ── scenario builders, in SHARADAR's own semantics ───────────────────────────────────────────────────

def _apply_cash_dividend(store, ticker: str, ex: date, *, cash: float = 1.0,
                         reflected: bool = True) -> None:
    """A cash distribution: the TRADED price drops by `cash` on the ex-date and stays down, while the
    adjusted series carries the total return and is therefore unchanged.

    `reflected=False` leaves the adjusted series flat-lining with the raw one, i.e. the distribution was
    declared but never applied — the contradiction case.
    """
    px = BASE - cash
    store.con.execute("UPDATE sep SET close = ?, closeunadj = ? WHERE ticker = ? AND date >= ?",
                      [px, px, ticker, ex])
    if not reflected:
        store.con.execute("UPDATE sep SET closeadj = ? WHERE ticker = ? AND date >= ?",
                          [px, ticker, ex])


def _apply_split(store, ticker: str, ex: date, *, mult: float) -> None:
    """A split of multiplier `mult`: `closeunadj` steps on the ex-date because that is what traded,
    while `close` is restated across the WHOLE history onto the post-split basis. The split factor
    `close/closeunadj` therefore steps by exactly `mult`, and the dividend factor never moves."""
    post = BASE / mult
    store.con.execute("UPDATE sep SET close = ?, closeadj = ? WHERE ticker = ?", [post, post, ticker])
    store.con.execute("UPDATE sep SET closeunadj = ? WHERE ticker = ? AND date >= ?",
                      [post, ticker, ex])


def _apply_split_and_cash(store, ticker: str, ex: date, *, mult: float, cash: float) -> None:
    """Both on one date: the history restates onto the post-split basis, and the ex-date traded price
    additionally drops by the (post-split) cash amount."""
    post_split = BASE / mult
    post = post_split - cash
    store.con.execute("UPDATE sep SET close = ?, closeadj = ? WHERE ticker = ?",
                      [post_split, post_split, ticker])
    store.con.execute("UPDATE sep SET close = ?, closeunadj = ? WHERE ticker = ? AND date >= ?",
                      [post, post, ticker, ex])


def _move_split_factor_only(store, ticker: str, ex: date, *, mult: float) -> None:
    """Move ONLY the split factor, leaving the dividend factor alone — an undeclared split."""
    store.con.execute("UPDATE sep SET closeunadj = closeunadj / ? WHERE ticker = ? AND date >= ?",
                      [mult, ticker, ex])


def _move_dividend_factor_only(store, ticker: str, ex: date, *, factor: float) -> None:
    """Move ONLY the dividend factor — an undeclared distribution."""
    store.con.execute("UPDATE sep SET closeadj = closeadj * ? WHERE ticker = ? AND date >= ?",
                      [factor, ticker, ex])


def _add_action(store, ticker: str, when: date, action: str, value: float | None,
                contraticker: str | None = "N/A") -> None:
    """Insert one source row. `contraticker` defaults to the vendor's literal 'N/A' sentinel, which is
    what EVERY real dividend and split row carries."""
    store.con.execute("INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?)",
                      [when, action, ticker, ticker, value, contraticker])


def _verify(store, **kw):
    kw.setdefault("window_start", WINDOW_START)
    kw.setdefault("session_date", SESSION)
    kw.setdefault("relevant_tickers", TICKERS)
    kw.setdefault("source", SOURCE)
    kw.setdefault("store_identity_sha256", "store-identity-under-test")
    return verify_adjustments(store, **kw)


def _only(ev):
    assert len(ev.checks) == 1, f"expected exactly one check, got {[c.action_types for c in ev.checks]}"
    return ev.checks[0]


# ── the arithmetic, on each factor ───────────────────────────────────────────────────────────────────

def test_a_correctly_reflected_cash_dividend_is_proven(store):
    """$1 dividend on a $100 name: traded price drops to 99, the adjusted series carries the total
    return, so closeadj_t/closeadj_{t-1} == (99 + 1)/100 == 1.0."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN and ev.proven
    assert ev.adjustment_series_consistent_with_declared_actions is True
    check = _only(ev)
    assert check.action_class is ActionClass.CASH_DIVIDEND
    assert check.status is ActionStatus.PROVEN_REFLECTED
    assert check.applicability is ActionApplicability.PRICE_ADJUSTMENT_EXPECTED
    assert check.reason_code == REASON_DIVIDEND_REFLECTED
    assert check.declared_cash_per_share == 1.0
    assert check.expected_ratio == pytest.approx(1.0) and check.observed_ratio == pytest.approx(1.0)
    assert check.permaticker == PERMATICKERS["AAA"]
    # a cash distribution reconciles the DIVIDEND factor and says nothing about the split factor
    assert check.proves_dividend_factor is True and check.proves_split_factor is False


def test_a_two_for_one_split_is_proven_on_the_split_factor(store):
    """`close` is already split-adjusted, so the multiplier appears in `close/closeunadj` and CANNOT
    appear in `closeadj/close`."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.action_class is ActionClass.SPLIT
    assert check.status is ActionStatus.PROVEN_REFLECTED
    assert check.reason_code == REASON_SPLIT_REFLECTED
    assert check.declared_split_multiplier == 2.0
    assert check.observed_ratio == pytest.approx(2.0)
    assert check.proves_split_factor is True and check.proves_dividend_factor is False


def test_a_reverse_split_is_proven(store):
    """1-for-4 reverse split, multiplier 0.25: the traded price quadruples."""
    _apply_split(store, "AAA", EX_DATE, mult=0.25)
    _add_action(store, "AAA", EX_DATE, "split", 0.25)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert _only(ev).observed_ratio == pytest.approx(0.25)


def test_a_same_day_split_and_dividend_reconciles_both_factors_independently(store):
    """2:1 split plus a $0.50 post-split dividend. Each factor is proved on its own series, and the
    cash leg carries NO split multiplier — `close` already expresses the split, so re-applying it
    would double-count."""
    _apply_split_and_cash(store, "AAA", EX_DATE, mult=2.0, cash=0.5)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.action_class is ActionClass.SPLIT_AND_CASH
    assert check.reason_code == REASON_SPLIT_AND_CASH_REFLECTED
    assert check.proves_dividend_factor is True and check.proves_split_factor is True


def test_two_cash_distributions_on_one_date_sum(store):
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.5)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "AAA", EX_DATE, "distribution", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert _only(ev).declared_cash_per_share == pytest.approx(1.5)


def test_a_series_that_contradicts_the_declared_action_is_proven_not_reflected(store):
    """The dividend is declared but the adjusted series behaves as if nothing happened."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0, reflected=False)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert ev.proven is False
    assert ev.adjustment_series_consistent_with_declared_actions is False
    check = _only(ev)
    assert check.status is ActionStatus.PROVEN_NOT_REFLECTED
    assert check.proves_dividend_factor is False and check.proves_split_factor is False


def test_a_split_declared_with_the_wrong_multiplier_is_proven_not_reflected(store):
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 3.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert _only(ev).status is ActionStatus.PROVEN_NOT_REFLECTED


# ── the window edge: one prior mark, or none ─────────────────────────────────────────────────────────

def test_an_action_on_the_first_window_session_verifies_against_the_preceding_mark(store):
    """The scan reaches ONE governed session before the window so an action effective on the window's
    first session is not refused for an artifact of where the window begins (measured: NXPI, STX)."""
    _apply_cash_dividend(store, "AAA", FIRST, cash=1.0)
    _add_action(store, "AAA", FIRST, "dividend", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert _only(ev).status is ActionStatus.PROVEN_REFLECTED


def test_a_genuinely_missing_prior_mark_is_still_insufficient_data(store):
    """NEWCO's history BEGINS at the window start, so no preceding mark exists anywhere. Missing either
    side of the relationship is NOT evidence that the action was harmless."""
    _apply_cash_dividend(store, NEWCO, FIRST, cash=1.0)
    _add_action(store, NEWCO, FIRST, "dividend", 1.0)
    ev = _verify(store, relevant_tickers=[NEWCO])
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert _only(ev).status is ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA


def test_an_action_without_a_declared_value_is_insufficient_data(store):
    _add_action(store, "AAA", EX_DATE, "dividend", None)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert _only(ev).status is ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA


# ── duplicate canonicalization (items 7/8) ───────────────────────────────────────────────────────────

def test_identical_duplicate_rows_are_canonicalized_not_conflicted(store):
    """The vendor emitting the same dividend twice says the same thing twice. Treating that as a
    contradiction blocked 260 measured groups that assert nothing inconsistent."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)                  # byte-identical duplicate
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.duplicate_disposition is DuplicateDisposition.CANONICALIZED_IDENTICAL_DUPLICATES
    assert check.raw_source_row_count == 2, "the multiplicity is RETAINED, not discarded"
    assert check.canonical_row_count == 1
    assert check.status is ActionStatus.PROVEN_REFLECTED


def test_incompatible_duplicate_values_are_a_source_conflict(store):
    """Same arithmetic label, different declared values, one date — the source contradicts itself."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "split", 3.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    check = _only(ev)
    assert check.status is ActionStatus.SOURCE_CONFLICT
    assert (check.duplicate_disposition
            is DuplicateDisposition.SOURCE_CONFLICT_INCOMPATIBLE_DUPLICATES)


def test_the_canonical_action_id_is_source_derived_and_stable(store):
    """⚠ Never a DuckDB `rowid`: that is a physical address, unstable across a rebuild and meaningless
    outside the file it came from."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    first = _only(_verify(store)).canonical_action_id
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)      # a duplicate PHYSICAL row, same content
    second = _only(_verify(store)).canonical_action_id
    assert first == second and len(first) == 64


def test_duplicate_provenance_points_at_the_sealed_export_when_supplied(store):
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    key = source_row_key("AAA", EX_DATE, "dividend", 1.0, "N/A")
    index = SourceRowIndex(sealed_actions_artifact_sha256="a" * 64,
                           row_set_identity_sha256="b" * 64, lines={key: (17, 4211)})
    check = _only(_verify(store, source_row_index=index))
    assert check.source_csv_line_numbers == (17, 4211)
    assert check.sealed_actions_artifact_sha256 == "a" * 64


# ── the default-deny applicability classifier (item 5) ───────────────────────────────────────────────

def test_a_contraticker_spinoff_keeps_the_default_and_blocks(store):
    _add_action(store, "AAA", EX_DATE, "spinoff", 1.0, contraticker="SPINCO")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    assert ev.proven is False
    check = _only(ev)
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert check.reason_code is None, "the default status carries NO reason code"


def test_an_unrecognised_label_keeps_the_default(store):
    _add_action(store, "AAA", EX_DATE, "some novel corporate event", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    assert _only(ev).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_an_acquisitionby_delisting_is_never_blanket_accepted(store):
    """The acquired side is exactly the case that must stay fail-closed — 'no prices' does NOT prove
    no adjustment was required. (This is the CWAN shape.)"""
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None, contraticker="N/A")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    assert _only(ev).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_only_proven_statuses_satisfy_readiness():
    """⚠ `UNRESOLVED_NONDECISION_MA_SEMANTICS` must NEVER be in this set. It is a DISCLOSED LIMITATION,
    not a proof; admitting it would relax the gate rather than describe the evidence."""
    expected = {
        ActionStatus.PROVEN_REFLECTED,
        ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE,
        ActionStatus.PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT}
    assert expected == SATISFIES_READINESS
    assert ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS not in SATISFIES_READINESS
    # ⚠ Nor `GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT` (2026-07-31). It is a governed DISCLOSURE of
    # a factor movement, not a proof about an action: it says the movement was observed, unexplained
    # and covered by the countersigned quarantine — never that the semantics were proven, that the
    # movement was reconciled, or that the identity is decision-irrelevant.
    assert ActionStatus.GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT not in SATISFIES_READINESS
    for status in ActionStatus:
        if status not in SATISFIES_READINESS:
            assert status.name.startswith(
                ("PROVEN_NOT", "NOT_PROVEN", "SOURCE", "UNRESOLVED", "GOVERNED_QUARANTINED"))


def test_every_reason_code_emitted_is_a_named_rule(store):
    """An action leaves the default ONLY via a named, tested rule whose code appears in the evidence."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "BBB", EX_DATE, "relation", None, contraticker="OTHER")
    ev = _verify(store)
    codes = {c.reason_code for c in ev.checks if c.reason_code}
    assert codes and codes <= NAMED_APPLICABILITY_RULES


# ── the named no-adjustment rules ────────────────────────────────────────────────────────────────────

def test_relationship_metadata_with_no_factor_movement_is_proven_not_applicable(store):
    _add_action(store, "AAA", EX_DATE, "relation", None, contraticker="OTHER")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.status is ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE
    assert check.reason_code == REASON_RELATIONSHIP_METADATA
    assert (check.applicability
            is ActionApplicability.NO_SINGLE_SECURITY_PRICE_ADJUSTMENT_EXPECTED)
    # it proves NOTHING about either factor, so it can suppress nothing
    assert check.proves_dividend_factor is False and check.proves_split_factor is False


def test_a_listing_on_the_securitys_first_session_has_no_history_to_adjust(store):
    _add_action(store, NEWCO, FIRST, "listed", None)
    ev = _verify(store, relevant_tickers=[NEWCO])
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert _only(ev).reason_code == REASON_INITIAL_LISTING_NO_HISTORY


def test_a_mid_life_listing_row_still_requires_both_factors_to_be_unchanged(store):
    _add_action(store, "AAA", EX_DATE, "listed", None)
    assert _only(_verify(store)).reason_code == REASON_INITIAL_LISTING_METADATA
    # ...and once a factor moves, the rule does not fire and the default takes over
    _move_split_factor_only(store, "BBB", EX_DATE, mult=2.0)
    _add_action(store, "BBB", EX_DATE, "listed", None)
    statuses = {c.ticker: c.status for c in _verify(store).checks}
    assert statuses["BBB"] is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_a_ticker_change_within_one_lineage_is_proven_not_applicable(store):
    _add_action(store, "AAA", EX_DATE, "tickerchangeto", None, contraticker="AAAX")
    _add_action(store, "AAA", EX_DATE, "tickerchangefrom", None, contraticker="AAAO")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert _only(ev).reason_code == REASON_TICKER_CHANGE_SAME_LINEAGE


# ── the empirical bare-`acquisitionof` rule (item 6) ─────────────────────────────────────────────────

def test_a_bare_acquisitionof_with_neither_factor_moving_is_proven_not_applicable(store):
    """All four conditions hold: the subject is the ACQUIRER, no economically distinct sibling action
    is declared, the lineage continues across the date, and NEITHER governed factor moves."""
    _add_action(store, "AAA", EX_DATE, "acquisitionof", 6768.8, contraticker="TARGET")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.status is ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE
    assert check.reason_code == REASON_ACQUIRER_CONTINUES
    assert check.action_class is ActionClass.ACQUIRER_REFERENCE
    assert check.proves_dividend_factor is False and check.proves_split_factor is False


@pytest.mark.parametrize("value", [None, 0.0, 6768.8, 9792.6, 3351.8])
def test_the_acquisition_value_field_never_determines_applicability(store, value):
    """⚠⚠ `ACTIONS.value` on an acquisition row is the REPORTED TRANSACTION VALUE IN MILLIONS — never a
    per-share consideration, never an exchange ratio, never a split multiplier.

    4,565 of 4,569 `acquisitionof` rows carry a non-null value, so a `value IS NULL` check reads as
    meaningful and is not. The outcome must be IDENTICAL across every value, including null and zero;
    only the measured factor behaviour may decide.
    """
    _add_action(store, "AAA", EX_DATE, "acquisitionof", value, contraticker="TARGET")
    check = _only(_verify(store))
    assert check.status is ActionStatus.PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE
    assert check.reason_code == REASON_ACQUIRER_CONTINUES


def test_two_acquisitionof_rows_with_different_values_are_not_a_source_conflict(store):
    """An acquirer buying two companies on one date declares two transaction values. That contradicts
    NOTHING about price adjustment — `value` is not consumed by the arithmetic for this label."""
    _add_action(store, "AAA", EX_DATE, "acquisitionof", 6768.8, contraticker="TARGET1")
    _add_action(store, "AAA", EX_DATE, "acquisitionof", 9792.6, contraticker="TARGET2")
    ev = _verify(store)
    check = _only(ev)
    assert check.status is not ActionStatus.SOURCE_CONFLICT
    assert check.duplicate_disposition is DuplicateDisposition.SINGLE_SOURCE_ROW
    assert ev.verdict is AdjustmentVerdict.PROVEN


def test_a_bare_acquisitionof_does_not_clear_when_a_factor_moves(store):
    """Condition (d) is the whole point: had a hidden consideration required an adjustment, a factor
    would move — so a moving factor means the rule must NOT fire."""
    _move_split_factor_only(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "acquisitionof", 6768.8, contraticker="TARGET")
    ev = _verify(store)
    check = _only(ev)
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert check.reason_code is None


def test_an_acquisitionof_with_a_price_affecting_sibling_does_not_clear(store):
    """'No economically distinct sibling action that date' — a spinoff alongside it is exactly that."""
    _add_action(store, "AAA", EX_DATE, "acquisitionof", 6768.8, contraticker="TARGET")
    _add_action(store, "AAA", EX_DATE, "spinoff", 1.0, contraticker="SPINCO")
    assert _only(_verify(store)).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_an_acquisitionof_whose_lineage_ends_at_the_date_does_not_clear(store):
    """The acquirer must be observed on BOTH sides. NEWCO's last mark is the session itself."""
    _add_action(store, NEWCO, SESSIONS[-1], "acquisitionof", 6768.8, contraticker="TARGET")
    ev = _verify(store, relevant_tickers=[NEWCO])
    assert _only(ev).status is ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA


# ── the bounded spinoff / ADR-ratio increment (owner ruling 2026-07-30) ──────────────────────────────
#
# NARROW AND FIELD-DRIVEN. Each rule fires only when the AUTHORITATIVE RECORD supplies the mechanical
# term; every "term absent / ambiguous / conflicting" branch must fail closed. These fixtures pin both
# directions, because a rule that only ever gets tested on its happy path is a rule that will quietly
# start accepting things it should refuse.

def test_a_spinoff_with_a_declared_distribution_value_is_proven_on_the_dividend_factor(store):
    """Value leaves the parent and is distributed through another security, so an adjustment IS
    expected. `spinoffdividend.value` is the distributed value PER PARENT SHARE and composes through
    the ordinary total-return relation unchanged."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=10.0)
    _add_action(store, "AAA", EX_DATE, "spinoff", 0.25, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "spinoffdividend", 10.0, contraticker="SPINCO")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.status is ActionStatus.PROVEN_REFLECTED
    assert check.reason_code == REASON_SPINOFF_REFLECTED
    assert check.declared_cash_per_share == pytest.approx(10.0)
    # a distribution reconciles the DIVIDEND factor only — it says nothing about the split factor
    assert check.proves_dividend_factor is True and check.proves_split_factor is False


def test_the_spinoff_SHARE_RATIO_is_never_used_as_the_price_term(store):
    """⚠ `spinoff.value` is the SHARE-COUNT RATIO, not the distributed value.

    Here the ratio (0.25) and the distributed value (10.0) are deliberately far apart: if the ratio
    were consumed as the price term the expectation would be (90 + 0.25)/100 and the check would fail.
    Measured on the corpus, `spinoffdividend / spinoff` equals the contra security's close for only
    SOME groups (LBRDK 31.00 == GLIBK 31.0) and diverges materially for others (HON 98.50 vs SOLS
    48.74), so a reconstruction from ratio x price is NOT equivalent to the declared field.
    """
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=10.0)
    _add_action(store, "AAA", EX_DATE, "spinoff", 0.25, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "spinoffdividend", 10.0, contraticker="SPINCO")
    assert _only(_verify(store)).status is ActionStatus.PROVEN_REFLECTED


def test_a_spinoff_without_a_distribution_value_fails_closed(store):
    """Only an event label and a contraticker: no mechanical term. The ratio must NOT be inferred from
    the observed price movement, relative market values or the ticker relationship."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=10.0)
    _add_action(store, "AAA", EX_DATE, "spinoff", 0.25, contraticker="SPINCO")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    check = _only(ev)
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert check.reason_code is None
    assert "must not be inferred" in check.detail


def test_a_spinoff_with_a_same_date_split_reconciles_both_factors(store):
    _apply_split_and_cash(store, "AAA", EX_DATE, mult=2.0, cash=0.5)
    _add_action(store, "AAA", EX_DATE, "spinoff", 1.0, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "spinoffdividend", 0.5, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.reason_code == REASON_SPINOFF_AND_SPLIT_REFLECTED
    assert check.proves_dividend_factor is True and check.proves_split_factor is True


def test_a_spinoff_the_series_does_not_reflect_is_proven_not_reflected(store):
    """Classifying it PRICE_ADJUSTMENT_EXPECTED means it can be DISPROVEN, not just proven."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=10.0)
    _add_action(store, "AAA", EX_DATE, "spinoff", 0.25, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "spinoffdividend", 2.0, contraticker="SPINCO")   # wrong term
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert _only(ev).status is ActionStatus.PROVEN_NOT_REFLECTED


def test_an_adr_ratio_change_with_a_reciprocal_split_is_proven_on_the_split_factor(store):
    """The multiplier is taken from the `split` row, whose direction convention is already governed;
    the ADR row is admitted only as a NON-CONFLICTING CO-DECLARATION (product == 1)."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "adrratiosplit", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.status is ActionStatus.PROVEN_REFLECTED
    assert check.reason_code == REASON_ADR_RATIO_REFLECTED
    assert check.proves_split_factor is True and check.proves_dividend_factor is False


def test_an_adr_ratio_change_ALONE_fails_closed(store):
    """80 of the corpus's 383 ADR groups carry no same-date split. With no second term the DIRECTION
    of the ratio is not established, and the only available tiebreak would be the observed price
    movement — precisely the inference the ruling forbids."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "adrratiosplit", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    check = _only(ev)
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert "direction" in check.detail


def test_a_non_reciprocal_adr_and_split_pair_fails_closed(store):
    """18 of the 303 both-term groups are neither reciprocal nor equal. Conflicting same-date terms
    mean the transformation is not uniquely determined."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "adrratiosplit", 3.0)          # 3.0 x 2.0 != 1
    check = _only(_verify(store))
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert "not reciprocal" in check.detail


def test_an_adr_pair_the_series_does_not_reflect_is_proven_not_reflected(store):
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 4.0)                  # series shows 2.0
    _add_action(store, "AAA", EX_DATE, "adrratiosplit", 0.25)
    assert _only(_verify(store)).status is ActionStatus.PROVEN_NOT_REFLECTED


def test_a_proven_spinoff_does_not_suppress_an_undeclared_split(store):
    """The factor-specific rule applies to the new shapes too: a spinoff reconciles the DIVIDEND factor
    and must not silence a split-factor movement on the same session."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=10.0)
    _add_action(store, "AAA", EX_DATE, "spinoff", 0.25, contraticker="SPINCO")
    _add_action(store, "AAA", EX_DATE, "spinoffdividend", 10.0, contraticker="SPINCO")
    _move_split_factor_only(store, "AAA", EX_DATE, mult=2.0)
    ev = _verify(store)
    assert ev.factor_census.undeclared_split_factor_changes == 1
    assert ev.proven is False


# ── the two CONTEXT rulings: lineage events and disclosed acquired-side semantics ────────────────────
#
# Both need whole-pass context a single group cannot see, so both are resolved in a post-pass. Only a
# check sitting at the DEFAULT may be promoted — neither ruling can rescue a disproven or conflicting
# action.

def _spinoff_parent_and_child(store):
    """AAA distributes $10/share into NEWCO on the window's first session; NEWCO's price history begins
    exactly there. The parent's distribution is reconcilable, so the child's listing is verifiable."""
    _apply_cash_dividend(store, "AAA", FIRST, cash=10.0)
    _add_action(store, "AAA", FIRST, "spinoff", 0.25, contraticker=NEWCO)
    _add_action(store, "AAA", FIRST, "spinoffdividend", 10.0, contraticker=NEWCO)
    _add_action(store, NEWCO, FIRST, "listed", None)
    _add_action(store, NEWCO, FIRST, "spunofffrom", None, contraticker="AAA")


def test_a_child_lineage_event_clears_when_the_parent_distribution_was_reconciled(store):
    _spinoff_parent_and_child(store)
    ev = _verify(store, relevant_tickers=["AAA", NEWCO])
    by = {c.ticker: c for c in ev.checks}
    assert by["AAA"].status is ActionStatus.PROVEN_REFLECTED
    child = by[NEWCO]
    assert child.status is ActionStatus.PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT
    assert child.reason_code == REASON_LINEAGE_EVENT_NO_ADJUSTMENT
    # it reconciles NO factor, so it can suppress nothing
    assert child.proves_dividend_factor is False and child.proves_split_factor is False
    assert ev.verdict is AdjustmentVerdict.PROVEN


def test_a_child_lineage_event_fails_closed_when_the_parent_was_not_reconciled(store):
    """Without the parent's distribution proven, clearing the child would let its listing silently
    stand in for a parent adjustment nobody verified."""
    _apply_cash_dividend(store, "AAA", FIRST, cash=10.0)
    _add_action(store, "AAA", FIRST, "spinoff", 0.25, contraticker=NEWCO)   # no distribution value
    _add_action(store, NEWCO, FIRST, "listed", None)
    _add_action(store, NEWCO, FIRST, "spunofffrom", None, contraticker="AAA")
    by = {c.ticker: c for c in _verify(store, relevant_tickers=["AAA", NEWCO]).checks}
    assert by["AAA"].status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert by[NEWCO].status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_a_child_lineage_event_fails_closed_when_history_predates_the_boundary(store):
    """AAA has pre-window history, so a `spunofffrom` dated mid-window does NOT begin at its boundary —
    inherited predecessor history is exactly what this clause exists to catch."""
    _apply_cash_dividend(store, "BBB", EX_DATE, cash=10.0)
    _add_action(store, "BBB", EX_DATE, "spinoff", 0.25, contraticker="AAA")
    _add_action(store, "BBB", EX_DATE, "spinoffdividend", 10.0, contraticker="AAA")
    _add_action(store, "AAA", EX_DATE, "listed", None)
    _add_action(store, "AAA", EX_DATE, "spunofffrom", None, contraticker="BBB")
    by = {c.ticker: c for c in _verify(store).checks}
    assert by["BBB"].status is ActionStatus.PROVEN_REFLECTED
    assert by["AAA"].status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def _disclosure(*keys, digest="d" * 64):
    return NonDecisionMADisclosure(assessment_artifact_sha256=digest, entries=frozenset(keys))


def test_a_disclosed_terminal_acquisition_is_recorded_as_a_limitation_not_a_proof(store):
    """The security's series STOPS at the event and the disclosure says it is decision-irrelevant."""
    store.con.execute("DELETE FROM sep WHERE ticker = 'AAA' AND date > ?", [EX_DATE])
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)
    ev = _verify(store, relevant_tickers=["AAA"],
                 ma_disclosure=_disclosure((PERMATICKERS["AAA"], EX_DATE)))
    check = _only(ev)
    assert check.status is ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS
    assert check.reason_code == REASON_MA_DISCLOSED_NONDECISION
    assert "DISCLOSED LIMITATION, not" in check.detail
    # ★ and it STILL BLOCKS — a disclosure is not a pass
    assert ev.proven is False
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    assert check.satisfies_readiness is False


def test_a_disclosure_is_REFUSED_when_the_security_is_not_economically_terminal(store):
    """The one clause this module can verify itself. A series continuing past its own delisting needs
    successor linkage nobody has proven, so the disclosure must not be honoured."""
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)          # AAA keeps trading afterwards
    ev = _verify(store, relevant_tickers=["AAA"],
                 ma_disclosure=_disclosure((PERMATICKERS["AAA"], EX_DATE)))
    check = _only(ev)
    assert check.status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert "REFUSED" in check.detail and "not economically terminal" in check.detail


def test_a_disclosure_is_REFUSED_when_the_session_shows_an_unexplained_movement(store):
    store.con.execute("DELETE FROM sep WHERE ticker = 'AAA' AND date > ?", [EX_DATE])
    _move_dividend_factor_only(store, "AAA", EX_DATE, factor=0.97)
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)
    ev = _verify(store, relevant_tickers=["AAA"],
                 ma_disclosure=_disclosure((PERMATICKERS["AAA"], EX_DATE)))
    assert _only(ev).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS
    assert "unexplained factor movement" in _only(ev).detail


def test_a_disclosure_is_keyed_by_permanent_identity_not_ticker(store):
    """A reused symbol must not inherit another issuer's disclosure."""
    store.con.execute("DELETE FROM sep WHERE ticker = 'AAA' AND date > ?", [EX_DATE])
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)
    ev = _verify(store, relevant_tickers=["AAA"],
                 ma_disclosure=_disclosure(("AAA", EX_DATE)))       # ticker text, not permaticker
    assert _only(ev).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_without_a_disclosure_an_acquired_side_action_stays_at_the_default(store):
    store.con.execute("DELETE FROM sep WHERE ticker = 'AAA' AND date > ?", [EX_DATE])
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)
    assert _only(_verify(store, relevant_tickers=["AAA"])).status is (
        ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS)


def test_the_increment_does_not_admit_an_acquisition_shape(store):
    """⛔ NOT a general M&A valuation engine. `acquisitionby` (+`delisted`) is outside the increment and
    must remain fail-closed — 'no prices' does not prove no adjustment was required."""
    _add_action(store, "AAA", EX_DATE, "acquisitionby", 1234.5, contraticker="BUYER")
    _add_action(store, "AAA", EX_DATE, "delisted", None)
    assert _only(_verify(store)).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


# ── direction (b): TWO legs, one per factor (items 1 + 3) ────────────────────────────────────────────

def test_an_undeclared_dividend_factor_movement_is_caught(store):
    """The governed store can hold ZERO action rows while `closeadj` departs from `close`. Counting
    declared actions would call this window clean; the series says otherwise."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)                # visible, undeclared
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.proven is False
    assert ev.factor_census.undeclared_dividend_factor_changes == 1
    assert ev.factor_census.undeclared_split_factor_changes == 0
    assert ev.unexplained_examples[0].ticker == "AAA"
    assert ev.unexplained_examples[0].factor is FactorKind.DIVIDEND
    assert ev.total_actions_in_window == 0


def test_an_undeclared_split_is_caught_by_the_split_leg(store):
    """★ THE DEFECT THE SINGLE-LEG FORMULATION WAS STRUCTURALLY BLIND TO.

    `closeadj/prev_closeadj` divided by `close/prev_close` is exactly `D_t/D_{t-1}`, and a split never
    changes D — so an undeclared split moved through the old check completely undetected.
    """
    _move_split_factor_only(store, "AAA", EX_DATE, mult=2.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.factor_census.undeclared_split_factor_changes == 1
    assert ev.factor_census.undeclared_dividend_factor_changes == 0
    assert ev.unexplained_examples[0].factor is FactorKind.SPLIT


def test_a_movement_in_both_factors_is_reported_as_combined(store):
    _move_split_factor_only(store, "AAA", EX_DATE, mult=2.0)
    _move_dividend_factor_only(store, "AAA", EX_DATE, factor=0.97)
    census = _verify(store).factor_census
    assert census.combined_or_ambiguous_changes == 1
    assert census.undeclared_dividend_factor_changes == 0
    assert census.undeclared_split_factor_changes == 0


def test_a_clean_window_with_an_authoritative_source_is_no_relevant_actions(store):
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NO_RELEVANT_ACTIONS and ev.proven is True
    assert ev.adjustment_series_consistent_with_declared_actions is True
    assert ev.factor_census.total_undeclared == 0


# ── ★★ the SIX suppression tests — the factor-specific `explained` sets (item 2) ─────────────────────
#
# These are the tests the correctness fix exists for. Under the REJECTED rule ("any declared action on
# (ticker, date) explains the session") each of the first four would pass while silently losing a whole
# defect class, because there is no other assertion anywhere that would fail.

def test_a_declared_dividend_does_not_suppress_an_undeclared_split(store):
    """SUPPRESSION 1/6. A reconciled cash distribution explains the DIVIDEND factor only."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _move_split_factor_only(store, "AAA", EX_DATE, mult=2.0)             # undeclared, same session
    ev = _verify(store)
    assert ev.factor_census.undeclared_split_factor_changes == 1, (
        "the declared dividend must NOT suppress the split-factor signal")
    assert ev.factor_census.undeclared_dividend_factor_changes == 0
    assert ev.proven is False


def test_a_declared_split_does_not_suppress_an_undeclared_dividend(store):
    """SUPPRESSION 2/6. A reconciled split explains the SPLIT factor only."""
    _apply_split(store, "AAA", EX_DATE, mult=2.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _move_dividend_factor_only(store, "AAA", EX_DATE, factor=0.97)       # undeclared, same session
    ev = _verify(store)
    assert ev.factor_census.undeclared_dividend_factor_changes == 1, (
        "the declared split must NOT suppress the dividend-factor signal")
    assert ev.factor_census.undeclared_split_factor_changes == 0
    # the split itself is still correctly reflected — it is not mislabelled as unreflected
    assert _only(ev).status is ActionStatus.PROVEN_REFLECTED


def test_a_bare_acquisitionof_suppresses_neither_factor(store):
    """SUPPRESSION 3/6. It reaches a PROVEN status, but it reconciles NO factor, so it explains none."""
    _move_dividend_factor_only(store, "BBB", EX_DATE, factor=0.97)
    _add_action(store, "BBB", EX_DATE, "acquisitionof", 6768.8, contraticker="TARGET")
    ev = _verify(store)
    assert ev.factor_census.undeclared_dividend_factor_changes == 1
    assert ev.proven is False


def test_an_unsupported_action_suppresses_nothing(store):
    """SUPPRESSION 4/6."""
    _move_dividend_factor_only(store, "AAA", EX_DATE, factor=0.97)
    _add_action(store, "AAA", EX_DATE, "spinoff", 1.0, contraticker="SPINCO")
    ev = _verify(store)
    assert ev.factor_census.undeclared_dividend_factor_changes == 1
    assert _only(ev).status is ActionStatus.NOT_PROVEN_UNSUPPORTED_SEMANTICS


def test_a_split_and_cash_explains_both_factors(store):
    """SUPPRESSION 5/6. The one case that legitimately suppresses BOTH — and only because each leg was
    verified independently."""
    _apply_split_and_cash(store, "AAA", EX_DATE, mult=2.0, cash=0.5)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    census = ev.factor_census
    assert census.total_undeclared == 0
    assert census.explained_dividend_factor_sessions == 1
    assert census.explained_split_factor_sessions == 1


def test_a_failed_reconciliation_does_not_suppress_the_series_signal(store):
    """SUPPRESSION 6/6. The most dangerous case: an action that was declared, was expected to adjust,
    and did NOT reconcile must not silence the very signal that exists to catch it."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 5.0)                  # declared 5, series shows 1
    ev = _verify(store)
    assert _only(ev).status is ActionStatus.PROVEN_NOT_REFLECTED
    assert ev.factor_census.undeclared_dividend_factor_changes == 1, (
        "a PROVEN_NOT_REFLECTED action explains NEITHER factor")
    assert ev.factor_census.explained_dividend_factor_sessions == 0


def test_the_explained_sets_are_keyed_by_permanent_identity_not_ticker(store):
    """A reconciled action registers under the lineage's permanent identity. Keying by symbol would let
    a suppression cross issuers wherever a ticker is reused."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.factor_census.explained_dividend_factor_sessions == 1
    assert _only(ev).permaticker == PERMATICKERS["AAA"] != "AAA"


def test_a_security_without_a_permanent_identity_fails_closed(store):
    """No fallback to ticker identity — the whole point of the contract."""
    store.con.execute("UPDATE tickers SET permaticker = NULL WHERE ticker = 'AAA'")
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.proven is False
    assert _only(ev).status is ActionStatus.NOT_PROVEN_INSUFFICIENT_DATA


def test_a_store_without_a_permaticker_column_is_refused(store):
    store.con.execute("ALTER TABLE tickers DROP COLUMN permaticker")
    with pytest.raises(AdjustmentVerificationError, match="permaticker"):
        _verify(store)


# ── the 'N/A' sentinel, and the live ticker NA ───────────────────────────────────────────────────────

def test_the_no_contra_sentinel_is_matched_exactly_and_never_case_folded():
    """⚠ `NA` is a LIVE TICKER (Nordic American Tankers) and `N/A` is the vendor's sentinel. A
    case-folded test, or a null-token set containing 'na', would classify NA's dividends as
    contraticker events and make them unverifiable. Third instance of this defect class."""
    assert classify_action("dividend", "N/A") is ActionClass.CASH_DIVIDEND
    assert classify_action("split", "N/A") is ActionClass.SPLIT
    assert classify_action("dividend", "NA") is ActionClass.UNSUPPORTED      # a real security
    assert classify_action("dividend", "n/a") is ActionClass.UNSUPPORTED     # no case folding
    assert classify_action("dividend", "N/a") is ActionClass.UNSUPPORTED
    assert classify_action("dividend", None) is ActionClass.CASH_DIVIDEND
    assert classify_action("dividend", "nan") is ActionClass.CASH_DIVIDEND   # pandas NaN artifact


def test_the_ticker_NA_is_an_ordinary_security_and_its_dividend_verifies(tmp_path):
    """The sentinel fix must not touch the security actually named NA."""
    st = FactorDataStore(db_path=str(tmp_path / "na.duckdb"))
    st.ingest_sep(_frame(_rows_for("NA", PRE_SESSIONS + SESSIONS)))
    st.ingest_tickers(_frame([{"ticker": "NA", "permaticker": PERMATICKERS["NA"],
                               "name": "NORDIC AMERICAN TANKERS", "exchange": "NYSE",
                               "category": "Domestic Common Stock", "sector": "Energy",
                               "industry": "Shipping", "isdelisted": False,
                               "firstpricedate": PRE_START, "lastpricedate": SESSION,
                               "lastupdated": SESSION}]))
    _apply_cash_dividend(st, "NA", EX_DATE, cash=1.0)
    _add_action(st, "NA", EX_DATE, "dividend", 1.0)                      # contraticker 'N/A'
    ev = verify_adjustments(st, window_start=WINDOW_START, session_date=SESSION,
                            relevant_tickers=["NA"], source=SOURCE,
                            store_identity_sha256="na-store")
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert ev.checks[0].action_class is ActionClass.CASH_DIVIDEND
    st.close()


@pytest.mark.parametrize(("label", "contra", "expected"), [
    ("dividend", None, ActionClass.CASH_DIVIDEND),
    ("split", None, ActionClass.SPLIT),
    ("spinoff", "NEWCO", ActionClass.SPINOFF_DISTRIBUTION),
    ("merger", "ACQ", ActionClass.MERGER_CONVERSION),
    ("tickerchange", None, ActionClass.SYMBOL_TRANSITION),
    ("acquisitionof", "TARGET", ActionClass.ACQUIRER_REFERENCE),
    ("relation", "OTHER", ActionClass.RELATIONSHIP_METADATA),
    ("some novel corporate event", None, ActionClass.UNSUPPORTED),
])
def test_action_classification(label, contra, expected):
    assert classify_action(label, contra) is expected


# ── source authority ─────────────────────────────────────────────────────────────────────────────────

def test_a_source_not_declared_authoritative_can_never_prove(store):
    ev = _verify(store, source=ActionSourceDeclaration(identity="unregistered", authoritative=False))
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.declared_action_source_authoritative is False


def test_a_source_that_does_not_cover_the_window_cannot_prove(store):
    ev = _verify(store, source=ActionSourceDeclaration(
        identity="sharadar/ACTIONS@partial", authoritative=True,
        coverage_start=date(2026, 6, 15), coverage_end=date(2026, 6, 30)))
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert "coverage" in ev.detail


def test_consistency_and_source_authority_are_reported_separately(store):
    """The arithmetic proves consistency with the DECLARED rows; it cannot prove the declaration itself
    is correct. The two facts stay separate in the evidence."""
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store, source=ActionSourceDeclaration(identity="x", authoritative=False))
    assert ev.adjustment_series_consistent_with_declared_actions is False   # not evaluated
    assert ev.declared_action_source_authoritative is False
    assert ev.proven is False


# ── relevance scope + evidence ───────────────────────────────────────────────────────────────────────

def test_actions_outside_the_relevance_set_do_not_gate(store):
    _apply_cash_dividend(store, "CCC", EX_DATE, cash=1.0)
    _add_action(store, "CCC", EX_DATE, "dividend", 1.0)
    ev = _verify(store, relevant_tickers=["AAA", "BBB"])
    assert ev.verdict is AdjustmentVerdict.NO_RELEVANT_ACTIONS
    assert ev.total_actions_in_window == 1
    assert ev.relevant_actions_in_window == 0 and ev.irrelevant_actions_in_window == 1
    assert ev.relevant_ticker_count == 2


def test_the_relevance_digest_binds_the_store_identity():
    a = relevance_digest(["AAA", "BBB"], WINDOW_START, SESSION, "identity-1")
    b = relevance_digest(["AAA", "BBB"], WINDOW_START, SESSION, "identity-2")
    c = relevance_digest(["BBB", "AAA"], WINDOW_START, SESSION, "identity-1")
    assert a != b                       # same names, different store state → different digest
    assert a == c                       # order-independent
    assert len(a) == 64


def test_evidence_is_open_provenance_only(store):
    _apply_cash_dividend(store, "AAA", EX_DATE, cash=1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    d = _verify(store).to_open_provenance()
    assert d["verdict"] == "PROVEN"
    assert d["tolerance"]["price_quantum"] == 1e-4
    assert d["checks"][0]["relative_tolerance"] > 0
    assert d["checks"][0]["status"] == "PROVEN_REFLECTED"
    assert d["factor_census"]["undeclared_split_factor_changes"] == 0
    forbidden = {"strategy_return", "sharpe", "equity", "pnl", "scores", "ranking", "weights"}
    assert not (forbidden & set(d))


def test_the_census_reports_each_factor_separately_in_provenance(store):
    """A merged count cannot be read: an undeclared split and an undeclared dividend are different
    defects with different causes."""
    d = _verify(store).to_open_provenance()["factor_census"]
    for key in ("undeclared_dividend_factor_changes", "undeclared_split_factor_changes",
                "combined_or_ambiguous_changes", "explained_dividend_factor_sessions",
                "explained_split_factor_sessions", "unresolved_identity_count"):
        assert key in d, f"{key} missing from the factor census"


def test_no_relevant_securities_is_insufficient_data(store):
    ev = _verify(store, relevant_tickers=[])
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA


def test_a_non_queryable_store_fails_closed():
    with pytest.raises(AdjustmentVerificationError, match="not a queryable store"):
        verify_adjustments(object(), window_start=WINDOW_START, session_date=SESSION,
                           relevant_tickers=TICKERS, source=SOURCE)


# ── tolerance discipline ─────────────────────────────────────────────────────────────────────────────

def test_the_tolerance_scales_with_the_price_quantum():
    """A 1e-4 quantum is a far larger relative error on a $1 name than on a $100 name, so the band is
    derived from the prices involved rather than picked as a round number."""
    tol = Tolerance()
    assert tol.for_prices(100.0) == pytest.approx(5e-6)      # 5 x 1e-4 x (1/100)
    assert tol.for_prices(1.0) == pytest.approx(5e-4)
    assert tol.for_prices(100.0, 100.0, 100.0, 100.0) == pytest.approx(2e-5)   # four rounded prices
    assert tol.for_prices(1_000_000.0) == tol.relative_floor  # the floor takes over
    assert tol.for_prices() == tol.relative_floor


def test_the_noise_safety_factor_records_its_ACTUAL_factor_specific_basis(store):
    """The old evidence string claimed one universal plateau. That claim was measured on the
    SEAM-CONTAMINATED predecessor store and is RETRACTED: on the rebuilt corpus the split leg plateaus
    but the dividend leg does not, and raising the factor destroys true dividend sensitivity.

    The value is unchanged at 5.0; what changed is that the record now states why.
    """
    basis = Tolerance().basis()
    assert basis["noise_safety_factor"] == 5.0
    assert basis["noise_safety_factor_status"] == "RETAINED_ON_FACTOR_SPECIFIC_EVIDENCE"
    why = str(basis["noise_safety_factor_basis"])
    assert "did not" in why, "the evidence must NOT claim a universal plateau"
    assert "RETRACTED" in why
    assert "8,155" in why and "7,977" in why, "the true-signal loss above 5x must be stated"


def test_one_common_tolerance_is_used_for_both_legs(store):
    """Splitting the band per factor is NOT authorised without a failing fixture proving a single band
    is technically invalid. This pins that there is one band."""
    tol = Tolerance()
    assert tol.for_prices(100.0, 100.0, 100.0, 100.0) == pytest.approx(2e-5)
    # the same callable serves both legs — there is no per-factor variant to drift apart
    assert not any(a.startswith("for_split") or a.startswith("for_dividend") for a in dir(tol))


def test_a_penny_stock_rounding_difference_is_within_tolerance(store):
    """$0.50 name, a $0.01 dividend, and the adjusted series rounded at the stored 4-decimal quantum:
    consistent, and it must not be reported as a contradiction."""
    store.con.execute("UPDATE sep SET close = 0.5, closeadj = 0.5, closeunadj = 0.5 "
                      "WHERE ticker = 'BBB'")
    store.con.execute("UPDATE sep SET close = 0.49, closeunadj = 0.49, closeadj = 0.5001 "
                      "WHERE ticker = 'BBB' AND date >= ?", [EX_DATE])
    _add_action(store, "BBB", EX_DATE, "dividend", 0.01)
    ev = _verify(store, relevant_tickers=["BBB"])
    assert ev.verdict is AdjustmentVerdict.PROVEN
    check = _only(ev)
    assert check.relative_residual is not None
    assert check.relative_residual <= check.relative_tolerance


def test_a_movement_outside_tolerance_is_not_absorbed(store):
    store.con.execute("UPDATE sep SET closeadj = 100.5 WHERE ticker = 'AAA' AND date >= ?", [EX_DATE])
    _add_action(store, "AAA", EX_DATE, "dividend", 0.01)
    assert _only(_verify(store)).status is ActionStatus.PROVEN_NOT_REFLECTED


# ── A3: bounded per-action evidence ──────────────────────────────────────────────────────────────────
#
# `checks` was unbounded — one entry per relevant (ticker, ex-date) group, all of them carried into an
# IMMUTABLE observation. Both dimensions are capped now, because a count limit alone still permits an
# oversized payload from long identifiers or metadata.

def _check(ticker="AAA", when="2026-07-24", types=("dividend",), detail=""):
    from app.validation.adjustment_verifier import ActionCheck

    return ActionCheck(
        ticker=ticker, permaticker="900001", action_date=when, action_types=tuple(types),
        action_class=ActionClass.CASH_DIVIDEND,
        applicability=ActionApplicability.PRICE_ADJUSTMENT_EXPECTED,
        status=ActionStatus.PROVEN_REFLECTED, reason_code=REASON_DIVIDEND_REFLECTED,
        declared_split_multiplier=None, declared_cash_per_share=1.0, prev_close=10.0, close=11.0,
        prev_closeadj=10.0, closeadj=11.0, expected_ratio=1.1, observed_ratio=1.1,
        absolute_residual=0.0, relative_residual=0.0, absolute_tolerance=0.0,
        relative_tolerance=1e-6, verdict=AdjustmentVerdict.PROVEN, detail=detail,
        proves_dividend_factor=True)


def test_the_action_count_cap_bounds_the_payload():
    from app.validation.adjustment_verifier import bound_action_evidence

    checks = tuple(_check(ticker=f"T{i:04d}") for i in range(50))
    included, ev = bound_action_evidence(checks, max_actions=10, max_serialized_bytes=10_000_000)
    assert len(included) == 10
    assert (ev.total_action_count, ev.included_action_count, ev.omitted_action_count) == (50, 10, 40)
    assert ev.truncated is True and ev.max_actions == 10


def test_the_byte_cap_is_measured_on_the_final_canonical_serialization():
    """Not estimated from Python object sizes, which bear no relation to the recorded bytes."""
    from app.validation.adjustment_verifier import (
        _canonical_bytes,
        _check_payload,
        bound_action_evidence,
    )

    checks = tuple(_check(ticker=f"T{i:04d}") for i in range(50))
    included, ev = bound_action_evidence(checks, max_actions=1000, max_serialized_bytes=4000)
    assert ev.serialized_bytes <= 4000
    assert ev.truncated is True and ev.omitted_action_count > 0
    # the reported size IS the size of what is carried
    assert ev.serialized_bytes == len(_canonical_bytes([_check_payload(c) for c in included]))


def test_a_single_oversized_action_cannot_bypass_the_cap():
    """One entry larger than the whole budget must not be admitted 'because it is the first'.

    And it must never be admitted PARTIALLY: an action record is atomic evidence, so the prefix either
    carries it whole or not at all. A truncated record would be worse than an omitted one — it would
    look like evidence while being unreconstructable.
    """
    from app.validation.adjustment_verifier import _canonical_bytes, bound_action_evidence

    huge = _check(detail="x" * 5000)
    included, ev = bound_action_evidence((huge,), max_actions=100, max_serialized_bytes=1000)
    assert included == ()
    assert ev.included_action_count == 0 and ev.omitted_action_count == 1
    assert ev.total_action_count == 1
    assert ev.truncated is True and ev.serialized_bytes <= 1000
    # exactly the empty serialization — nothing partial was written
    assert ev.serialized_bytes == len(_canonical_bytes([]))


def test_an_oversized_leading_action_stops_the_prefix_without_skipping_ahead():
    """The prefix rule is strict: a smaller entry that sorts AFTER an oversized one is not promoted.

    Skip-and-continue would make inclusion depend on the sizes of neighbouring entries, so the same
    action set could be selected differently by an unrelated change elsewhere in the window.
    """
    from app.validation.adjustment_verifier import bound_action_evidence

    oversized = _check(ticker="AAA", when="2026-01-01", detail="x" * 5000)
    small = _check(ticker="ZZZ", when="2026-12-31")
    included, ev = bound_action_evidence(
        (oversized, small), max_actions=100, max_serialized_bytes=1500)

    assert included == (), "a later small entry must not be promoted past the stopped prefix"
    assert (ev.total_action_count, ev.included_action_count, ev.omitted_action_count) == (2, 0, 2)
    assert ev.truncated is True and ev.serialized_bytes <= 1500


def test_the_selection_order_is_deterministic_and_not_database_order():
    """Ordered by (action_date, action_types, ticker, action_digest) — never incidental row order."""
    from app.validation.adjustment_verifier import bound_action_evidence

    a = _check(ticker="ZZZ", when="2026-01-02")
    b = _check(ticker="AAA", when="2026-01-01")
    c = _check(ticker="MMM", when="2026-01-01")
    forward, _ = bound_action_evidence((a, b, c), max_actions=3, max_serialized_bytes=10_000_000)
    shuffled, _ = bound_action_evidence((c, a, b), max_actions=3, max_serialized_bytes=10_000_000)
    assert [x.ticker for x in forward] == ["AAA", "MMM", "ZZZ"]      # date first, then ticker
    assert [x.ticker for x in shuffled] == [x.ticker for x in forward]


def test_an_untruncated_payload_reports_itself_as_such():
    from app.validation.adjustment_verifier import bound_action_evidence

    checks = tuple(_check(ticker=f"T{i}") for i in range(3))
    included, ev = bound_action_evidence(checks, max_actions=100, max_serialized_bytes=10_000_000)
    assert len(included) == 3
    assert ev.truncated is False and ev.omitted_action_count == 0
    assert ev.selection_rule and "deterministic prefix" in ev.selection_rule


def test_truncating_the_payload_never_distorts_the_verdict_census(store, monkeypatch):
    """THE correctness property of A3, end to end.

    `checks_by_verdict` is how a reader learns what the omitted entries were. If it were counted over
    the bounded selection, truncation would quietly rewrite the census and a window with 40 proven
    actions would report as though it had 2 — the payload would be smaller AND the record would be
    wrong, which is worse than the unbounded version it replaced.
    """
    import app.validation.adjustment_verifier as av

    for ticker in TICKERS:
        for offset in (4, 6, 8):
            ex = SESSIONS[10 + offset]
            _add_action(store, ticker, ex, "relation", None, contraticker="OTHER")

    monkeypatch.setattr(av, "MAX_EVIDENCE_ACTIONS", 2)
    ev = _verify(store)

    counted = sum(ev.checks_by_verdict.values())
    assert ev.action_evidence is not None
    assert ev.action_evidence.truncated is True
    assert len(ev.checks) <= 2 < counted, "the payload is bounded but the census is not"
    assert counted == ev.action_evidence.total_action_count
    assert (ev.action_evidence.included_action_count + ev.action_evidence.omitted_action_count
            == ev.action_evidence.total_action_count)
    # the status census is bounded-independent too
    assert sum(ev.checks_by_status.values()) == counted


def test_the_bounded_payload_is_reported_in_open_provenance(store):
    """An operator reading the record must be able to tell a short list from a truncated one."""
    _apply_split(store, TICKERS[0], EX_DATE, mult=2.0)
    _add_action(store, TICKERS[0], EX_DATE, "split", 2.0)
    provenance = _verify(store).to_open_provenance()

    bounded = provenance["action_evidence"]
    for key in ("total_action_count", "included_action_count", "omitted_action_count",
                "serialized_bytes", "max_actions", "max_serialized_bytes", "truncated",
                "selection_rule"):
        assert key in bounded, f"{key} missing from the bounded-evidence diagnostics"
    assert bounded["truncated"] is False
