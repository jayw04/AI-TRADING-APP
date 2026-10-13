"""Classify the missing-minute census (pure, offline; reads the frozen manifest and probe output).

    python -I classify_census.py --manifest M.json --probe PROBE.json [--probe P2.json] --out OUT.json

Per MISSING MINUTE (frozen method, in this order):

  UNRESOLVED_INCOMPLETE          the response was not complete (cap, HTTP error, truncation) or the
                                 sample was never attempted
  UNRESOLVED_CONTROL_FAILED      a stored-bar control minute in the window returned no bar-eligible
                                 trade, or returned timestamps fall outside the query window: the
                                 query construction (request mapping / timing / boundaries) is
                                 not verified (controls do NOT establish issuer identity)
  UNRESOLVED_NO_CONTROL          no stored-bar minute inside the window to verify against
  UNRESOLVED_SUSPECTED_PROVIDER_GAP  the minute is a suspected common-provider gap (>= OUTAGE_SHARE
                                 of the day's symbols lack a bar): never accounted for
  TRADES_PRESENT_BAR_ABSENT      at least one trade in the minute is bar-eligible under the
                                 documented rule yet no bar is stored: a discrepancy finding
  ACCOUNTED_FOR_POSITIVE         trades are present and every one is documented as NOT updating a
                                 minute bar (positive evidence)
  ACCOUNTED_FOR_EMPTY_SAME_PROVIDER  a complete response returned no trade in the minute (same
                                 provider as the bars: supporting, not independent, evidence)

A day's opening range is ACCOUNTED when all its missing minutes are ACCOUNTED_FOR_*. Counts are
reported for the strict reading (positive evidence only) and for both tiers. Nothing here
fabricates a bar or an opening price.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

UNRESOLVED_INCOMPLETE = "UNRESOLVED_INCOMPLETE"
UNRESOLVED_CONTROL_FAILED = "UNRESOLVED_CONTROL_FAILED"
UNRESOLVED_NO_CONTROL = "UNRESOLVED_NO_CONTROL"
UNRESOLVED_GAP = "UNRESOLVED_SUSPECTED_PROVIDER_GAP"
BAR_ABSENT = "TRADES_PRESENT_BAR_ABSENT"
ACCOUNTED_POSITIVE = "ACCOUNTED_FOR_POSITIVE"
ACCOUNTED_EMPTY = "ACCOUNTED_FOR_EMPTY_SAME_PROVIDER"
ACCOUNTED = (ACCOUNTED_POSITIVE, ACCOUNTED_EMPTY)


def _record_matches(sample: dict[str, Any], rec: dict[str, Any]) -> bool:
    """The probe record must describe exactly this manifest sample (ids alone are not trusted)."""
    want = {
        "symbol": sample.get("symbol"),
        "request_symbol": sample.get("request_symbol"),
        "asof": sample.get("asof"),
        "day": sample.get("day"),
        "interval_et": f"{sample.get('interval_start_et')}-{sample.get('interval_end_et')}",
        "window_et": f"{sample.get('window_start_et')}-{sample.get('window_end_et')}",
    }
    return all(rec.get(k) == v for k, v in want.items() if v is not None and v != "None-None")


def classify_sample(sample: dict[str, Any], rec: dict[str, Any] | None) -> dict[str, str]:
    """minute (HH:MM) -> class for every missing minute of one sample."""
    minutes = {m[:5] for m in sample["missing_minutes"]}
    if rec is None or not rec.get("complete") or rec.get("http_status") != 200:
        return dict.fromkeys(minutes, UNRESOLVED_INCOMPLETE)
    if not _record_matches(sample, rec):  # another symbol-day/interval: never applied
        return dict.fromkeys(minutes, UNRESOLVED_INCOMPLETE)
    per = rec.get("minutes", {})
    controls = [m[:5] for m in sample["control_minutes"]]
    if not rec.get("timestamps_within_window", False):
        return dict.fromkeys(minutes, UNRESOLVED_CONTROL_FAILED)
    if not controls:
        return dict.fromkeys(minutes, UNRESOLVED_NO_CONTROL)
    if any(per.get(m, {}).get("eligible", 0) < 1 for m in controls):
        return dict.fromkeys(minutes, UNRESOLVED_CONTROL_FAILED)
    gap = {m[:5] for m in sample.get("suspected_provider_gap_minutes", [])}
    out: dict[str, str] = {}
    for m in minutes:
        slot = per.get(m, {"trades": 0, "eligible": 0})
        if m in gap:
            out[m] = UNRESOLVED_GAP
        elif slot["eligible"] > 0:
            out[m] = BAR_ABSENT
        elif slot["trades"] > 0:
            out[m] = ACCOUNTED_POSITIVE
        else:
            out[m] = ACCOUNTED_EMPTY
    return out


def classify(manifest: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    minute_class: Counter[str] = Counter()
    by_day: dict[tuple[str, str], list[str]] = defaultdict(list)
    per_sample: list[dict[str, Any]] = []
    for s in manifest["samples"]:
        res = classify_sample(s, records.get(s["id"]))
        minute_class.update(res.values())
        by_day[(s["symbol"], s["day"])].extend(res.values())
        per_sample.append(
            {
                "id": s["id"],
                "symbol": s["symbol"],
                "day": s["day"],
                "interval_et": f"{s.get('interval_start_et')}-{s.get('interval_end_et')}",
                "classes": dict(sorted(res.items())),
            }
        )
    days = len(by_day)
    strict = sum(1 for v in by_day.values() if all(c == ACCOUNTED_POSITIVE for c in v))
    both = sum(1 for v in by_day.values() if all(c in ACCOUNTED for c in v))
    with_bar_absent = sum(1 for v in by_day.values() if BAR_ABSENT in v)
    unresolved = sum(1 for v in by_day.values() if any(c.startswith("UNRESOLVED") for c in v))
    return {
        "schema": "range002.census_classification.v1",
        "rule_source": "https://docs.alpaca.markets/us/docs/market-data-faq (condition table, minute bars)",
        "samples": len(manifest["samples"]),
        "missing_minutes": sum(minute_class.values()),
        "minute_classes": dict(sorted(minute_class.items())),
        "incomplete_member_days": days,
        "days_all_minutes_accounted_positive_only": strict,
        "days_all_minutes_accounted_both_tiers": both,
        "days_with_trades_present_bar_absent": with_bar_absent,
        "days_with_any_unresolved_minute": unresolved,
        "per_sample": per_sample,
    }


def _load_records(paths: list[Path]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in paths:
        text = p.read_text(encoding="utf-8")
        seen_here: set[str] = set()
        if p.suffix == ".jsonl":
            recs = [json.loads(x) for x in text.splitlines() if x.strip()]
        else:
            recs = json.loads(text)["records"]
        for r in recs:
            if r["id"] in out or r["id"] in seen_here:
                raise SystemExit(f"duplicate probe record id {r['id']}: refused")
            seen_here.add(r["id"])
            out[r["id"]] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--probe", required=True, type=Path, action="append")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; never overwritten")
    man_sha = hashlib.sha256(a.manifest.read_bytes()).hexdigest()
    for pth in a.probe:
        if pth.suffix != ".jsonl":
            bound = json.loads(pth.read_text(encoding="utf-8")).get("manifest_sha256")
            if bound is not None and bound != man_sha:
                raise SystemExit(f"{pth.name} was produced for another manifest: refused")
    res = classify(json.loads(a.manifest.read_text(encoding="utf-8")), _load_records(a.probe))
    res["manifest_sha256"] = hashlib.sha256(a.manifest.read_bytes()).hexdigest()
    res["probe_files_sha256"] = [hashlib.sha256(x.read_bytes()).hexdigest() for x in a.probe]
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out} sha256={hashlib.sha256(text.encode()).hexdigest()}")
    print({k: v for k, v in res.items() if k != "per_sample"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
