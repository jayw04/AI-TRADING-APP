"""The watchdog's in-container store query — executed for real, against a real DuckDB store.

⚠ THIS BLOCK HAD NO BEHAVIOURAL COVERAGE BEFORE. The bash harness fakes ``docker`` and feeds
a canned store report, so every per-name freshness case it exercises is a *fixture*, not this
code. The block was therefore only ever compile-checked — and the first time it ran against
the live store (2026-08-08) it produced a FAIL that would have blocked strategies 7 and 8.

What it got wrong is worth stating precisely, because the fix is easy to get wrong in the
other direction: SATS (EchoStar) stopped trading on 2026-06-12. A delisted name reports no
fresh ``lastpricedate`` and is dropped from the ranking pool — correct market mechanics. The
refresh pipeline already establishes this per symbol, with provider corroboration and a
liveness control, in ``_factor_exhaustion_evidence.json``. The watchdog did not consult it,
so it was STRICTER than the rest of the system, permanently, for a name nothing was wrong
with. Once its verdict became a dispatch veto, that over-strictness became a trading halt.

The opposite failure is worse, so every test below that grants an exemption has a sibling
proving the exemption cannot be widened into a suppressed check.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh"

TODAY = datetime.date(2026, 8, 8)
FRONTIER = datetime.date(2026, 8, 6)


HELPER = REPO_ROOT / "apps" / "backend" / "scripts" / "factor_adjudication.py"


def _query_source() -> str:
    """The store-query block, composed with the shared helper exactly as the watchdog
    composes them: helper source first, driver second, one program.

    The driver alone is no longer a runnable unit — it calls ``adjudicate`` and friends,
    which arrive over the same stdin. Composing them here is the point: it is the real
    arrangement under test, not a fragment of it.
    """
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", WATCHDOG.read_text(encoding="utf-8"), re.S)
    matching = [b for b in blocks if "DATA_UNADJUDICATED_STALE" in b]
    assert len(matching) == 1, f"expected exactly one store-query block, found {len(matching)}"
    return HELPER.read_text(encoding="utf-8") + "\n" + matching[0]


def _app_db(tmp: Path) -> Path:
    """A minimal app DB. ``operational_facts`` recomputes held/registered facts from it,
    and an unreadable DB is a FAILURE rather than an empty set — so the tests must supply
    a real one, the same as production does."""
    import sqlite3

    p = tmp / "workbench.sqlite"
    con = sqlite3.connect(p)
    con.executescript(
        """
        CREATE TABLE symbols (id INTEGER PRIMARY KEY, ticker TEXT);
        CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol_id INTEGER, qty REAL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, symbol_id INTEGER, status TEXT);
        CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT, symbols_json TEXT);
        """
    )
    con.commit()
    con.close()
    return p


def _store(tmp: Path, names: dict[str, tuple[datetime.date, datetime.date]]) -> Path:
    """names: ticker -> (sep max date, lastpricedate)."""
    duckdb = pytest.importorskip("duckdb")
    p = tmp / "factor_data.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    for ticker, (sep_max, lpd) in names.items():
        con.execute("INSERT INTO sep VALUES (?, ?, 1.0, 1.0)", [ticker, sep_max])
        con.execute("INSERT INTO tickers VALUES (?, ?)", [ticker, lpd])
    con.close()
    return p


def _run(tmp: Path, monkeypatch, capsys, *, universe, evidence, names) -> str:
    sealed = tmp / "_factor_refresh_universe_sealed.json"
    sealed.write_text(json.dumps({"as_of": "2026-08-07", "universe": universe}), encoding="utf-8")

    ev_path = tmp / "_factor_exhaustion_evidence.json"
    if evidence is not None:
        ev_path.write_text(
            evidence if isinstance(evidence, str) else json.dumps(evidence), encoding="utf-8"
        )

    for key, value in {
        "TOLERANCE": "4",
        "MAX_LAG_DAYS": "4",
        "MIN_COVERAGE": "0.98",
        "STALE_SAMPLE": "12",
        "SEALED_PATH": str(sealed),
        "EXHAUSTION_PATH": str(ev_path),
        "STORE_PATH": str(_store(tmp, names)),
        "APP_DB": str(_app_db(tmp)),
        "ET_TODAY": TODAY.isoformat(),
        "REFRESH_TZ": "America/New_York",
    }.items():
        monkeypatch.setenv(key, value)

    exec(
        compile(_query_source(), "factor-freshness.sh:<store query>", "exec"),
        {"__name__": "__main__"},
    )  # noqa: S102
    return capsys.readouterr().out


def _evidence(*symbols_and_classes) -> dict:
    """Evidence as the shared adjudicator requires it.

    ⚠ The classification written here is a CLAIM, not a verdict. It selects which records
    are adjudicable at all; the verdict is re-derived from the frontiers, corroboration
    and operational facts below. Supplying the label alone — which is all the watchdog
    used to need — now attributes nothing, which is the defect these tests pin.

    ``last_date`` is what separates the two attributable classes: a dead instrument stops
    everywhere (PROVIDER_EXHAUSTED), one outside the subscription keeps trading
    (PROVIDER_NOT_COVERED). AAPL is the liveness control.
    """
    records = []
    for symbol, claim in symbols_and_classes:
        alive = claim == "PROVIDER_NOT_COVERED"
        records.append(
            {
                "symbol": symbol,
                "expected_classification": claim,
                "requested": True,
                "request_status": "ok",
                "provider_rows_after_live_frontier": 0,
                "corroboration": {
                    "source": "alpaca",
                    "control_symbol": "AAPL",
                    "control_last_date": FRONTIER.isoformat(),
                    "last_date": FRONTIER.isoformat() if alive else None,
                },
            }
        )
    return {
        "generated_at_utc": "2026-08-05T00:44:00Z",
        "governing_authorization": "ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001",
        "symbols": records,
    }


CURRENT = (FRONTIER, FRONTIER)
DELISTED = (datetime.date(2026, 6, 12), datetime.date(2026, 6, 12))


# ═══════════════════════════════════════════════════════════════════════════════════
# THE 2026-08-08 CASE
# ═══════════════════════════════════════════════════════════════════════════════════


def test_an_adjudicated_delisting_does_not_fail_freshness(tmp_path, monkeypatch, capsys):
    """SATS exactly: in the sealed universe, dead since 06-12, adjudicated
    PROVIDER_EXHAUSTED with provider corroboration. Everything else is current. This must
    NOT report a data-freshness problem — the pool is 2/2 healthy, not 2/3 broken."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "MSFT", "SATS"],
        evidence=_evidence(("SATS", "PROVIDER_EXHAUSTED")),
        names={"AAPL": CURRENT, "MSFT": CURRENT, "SATS": DELISTED},
    )
    assert "PROBLEM" not in out, out
    assert "DATA_EXEMPT_ADJUDICATED" in out
    assert "attributed=1" in out and "assessable=2" in out and "universe=3" in out
    assert "coverage=1.0000" in out


def test_a_stale_name_that_is_NOT_adjudicated_still_fails(tmp_path, monkeypatch, capsys):
    """The check must keep working. This is the 2026-07-06 class the check exists for: a
    name silently dropped from the pool with no adjudication explaining why."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "MSFT", "ZZZZ"],
        evidence=_evidence(("SATS", "PROVIDER_EXHAUSTED")),
        names={"AAPL": CURRENT, "MSFT": CURRENT, "ZZZZ": DELISTED},
    )
    assert "PROBLEM DATA_UNADJUDICATED_STALE" in out
    assert "ZZZZ" in out


def test_provider_not_covered_is_also_exempt(tmp_path, monkeypatch, capsys):
    """The nine ETFs the provider does not cover are adjudicated the same way."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "SPY"],
        evidence=_evidence(("SPY", "PROVIDER_NOT_COVERED")),
        names={"AAPL": CURRENT},  # SPY absent from the store entirely: never covered
    )
    assert "PROBLEM" not in out, out
    assert "attributed=1" in out


def test_an_unlisted_classification_is_not_exempt(tmp_path, monkeypatch, capsys):
    """Only the two adjudicated classifications excuse a name. Anything else in the file —
    a new status, a typo, a placeholder — must not silently become an exemption."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "WEIRD"],
        evidence=_evidence(("WEIRD", "UNDER_INVESTIGATION")),
        names={"AAPL": CURRENT, "WEIRD": DELISTED},
    )
    assert "PROBLEM DATA_UNADJUDICATED_STALE" in out
    assert "WEIRD" in out


# ═══════════════════════════════════════════════════════════════════════════════════
# THE EXEMPTION MUST NOT BECOME A WAY TO SWITCH THE CHECK OFF
# ═══════════════════════════════════════════════════════════════════════════════════


def test_absent_evidence_exempts_nothing(tmp_path, monkeypatch, capsys):
    """Fail-closed direction. No evidence artifact ⇒ no name is excused, so a genuinely
    stale pool still fails. Losing the file must not quietly widen what passes."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "SATS"],
        evidence=None,
        names={"AAPL": CURRENT, "SATS": DELISTED},
    )
    assert "PROBLEM DATA_UNADJUDICATED_STALE" in out
    assert "attributed=0" in out


def test_unreadable_evidence_exempts_nothing_and_says_so(tmp_path, monkeypatch, capsys):
    """A corrupt evidence artifact is its own reportable condition — distinct from a stale
    store, and repaired differently."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "SATS"],
        evidence='{"symbols": [',
        names={"AAPL": CURRENT, "SATS": DELISTED},
    )
    assert "PROBLEM DATA_EXHAUSTION_EVIDENCE_UNREADABLE" in out
    assert "PROBLEM DATA_UNADJUDICATED_STALE" in out
    assert "attributed=0" in out


def test_an_implausibly_large_exemption_is_itself_a_failure(tmp_path, monkeypatch, capsys):
    """The attack this closes: writing a big evidence file turns the freshness check into a
    no-op. Excusing most of the pool is a suppressed check, not a healthy store — and when
    the ceiling trips, NOTHING is exempted, so the underlying staleness surfaces too."""
    universe = [f"T{i:03d}" for i in range(20)]
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=universe,
        evidence=_evidence(*[(t, "PROVIDER_EXHAUSTED") for t in universe[:15]]),
        names={t: (DELISTED if t in universe[:15] else CURRENT) for t in universe},
    )
    assert "PROBLEM DATA_EXEMPTION_IMPLAUSIBLE" in out
    assert "PROBLEM DATA_UNADJUDICATED_STALE" in out
    assert "attributed=0" in out


def test_a_wholly_exempt_universe_is_a_failure(tmp_path, monkeypatch, capsys):
    """Measuring nothing is not the same as measuring nothing wrong."""
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["SATS", "SPY"],
        evidence=_evidence(("SATS", "PROVIDER_EXHAUSTED"), ("SPY", "PROVIDER_NOT_COVERED")),
        # AAPL is in the STORE but not the universe: it only sets the frontier, so both
        # universe names are genuinely behind it. SPY is absent from the store entirely —
        # that is what "never covered" looks like; a stale date would instead describe a
        # coverage regression, which the shared rules refuse.
        names={"SATS": DELISTED, "AAPL": CURRENT},
    )
    assert "PROBLEM DATA_PER_NAME_UNASSESSABLE" in out
    assert "attributed=2" in out and "assessable=0" in out


# ═══════════════════════════════════════════════════════════════════════════════════
# THE CHECKS THAT WERE ALREADY THERE STILL WORK
# ═══════════════════════════════════════════════════════════════════════════════════


def test_a_healthy_pool_reports_no_problem(tmp_path, monkeypatch, capsys):
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=["AAPL", "MSFT"],
        evidence=_evidence(),
        names={"AAPL": CURRENT, "MSFT": CURRENT},
    )
    assert "PROBLEM" not in out, out
    assert "coverage=1.0000" in out


def test_per_name_coverage_still_fails_a_frozen_pool(tmp_path, monkeypatch, capsys):
    """2026-07-06: 301/500 names frozen while max(date) stayed green."""
    universe = [f"T{i:03d}" for i in range(10)]
    out = _run(
        tmp_path,
        monkeypatch,
        capsys,
        universe=universe,
        evidence=_evidence(),
        names={t: (DELISTED if i < 6 else CURRENT) for i, t in enumerate(universe)},
    )
    assert "PROBLEM DATA_PER_NAME_COVERAGE" in out


def test_sealed_universe_unreadable_is_a_failure(tmp_path, monkeypatch, capsys):
    sealed = tmp_path / "_factor_refresh_universe_sealed.json"
    ev = tmp_path / "_factor_exhaustion_evidence.json"
    ev.write_text(json.dumps(_evidence()), encoding="utf-8")
    sealed.write_text("{not json", encoding="utf-8")
    for key, value in {
        "TOLERANCE": "4",
        "MAX_LAG_DAYS": "4",
        "MIN_COVERAGE": "0.98",
        "STALE_SAMPLE": "12",
        "SEALED_PATH": str(sealed),
        "EXHAUSTION_PATH": str(ev),
        "STORE_PATH": str(_store(tmp_path, {"AAPL": CURRENT})),
        "APP_DB": str(_app_db(tmp_path)),
        "ET_TODAY": TODAY.isoformat(),
        "REFRESH_TZ": "America/New_York",
    }.items():
        monkeypatch.setenv(key, value)
    exec(
        compile(_query_source(), "factor-freshness.sh:<store query>", "exec"),
        {"__name__": "__main__"},
    )  # noqa: S102
    out = capsys.readouterr().out
    assert "PROBLEM DATA_PER_NAME_UNAVAILABLE" in out


def test_the_store_query_reads_the_evidence_artifact_by_its_exact_name():
    """Both the shell wrapper and the refresh pipeline derive this name independently."""
    text = WATCHDOG.read_text(encoding="utf-8")
    assert 'EXHAUSTION_BASENAME="_factor_exhaustion_evidence.json"' in text
    assert 'EXHAUSTION_PATH="$CONTAINER_EXHAUSTION"' in text
