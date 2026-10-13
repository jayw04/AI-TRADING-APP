"""RANGE-002 bounded AUDIT REPLAY of a COMPLETED governed run (no new strategy attempt).

    python -I audit_replay_run.py --parent-run-id range002-run-000011 --audit-id AUDIT-... \\
        --spec FROZEN.json --registry RUNS.jsonl --parent-report report.json \\
        --daily-snapshot DIR --snapshot-manifest MANIFEST.json --minute-bars STORE.duckdb \\
        --minute-feed sip --minute-ts-convention start --table-filter SEP \\
        --lookback-calendar-days 45 --coverage-threshold 0.98 --equity 100000 --tick 0.01 \\
        --code-sha <40 hex> --out-dir AUDIT_DIR --audit-log LOG.jsonl \\
        --raw-vendor-rows-attested --allow-sequential-pulls-ref REF --delisting-action-value delisted \\
        [--parent-evidence acquisition_evidence_*.json --mapping FILE --universe FILE]

What it is: a deterministic re-execution of the parent's screen over the parent's OWN stored data,
under a DISTINCT audit capability (``results_guard.authorize_audit_replay``). It consumes no P3A
attempt, never revives the closed parent capability, fetches nothing, changes no parameter,
selects no candidate, reads no other date range and never touches the holdout. Every invocation is
appended to a hash-chained audit log. Inputs that differ from the parent's recorded hashes are
refused. Outputs go to a separate directory; the parent's evidence is never written.

What it verifies (aggregates are compared with the parent's report within ``TOLERANCE``; any
discrepancy is a DEFECT, never smoothed over):
  * reproduction of every candidate summary, the funnel and the coverage report;
  * per-trade gross / base / stress arithmetic, independently recomputed from the trade's own
    prices (including partial exits), and the stress/base cost ratio;
  * representative gapped, stop, target, trailing and scale-out trades (full records);
  * cost by executed-trade opening-range-width bucket;
  * top-five-trade and top-five-day concentration;
  * the actual R impact of same-bar (ambiguous) fills, per trade, under the opposite ordering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_descriptive_screen as rds  # noqa: E402

from app.licensing.envelope import write_sidecar  # noqa: E402
from app.research.range002.governance.results_guard import (  # noqa: E402
    AuditParentBinding,
    authorize_audit_replay,
)
from app.research.range002.governance.results_guard import (  # noqa: E402
    _audit_log_append as append_audit_log,
)
from app.research.range002.governance.run_registry import RunRegistry, RunStatus  # noqa: E402

TOOL_VERSION = "1.0.0"
#: relative tolerance for float reproduction/arithmetic (the replay is deterministic, so this is
#: a numerical-noise bound, not an allowance for behavioural differences)
TOLERANCE = 1e-9
EXIT_OK, EXIT_REFUSED, EXIT_DEFECT = 0, 2, 3
WIDTH_BUCKETS = ((0.0, 0.003), (0.003, 0.006), (0.006, 0.010), (0.010, 0.020), (0.020, 9.0))
REPRESENTATIVES_PER_CATEGORY = 2


class AuditRefusal(RuntimeError):
    """The audit was refused (altered input, unknown parent, bad arguments)."""


def _close(a: float | None, b: float | None, tol: float = TOLERANCE) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


_sha256_path = rds._path_digest


def _compare(parent: Any, mine: Any, path: str, out: list[str]) -> None:
    if isinstance(parent, dict) and isinstance(mine, dict):
        for k in sorted(set(parent) | set(mine)):
            if k not in parent or k not in mine:
                out.append(f"{path}.{k}: present on one side only")
            else:
                _compare(parent[k], mine[k], f"{path}.{k}", out)
    elif isinstance(parent, list) and isinstance(mine, list):
        if len(parent) != len(mine):
            out.append(f"{path}: length {len(parent)} != {len(mine)}")
        for i, (a, b) in enumerate(zip(parent, mine, strict=False)):
            _compare(a, b, f"{path}[{i}]", out)
    elif (
        isinstance(parent, (int, float))
        and isinstance(mine, (int, float))
        and not isinstance(parent, bool)
    ):
        if not _close(float(parent), float(mine)):
            out.append(f"{path}: {parent!r} != {mine!r}")
    elif parent != mine:
        out.append(f"{path}: {parent!r} != {mine!r}")


# ------------------------------------------------------------------------------ replay


def replay(
    cap: Any,
    *,
    view: Any,
    draft: Any,
    daily_snapshot: Path,
    minute_bars: Path,
    minute_feed: str,
    minute_ts_convention: str,
    table_filter: str,
    lookback_calendar_days: int,
    coverage_threshold: float,
    equity: float,
    tick: float,
    delisting_actions: tuple[str, ...],
    raw_vendor_rows_attested: bool,
    no_trade_evidence: dict[Any, Any] | None = None,
) -> dict[str, Any]:
    """Mirror of the parent runner's evaluation (no fetching), returning trades and aggregates."""
    duckdb = rds.duckdb
    params = rds.extract_params(cap, draft)
    uparams = rds.universe_params_from_draft(cap, draft)
    authorized = cap.date_range
    daily_con = rds.open_snapshot(daily_snapshot)
    sessions_cal = rds.expected_sessions(authorized.start, authorized.end)
    expected: list[tuple[str, date]] = []
    perma: dict[tuple[str, date], str] = {}
    exclusions: dict[tuple[str, date], str] = {}
    events = rds._delisting_events(daily_con, delisting_actions)
    delist_after: dict[tuple[str, date], date] = {}
    builds = []
    for ms in rds._month_starts(authorized.start, authorized.end):
        mb = rds.build_month_from_store(
            cap,
            daily_con,
            ms,
            uparams,
            table_filter=table_filter,
            lookback_calendar_days=lookback_calendar_days,
            raw_vendor_rows_attested=raw_vendor_rows_attested,
            exploratory_scope_amendment_id=None,
        )
        builds.append(mb)
        for m in mb.universe.members:
            later = sorted(
                e for e in events.get(m.vendor_ticker, ()) if e > mb.universe.decision_day
            )
            if later:
                delist_after[(m.vendor_ticker, ms)] = later[0]
        days = [d for d in sorted(sessions_cal) if ms <= d <= rds._month_last(ms, authorized.end)]
        for m in mb.universe.members:
            for d in days:
                key = (m.vendor_ticker, d)
                expected.append(key)
                perma[key] = m.permaticker
                ev_day = delist_after.get((m.vendor_ticker, ms))
                if ev_day is not None and d > ev_day:
                    exclusions[key] = "DELISTED_BEFORE_DAY"
    minute_con = duckdb.connect(str(minute_bars), read_only=True)
    try:
        to_load = [k for k in expected if k not in exclusions]
        sessions, missing = rds.load_sessions(
            cap,
            minute_con,
            params,
            to_load,
            sessions_cal,
            source_feed=minute_feed,
            source_ts_convention=minute_ts_convention,
            no_trade_evidence=no_trade_evidence or {},
            permaticker_of=perma,
        )
    finally:
        minute_con.close()
    observed = {
        (s.symbol, s.day): rds.presence_from_minutes(
            [b.start for b in s.bars], sorted(s.gap_minutes), params.or_start, params.or_end
        )
        for s in sessions
    }
    cov = rds.coverage_report(
        expected,
        observed,
        exclusions=exclusions,
        missing_causes=dict.fromkeys(missing, rds.MISSING_NO_DATA),
        or_max_gap_minutes=params.or_max_gap_minutes,
        threshold=coverage_threshold,
    )
    screen = rds.run_screen(cap, params, sessions, tick, equity)
    rds.reconcile_funnel(cap, screen.funnel)
    cand_ids = [c.id for c in params.candidates]
    candidates = {cid: rds.summarize(cap, screen.trades[cid]) for cid in cand_ids}
    return {
        "params": params,
        "screen": screen,
        "coverage": cov,
        "candidates": candidates,
        "sessions": sessions,
        "missing": missing,
    }


# ------------------------------------------------------------------------------ analysis


def _trade_record(t: Any) -> dict[str, Any]:
    d = asdict(t)
    d["day"] = t.day.isoformat()
    d["entry_time"] = t.entry_time.isoformat()
    d["exit_time"] = t.exit_time.isoformat()
    return d


def _arith(
    t: Any, base_bps: float, stress_bps: float, scale_fraction: float = 0.5
) -> dict[str, Any]:
    """Independent recomputation from the trade's own prices. Returns the discrepancies (empty
    list when the trade reconciles) plus the recomputed pieces."""
    probs: list[str] = []
    r = t.r_fill
    if t.scaled_out:
        partial_px = t.entry_price + r  # +1R partial fill (the kernel's scale level)
        weighted = scale_fraction * partial_px + (1 - scale_fraction) * t.exit_price
    else:
        weighted = t.exit_price
    gross = (weighted - t.entry_price) / r
    if not _close(gross, t.gross_r):
        probs.append(f"gross_r {t.gross_r!r} != recomputed {gross!r}")
    for label, bps, net in (
        ("base", base_bps, t.net_r_base),
        ("stress", stress_bps, t.net_r_stress),
    ):
        cost = (bps / 10_000.0) * (t.entry_price + weighted) / r
        if not _close(t.gross_r - net, cost):
            probs.append(f"{label} cost {t.gross_r - net!r} != recomputed {cost!r}")
    cb, cs = t.gross_r - t.net_r_base, t.gross_r - t.net_r_stress
    if cb and not _close(cs / cb, stress_bps / base_bps, 1e-7):
        probs.append(f"stress/base cost ratio {cs / cb!r} != {stress_bps / base_bps!r}")
    return {"problems": probs, "gross_recomputed": gross, "weighted_exit": weighted}


def _bar_checks(
    t: Any, bars: dict[Any, Any], spec: Any, trigger_offset_ticks: float, tick: float
) -> list[str]:
    """Check the trade's entry and exit against the stored minute bars (independent of the
    kernel's walk): entry fill, risk, exit fill, and that the exit price is a price the exit
    bar could have printed."""
    probs: list[str] = []
    eb, xb = bars.get(t.entry_time), bars.get(t.exit_time)
    if eb is None or xb is None:
        return ["entry or exit bar missing from the stored session"]
    trigger = t.or_high + trigger_offset_ticks * tick
    if not _close(t.trigger, trigger):
        probs.append(f"trigger {t.trigger!r} != or_high + offset {trigger!r}")
    if eb.high < t.trigger:
        probs.append("entry bar never reached the trigger")
    if not _close(t.entry_price, max(t.trigger, eb.open)):
        probs.append(f"entry price {t.entry_price!r} != max(trigger, open)")
    if not _close(t.r_fill, t.entry_price - t.or_low):
        probs.append("r_fill != entry - or_low")
    if t.exit_reason in ("EOD", "STOP_GAP"):
        if not _close(t.exit_price, xb.open):
            probs.append(f"{t.exit_reason} exit {t.exit_price!r} != exit-bar open {xb.open!r}")
    elif t.exit_reason == "STOP":
        if not _close(t.exit_price, t.or_low) or xb.low > t.exit_price:
            probs.append("STOP exit is not the initial stop within the exit bar's range")
    elif t.exit_reason == "TRAIL_STOP":
        if t.exit_price < t.or_low or xb.low > t.exit_price:
            probs.append("TRAIL_STOP exit not a raised stop within the exit bar's range")
    elif t.exit_reason == "TARGET":
        want = t.entry_price + (spec.r_multiple or 0.0) * t.r_fill
        if not _close(t.exit_price, want) or xb.high < want:
            probs.append("TARGET exit != entry + k*R or exit bar never reached it")
    elif t.exit_reason != "EOD_LASTBAR_FALLBACK":
        probs.append(f"unrecognised exit reason {t.exit_reason!r}")
    return probs


def _bucket(width_pct: float) -> str:
    for lo, hi in WIDTH_BUCKETS:
        if lo <= width_pct < hi:
            return f"[{lo * 100:.1f}%,{min(hi, 9.0) * 100:.1f}%)"
    return "other"


def _ambiguity(t: Any, spec: Any, base_bps: float, stress_bps: float) -> dict[str, Any]:
    """Counterfactual for ONE ambiguous same-bar fill: the kernel took the stop (worst case). The
    alternative ordering fills the target (fixed R) or the +1R partial first, then the remainder
    is stopped at the recorded exit price."""
    r = t.r_fill
    legs: tuple[tuple[float, float], ...]
    if spec.family == "fixed_r" and spec.r_multiple is not None:
        legs = ((1.0, t.entry_price + spec.r_multiple * r),)
    elif spec.family == "scale_out":
        legs = ((0.5, t.entry_price + r), (0.5, t.exit_price))
    else:  # trailing: the partial/target concept does not apply to a trail
        legs = ((1.0, t.exit_price),)
    weighted = sum(f * px for f, px in legs)
    gross = (weighted - t.entry_price) / r
    cost_b = (base_bps / 10_000.0) * (t.entry_price + weighted) / r
    cost_s = (stress_bps / 10_000.0) * (t.entry_price + weighted) / r
    return {
        "symbol": t.symbol,
        "day": t.day.isoformat(),
        "exit_reason_recorded": t.exit_reason,
        "net_r_base_recorded": t.net_r_base,
        "net_r_stress_recorded": t.net_r_stress,
        "net_r_base_if_other_order": gross - cost_b,
        "net_r_stress_if_other_order": gross - cost_s,
        "base_delta_r": (gross - cost_b) - t.net_r_base,
        "stress_delta_r": (gross - cost_s) - t.net_r_stress,
    }


def or_incomplete_diagnostics(run_out: dict[str, Any]) -> dict[str, Any]:
    """Descriptive breakdown of loaded sessions whose opening range is incomplete. It classifies
    NOTHING as no-trade: a minute with no stored bar stays an unresolved DATA_GAP (no independent
    evidence of "no print" is available), so cause remains unresolved here."""
    params = run_out["params"]
    first = params.or_start
    by_missing: dict[int, int] = defaultdict(int)
    by_month: dict[str, dict[str, int]] = defaultdict(lambda: {"loaded": 0, "incomplete": 0})
    by_symbol: dict[str, int] = defaultdict(int)
    first_minute_missing = 0
    incomplete = 0
    for sess in run_out["sessions"]:
        miss = sorted(m for m in sess.gap_minutes if params.or_start <= m <= params.or_end)
        month = by_month[f"{sess.day.year}-{sess.day.month:02d}"]
        month["loaded"] += 1
        if len(miss) > params.or_max_gap_minutes:
            incomplete += 1
            month["incomplete"] += 1
            by_missing[len(miss)] += 1
            by_symbol[sess.symbol] += 1
            if first in miss:
                first_minute_missing += 1
    top = sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {
        "or_incomplete_sessions": incomplete,
        "missing_or_minutes_histogram": {str(k): v for k, v in sorted(by_missing.items())},
        "sessions_missing_first_or_minute": first_minute_missing,
        "by_month": dict(sorted(by_month.items())),
        "symbols_affected": len(by_symbol),
        "top_symbols": [{"symbol": k, "incomplete_days": v} for k, v in top],
        "classification": "UNRESOLVED: missing minutes are not classified as no-trade without "
        "independent evidence; the cause (true no-print vs source construction) is open and is "
        "a separate investigation of the SIP minute-bar construction",
    }


def parent_annotation(parent: dict[str, Any], threshold: float) -> dict[str, Any]:
    """A NEW, separate annotation of the parent's status. It re-grades nothing: the original
    report and registry rows are untouched and the gate is applied as a labelled annotation, not
    as a retroactive pass or fail of the run's own rules."""
    o = parent["or_completeness"]
    cov = parent["coverage"]
    rate = o["of_expected"]
    meets = rate is not None and rate >= threshold
    return {
        "parent_status_original": parent["status"],
        "annotated_status": (
            parent["status"] if meets else "DESCRIPTIVE_COMPLETE_WITH_DATA_QUALITY_DEFECT"
        ),
        "measures": {
            "returned_coverage": {
                "numerator": cov["observed"],
                "denominator": cov["denominator"],
                "rate": cov["coverage_rate"],
                "threshold": cov["threshold"],
                "meets": cov["meets_threshold"],
            },
            "or_completeness_of_expected": {
                "numerator": o["complete_count"],
                "denominator": cov["denominator"],
                "rate": rate,
                "threshold": threshold,
                "meets": meets,
            },
            "or_completeness_of_observed": o["of_observed"],
        },
        "advancement": "none: no candidate is selected or advanced from the parent run",
        "note": "annotation only; original report.json / registry history are not modified, "
        "and a revised completeness policy would be explicit and prospective",
    }


def analyse(run_out: dict[str, Any], tick: float) -> dict[str, Any]:
    params = run_out["params"]
    screen = run_out["screen"]
    base_bps, stress_bps = params.base_bps_per_side, params.stress_bps_per_side
    specs = {c.id: c for c in params.candidates}
    out: dict[str, Any] = {"per_candidate": {}}
    bars_of = {(s.symbol, s.day): {b.start: b for b in s.bars} for s in run_out["sessions"]}
    offset = params.tick_offset
    for cid, trades in screen.trades.items():
        ordered = sorted(trades, key=lambda t: (t.day, t.entry_time, t.symbol))
        arith_bad = []
        gross_sum = base_sum = stress_sum = entry_cost = exit_cost = 0.0
        for t in ordered:
            a = _arith(t, base_bps, stress_bps)
            a["problems"] += _bar_checks(t, bars_of[(t.symbol, t.day)], specs[cid], offset, tick)
            entry_cost += (base_bps / 10_000.0) * t.entry_price / t.r_fill
            exit_cost += (base_bps / 10_000.0) * a["weighted_exit"] / t.r_fill
            gross_sum += t.gross_r
            base_sum += t.net_r_base
            stress_sum += t.net_r_stress
            if a["problems"]:
                arith_bad.append(
                    {"symbol": t.symbol, "day": t.day.isoformat(), "problems": a["problems"]}
                )
        n = len(ordered)
        cost_base = gross_sum - base_sum
        cost_stress = gross_sum - stress_sum
        # cost by executed-trade OR width
        buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"n": 0, "gross": 0.0, "base_cost": 0.0, "stress_cost": 0.0, "net_base": 0.0}
        )
        for t in ordered:
            mid = (t.or_high + t.or_low) / 2.0
            b = buckets[_bucket((t.or_high - t.or_low) / mid)]
            b["n"] += 1
            b["gross"] += t.gross_r
            b["base_cost"] += t.gross_r - t.net_r_base
            b["stress_cost"] += t.gross_r - t.net_r_stress
            b["net_base"] += t.net_r_base
        by_width = {
            k: {
                "n": int(v["n"]),
                "mean_gross_r": v["gross"] / v["n"],
                "mean_base_cost_r": v["base_cost"] / v["n"],
                "mean_stress_cost_r": v["stress_cost"] / v["n"],
                "mean_net_r_base": v["net_base"] / v["n"],
                "total_net_r_base": v["net_base"],
            }
            for k, v in sorted(buckets.items())
        }
        # concentration
        sorted_trades = sorted(ordered, key=lambda t: t.net_r_base, reverse=True)
        top5_trades = sorted_trades[:5]
        day_totals: dict[date, float] = defaultdict(float)
        for t in ordered:
            day_totals[t.day] += t.net_r_base
        top_days = sorted(day_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
        total = base_sum
        # ambiguity
        amb = [t for t in ordered if t.path_ambiguous]
        amb_rows = [_ambiguity(t, specs[cid], base_bps, stress_bps) for t in amb]
        # representatives
        cats = {
            "gapped_entry": lambda t: t.gapped_entry,
            "stop_gap_exit": lambda t: t.exit_reason == "STOP_GAP",
            "stop_exit": lambda t: t.exit_reason == "STOP",
            "target_exit": lambda t: t.exit_reason == "TARGET",
            "trailing_exit": lambda t: t.exit_reason == "TRAIL_STOP",
            "scale_out": lambda t: t.scaled_out,
            "ambiguous_fill": lambda t: t.path_ambiguous,
        }
        reps = {
            name: [
                _trade_record(t) | {"arith": _arith(t, base_bps, stress_bps)}
                for t in [x for x in ordered if pred(x)][:REPRESENTATIVES_PER_CATEGORY]
            ]
            for name, pred in cats.items()
        }
        out["per_candidate"][cid] = {
            "trades": n,
            "gross_total_r": gross_sum,
            "base_cost_total_r": cost_base,
            "stress_cost_total_r": cost_stress,
            "base_net_total_r": base_sum,
            "stress_net_total_r": stress_sum,
            "base_entry_cost_total_r": entry_cost,
            "base_exit_cost_total_r": exit_cost,
            "stress_over_base_cost": (cost_stress / cost_base) if cost_base else None,
            "gross_mean_r": gross_sum / n if n else None,
            "base_cost_mean_r": cost_base / n if n else None,
            "arithmetic_discrepancies": arith_bad,
            "cost_by_executed_trade_or_width": by_width,
            "top5_trades": [
                {
                    "symbol": t.symbol,
                    "day": t.day.isoformat(),
                    "net_r_base": t.net_r_base,
                    "exit": t.exit_reason,
                }
                for t in top5_trades
            ],
            "top5_trades_total_r": sum(t.net_r_base for t in top5_trades),
            "net_r_after_removing_top5_trades": total - sum(t.net_r_base for t in top5_trades),
            "top5_days": [{"day": d.isoformat(), "net_r_base": v} for d, v in top_days],
            "top5_days_total_r": sum(v for _, v in top_days),
            "net_r_after_removing_top5_days": total - sum(v for _, v in top_days),
            "traded_days": len(day_totals),
            "ambiguous_fills": {
                "count": len(amb),
                "trades": amb_rows,
                "base_net_r_if_all_ordered_the_other_way": base_sum
                + sum(r["base_delta_r"] for r in amb_rows),
                "total_base_delta_r": sum(r["base_delta_r"] for r in amb_rows),
                "total_stress_delta_r": sum(r["stress_delta_r"] for r in amb_rows),
            },
            "representative_trades": reps,
        }
    return out


# ------------------------------------------------------------------------------ main


def run_audit(a: argparse.Namespace) -> int:
    out_dir = Path(a.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise AuditRefusal(f"{out_dir} is not empty: audit outputs are never overwritten")
    parent_report_path = Path(a.parent_report)
    parent_bytes = parent_report_path.read_bytes()
    parent = json.loads(parent_bytes.decode("utf-8"))
    parent_report_sha = hashlib.sha256(parent_bytes).hexdigest()

    # ---- bound inputs: every one must equal what the parent recorded
    view, draft = rds._load_spec(Path(a.spec))
    problems: list[str] = []
    if parent["spec"]["sha256"] != view.spec_sha256:
        problems.append("spec sha256 differs from the parent report's")
    data = parent["data"]
    if data["code_sha"] != a.code_sha:
        problems.append("code sha differs from the parent report's")
    if (
        data["snapshot_manifest_sha256"]
        != hashlib.sha256(Path(a.snapshot_manifest).read_bytes()).hexdigest()
    ):
        problems.append("snapshot manifest differs from the parent report's")
    if data["daily_snapshot"]["sha256"] != _sha256_path(Path(a.daily_snapshot)):
        problems.append("daily snapshot differs from the parent report's")
    if data["minute_bars"]["sha256"] != _sha256_path(Path(a.minute_bars)):
        problems.append("minute-bar store differs from the parent report's")
    if (data["minute_feed"], data["minute_ts_convention"], data["table_filter"]) != (
        a.minute_feed,
        a.minute_ts_convention,
        a.table_filter,
    ):
        problems.append("feed / timestamp convention / table filter differ from the parent's")
    if a.parent_evidence:
        ev = json.loads(Path(a.parent_evidence).read_text(encoding="utf-8"))
        b = ev.get("binding", {})
        if a.mapping and hashlib.sha256(Path(a.mapping).read_bytes()).hexdigest() != b.get(
            "symbol_mapping_sha256"
        ):
            problems.append("symbol mapping differs from the parent's binding")
        if a.universe and hashlib.sha256(Path(a.universe).read_bytes()).hexdigest() != b.get(
            "universe_sha256"
        ):
            problems.append("fetch universe differs from the parent's binding")
        if (
            a.parent_evidence
            and ev.get("store_sha256")
            and ev["store_sha256"] != hashlib.sha256(Path(a.minute_bars).read_bytes()).hexdigest()
        ):
            problems.append("minute-bar store bytes differ from the parent evidence's store_sha256")
        if (a.price_tolerance, a.price_max_mismatch_fraction) != (
            b.get("price_consistency_settings", {}).get("tolerance"),
            b.get("price_consistency_settings", {}).get("max_mismatch_fraction"),
        ):
            problems.append("price-consistency settings differ from the parent's binding")
    if problems:
        raise AuditRefusal("altered or mismatched input(s): " + "; ".join(problems))

    ntm_map: dict[Any, Any] = {}
    parent_ev = (parent.get("or_completeness_gate") or {}).get("accounted_minutes")
    if a.no_trade_evidence is not None:
        if not (
            a.no_trade_evidence_sha256
            and a.census_manifest
            and a.census_manifest_sha256
            and a.accounted_tiers
        ):
            raise AuditRefusal(
                "evidence needs its sha256, the census manifest, its sha256 and tiers"
            )
        ntm_map, info = rds._load_no_trade_evidence(
            Path(a.no_trade_evidence),
            a.no_trade_evidence_sha256,
            Path(a.census_manifest),
            a.census_manifest_sha256,
            Path(a.minute_bars),
            a.accounted_tiers,
        )
        if not parent_ev or (
            parent_ev.get("classification_sha256") != info["classification_sha256"]
            or parent_ev.get("census_manifest_sha256") != info["census_manifest_sha256"]
            or parent_ev.get("tiers") != info["tiers"]
        ):
            raise AuditRefusal("missing-minute evidence differs from what the parent recorded")
    elif parent_ev:
        raise AuditRefusal("the parent used missing-minute evidence; supply the same artefacts")
    registry = RunRegistry(Path(a.registry))
    audit_cap = authorize_audit_replay(
        spec=view,
        registry=registry,
        parent_run_id=a.parent_run_id,
        audit_id=a.audit_id,
        binding=AuditParentBinding(
            parent_report_sha256=parent_report_sha,
            code_sha=a.code_sha,
            data_manifest_sha256=data["snapshot_manifest_sha256"],
            authorized_range=rds.DateRange(
                date.fromisoformat(parent["authorized_range"]["start"]),
                date.fromisoformat(parent["authorized_range"]["end"]),
            ),
        ),
        audit_log_path=Path(a.audit_log),
    )
    audit_run_id = audit_cap.run_id
    try:
        run_out = replay(
            audit_cap,
            view=view,
            draft=draft,
            daily_snapshot=Path(a.daily_snapshot),
            minute_bars=Path(a.minute_bars),
            minute_feed=a.minute_feed,
            minute_ts_convention=a.minute_ts_convention,
            table_filter=a.table_filter,
            lookback_calendar_days=a.lookback_calendar_days,
            coverage_threshold=a.coverage_threshold,
            equity=a.equity,
            tick=a.tick,
            delisting_actions=tuple(a.delisting_action_value or ()),
            raw_vendor_rows_attested=a.raw_vendor_rows_attested,
            no_trade_evidence=ntm_map,
        )
        # reproduction against the parent's recorded aggregates
        defects: list[str] = []
        _compare(
            parent["candidates"],
            json.loads(json.dumps(run_out["candidates"], default=str)),
            "candidates",
            defects,
        )
        cov_dict = rds.dataclasses.asdict(run_out["coverage"])
        cov_dict["by_year"] = {str(y): v for y, v in sorted(run_out["coverage"].by_year.items())}
        _compare(parent["coverage"], cov_dict, "coverage", defects)
        pf = parent["funnel"]
        _compare(pf["states"], run_out["screen"].funnel.states, "funnel.states", defects)
        _compare(pf["exits"], run_out["screen"].funnel.exits, "funnel.exits", defects)
        findings = analyse(run_out, a.tick)
        findings["or_incomplete_diagnostics"] = or_incomplete_diagnostics(run_out)
        arith_total = sum(
            len(v["arithmetic_discrepancies"]) for v in findings["per_candidate"].values()
        )
        report = {
            "schema": "range002.audit_replay.v1",
            "tool_version": TOOL_VERSION,
            "audit_id": a.audit_id,
            "audit_run_id": audit_run_id,
            "parent_run_id": a.parent_run_id,
            "parent_report_sha256": parent_report_sha,
            "bound": {
                "spec_sha256": view.spec_sha256,
                "code_sha": a.code_sha,
                "snapshot_manifest_sha256": data["snapshot_manifest_sha256"],
                "daily_snapshot_sha256": data["daily_snapshot"]["sha256"],
                "minute_bars_sha256": data["minute_bars"]["sha256"],
                "authorized_range": parent["authorized_range"],
            },
            "no_new_attempt": "phase AUDIT; no P3A strategy attempt consumed; closed parent capability not revived",
            "tolerance": TOLERANCE,
            "reproduction": {
                "matches_parent": not defects,
                "discrepancies": defects[:50],
                "n_discrepancies": len(defects),
            },
            "arithmetic": {"trades_with_discrepancy": arith_total},
            "parent_annotation": parent_annotation(parent, a.or_completeness_threshold),
            "findings": findings,
            "private": "US-sourced results: private to the owner; not for meeting materials (PU-1)",
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        for cid, trades in run_out["screen"].trades.items():
            with open(out_dir / f"trades_{cid}.jsonl", "x", encoding="utf-8", newline="\n") as fh:
                for t in sorted(trades, key=lambda x: (x.day, x.entry_time, x.symbol)):
                    fh.write(json.dumps(_trade_record(t), sort_keys=True) + "\n")
        text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
        (out_dir / "audit_report.json").write_text(text, encoding="utf-8")
        for artifact in sorted(out_dir.iterdir()):  # PU-1: scope sidecar on every output
            write_sidecar(artifact, rds.PU1_SOURCES)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        registry.close_run(audit_run_id, RunStatus.COMPLETED, digest)
        print(
            f"AUDIT_COMPLETE audit_run={audit_run_id} report_sha256={digest} matches_parent={not defects} arithmetic_discrepant_trades={arith_total}"
        )
        return EXIT_OK if (not defects and arith_total == 0) else EXIT_DEFECT
    except BaseException as exc:
        rds._abort(registry, audit_run_id, exc)
        raise


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    add = p.add_argument
    add("--parent-run-id", required=True)
    add("--audit-id", required=True)
    add("--spec", required=True, type=Path)
    add("--registry", required=True, type=Path)
    add("--parent-report", required=True, type=Path)
    add("--daily-snapshot", required=True, type=Path)
    add("--snapshot-manifest", required=True, type=Path)
    add("--minute-bars", required=True, type=Path)
    add("--minute-feed", required=True)
    add("--minute-ts-convention", required=True)
    add("--table-filter", required=True)
    add("--lookback-calendar-days", required=True, type=int)
    add("--coverage-threshold", required=True, type=float)
    add("--equity", required=True, type=float)
    add("--tick", required=True, type=float)
    add("--code-sha", required=True)
    add("--out-dir", required=True, type=Path)
    add("--audit-log", required=True, type=Path)
    add("--raw-vendor-rows-attested", action="store_true")
    add("--delisting-action-value", action="append", default=None)
    add("--no-trade-evidence", type=Path, default=None)
    add("--no-trade-evidence-sha256", default=None)
    add("--census-manifest", type=Path, default=None)
    add("--census-manifest-sha256", default=None)
    add("--accounted-tiers", choices=("positive", "both"), default=None)
    add("--parent-evidence", type=Path, default=None)
    add("--mapping", type=Path, default=None)
    add("--universe", type=Path, default=None)
    add("--or-completeness-threshold", type=float, default=0.98)
    add("--price-tolerance", type=float, default=None)
    add("--price-max-mismatch-fraction", type=float, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    log = Path(a.audit_log)
    append_audit_log(
        log,
        {
            "event": "audit_invocation",
            "requested_audit_id": a.audit_id,
            "parent_run_id": a.parent_run_id,
            "tool_version": TOOL_VERSION,
            "code_sha": a.code_sha,
        },
    )
    try:
        rc = run_audit(a)
        outcome, detail = ("COMPLETE" if rc == EXIT_OK else "DEFECT"), ""
    except Exception as exc:  # every refusal is reported; the audit run is already closed
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        rc, outcome, detail = EXIT_REFUSED, "REFUSED", f"{type(exc).__name__}: {exc}"[:500]
    append_audit_log(
        log,
        {
            "event": "audit_outcome",
            "requested_audit_id": a.audit_id,
            "outcome": outcome,
            "detail": detail,
        },
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
