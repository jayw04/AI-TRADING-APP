"""SEC-001 V3 — governed weekly-grid classification-coverage measurement.

Implements the frozen definition in ``docs/design/SEC-001/SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md``
§2 (four clauses) and §3 (theta values), under the owner adjudication of 2026-08-26 that the join
runs **through CIK**, never the per-CIK segment filename's ticker:

    ticker/week -> frozen CIK resolution -> effective-dated CIK classification -> attach the ticker

Emits **coverage statistics only** (freeze §4): resolved/unresolved counts per rebalance, per year
and per failure clause. It computes no return, no Sharpe, no drawdown and no sector-level economic
quantity, by construction — there is nothing in this module that could.

Frozen semantics are imported from the repository rather than reimplemented:
``et_close_cutoff_iso`` for the close-t cutoff, and the covering-row / latest-``effective_from`` /
same-effective-conflict rules mirrored from ``spq1.phase2b.sic_sector.resolve_sector``.

Every input is verified against a pinned SHA-256 before use; a mismatch aborts. Run:

    python scripts/sec001_v3_coverage_measure.py --inputs <dir> [--pins <json>] [--out <json>]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

THETA_NAME = 0.95

#: Inputs and the SHA-256 each must carry. Override with --pins for a later universe version.
DEFAULT_PINS = {
    "governed_grid.json":
        "8c962f2e2d370ecd00fbf478e0a6ded7abf125050e503dd6bd1abb1ba95ef7a0",
    "pit200_membership_v2.json":
        "985672ff3cf49a59f7bf2e7be2183eecdd8e2bdce1d66515751ac243475302dc",
    "segments_projection.json":
        "90d7d9f7b55482ea2b2fdbe338062db2ff48bd70795ace50e232d93c0410e97f",
    "identity_rows.json":
        "82f317acb791cc94397473bc2f0b11f1ab44e1ae85f9b468e7a555acfdfeb29e",
    "sic_mapping.json":
        "633dc4cfa4ee9e7f893e65353ea8bf02f7b9bc1036a95df23a3af2e43e39bcb6",
}

GRID_SHA256 = "baf0da7c20bed5903986c9a94ffae5f54c06cbcba23adb1242ca27e415305a51"


class InputUnpinned(RuntimeError):
    """An input's digest does not match its pin. Fails closed — never measure on unpinned data."""


def load_pinned(directory: Path, name: str, pins: dict[str, str]) -> Any:
    raw = (directory / name).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    want = pins.get(name)
    if want is None:
        raise InputUnpinned(f"{name}: no pinned digest supplied")
    if got != want:
        raise InputUnpinned(f"{name}: sha256 {got} != pinned {want}")
    print(f"  input OK  {name:<28} {len(raw):>9,} B  sha256 {got[:16]}…")
    return json.loads(raw)


def et_close_cutoff(session_date: str) -> datetime:
    """Registered close-t cutoff — mirrors app/research/mr002/spq1/phase2b/cutoff.py."""
    d = datetime.strptime(session_date[:10], "%Y-%m-%d").date()
    return datetime.combine(d, time(16, 0), tzinfo=NY).astimezone(UTC)


class Resolver:
    """The four frozen clauses, evaluated for one (CIK, rebalance) pair."""

    def __init__(self, segments: list[list[Any]], sic_mapping: list[dict[str, Any]]) -> None:
        self.segs: dict[int, list[tuple[datetime, str]]] = collections.defaultdict(list)
        for cik, sic, eff_from, _eff_to in segments:
            self.segs[int(cik)].append(
                (datetime.fromisoformat(eff_from).astimezone(UTC), str(sic)))
        for v in self.segs.values():
            v.sort(key=lambda s: s[0])
        self.rows = [(int(r["sic_start"]), int(r["sic_end"]),
                      str(r["effective_from"])[:10] if r["effective_from"] else None,
                      str(r["research_sector"]), str(r["sector_etf"]), str(r["review_status"]))
                     for r in sic_mapping]

    def resolve(self, cik: int, close_dt: datetime, close_day: str) -> tuple[bool, str | None, str | None]:
        """(resolved, failure_reason, sic). Clause 3 then clause 4; both fail closed."""
        segs = self.segs.get(cik)
        if not segs:
            return False, "C3_no_pit_sic_for_cik", None
        available = [s for s in segs if s[0] <= close_dt]
        if not available:
            return False, "C3_no_sic_accepted_by_close_t", None
        latest = max(s[0] for s in available)
        winners = {s[1] for s in available if s[0] == latest}
        if len(winners) != 1:
            return False, "C3_SECTOR_EFFECTIVE_DATE_CONFLICT", None
        sic_str = next(iter(winners))
        sic = int(sic_str)
        covering = [r for r in self.rows
                    if r[0] <= sic <= r[1] and (r[2] is None or r[2] <= close_day)]
        if not covering:
            return False, "C4_sic_maps_to_no_registered_sector", sic_str
        top = max((r[2] or "") for r in covering)
        top_rows = [r for r in covering if (r[2] or "") == top]
        if len({(r[3], r[4]) for r in top_rows}) != 1:
            return False, "C4_SECTOR_EFFECTIVE_DATE_CONFLICT", sic_str
        if top_rows[0][5] == "excluded_low":
            return False, "C4_mapping_review_status_excluded_low", sic_str
        return True, None, sic_str


def measure(directory: Path, pins: dict[str, str]) -> dict[str, Any]:
    print("Inputs (all pinned by sha256):")
    grid = load_pinned(directory, "governed_grid.json", pins)
    membership = load_pinned(directory, "pit200_membership_v2.json", pins)
    segments = load_pinned(directory, "segments_projection.json", pins)
    identities = load_pinned(directory, "identity_rows.json", pins)
    sic_mapping = load_pinned(directory, "sic_mapping.json", pins)

    slots: list[str] = grid["slots"]
    if len(slots) != grid["slot_count"] or grid["grid_sha256"] != GRID_SHA256:
        raise InputUnpinned("governed grid failed its internal identity check")

    cik_of: dict[str, int] = {}
    for cik, ticker, _perma, _unit_key in identities:
        if ticker in cik_of:
            raise InputUnpinned(f"frozen population carries a duplicate ticker: {ticker}")
        cik_of[ticker] = int(cik)

    resolver = Resolver(segments, sic_mapping)
    reasons: collections.Counter[str] = collections.Counter()
    cache: dict[tuple[int, str], tuple[bool, str | None, str | None]] = {}
    per_slot: list[dict[str, Any]] = []
    num_total = den_total = cik_num = cik_den = 0

    # NOTE: membership carries the holiday Mondays too; only the governed slots are measured.
    for slot in slots:
        members = membership[slot]
        close_dt, close_day = et_close_cutoff(slot), slot[:10]
        resolved_ciks: dict[int, bool] = {}
        num = 0
        for ticker in members:
            cik = cik_of.get(ticker)
            if cik is None:
                reasons["C1_ticker_not_in_frozen_population"] += 1
                continue
            key = (cik, close_day)
            if key not in cache:
                cache[key] = resolver.resolve(cik, close_dt, close_day)
            ok, reason, _sic = cache[key]
            if ok:
                num += 1
            elif reason:
                reasons[reason] += 1
            resolved_ciks[cik] = resolved_ciks.get(cik, False) or ok
        den = len(members)
        num_total += num
        den_total += den
        cik_den += len(resolved_ciks)
        cik_num += sum(1 for v in resolved_ciks.values() if v)
        per_slot.append({"slot": slot, "den": den, "num": num,
                         "R": num / den if den else 0.0,
                         "cik_den": len(resolved_ciks),
                         "cik_num": sum(1 for v in resolved_ciks.values() if v)})

    met = [s for s in per_slot if s["R"] >= THETA_NAME]
    return {
        "artifact": "SEC001_V3_WEEKLY_GRID_COVERAGE_V1",
        "definition": "SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md sec.2; CIK join per owner ruling 2026-08-26",
        "inputs_sha256": pins,
        "grid": {"calendar_version": grid["calendar_version"], "slot_count": len(slots),
                 "start": grid["start"], "end": grid["end"], "grid_sha256": grid["grid_sha256"]},
        "theta_name": THETA_NAME,
        "ticker_week": {"denominator": den_total, "numerator": num_total,
                        "coverage": num_total / den_total,
                        "slots_meeting_theta_name": len(met), "slots": len(per_slot)},
        "cik_week": {"denominator": cik_den, "numerator": cik_num,
                     "coverage": cik_num / cik_den},
        "unresolved_reasons": dict(reasons),
        "per_slot": per_slot,
    }


def span_decision(per_slot: list[dict[str, Any]]) -> dict[str, Any]:
    """Freeze §3 decision rule.

    The five regenerated windows partition the span, so "all five windows >= theta_window" implies
    "span-wide pass fraction >= theta_window". A span below that cannot have five admissible windows
    under any boundary placement, so the gate is decidable without constructing a single window —
    which also means no window boundary can have been influenced by a result.
    """
    ok = [1 if s["R"] >= THETA_NAME else 0 for s in per_slot]
    n = len(per_slot)
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + ok[i]
    spans = [(per_slot[i]["slot"], n - i, suffix[i] / (n - i)) for i in range(n)]
    qualifying = [s for s in spans if s[2] >= 0.95]
    best = max(spans, key=lambda s: s[2])
    return {"best_start": best[0], "best_rebalances": best[1], "best_pass_fraction": best[2],
            "qualifying_spans": len(qualifying),
            "earliest_qualifying_start": min((s[0] for s in qualifying), default=None),
            "outcome": "ADMISSIBLE_SPAN_FOUND" if qualifying else "STOP_REDESIGN_freeze_3_step_3"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inputs", type=Path, required=True,
                    help="directory holding the five pinned input artifacts")
    ap.add_argument("--pins", type=Path, default=None,
                    help="JSON {filename: sha256} overriding the built-in pins")
    ap.add_argument("--out", type=Path, default=None, help="write the result artifact here")
    args = ap.parse_args()

    pins = dict(DEFAULT_PINS)
    if args.pins:
        pins.update(json.loads(args.pins.read_text(encoding="utf-8")))

    result = measure(args.inputs, pins)
    tw, cw = result["ticker_week"], result["cik_week"]
    print()
    print(f"  ticker-week coverage  {100.0 * tw['coverage']:.4f}%  "
          f"({tw['numerator']:,} / {tw['denominator']:,})")
    print(f"  rebalances >= theta_name  {tw['slots_meeting_theta_name']:,} / {tw['slots']:,}")
    print(f"  CIK-week coverage (diagnostic)  {100.0 * cw['coverage']:.4f}%")
    print()
    print("  uncovered-cell sources:")
    for reason, count in sorted(result["unresolved_reasons"].items(), key=lambda kv: -kv[1]):
        print(f"    {reason:<44}{count:>9,}")

    decision = span_decision(result["per_slot"])
    result["span_decision"] = decision
    print()
    print(f"  freeze sec.3 decision: {decision['outcome']}")
    print(f"    best trailing span {decision['best_start']} — "
          f"pass fraction {100.0 * decision['best_pass_fraction']:.3f}% (required 95%)")

    if args.out:
        tmp = args.out.with_suffix(args.out.suffix + ".tmp")
        tmp.write_bytes(json.dumps(result, separators=(",", ":"), sort_keys=True).encode())
        tmp.replace(args.out)
        print(f"  wrote {args.out}  sha256 {hashlib.sha256(args.out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
