#!/usr/bin/env python3
"""RANGE-002 bounded DESCRIPTIVE screen run (owner-authorized lane D).

    python run_descriptive_screen.py \\
        --spec FROZEN.json --registry RUNS.jsonl --exposure-ledger LEDGER.json \\
        --daily-snapshot SNAP.duckdb|PARQUET_DIR --snapshot-manifest MANIFEST.json \\
        --minute-bars MINUTES.duckdb --minute-feed sip --minute-ts-convention start \\
        --date-start 2016-01-01 --date-end 2016-03-31 \\
        --partition DEVELOPMENT_SELECTION|REPLAY_RNG001 --table-filter SEP \\
        --lookback-calendar-days 40 --coverage-threshold 0.98 --equity 100000 --tick 0.01 \\
        --code-sha <40 hex> --out-dir OUT \\
        [--exploratory-scope-amendment-id ID | --raw-vendor-rows-attested] \\
        (--delisting-action-value ACTION [...] | --no-delisting-evidence) \\
        [--provenance KEY=VALUE ...] [--statistics-config STATS.json] [--dry-plan]

Authorization is the weekly-meeting decision record: the frozen spec must carry a DecisionRef
(``approved``, ``run`` scope, the partition covered, byte-identical committed minutes, spec-hash
bound). Every decision-bearing value is an explicit argument; nothing is defaulted. The only
partitions this command will name are DEVELOPMENT_SELECTION (phase P3A) and REPLAY_RNG001 (phase
P2, never citable); HOLDOUT, CONFIRMATION and PAPER are not reachable from here.

Flow (all through the real APIs): load_frozen -> to_guard_view -> RunRegistry.open_run ->
authorize -> extract_params / universe_params_from_draft -> per month build_month_from_store ->
expected symbol-days (members x NYSE sessions) -> load_sessions (a missing symbol-day stays in
the denominator) -> coverage_report -> run_screen (every spec candidate) -> report.summarize ->
report.json + report.md -> close_run(COMPLETED, sha256(report.json bytes)). Any refusal after
the run row is written closes the run ABORTED; a run is never left OPEN.

Output is DESCRIPTIVE ONLY and carries the label NON_INFERENTIAL_DESCRIPTIVE: statistical
choices made after viewing it are not preregistered confirmation. Coverage below the threshold
is a DATA-QUALITY DEFECT: the report is still written, with no strategy conclusion. An optional
day-cluster bootstrap section is added only when ``--statistics-config`` is supplied (and only
when coverage is sound); it is kept separate from the descriptive tables.

Exit codes: 0 report written; 2 refused/aborted; 3 report written with a DATA-QUALITY DEFECT.
``--dry-plan`` prints the plan and exits without opening a run, a capability, or any bar.

Disclosures carried into every report: bar-level fills with all-in bps costs (execution
settings that are present in the spec are NOT simulated); the unavailable-exit valuation rule;
the NYSE schedule is not independently verified against vendor sessions; a regular-session
minute with no bar is a DATA_GAP (no independent no-trade evidence is supplied).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import sys
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb  # noqa: E402

from app.licensing.envelope import sidecar_path, write_sidecar  # noqa: E402
from app.licensing.render import stamp  # noqa: E402
from app.research.range002.data.bar_loader import load_sessions  # noqa: E402
from app.research.range002.data.manifest import (  # noqa: E402
    SEQUENTIAL_PULLS_LIMITATION,
    ManifestError,
    parse_snapshot_manifest,
    verify_snapshot_files,
)
from app.research.range002.data.store_adapter import (  # noqa: E402
    build_month_from_store,
    open_snapshot,
    universe_params_from_draft,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger  # noqa: E402
from app.research.range002.governance.model import DateRange, Partition, Phase  # noqa: E402
from app.research.range002.governance.results_guard import (  # noqa: E402
    ResultsCapability,
    authorize,
)
from app.research.range002.governance.run_registry import (  # noqa: E402
    RunRegistry,
    RunStatus,
)
from app.research.range002.governance.spec_adapter import GuardSpecView, to_guard_view  # noqa: E402
from app.research.range002.screen.coverage import (  # noqa: E402
    MISSING_NO_DATA,
    coverage_report,
    presence_from_minutes,
)
from app.research.range002.screen.errors import DataDefectError, FunnelMismatchError  # noqa: E402
from app.research.range002.screen.params import extract_params  # noqa: E402
from app.research.range002.screen.report import summarize  # noqa: E402
from app.research.range002.screen.session_calendar import expected_sessions  # noqa: E402
from app.research.range002.screen.simulate import reconcile_funnel, run_screen  # noqa: E402
from app.research.range002.screen.stats import (  # noqa: E402
    BootstrapConfig,
    build_day_matrix,
    max_statistic_test,
    mean_interval,
)
from app.research.range002.screen.types import (  # noqa: E402
    STATE_ENTERED,
    UNAVAILABLE_EXIT_VALUATION_RULE,
)
from app.research.range002.spec import decision as decision_check  # noqa: E402
from app.research.range002.spec.hashing import file_sha256  # noqa: E402
from app.research.range002.spec.loader import load_draft, load_frozen  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_DEFECT = 3

LABEL = "NON_INFERENTIAL_DESCRIPTIVE"
LABEL_SENTENCE = (
    "These are descriptive statistics only. Any statistical choice made after viewing them is "
    "not preregistered confirmation of the same results."
)
STATUS_COMPLETE = "DESCRIPTIVE_COMPLETE"
STATUS_DEFECT = "DEFECT_DATA_QUALITY_COVERAGE_BELOW_THRESHOLD"
NO_VERDICT_NOTE = (
    "Coverage is below the frozen threshold. This is a data-quality DEFECT, not a strategy "
    "result: the figures below describe incomplete data and support no strategy conclusion."
)

#: The only partitions this command can name, and the phase each one runs under.
_PARTITIONS: dict[str, tuple[Phase, Partition]] = {
    "DEVELOPMENT_SELECTION": (Phase.P3A, Partition.DEVELOPMENT_SELECTION),
    "REPLAY_RNG001": (Phase.P2, Partition.REPLAY_RNG001),
}
PARTITION_CHOICES = tuple(_PARTITIONS)

_HEX40 = frozenset("0123456789abcdef")


class DescriptiveRunRefusal(RuntimeError):
    """The run's own pre-conditions are not met (argument, scope or data-quality blocker)."""


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    status: str  # STATUS_COMPLETE | STATUS_DEFECT
    report_json: Path
    report_md: Path
    report_sha256: str
    report: dict[str, Any]
    #: the capability the run used; it is DEAD once the run is closed (kept for inspection only)
    capability: ResultsCapability


# --------------------------------------------------------------------------- helpers


def _parse_date(text: str, name: str) -> date:
    try:
        return date.fromisoformat(text) if isinstance(text, str) else text
    except (TypeError, ValueError) as exc:
        raise DescriptiveRunRefusal(f"{name} must be an ISO date: {text!r}") from exc


def _month_starts(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
    return out


def _month_last(month_start: date, end: date) -> date:
    return min(
        date(
            month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1]
        ),
        end,
    )


def _path_digest(path: Path) -> str:
    """sha256 of a file, or a combined digest of (relative path, file sha256) for a directory."""
    if path.is_file():
        return file_sha256(path)
    if path.is_dir():
        h = hashlib.sha256()
        for f in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(f.relative_to(path).as_posix().encode("utf-8") + b"\0")
            h.update(file_sha256(f).encode("ascii") + b"\n")
        return h.hexdigest()
    raise DescriptiveRunRefusal(f"{path} does not exist")


def _validate_args(
    *,
    partition: str,
    date_start: date,
    date_end: date,
    table_filter: str,
    lookback_calendar_days: int,
    coverage_threshold: float,
    equity: float,
    tick: float,
    code_sha: str,
    minute_feed: str,
    minute_ts_convention: str,
    exploratory_scope_amendment_id: str | None,
    raw_vendor_rows_attested: bool,
) -> None:
    if partition not in _PARTITIONS:
        raise DescriptiveRunRefusal(
            f"partition {partition!r} is not runnable here; only {sorted(_PARTITIONS)}"
        )
    if date_start > date_end:
        raise DescriptiveRunRefusal("date-start is after date-end")
    if date_start.day != 1:
        raise DescriptiveRunRefusal(
            "date-start must be a calendar month start: the PIT universe is defined per "
            "calendar month and its first day must lie inside the authorized range"
        )
    if not isinstance(table_filter, str) or not table_filter.strip():
        raise DescriptiveRunRefusal("table-filter must be a non-empty vendor table name")
    if lookback_calendar_days <= 0:
        raise DescriptiveRunRefusal("lookback-calendar-days must be positive")
    if not 0.0 < coverage_threshold <= 1.0:
        raise DescriptiveRunRefusal("coverage-threshold must be in (0, 1]")
    if equity <= 0 or tick <= 0:
        raise DescriptiveRunRefusal("equity and tick must be positive")
    if len(code_sha) != 40 or not set(code_sha) <= _HEX40:
        raise DescriptiveRunRefusal("code-sha must be 40 lowercase hex characters")
    if not minute_feed.strip() or not minute_ts_convention.strip():
        raise DescriptiveRunRefusal("minute-feed and minute-ts-convention must be stated")
    if exploratory_scope_amendment_id and raw_vendor_rows_attested:
        raise DescriptiveRunRefusal(
            "give EITHER exploratory-scope-amendment-id OR raw-vendor-rows-attested, not both"
        )


def _load_spec(spec_path: Path) -> tuple[GuardSpecView, Any]:
    view = to_guard_view(load_frozen(spec_path))  # edited-after-decision spec: loader refuses
    return view, load_draft(spec_path)


def _decision_block(view: GuardSpecView) -> dict[str, Any]:
    return {
        "decision": view.decision,
        "scope": list(view.decision_scope),
        "partitions": list(view.decision_partitions),
        "minutes_path": view.minutes_path,
        "minutes_sha256": view.minutes_sha256,
    }


# --------------------------------------------------------------------------- dry plan


def plan(
    *,
    spec_path: Path,
    date_start: date | str,
    date_end: date | str,
    partition: str,
    daily_snapshot: Path,
    minute_bars: Path,
    exposure_ledger_path: Path | None = None,
) -> dict[str, Any]:
    """The run plan, computed WITHOUT a capability, a run row, or any snapshot/bar access.

    The expected symbol-day count is an UPPER BOUND (universe.n x sessions): the exact count
    needs the PIT membership, which only an authorized run may read."""
    d0, d1 = _parse_date(date_start, "date-start"), _parse_date(date_end, "date-end")  # type: ignore[arg-type]
    if partition not in _PARTITIONS:
        raise DescriptiveRunRefusal(f"partition {partition!r} is not runnable here")
    view, draft = _load_spec(spec_path)
    problems: list[str] = []
    part = _PARTITIONS[partition][1]
    if view.decision != "approved":
        problems.append(f"decision is {view.decision!r}, not 'approved'")
    if "run" not in view.decision_scope:
        problems.append("decision scope lacks 'run'")
    if part.value not in view.decision_partitions:
        problems.append(f"decision does not cover {part.value}")
    try:
        decision_check.check_minutes_file(str(view.minutes_path), str(view.minutes_sha256))
    except decision_check.MinutesError as exc:
        problems.append(f"minutes: {exc}")
    sel = view.partitions.selection
    if part is Partition.DEVELOPMENT_SELECTION and not sel.contains(DateRange(d0, d1)):
        problems.append(f"range is outside the selection partition {sel.as_dict()}")
    if d0.day != 1:
        problems.append("date-start is not a calendar month start")
    months = _month_starts(d0, d1) if d0 <= d1 else []
    sessions = expected_sessions(d0, d1) if d0 <= d1 else {}
    n = draft.universe.n
    return {
        "mode": "DRY_PLAN_NO_BAR_READ",
        "label": LABEL,
        "spec_sha256": view.spec_sha256,
        "profile": view.profile,
        "decision_reference": {
            **_decision_block(view),
            "baseline_id": view.baseline_id,
            "strategy_version": view.strategy_version,
        },
        "request_scope": {
            "phase": _PARTITIONS[partition][0].value,
            "partition": part.value,
            "date_start": d0.isoformat(),
            "date_end": d1.isoformat(),
            "citable": part is not Partition.REPLAY_RNG001,
        },
        "universe_months": [m.isoformat() for m in months],
        "sessions_in_range": len(sessions),
        "universe_n": n,
        "expected_symbol_days_upper_bound": (None if n is None else int(n) * len(sessions)),
        "candidates": [c.id for c in draft.exits.candidates or []],
        "preflight_problems": problems,
        "would_be_refused": bool(problems),
        "daily_snapshot": str(daily_snapshot),
        "minute_bars": str(minute_bars),
        "note": "no snapshot opened, no bar read, no run row written, no capability issued",
    }


# --------------------------------------------------------------------------- the run


def _abort(registry: RunRegistry, run_id: str, cause: BaseException) -> None:
    try:
        state = registry.get_run(run_id)
        if state is not None and state.status is RunStatus.OPEN:
            registry.close_run(run_id, RunStatus.ABORTED, None)
    except Exception as exc:  # the original refusal still propagates, with this attached
        cause.add_note(f"ALSO FAILED to close run {run_id} ABORTED: {type(exc).__name__}: {exc}")


def _bootstrap_section(
    cap: ResultsCapability, trades: dict[str, Any], days: list[date], cfg_raw: dict[str, Any]
) -> dict[str, Any]:
    need = ("mean_block_days", "reps", "seed", "confidence", "alpha")
    missing = [k for k in need if k not in cfg_raw]
    if missing:
        raise DescriptiveRunRefusal(f"statistics config lacks {missing}")
    cfg = BootstrapConfig(
        float(cfg_raw["mean_block_days"]), int(cfg_raw["reps"]), int(cfg_raw["seed"])
    )
    matrix = build_day_matrix(cap, trades, days)
    intervals = {
        cid: dataclasses.asdict(mean_interval(cap, matrix, cid, float(cfg_raw["confidence"]), cfg))
        for cid in matrix.candidates
    }
    test = max_statistic_test(cap, matrix, float(cfg_raw["alpha"]), cfg)
    return {
        "section": "OPTIONAL_BOOTSTRAP",
        "separate_from_descriptive_tables": True,
        "preregistered": False,
        "note": (
            "Supplied at run time via --statistics-config, not frozen in the spec; it is not "
            "preregistered confirmation and selects no candidate."
        ),
        "config": dataclasses.asdict(cfg),
        "mean_net_r_intervals": intervals,
        "max_statistic_test": dataclasses.asdict(test),
    }


def _render_md(rep: dict[str, Any]) -> str:
    def f(x: Any) -> str:
        return "n/a" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))

    L: list[str] = []
    L.append(f"# RANGE-002 descriptive screen - {rep['label']}\n")
    L.append(f"**{rep['label_sentence']}**\n")
    L.append(f"- Status: `{rep['status']}`")
    if rep["status"] != STATUS_COMPLETE:
        L.append(f"- **{NO_VERDICT_NOTE}**")
    r, s, d = rep["run"], rep["spec"], rep["decision_reference"]
    L.append(
        f"- Run id: `{r['run_id']}` (phase {r['phase']}, partition {r['partition']}, "
        f"citable: {r['citable']})"
    )
    L.append(
        f"- Spec sha256: `{s['sha256']}`; baseline `{s['baseline_id']}`, "
        f"strategy version `{s['strategy_version']}`"
    )
    L.append(
        f"- Decision: {d['decision']} scope {d['scope']} partitions {d['partitions']}; "
        f"minutes `{d['minutes_path']}` sha256 `{d['minutes_sha256']}`"
    )
    L.append(
        f"- Authorized dates: {rep['authorized_range']['start']} .. "
        f"{rep['authorized_range']['end']}"
    )
    dt = rep["data"]
    L.append(
        f"- Data: daily `{dt['daily_snapshot']['path']}` ({dt['daily_snapshot']['sha256']}); "
        f"minutes `{dt['minute_bars']['path']}` ({dt['minute_bars']['sha256']}); "
        f"manifest sha256 `{dt['snapshot_manifest_sha256']}`; code `{dt['code_sha']}`; "
        f"universe scope {dt['universe_scopes']}"
    )
    if dt["snapshot_manifest"].get("limitation"):
        sm = dt["snapshot_manifest"]
        L.append(
            f"- **{sm['limitation']}** Opt-in reference: `{sm['sequential_pulls_opt_in_ref']}`; "
            f"manifest integrity checks all passed: {sm['integrity_all_passed']}"
        )
    if dt["provenance"]:
        L.append(f"- Provenance supplied: {dt['provenance']}")
    c = rep["coverage"]
    L.append("\n## Coverage (every expected PIT symbol-day is in the denominator)\n")
    L.append(
        f"- expected {c['expected']}, legitimate exclusions {c['legitimate_exclusions']}, "
        f"denominator {c['denominator']}, observed {c['observed']}, "
        f"rate {f(c['coverage_rate'])} (threshold {c['threshold']}, "
        f"meets: {c['meets_threshold']})"
    )
    L.append(
        f"- unresolved missingness: no-data {c['missing_no_data']}, identity-mapping "
        f"{c['missing_identity_mapping']}, unexplained {c['unresolved_unexplained']}"
    )
    L.append("\n| year | expected | observed |\n|---|---|---|")
    for y, row in sorted(c["by_year"].items()):
        L.append(f"| {y} | {row['expected']} | {row['observed']} |")
    o = rep["or_completeness"]
    L.append(
        f"\n- OR completeness (max DATA_GAP minutes {o['or_max_gap_minutes']}): "
        f"{o['complete_count']} complete; of observed {f(o['of_observed'])}, "
        f"of expected {f(o['of_expected'])}"
    )
    fu = rep["funnel"]
    L.append("\n## Funnel\n")
    L.append(f"- eligible (loaded) symbol-days {fu['eligible']}; states {fu['states']}")
    L.append(f"- reconciliation: {fu['reconciliation']}")
    L.append("\n## Candidates (descriptive, R units, all candidates)\n")
    L.append(
        "| candidate | trades | days | mean R base | total R base | PF base | win base | "
        "mean R stress | total R stress | maxDD (R, daily) | unexecutable exits |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for cid, sm in rep["candidates"].items():
        b, st = sm["base"], sm["stress"]
        L.append(
            f"| {cid} | {sm['trades']} | {sm['traded_days']} | {f(b['mean_net_r'])} | "
            f"{f(b['total_net_r'])} | {f(b['profit_factor'])} | {f(b['win_rate'])} | "
            f"{f(st['mean_net_r'])} | {f(st['total_net_r'])} | "
            f"{f(sm['max_drawdown_r_daily'])} | {sm['unexecutable_exits']} |"
        )
    u = rep["unavailable_exit_valuation"]
    L.append(
        f"\n- Unavailable-exit valuation rule: `{u['rule']}`; unexecutable exits by "
        f"candidate: {u['unexecutable_by_candidate']}"
    )
    e = rep["execution_disclosure"]
    L.append(
        f"- Execution realism: **{e['execution_realism']}**. {e['statement']} "
        f"Unmodelled spec fields present: {e['unmodelled_fields_present']}"
    )
    L.append(f"- Exposure: {rep['exposure_note']}")
    for lim in rep["limitations"]:
        L.append(f"- Limitation: {lim}")
    if rep.get("optional_bootstrap"):
        L.append("\n## Optional bootstrap (separate; not preregistered)\n")
        L.append(
            "```json\n" + json.dumps(rep["optional_bootstrap"], indent=2, default=str) + "\n```"
        )
    L.append(f"\n**{rep['label']}**: {rep['label_sentence']}\n")
    return "\n".join(L)


@dataclass(frozen=True)
class FetchPlan:
    """Opt-in: acquire the SIP minute bars INSIDE this governed run, with this run's capability.

    One authorization, one attempt: the acquisition and the screen are the same run, so a fetch
    never consumes an attempt of its own and a closed run's capability can neither fetch nor
    screen. The universe fetched is the run's own monthly top-N union; ``universe_sha256`` binds
    it to the list reviewed beforehand (``build_fetch_universe``)."""

    universe_sha256: str
    journal_path: Path
    key_env: str
    secret_env: str
    requests_per_minute: int
    max_requests: int
    asof: str
    authorization_id: str
    permitted_use_ref: str
    entitlement_ref: str
    permission_basis_claimed: str
    storage_permitted: bool
    #: a store/journal left by an earlier run may be reused only with this explicit statement:
    #: the re-run is a NEW governed attempt (it draws on the attempt budget again)
    acknowledge_new_attempt_ref: str | None = None
    #: explicit request symbol + provenance for EVERY universe symbol (build_symbol_mapping.py)
    symbol_map_path: Path | None = None
    symbol_map_sha256: str | None = None
    limit: int = 10000
    max_pages: int = 100
    max_retries: int = 5
    transport_factory: Any = None  # test seam: (capability, authorization) -> transport
    environ: Any = None  # test seam


def _load_symbol_mapping(plan: FetchPlan) -> dict[str, Any]:
    """The explicit, hash-bound request-symbol mapping (``build_symbol_mapping.py``). Refused when
    missing, altered, or when any entry is UNVERIFIED: nothing is guessed or silently dropped."""
    path = plan.symbol_map_path
    if path is None or not plan.symbol_map_sha256:
        raise DescriptiveRunRefusal(
            "fetch: --fetch-symbol-map and --fetch-symbol-map-sha256 are required: every symbol "
            "needs an explicit request symbol and provenance before anything is requested"
        )
    if not Path(path).is_file():
        raise DescriptiveRunRefusal(f"fetch: symbol mapping {path} does not exist")
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != plan.symbol_map_sha256:
        raise DescriptiveRunRefusal(
            "fetch: the symbol mapping file does not match its bound sha256"
        )
    doc = json.loads(data.decode("utf-8"))
    if doc.get("schema") != "range002.symbol_mapping.v1":
        raise DescriptiveRunRefusal(
            "fetch: symbol mapping schema is not range002.symbol_mapping.v1"
        )
    bad = [
        e["vendor_ticker"] for e in doc.get("entries", []) if e.get("provenance") == "UNVERIFIED"
    ]
    if bad or doc.get("unverified"):
        raise DescriptiveRunRefusal(f"fetch: symbol mapping has UNVERIFIED symbols {bad}")
    return doc


def _fetch_module() -> Any:
    name = "fetch_sip_minutes"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "fetch_sip_minutes.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DescriptiveRunRefusal(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _symbols_sha256(symbols: list[str]) -> str:
    """SHA-256 of the one-symbol-per-line list ``build_fetch_universe`` writes."""
    return hashlib.sha256("".join(f"{s}\n" for s in symbols).encode("utf-8")).hexdigest()


def _fetch_preflight(plan: FetchPlan, minute_bars: Path) -> None:
    """Refusals that must happen BEFORE a run row exists, so a refusal consumes no attempt."""
    if not plan.storage_permitted:
        raise DescriptiveRunRefusal(
            "fetch needs --fetch-storage-permitted (recorded, not verified)"
        )
    for name in ("key_env", "secret_env", "asof", "authorization_id", "permitted_use_ref",
                 "entitlement_ref", "permission_basis_claimed"):  # fmt: skip
        if not str(getattr(plan, name)).strip():
            raise DescriptiveRunRefusal(f"fetch plan: {name} is empty")
    if plan.requests_per_minute <= 0 or plan.max_requests <= 0 or plan.max_retries < 0:
        raise DescriptiveRunRefusal(
            "fetch plan: requests-per-minute and max-requests must be positive"
        )
    if len(plan.universe_sha256) != 64:
        raise DescriptiveRunRefusal("fetch plan: universe sha256 must be 64 hex")
    _load_symbol_mapping(plan)  # refuses missing / altered / UNVERIFIED before an attempt exists
    have_store, have_journal = Path(minute_bars).exists(), plan.journal_path.exists()
    if have_store != have_journal:
        raise DescriptiveRunRefusal(
            "fetch: the minute store and its journal must both exist (resume) or both be absent"
        )
    if have_store and not (plan.acknowledge_new_attempt_ref or "").strip():
        raise DescriptiveRunRefusal(
            "fetch: a store/journal from an earlier run exists. Re-running is a NEW governed "
            "attempt; pass --fetch-acknowledge-new-attempt-ref naming the recorded decision. "
            "Nothing was opened and no attempt was consumed."
        )


def _verify_cache(store: Path, journal: Path) -> dict[str, Any]:
    """Every journaled window must match the store exactly (rows, first and last timestamp), and
    the store must hold nothing outside the journaled windows. Returns a summary or raises."""
    lines = [
        json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    chunks = [r for r in lines if r.get("type") == "chunk"]
    con = duckdb.connect(str(store), read_only=True)
    try:
        defects: list[str] = []
        total = 0
        for c in chunks:
            lo, _, hi = c["chunk_key"].partition("|")
            row = con.execute(
                "SELECT COUNT(*), MIN(ts), MAX(ts) FROM minute_bars "
                "WHERE symbol = ? AND ts >= CAST(? AS TIMESTAMP) AND ts < CAST(? AS TIMESTAMP)",
                [c["symbol"], lo, hi],
            ).fetchone()
            assert row is not None
            n, t0, t1 = row
            total += int(n)
            if int(n) != int(c["bars"]):
                defects.append(f"{c['symbol']} {lo}: store {n} rows != journal {c['bars']}")
            if c["bars"] and (
                str(t0).replace(" ", "T") != c["min_ts_utc"].rstrip("Z")
                or str(t1).replace(" ", "T") != c["max_ts_utc"].rstrip("Z")
            ):
                defects.append(f"{c['symbol']} {lo}: first/last timestamp differ from the journal")
        stored_row = con.execute("SELECT COUNT(*) FROM minute_bars").fetchone()
        stored = int(stored_row[0]) if stored_row else 0
        if stored != total:
            defects.append(f"store holds {stored} rows, journaled windows account for {total}")
        bad_row = con.execute(
            "SELECT COUNT(*) FROM minute_bars WHERE basis IS NULL OR basis <> 'raw'"
        ).fetchone()
        bad_basis = int(bad_row[0]) if bad_row else 0
        if bad_basis:
            defects.append(f"{bad_basis} stored rows are not basis 'raw'")
        if defects:
            raise DataDefectError("cached/acquired bars fail integrity: " + "; ".join(defects[:5]))
        return {"windows": len(chunks), "rows": stored, "all_windows_match_journal": True}
    finally:
        con.close()


def _acquire(
    cap: Any,
    plan: FetchPlan,
    *,
    builds: list[Any],
    daily_con: Any,
    table_filter: str,
    authorized: DateRange,
    sessions_cal: Any,
    view: Any,
    code_sha: str,
    manifest_sha: str,
    minute_bars: Path,
    run_id: str,
    out_dir: Path,
) -> tuple[dict[str, Any], Path]:
    """Fetch inside the authorized run, then validate before anything is screened."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.research.range002.data.alpaca_transport import AlpacaTransportConfig
    from app.research.range002.data.fetch_adapter import (
        REQUIRED_ADJUSTMENT,
        REQUIRED_FEED,
        FetchAuthorization,
        fetch_symbol_window,
        vendor_transport,
    )
    from app.research.range002.spec.hashing import file_sha256

    fm = _fetch_module()
    symbols = sorted({m.vendor_ticker for mb in builds for m in mb.universe.members})
    got_sha = _symbols_sha256(symbols)
    if got_sha != plan.universe_sha256:
        raise DataDefectError(
            f"the run's own monthly universe ({len(symbols)} symbols, sha256 {got_sha[:16]}) "
            f"differs from the bound fetch universe (sha256 {plan.universe_sha256[:16]}); "
            "nothing was requested"
        )
    d0, d1 = authorized.start, authorized.end
    auth = FetchAuthorization(
        plan.authorization_id, plan.permitted_use_ref, plan.entitlement_ref, plan.storage_permitted
    )
    mapping = _load_symbol_mapping(plan)
    entries = {e["vendor_ticker"]: e for e in mapping["entries"]}
    if set(entries) != set(symbols):
        raise DataDefectError(
            f"the symbol mapping covers {len(entries)} symbols but the run's universe has "
            f"{len(symbols)}; missing={sorted(set(symbols) - set(entries))[:5]} "
            f"extra={sorted(set(entries) - set(symbols))[:5]}; nothing was requested"
        )
    amap = {v: e["request_symbol"] for v, e in entries.items() if e["request_symbol"] != v}
    binding = {
        "symbol_map": dict(sorted(amap.items())),
        "symbol_mapping_sha256": plan.symbol_map_sha256,
        "symbol_mapping_by_provenance": mapping.get("by_provenance"),
        "spec_sha256": view.spec_sha256,
        "baseline_id": view.baseline_id,
        "strategy_version": view.strategy_version,
        "date_from": d0.isoformat(),
        "date_to": d1.isoformat(),
        "universe_sha256": plan.universe_sha256,
        "symbols": len(symbols),
        "feed": REQUIRED_FEED,
        "adjustment": REQUIRED_ADJUSTMENT,
        "max_requests": plan.max_requests,
        "requests_per_minute": plan.requests_per_minute,
        "snapshot_manifest_sha256": manifest_sha,
        "code_sha": code_sha,
    }
    if plan.transport_factory is not None:
        transport = plan.transport_factory(cap, auth)
    else:
        transport = vendor_transport(
            cap,
            auth,
            config=AlpacaTransportConfig(
                key_env=plan.key_env,
                secret_env=plan.secret_env,
                requests_per_minute=plan.requests_per_minute,
                max_retries=plan.max_retries,
                max_requests=plan.max_requests,
                environ=plan.environ,
            ),
        )
    attempts = getattr(transport, "__dict__", {}).get("http_attempts", lambda: 0)
    planned = fm.plan(symbols, d0, d1, plan.limit)  # an ESTIMATE; actuals are counted separately
    evidence_path = out_dir / f"acquisition_evidence_{run_id}.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_evidence(doc: dict[str, Any]) -> None:
        tmp = evidence_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(doc, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        tmp.replace(evidence_path)

    evidence: dict[str, Any] = {
        "schema": "range002.acquisition_evidence.v1",
        "run_id": run_id,
        "binding": binding,
        "planned_estimate": planned,
        "actual": {"http_attempts": None, "bars_returned": None},
        "probe": None,
        "status": "STARTED",
    }
    write_evidence(evidence)
    try:
        resumed = Path(minute_bars).exists()
        probe: dict[str, Any] | None = None
        if not resumed:
            # a small first request inside this authorized run: one symbol, thirty minutes at the
            # open of the first session. It verifies the envelope, feed, timestamps and that the
            # symbol has data BEFORE the bulk acquisition; it counts against the same cap.
            first_day = sorted(sessions_cal)[0]
            et = ZoneInfo("America/New_York")
            lo = datetime.combine(first_day, datetime.min.time(), tzinfo=et).replace(
                hour=9, minute=30
            )
            start = lo.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            end = start + timedelta(minutes=30)
            res = fetch_symbol_window(
                cap, transport, symbol=symbols[0], start_utc=start, end_utc=end,
                feed=REQUIRED_FEED, adjustment=REQUIRED_ADJUSTMENT, asof=plan.asof,
                limit=100, max_pages=1,
            )  # fmt: skip
            probe = {
                "symbol": symbols[0],
                "window_start_utc": start.isoformat() + "Z",
                "bars": len(res.bars),
                "first_bar_utc": res.bars[0].t.isoformat() + "Z" if res.bars else None,
                "first_bar_is_0930_et": bool(res.bars and res.bars[0].t == start),
                "http_attempts_after_probe": attempts(),
            }
            evidence["probe"] = probe
            write_evidence(evidence)
            if not res.bars:
                raise DataDefectError(
                    "first request returned no bars for the first symbol at the open of the first "
                    "session: entitlement, availability or symbol mapping must be investigated; "
                    "the bulk acquisition was not started"
                )
            if not probe["first_bar_is_0930_et"]:
                raise DataDefectError(
                    "timestamp convention evidence contradicts 'start': the first bar for the "
                    f"first symbol is {probe['first_bar_utc']}, not the 09:30 ET interval start "
                    f"{probe['window_start_utc']}; the bulk acquisition was not started"
                )
        cfg = fm.RunConfig(
            mode="store",
            symbols=tuple(symbols),
            date_from=d0,
            date_to=d1,
            asof=plan.asof,
            limit=plan.limit,
            max_pages=plan.max_pages,
            universe_sha256=plan.universe_sha256,
            requests_per_minute=plan.requests_per_minute,
            max_requests=plan.max_requests,
            authorization=auth,
            permission_basis_claimed=plan.permission_basis_claimed,
            store_path=Path(minute_bars),
            journal_path=plan.journal_path,
            script_sha256=file_sha256(Path(fm.__file__)),
            binding=binding,
            symbol_map={v: (a, plan.asof) for v, a in amap.items()},
        )
        fm.run_fetch(cap, transport, cfg, http_attempts=attempts)
        cache = _verify_cache(Path(minute_bars), plan.journal_path)
        lines = [
            json.loads(ln)
            for ln in plan.journal_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        chunks = [r for r in lines if r.get("type") == "chunk"]
        days = [d for c in chunks for d in c.get("days", [])]
        evidence["actual"] = {
            "http_attempts": attempts(),
            "http_requests_in_journal_windows": sum(int(c.get("http_requests", 0)) for c in chunks),
            "bars_returned": sum(int(c["bars"]) for c in chunks),
            "windows": len(chunks),
            "resumed_from_existing_store": resumed,
        }
        evidence["convention_check"] = fm.convention_summary(days)
        evidence["cache_integrity"] = cache
        evidence["store_sha256"] = file_sha256(Path(minute_bars))
        evidence["status"] = "ACQUIRED_VALIDATED"
        write_evidence(evidence)
    except BaseException as exc:
        evidence["status"] = f"FAILED: {type(exc).__name__}"
        evidence["actual"]["http_attempts"] = attempts()
        write_evidence(evidence)
        raise
    return evidence, evidence_path


def _count_by(items: Any) -> dict[str, int]:
    """Deterministic label -> count mapping (sorted keys) for the report."""
    out: dict[str, int] = {}
    for it in items:
        out[str(it)] = out.get(str(it), 0) + 1
    return dict(sorted(out.items()))


def _delisting_events(con: Any, action_values: tuple[str, ...]) -> dict[str, list[date]]:
    """ACTIONS rows whose action is one of the EXPLICITLY supplied values, by ticker.

    The vendor's exact action strings are not documented, so none is assumed: with no values no
    event is returned and nothing is ever excluded."""
    if not action_values:
        return {}
    marks = ", ".join("?" for _ in action_values)
    rows = con.execute(
        f'SELECT ticker, CAST(date AS DATE) FROM "actions" WHERE lower(action) IN ({marks})',
        [a.lower() for a in action_values],
    ).fetchall()
    out: dict[str, list[date]] = {}
    for ticker, day in rows:
        if ticker is not None and day is not None:
            out.setdefault(str(ticker).strip(), []).append(day)
    return out


def run(
    *,
    spec_path: Path,
    registry_path: Path,
    exposure_ledger_path: Path,
    daily_snapshot: Path,
    snapshot_manifest: Path,
    minute_bars: Path,
    minute_feed: str,
    minute_ts_convention: str,
    date_start: date | str,
    date_end: date | str,
    partition: str,
    table_filter: str,
    lookback_calendar_days: int,
    coverage_threshold: float,
    equity: float,
    tick: float,
    code_sha: str,
    out_dir: Path,
    delisting_actions: tuple[str, ...],
    exploratory_scope_amendment_id: str | None = None,
    raw_vendor_rows_attested: bool = False,
    provenance: dict[str, str] | None = None,
    statistics_config: dict[str, Any] | None = None,
    allow_sequential_pulls_ref: str | None = None,
    fetch_plan: FetchPlan | None = None,
) -> RunOutcome:
    """Execute one authorized descriptive run. Raises on any refusal; never leaves a run OPEN."""
    d0, d1 = _parse_date(date_start, "date-start"), _parse_date(date_end, "date-end")  # type: ignore[arg-type]
    _validate_args(
        partition=partition,
        date_start=d0,
        date_end=d1,
        table_filter=table_filter,
        lookback_calendar_days=lookback_calendar_days,
        coverage_threshold=coverage_threshold,
        equity=equity,
        tick=tick,
        code_sha=code_sha,
        minute_feed=minute_feed,
        minute_ts_convention=minute_ts_convention,
        exploratory_scope_amendment_id=exploratory_scope_amendment_id,
        raw_vendor_rows_attested=raw_vendor_rows_attested,
    )
    phase, part = _PARTITIONS[partition]
    out_dir = Path(out_dir)
    json_path, md_path = out_dir / "report.json", out_dir / "report.md"
    if json_path.exists() or md_path.exists():
        raise DescriptiveRunRefusal(f"{out_dir} already holds a report; never overwritten")
    required = (daily_snapshot, snapshot_manifest, exposure_ledger_path, spec_path)
    for p in required if fetch_plan is not None else (*required, minute_bars):
        if not Path(p).exists():
            raise DescriptiveRunRefusal(f"{p} does not exist")
    if fetch_plan is not None:
        _fetch_preflight(fetch_plan, Path(minute_bars))

    # Everything that needs no registry row: spec (hash-bound decision), manifest, ledger.
    view, draft = _load_spec(Path(spec_path))
    manifest_bytes = Path(snapshot_manifest).read_bytes()
    try:
        manifest = parse_snapshot_manifest(manifest_bytes.decode("utf-8"))
    except (ManifestError, UnicodeDecodeError) as exc:
        raise DescriptiveRunRefusal(f"snapshot manifest refused: {exc}") from exc
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    verify_root = (
        Path(daily_snapshot) if Path(daily_snapshot).is_dir() else Path(daily_snapshot).parent
    )
    if allow_sequential_pulls_ref is not None and not allow_sequential_pulls_ref.strip():
        raise DescriptiveRunRefusal("allow-sequential-pulls-ref must name the recorded decision")
    verified = verify_snapshot_files(
        manifest, verify_root, allow_sequential_pulls=allow_sequential_pulls_ref is not None
    )
    if not verified.ok:
        raise DescriptiveRunRefusal(f"snapshot manifest verification failed: {verified.defects}")
    ledger = ExposureLedger.from_text(Path(exposure_ledger_path).read_text(encoding="utf-8"))
    registry = RunRegistry(Path(registry_path))

    requested = DateRange(d0, d1)
    if requested.overlaps(view.partitions.holdout):
        raise DescriptiveRunRefusal("the requested range overlaps the holdout partition")
    protected = view.partitions.selection if phase is Phase.P3A else None
    run_id = registry.open_run(
        phase=phase,
        spec_sha256=view.spec_sha256,
        code_sha=code_sha,
        data_manifest_sha256=manifest_sha,
        partition=part,
        seeds={"descriptive_run_no_rng": 0},
        exit_candidates=[c.id for c in draft.exits.candidates or []],
        protected_range=protected,
    )
    cap: ResultsCapability | None = None
    written: list[Path] = []
    daily_con: Any = None
    minute_con: Any = None
    try:
        cap = authorize(
            spec=view,
            phase=phase,
            partition=part,
            run_id=run_id,
            registry=registry,
            exposure_ledger=ledger,
            requested_range=requested,
        )
        params = extract_params(cap, draft)
        uparams = universe_params_from_draft(cap, draft)
        authorized = cap.date_range
        if authorized.overlaps(view.partitions.holdout):
            raise DescriptiveRunRefusal("authorized range overlaps the holdout partition")

        daily_con = open_snapshot(Path(daily_snapshot))
        sessions_cal = expected_sessions(authorized.start, authorized.end)
        builds = []
        expected: list[tuple[str, date]] = []
        perma: dict[tuple[str, date], str] = {}
        exclusions: dict[tuple[str, date], str] = {}
        month_rows: list[dict[str, Any]] = []
        events = _delisting_events(daily_con, delisting_actions)
        evidence_rows: list[tuple[str, str]] = []
        delist_after: dict[tuple[str, date], date] = {}
        for ms in _month_starts(authorized.start, authorized.end):
            mb = build_month_from_store(
                cap,
                daily_con,
                ms,
                uparams,
                table_filter=table_filter,
                lookback_calendar_days=lookback_calendar_days,
                raw_vendor_rows_attested=raw_vendor_rows_attested,
                exploratory_scope_amendment_id=exploratory_scope_amendment_id,
            )
            builds.append(mb)
            for m in mb.universe.members:
                later = sorted(
                    e for e in events.get(m.vendor_ticker, ()) if e > mb.universe.decision_day
                )
                if later:  # earlier events belong to an earlier issuer of the ticker
                    delist_after[(m.vendor_ticker, ms)] = later[0]
            days = [d for d in sorted(sessions_cal) if ms <= d <= _month_last(ms, authorized.end)]
            for m in mb.universe.members:
                for d in days:
                    key = (m.vendor_ticker, d)
                    if key in perma:
                        raise DataDefectError(f"duplicate expected symbol-day {key}")
                    expected.append(key)
                    perma[key] = m.permaticker
                    ev_day = delist_after.get((m.vendor_ticker, ms))
                    if ev_day is not None and d > ev_day:
                        # Historical LISTING evidence (an ACTIONS delisting event dated after
                        # this month's decision day) establishes the day is outside the
                        # eligible population. A vendor lastpricedate alone never does.
                        exclusions[key] = "DELISTED_BEFORE_DAY"
                        evidence_rows.append((m.vendor_ticker, ev_day.isoformat()))
            u = mb.universe
            month_rows.append(
                {
                    "month_start": ms.isoformat(),
                    "decision_day": u.decision_day.isoformat(),
                    "population": u.population,
                    "members": len(u.members),
                    "below_cut": u.below_cut,
                    "excluded": len(u.excluded),
                    # Visible, not silent: excluded listings by observed category label and by
                    # reason, against the full listing population of this month.
                    "excluded_by_reason": _count_by(e.reason for e in u.excluded),
                    "not_common_stock_by_category": _count_by(
                        e.detail for e in u.excluded if e.reason == "NOT_COMMON_STOCK"
                    ),
                    "sessions": len(days),
                    "scope": mb.scope,
                    "identity_one_row_per_ticker": mb.identity.one_row_per_ticker,
                    "identity_refused_rows": len(mb.identity.refused),
                    "unattributed_sep_rows": mb.observations.unattributed_rows,
                    "ambiguous_sep_rows": mb.observations.ambiguous_rows,
                }
            )

        acquisition: dict[str, Any] | None = None
        evidence_path: Path | None = None
        if fetch_plan is not None:
            acquisition, evidence_path = _acquire(
                cap,
                fetch_plan,
                builds=builds,
                daily_con=daily_con,
                table_filter=table_filter,
                authorized=authorized,
                sessions_cal=sessions_cal,
                view=view,
                code_sha=code_sha,
                manifest_sha=manifest_sha,
                minute_bars=Path(minute_bars),
                run_id=run_id,
                out_dir=out_dir,
            )
        minute_con = duckdb.connect(str(minute_bars), read_only=True)
        to_load = [k for k in expected if k not in exclusions]
        sessions, missing = load_sessions(
            cap,
            minute_con,
            params,
            to_load,
            sessions_cal,
            source_feed=minute_feed,
            source_ts_convention=minute_ts_convention,
            no_trade_evidence={},
            permaticker_of=perma,
        )
        observed = {
            (s.symbol, s.day): presence_from_minutes(
                [b.start for b in s.bars], sorted(s.gap_minutes), params.or_start, params.or_end
            )
            for s in sessions
        }
        cov = coverage_report(
            expected,
            observed,
            exclusions=exclusions,
            missing_causes=dict.fromkeys(missing, MISSING_NO_DATA),
            or_max_gap_minutes=params.or_max_gap_minutes,
            threshold=coverage_threshold,
        )
        if cov.observed != len(sessions):
            raise FunnelMismatchError(
                f"coverage observed {cov.observed} != loaded sessions {len(sessions)}"
            )
        if acquisition is not None and evidence_path is not None:
            # validate and REPORT coverage before anything is screened; a data defect
            # refuses the screen (the run closes ABORTED, the evidence file is kept)
            cov_summary = dataclasses.asdict(cov)
            cov_summary["by_year"] = {str(y): v for y, v in sorted(cov.by_year.items())}
            acquisition["coverage_before_screening"] = cov_summary
            acquisition["missing_symbol_days"] = len(missing)
            acquisition["status"] = (
                "COVERAGE_OK" if cov.meets_threshold else "COVERAGE_BELOW_THRESHOLD_SCREEN_REFUSED"
            )
            evidence_path.write_text(
                json.dumps(acquisition, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
            if not cov.meets_threshold:
                raise DataDefectError(
                    f"coverage {cov.coverage_rate:.4f} is below the threshold "
                    f"{coverage_threshold}: screening refused; see {evidence_path.name}"
                )

        screen = run_screen(cap, params, sessions, tick, equity)
        reconcile_funnel(cap, screen.funnel)
        entered = screen.funnel.states[STATE_ENTERED]
        cand_ids = [c.id for c in params.candidates]
        if set(screen.trades) != set(cand_ids):
            raise FunnelMismatchError("screen candidates differ from the spec's candidates")
        candidates = {cid: summarize(cap, screen.trades[cid]) for cid in cand_ids}

        defect = not cov.meets_threshold
        cov_dict = dataclasses.asdict(cov)
        cov_dict["by_year"] = {str(y): v for y, v in sorted(cov.by_year.items())}
        scopes = sorted({b.scope for b in builds})
        report: dict[str, Any] = {
            "label": LABEL,
            "label_sentence": LABEL_SENTENCE,
            "status": STATUS_DEFECT if defect else STATUS_COMPLETE,
            "defect_note": NO_VERDICT_NOTE if defect else None,
            "run": {
                "run_id": run_id,
                "phase": phase.value,
                "partition": part.value,
                "citable": cap.citable,
                "profile": cap.profile,
            },
            "spec": {
                "sha256": view.spec_sha256,
                "baseline_id": view.baseline_id,
                "strategy_version": view.strategy_version,
            },
            "decision_reference": _decision_block(view),
            "authorized_range": authorized.as_dict(),
            "data": {
                "daily_snapshot": {
                    "path": str(daily_snapshot),
                    "sha256": _path_digest(Path(daily_snapshot)),
                },
                "minute_bars": {
                    "path": str(minute_bars),
                    "sha256": _path_digest(Path(minute_bars)),
                },
                "snapshot_manifest_sha256": manifest_sha,
                "snapshot_manifest": {
                    "source": manifest.source,
                    "extracted_at_utc": manifest.extracted_at_utc,
                    "method": manifest.method,
                    "cross_table_consistent": manifest.cross_table_consistent,
                    "consistency_class": manifest.consistency_class,
                    "integrity_all_passed": manifest.integrity_all_passed,
                    "sequential_pulls_opt_in_ref": (
                        allow_sequential_pulls_ref if not manifest.cross_table_consistent else None
                    ),
                    "limitation": (
                        SEQUENTIAL_PULLS_LIMITATION if not manifest.cross_table_consistent else None
                    ),
                },
                "code_sha": code_sha,
                "table_filter": table_filter,
                "minute_feed": minute_feed,
                "minute_ts_convention": minute_ts_convention,
                "universe_scopes": scopes,
                "exploratory": scopes != ["PIT_FULL"],
                "provenance": dict(provenance or {}),
                "acquisition": (
                    {
                        "evidence_file": evidence_path.name if evidence_path else None,
                        "binding": acquisition["binding"],
                        "planned_estimate": acquisition["planned_estimate"],
                        "actual": acquisition["actual"],
                        "probe": acquisition["probe"],
                        "convention_check": acquisition.get("convention_check"),
                        "store_sha256": acquisition.get("store_sha256"),
                    }
                    if acquisition is not None
                    else None
                ),
            },
            "universe_months": month_rows,
            "coverage": cov_dict,
            "or_completeness": {
                "or_max_gap_minutes": params.or_max_gap_minutes,
                "complete_count": cov.or_complete_count,
                "of_observed": cov.or_complete_of_observed,
                "of_expected": cov.or_complete_of_expected,
            },
            "funnel": {
                "eligible": screen.funnel.eligible,
                "states": screen.funnel.states,
                "exits": screen.funnel.exits,
                "reconciliation": {
                    "ok": True,
                    "states_sum": sum(screen.funnel.states.values()),
                    "eligible": screen.funnel.eligible,
                    "entered": entered,
                    "exits_sum_by_candidate": {
                        c: sum(v.values()) for c, v in screen.funnel.exits.items()
                    },
                    "expected_symbol_days": cov.expected,
                    "denominator": cov.denominator,
                    "loaded": len(sessions),
                    "missing_symbol_days": len(missing),
                },
            },
            "candidates": candidates,
            "unavailable_exit_valuation": {
                "rule": UNAVAILABLE_EXIT_VALUATION_RULE,
                "unexecutable_by_candidate": {
                    c: s["unexecutable_exits"] for c, s in candidates.items()
                },
                "unexecutable_total": sum(s["unexecutable_exits"] for s in candidates.values()),
            },
            "execution_disclosure": {
                "execution_realism": "NOT_MODELLED",
                "statement": (
                    "Fills are bar-level with all-in bps costs. Execution settings present in "
                    "the spec are not simulated; a non-null value does not imply execution "
                    "realism."
                ),
                "unmodelled_fields_present": list(params.unmodelled_execution),
            },
            "exposure_note": (
                "REPLAY_RNG001 over an already-exposed window: engine validation only, never "
                "citable."
                if not cap.citable
                else (
                    f"checked against exposure ledger {cap.exposure_ledger_sha256}; the range "
                    "overlaps no ledger entry and not the R2-excluded window. This run VIEWS "
                    f"{authorized.start}..{authorized.end}: record it in the exposure ledger "
                    "before any later run touches overlapping dates."
                )
            ),
            "limitations": [
                "NYSE schedule from pandas_market_calendars; not independently verified "
                "against vendor session data",
                "regular-session minutes with no bar are DATA_GAP (no independent no-trade "
                "evidence supplied)",
                "a symbol-day is excluded as DELISTED_BEFORE_DAY ONLY on an ACTIONS delisting "
                "event dated after the month's decision day; a final price date alone never "
                "shrinks the denominator (missing days stay expected and are reported as missing)",
                f"delisting evidence actions requested: {list(delisting_actions)} "
                f"(none means no exclusion of any kind); evidence rows applied: {len(evidence_rows)}",
            ],
            "optional_bootstrap": None,
        }
        if statistics_config is not None and not defect:
            eligible_days = sorted({s.day for s in sessions})
            report["optional_bootstrap"] = _bootstrap_section(
                cap, screen.trades, eligible_days, statistics_config
            )

        json_bytes = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode()
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(json_path, "xb") as fh:
            written.append(json_path)
            fh.write(json_bytes)
        with open(md_path, "x", encoding="utf-8", newline="\n") as fh:
            written.append(md_path)
            # PU-1: the minute bars are Alpaca SIP (personal use) and the daily snapshot is Sharadar
            # (licence UNKNOWN), so the readable report carries the fixed footer. report.json keeps
            # its exact bytes (its digest is bound to the run registry); its scope travels in a sidecar.
            fh.write(stamp(_render_md(report), sources=PU1_SOURCES))
        for artifact in (json_path, md_path):
            write_sidecar(artifact, PU1_SOURCES)
            written.append(sidecar_path(artifact))
        digest = hashlib.sha256(json_bytes).hexdigest()
        registry.close_run(run_id, RunStatus.COMPLETED, digest)
    except BaseException as exc:
        for p in written:
            p.unlink(missing_ok=True)
        _abort(registry, run_id, exc)
        raise
    finally:
        for con in (daily_con, minute_con):
            if con is not None:
                con.close()
    return RunOutcome(run_id, report["status"], json_path, md_path, digest, report, cap)


#: Data lineage of every report this runner writes (PU-1). Fixed, not a parameter: the runner reads
#: SIP minute bars (feed 'sip') and a Sharadar daily snapshot, so its output is never presentable.
PU1_SOURCES: tuple[str, ...] = ("alpaca_market_data", "sharadar")


# --------------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    req = p.add_argument
    req("--spec", required=True, type=Path)
    req("--registry", required=True, type=Path)
    req("--exposure-ledger", required=True, type=Path)
    req("--daily-snapshot", required=True, type=Path)
    req("--snapshot-manifest", required=True, type=Path)
    req("--minute-bars", required=True, type=Path)
    req("--minute-feed", required=True)
    req("--minute-ts-convention", required=True)
    req("--date-start", required=True)
    req("--date-end", required=True)
    req("--partition", required=True, choices=PARTITION_CHOICES)
    req("--table-filter", required=True)
    req("--lookback-calendar-days", required=True, type=int)
    req("--coverage-threshold", required=True, type=float)
    req("--equity", required=True, type=float)
    req("--tick", required=True, type=float)
    req("--code-sha", required=True)
    req("--out-dir", required=True, type=Path)
    req("--exploratory-scope-amendment-id", default=None)
    req("--raw-vendor-rows-attested", action="store_true")
    req(
        "--allow-sequential-pulls-ref",
        default=None,
        help="explicit opt-in: accept a v2 snapshot of class sequential_pulls_evidence_checked "
        "whose integrity checks all passed; the value names the recorded decision and is carried "
        "into the report with the limitation text. Without it such a snapshot is refused.",
    )
    ev = p.add_mutually_exclusive_group(required=True)
    ev.add_argument(
        "--delisting-action-value",
        action="append",
        default=None,
        help="an exact ACTIONS action string that records a delisting (repeatable)",
    )
    ev.add_argument(
        "--no-delisting-evidence",
        action="store_true",
        help="no listing evidence is used: no symbol-day is excluded",
    )
    req("--provenance", action="append", default=[], metavar="KEY=VALUE")
    req(
        "--fetch-bars",
        action="store_true",
        help="acquire the SIP minute bars INSIDE this run with its capability (one attempt)",
    )
    req("--fetch-universe-sha256", default=None)
    req("--fetch-journal", type=Path, default=None)
    req("--fetch-key-env", default=None)
    req("--fetch-secret-env", default=None)
    req("--fetch-requests-per-minute", type=int, default=None)
    req("--fetch-max-requests", type=int, default=None)
    req("--fetch-asof", default=None)
    req("--fetch-authorization-id", default=None)
    req("--fetch-permitted-use-ref", default=None)
    req("--fetch-entitlement-ref", default=None)
    req("--fetch-permission-basis-claimed", default=None)
    req("--fetch-storage-permitted", action="store_true")
    req("--fetch-acknowledge-new-attempt-ref", default=None)
    req("--fetch-symbol-map", type=Path, default=None)
    req("--fetch-symbol-map-sha256", default=None)
    req("--fetch-limit", type=int, default=10000)
    req("--fetch-max-pages", type=int, default=100)
    req("--statistics-config", type=Path, default=None)
    req("--dry-plan", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _build_parser().parse_args(argv)
    try:
        if a.dry_plan:
            out = plan(
                spec_path=a.spec,
                date_start=a.date_start,
                date_end=a.date_end,
                partition=a.partition,
                daily_snapshot=a.daily_snapshot,
                minute_bars=a.minute_bars,
            )
            print(json.dumps(out, indent=2, sort_keys=True))
            return EXIT_OK
        prov: dict[str, str] = {}
        for item in a.provenance:
            k, sep, v = item.partition("=")
            if not sep or not k:
                raise DescriptiveRunRefusal(f"--provenance needs KEY=VALUE, got {item!r}")
            prov[k] = v
        stats = (
            json.loads(a.statistics_config.read_text(encoding="utf-8"))
            if a.statistics_config
            else None
        )
        fetch_plan: FetchPlan | None = None
        if a.fetch_bars:
            need = {
                "--fetch-universe-sha256": a.fetch_universe_sha256,
                "--fetch-journal": a.fetch_journal,
                "--fetch-key-env": a.fetch_key_env,
                "--fetch-secret-env": a.fetch_secret_env,
                "--fetch-requests-per-minute": a.fetch_requests_per_minute,
                "--fetch-max-requests": a.fetch_max_requests,
                "--fetch-asof": a.fetch_asof,
                "--fetch-authorization-id": a.fetch_authorization_id,
                "--fetch-permitted-use-ref": a.fetch_permitted_use_ref,
                "--fetch-entitlement-ref": a.fetch_entitlement_ref,
                "--fetch-permission-basis-claimed": a.fetch_permission_basis_claimed,
            }
            missing_args = [k for k, v in need.items() if v is None]
            if missing_args:
                raise DescriptiveRunRefusal(f"--fetch-bars needs {missing_args}")
            fetch_plan = FetchPlan(
                universe_sha256=a.fetch_universe_sha256,
                journal_path=a.fetch_journal,
                key_env=a.fetch_key_env,
                secret_env=a.fetch_secret_env,
                requests_per_minute=a.fetch_requests_per_minute,
                max_requests=a.fetch_max_requests,
                asof=a.fetch_asof,
                authorization_id=a.fetch_authorization_id,
                permitted_use_ref=a.fetch_permitted_use_ref,
                entitlement_ref=a.fetch_entitlement_ref,
                permission_basis_claimed=a.fetch_permission_basis_claimed,
                storage_permitted=bool(a.fetch_storage_permitted),
                acknowledge_new_attempt_ref=a.fetch_acknowledge_new_attempt_ref,
                symbol_map_path=a.fetch_symbol_map,
                symbol_map_sha256=a.fetch_symbol_map_sha256,
                limit=a.fetch_limit,
                max_pages=a.fetch_max_pages,
            )
        outcome = run(
            spec_path=a.spec,
            registry_path=a.registry,
            exposure_ledger_path=a.exposure_ledger,
            daily_snapshot=a.daily_snapshot,
            snapshot_manifest=a.snapshot_manifest,
            minute_bars=a.minute_bars,
            minute_feed=a.minute_feed,
            minute_ts_convention=a.minute_ts_convention,
            date_start=a.date_start,
            date_end=a.date_end,
            partition=a.partition,
            table_filter=a.table_filter,
            lookback_calendar_days=a.lookback_calendar_days,
            coverage_threshold=a.coverage_threshold,
            equity=a.equity,
            tick=a.tick,
            code_sha=a.code_sha,
            out_dir=a.out_dir,
            exploratory_scope_amendment_id=a.exploratory_scope_amendment_id,
            raw_vendor_rows_attested=a.raw_vendor_rows_attested,
            delisting_actions=tuple(a.delisting_action_value or ()),
            provenance=prov,
            statistics_config=stats,
            allow_sequential_pulls_ref=a.allow_sequential_pulls_ref,
            fetch_plan=fetch_plan,
        )
    except Exception as exc:  # every refusal is reported, run already ABORTED
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(
        f"{outcome.status} run={outcome.run_id} report={outcome.report_json} "
        f"sha256={outcome.report_sha256}"
    )
    return EXIT_DEFECT if outcome.status == STATUS_DEFECT else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
