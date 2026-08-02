"""Layer 2 — the decision window is derived, and base-corpus facts are measured.

PR #589 generalized the session constants a scalar-assignment sweep could see. Three shape classes
survived it, and this covers all three:

  1. a **tuple-bound window** — `DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))`;
  2. a **declared base-coverage edge** — `BASE_COVERAGE_THROUGH = date(2026, 7, 24)`;
  3. a **declared mutable base census** — `BASE_TICKERS_ROWS`, `BASE_MAX_LASTPRICEDATE`.

The sharpest of the three is (2), and not because it was stale. `BASE_COVERAGE_THROUGH` named the
coverage of the base *before any delta*. The lower edge of a NEW delta is the coverage of the corpus
as it now stands — base PLUS every committed delta. Those coincided exactly once, for the first
governed session, when the manifest carried no prior delta. Every later session diverges, and a
2026-07-28 delta bounded at 2026-07-24 would silently re-ingest three sessions the corpus already
holds. So `test_the_lower_edge_follows_committed_deltas` is the test that matters most here.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.validation.governed_corpus import CorpusManifest  # noqa: E402
from scripts.forward_validation._base_facts import (  # noqa: E402
    BaseFactsError,
    MeasuredBase,
    bind_delta_lower_bound,
    bind_tickers_base,
    require_delta_window,
)
from scripts.forward_validation._governed_window import (  # noqa: E402
    REQUIRED_HISTORY_SESSIONS,
    GovernedWindowError,
    governed_decision_window,
)

TOOL_DIR = BACKEND / "scripts" / "forward_validation"

SHA = "a" * 64


# ── fixtures ────────────────────────────────────────────────────────────────────────────────────


def _tickers_payload(rows: int = 21_853, cutoff: str = "2026-06-12") -> dict:
    return {
        "schema_version": "TICKERS_V2_PERMATICKER",
        "columns": ["permaticker", "ticker", "firstpricedate", "lastpricedate"],
        "rows": rows,
        "permanent_ids": rows,
        "row_identity_sha256": SHA,
        "coverage_cutoff": cutoff,
        "artifact_sha256": SHA,
        "source_identity": "SHARADAR/TICKERS",
        "countersignature": "TickersManifest_v1.0",
    }


def _manifest(*, base_coverage: str = "2026-07-24", deltas: list[str] | None = None,
              tickers_rows: int = 21_853, tickers_cutoff: str = "2026-06-12") -> CorpusManifest:
    """A corpus manifest with `deltas` committed sessions, parsed through the real typed contract."""
    return CorpusManifest.from_payload({
        "base_corpus_sha256": SHA,
        "base_coverage_through": base_coverage,
        "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
        "governed_universe_sha256": SHA,
        "governed_universe_size": 14_150,
        "actions_manifest_sha256": SHA,
        "actions_authoritative": True,
        "tickers": _tickers_payload(tickers_rows, tickers_cutoff),
        "tickers_authoritative": True,
        "security_identity_contract": "PERMATICKER_EFFECTIVE_INTERVAL_V1",
        "deltas": [
            {"session_date": d, "coverage_through": d, "sha256": SHA, "source_sha256": SHA,
             "universe_sha256": SHA, "rows": 5_881, "retrieved_at": "2026-07-29T12:21:08Z",
             "countersignature": f"GovernedDelta_{d}_v1.0", "exclusions": []}
            for d in (deltas or [])
        ],
    })


def _measured(coverage: str, *, tickers_rows: int = 21_853,
              tickers_max: str | None = "2026-06-12") -> MeasuredBase:
    return MeasuredBase(
        corpus_path=":memory:",
        sep_coverage_through=date.fromisoformat(coverage),
        tickers_rows=tickers_rows,
        tickers_max_lastpricedate=date.fromisoformat(tickers_max) if tickers_max else None,
    )


def _corpus_with_sessions(n: int, last: date) -> duckdb.DuckDBPyConnection:
    """An in-memory corpus holding `n` consecutive daily SEP sessions ending on `last`."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE)")
    con.executemany(
        "INSERT INTO sep VALUES ('AAA', ?)",
        [[date.fromordinal(last.toordinal() - i)] for i in range(n)])
    return con


# ── the derived decision window ─────────────────────────────────────────────────────────────────


def test_the_window_ends_on_the_requested_session() -> None:
    session = date(2026, 7, 28)
    con = _corpus_with_sessions(400, session)
    try:
        w0, w1 = governed_decision_window(con, session)
    finally:
        con.close()
    assert w1 == session
    assert (w1.toordinal() - w0.toordinal()) + 1 == REQUIRED_HISTORY_SESSIONS


def test_a_different_session_yields_a_different_window() -> None:
    """The whole point: the window follows the session instead of being pinned to July 27."""
    con = _corpus_with_sessions(400, date(2026, 7, 28))
    try:
        _, prev = governed_decision_window(con, date(2026, 7, 27))
        _, cur = governed_decision_window(con, date(2026, 7, 28))
    finally:
        con.close()
    assert prev == date(2026, 7, 27)
    assert cur == date(2026, 7, 28)


def test_a_corpus_that_stops_before_the_session_refuses() -> None:
    """The old constant would have scored July 28 over a window ending July 27, silently."""
    con = _corpus_with_sessions(400, date(2026, 7, 27))
    try:
        with pytest.raises(GovernedWindowError, match="does not contain the governed session"):
            governed_decision_window(con, date(2026, 7, 28))
    finally:
        con.close()


def test_a_short_window_refuses_rather_than_truncates() -> None:
    con = _corpus_with_sessions(REQUIRED_HISTORY_SESSIONS - 1, date(2026, 7, 28))
    try:
        with pytest.raises(GovernedWindowError, match="needs exactly"):
            governed_decision_window(con, date(2026, 7, 28))
    finally:
        con.close()


# ── the measured, manifest-bound base ───────────────────────────────────────────────────────────


def test_the_lower_edge_follows_committed_deltas() -> None:
    """⚠ The defect this PR exists to close.

    With the July 27 delta committed, the corpus covers through July 27 — so a July 28 delta opens at
    July 27, NOT at the base's July 24. The retired constant said 2026-07-24 and would have re-ingested
    three sessions the corpus already holds.
    """
    manifest = _manifest(base_coverage="2026-07-24", deltas=["2026-07-27"])
    lower = bind_delta_lower_bound(manifest, _measured("2026-07-27"), session=date(2026, 7, 28))
    assert lower == date(2026, 7, 27)
    assert lower != manifest.base_coverage_through


def test_july27_semantics_are_preserved() -> None:
    """The known-good construction still reproduces the value the constant carried.

    At the first governed session the manifest held no delta, so base coverage WAS the lower edge —
    which is why the constant went unnoticed. The new derivation must return exactly 2026-07-24 there.
    """
    manifest = _manifest(base_coverage="2026-07-24", deltas=[])
    lower = bind_delta_lower_bound(manifest, _measured("2026-07-24"), session=date(2026, 7, 27))
    assert lower == date(2026, 7, 24)


def test_a_store_that_disagrees_with_its_manifest_refuses() -> None:
    manifest = _manifest(base_coverage="2026-07-24", deltas=["2026-07-27"])
    with pytest.raises(BaseFactsError, match="different corpora"):
        bind_delta_lower_bound(manifest, _measured("2026-07-24"), session=date(2026, 7, 28))


@pytest.mark.parametrize("session", ["2026-07-27", "2026-07-26"])
def test_a_session_at_or_before_coverage_refuses(session: str) -> None:
    manifest = _manifest(base_coverage="2026-07-24", deltas=["2026-07-27"])
    with pytest.raises(BaseFactsError, match="historical correction"):
        bind_delta_lower_bound(manifest, _measured("2026-07-27"),
                               session=date.fromisoformat(session))


def test_delta_dates_outside_the_window_refuse() -> None:
    lower, session = date(2026, 7, 27), date(2026, 7, 28)
    require_delta_window(lower, session, ["2026-07-28"])          # in window: silent
    with pytest.raises(BaseFactsError, match="outside the governed window"):
        require_delta_window(lower, session, ["2026-07-27", "2026-07-28"])
    with pytest.raises(BaseFactsError, match="outside the governed window"):
        require_delta_window(lower, session, ["2026-07-29"])


def test_a_ticker_census_mismatch_refuses() -> None:
    manifest = _manifest(tickers_rows=21_853)
    bind_tickers_base(manifest, _measured("2026-07-27", tickers_rows=21_853))
    with pytest.raises(BaseFactsError, match="TICKERS rows"):
        bind_tickers_base(manifest, _measured("2026-07-27", tickers_rows=21_854))


def test_a_max_lastpricedate_mismatch_refuses() -> None:
    manifest = _manifest(tickers_cutoff="2026-06-12")
    bind_tickers_base(manifest, _measured("2026-07-27", tickers_max="2026-06-12"))
    with pytest.raises(BaseFactsError, match="max\\(lastpricedate\\)"):
        bind_tickers_base(manifest, _measured("2026-07-27", tickers_max="2026-07-27"))


# ── the CLI contract ────────────────────────────────────────────────────────────────────────────


def _help(tool: str) -> str:
    out = subprocess.run(  # noqa: S603
        [sys.executable, str(TOOL_DIR / f"{tool}.py"), "--help"],
        capture_output=True, text=True, cwd=BACKEND, check=False,
        env={"PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8",
             "PATH": __import__("os").environ.get("PATH", ""),
             "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize(("tool", "flag"), [
    ("build_universe_crosswalk", "--session"),
    ("build_delta_artifacts", "--base-manifest"),
    ("build_combined_delta", "--base-manifest"),
    ("build_tickers_delta", "--base-manifest"),
])
def test_the_governed_input_is_required_with_no_default(tool: str, flag: str) -> None:
    """argparse lists required options in the usage line WITHOUT surrounding brackets."""
    text = _help(tool)
    assert flag in text, f"{tool} does not expose {flag}"
    usage = text.split("options:")[0]
    assert f"[{flag}" not in usage, f"{tool}: {flag} is optional; a governed input must be required"


@pytest.mark.parametrize(("tool", "constant"), [
    ("build_universe_crosswalk", "DECISION_WINDOW = ("),
    ("build_delta_artifacts", "BASE_COVERAGE_THROUGH = "),
    ("build_combined_delta", "BASE_COVERAGE_THROUGH = "),
    ("build_tickers_delta", "BASE_TICKERS_ROWS = "),
    ("build_tickers_delta", "BASE_MAX_LASTPRICEDATE = "),
])
def test_the_retired_constants_do_not_come_back(tool: str, constant: str) -> None:
    src = (TOOL_DIR / f"{tool}.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert constant not in code, f"{tool} reintroduced {constant.strip()}"


def test_the_window_length_has_exactly_one_definition() -> None:
    """Step 5 measures the same window; two copies of the length are two things that can drift."""
    src = (TOOL_DIR / "layer2_step5_exclusion_impact_273.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "REQUIRED_HISTORY_SESSIONS = 273" not in code
    assert REQUIRED_HISTORY_SESSIONS == 273


# ── the literal invariant itself ────────────────────────────────────────────────────────────────


def _checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_layer2_date_literals", BACKEND / "scripts" / "check_layer2_date_literals.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: Every shape the sweep must catch. The first is the one PR #589 missed.
SHAPES = [
    ("tuple", 'WINDOW = (date(2025, 6, 25), date(2026, 7, 27))'),
    ("list", 'WINDOW = [date(2026, 7, 27)]'),
    ("scalar_call", 'SESSION = date(2026, 7, 27)'),
    ("iso_string", 'CUTOFF = "2026-07-27"'),
    ("dict_value", 'CFG = {"cutoff": "2026-07-27"}'),
    ("arg_default", 'def f(session=date(2026, 7, 27)): return session'),
    ("inline_compare", 'def f(d): return d <= date(2026, 7, 27)'),
    ("nested", 'CFG = {"w": [("a", date(2026, 7, 27))]}'),
]


@pytest.mark.parametrize(("shape", "code"), SHAPES, ids=[s for s, _ in SHAPES])
def test_the_sweep_catches_every_assignment_shape(shape: str, code: str, tmp_path: Path) -> None:
    mod = _checker()
    f = tmp_path / "probe.py"
    f.write_text(f"from datetime import date\n{code}\n", encoding="utf-8")
    assert mod.scan_file(f), f"the sweep missed a date literal in {shape} shape"


def test_the_sweep_ignores_commentary_and_docstrings(tmp_path: Path) -> None:
    """A line-based scan trips on prose; this codebase has been bitten by that twice.

    A tool must be able to document the constant it used to carry without having to reword its way
    past a checker.
    """
    mod = _checker()
    f = tmp_path / "probe.py"
    f.write_text(
        '"""It WAS the constant SESSION = date(2026, 7, 27), now derived from --session."""\n'
        "# Retired: DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))\n"
        "from datetime import date  # noqa: F401\n",
        encoding="utf-8")
    assert mod.scan_file(f) == []


def test_the_live_toolchain_is_clean() -> None:
    mod = _checker()
    findings: list[str] = []
    for f in sorted((BACKEND / "scripts" / "forward_validation").glob("*.py")):
        findings.extend(mod.scan_file(f))
    assert findings == [], "ungoverned date literals present:\n" + "\n".join(findings)
