#!/usr/bin/env python3
"""GitHub Actions usage report (GITHUB-OPS-001 §7 measurement).

Reconstructs billable runner minutes from the Actions API. The /timing endpoint
returns zeros on this plan, so minutes are computed from per-job started_at /
completed_at, billed rounded UP to the minute the way GitHub charges.

Validated against the July 2026 invoice: 8,007 computed vs 8,073 billed (99%).

Reports event type, run counts, duration percentiles, billable minutes, cancelled
minutes, job-level runtime, retries and failures — the export GITHUB-OPS-001 asks
for before/after each optimization wave.

Usage:
  python scripts/ci_usage_report.py --since 2026-07-01 --until 2026-07-31
  python scripts/ci_usage_report.py --since 2026-08-01 --until 2026-08-31 --json out.json
  python scripts/ci_usage_report.py --since 2026-07-01 --until 2026-07-31 --steps

Requires the `gh` CLI, authenticated.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime

REPO = "jayw04/AI-TRADING-APP"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def gh_json(path: str, paginate: bool = False) -> list[dict]:
    cmd = ["gh", "api", path] + (["--paginate"] if paginate else [])
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        print(f"ERROR: gh api {path}: {p.stderr.decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        return []
    s = p.stdout.decode("utf-8", "replace").strip()
    out, dec, i = [], json.JSONDecoder(), 0
    while i < len(s):
        obj, j = dec.raw_decode(s, i)
        out.append(obj)
        i = j
        while i < len(s) and s[i] in " \n\r\t":
            i += 1
    return out


def parse(t: str | None) -> datetime | None:
    return datetime.strptime(t, FMT) if t else None


def billed_minutes(started: str | None, completed: str | None, conclusion: str | None) -> tuple[int, float]:
    st, ct = parse(started), parse(completed)
    if not st or not ct:
        return 0, 0.0
    secs = max((ct - st).total_seconds(), 0.0)
    if conclusion == "skipped" and secs < 5:
        return 0, secs
    return (math.ceil(secs / 60) if secs > 0 else 0), secs


def fetch(repo: str, since: str, until: str, workers: int, want_steps: bool):
    pages = gh_json(f"repos/{repo}/actions/runs?per_page=100&created={since}..{until}", paginate=True)
    runs = [r for p in pages for r in p.get("workflow_runs", [])]
    if not runs:
        print("No runs in range.", file=sys.stderr)
        raise SystemExit(1)

    def jobs_for(r):
        pages = gh_json(f"repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100", paginate=True)
        return r, [j for p in pages for j in p.get("jobs", [])]

    rows, steps = [], collections.defaultdict(list)
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (r, js) in enumerate(pool.map(jobs_for, runs), 1):
            for j in js:
                mins, secs = billed_minutes(j.get("started_at"), j.get("completed_at"), j.get("conclusion"))
                rows.append({
                    "run": r["id"], "event": r["event"], "day": r["created_at"][:10],
                    "branch": r.get("head_branch"), "run_conclusion": r.get("conclusion"),
                    "attempt": r.get("run_attempt", 1), "job": j.get("name"),
                    "job_conclusion": j.get("conclusion"), "billed_min": mins, "secs": secs,
                })
                if want_steps:
                    for s in j.get("steps", []) or []:
                        _, ssecs = billed_minutes(s.get("started_at"), s.get("completed_at"), s.get("conclusion"))
                        if ssecs > 0:
                            steps[(j.get("name"), s.get("name"))].append(ssecs)
            if n % 150 == 0:
                print(f"  ...{n}/{len(runs)} runs", file=sys.stderr)
    return runs, rows, steps


def table(rows, key, title, tot, top=None):
    agg = collections.defaultdict(lambda: [0, 0])
    for x in rows:
        agg[x[key]][0] += x["billed_min"]
        agg[x[key]][1] += 1
    items = sorted(agg.items(), key=lambda kv: -kv[1][0])[:top]
    print(f"\n{title}")
    print(f"  {'':<46}{'min':>8}{'%':>7}{'count':>8}{'avg':>7}")
    for k, (m, c) in items:
        print(f"  {str(k)[:44]:<46}{m:>8,}{100 * m / tot if tot else 0:>6.1f}%{c:>8,}{m / c if c else 0:>7.1f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="YYYY-MM-DD")
    ap.add_argument("--until", required=True, help="YYYY-MM-DD")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--steps", action="store_true", help="Also break down step timings per job")
    ap.add_argument("--json", type=str, default="", help="Write raw rows to this path")
    args = ap.parse_args(argv)

    runs, rows, steps = fetch(args.repo, args.since, args.until, args.workers, args.steps)
    tot = sum(x["billed_min"] for x in rows)

    print(f"\n{'=' * 72}\nACTIONS USAGE — {args.repo}  {args.since}..{args.until}\n{'=' * 72}")
    print(f"  workflow runs      : {len(runs):,}")
    print(f"  jobs               : {len(rows):,}  ({len(rows) / len(runs):.1f} per run)")
    print(f"  BILLABLE MINUTES   : {tot:,}  ({tot / 60:,.1f} runner-hours)")

    by_run = collections.defaultdict(int)
    for x in rows:
        by_run[x["run"]] += x["billed_min"]
    vals = sorted(by_run.values())
    if vals:
        print(f"  minutes per run    : median {statistics.median(vals):.0f}  mean {statistics.mean(vals):.1f}  max {max(vals)}")
    wall = [(parse(r['updated_at']) - parse(r['created_at'])).total_seconds() / 60
            for r in runs if r.get('updated_at') and r.get('created_at')]
    if wall:
        print(f"  wall-clock per run : median {statistics.median(wall):.1f} min  (billable > wall when jobs run concurrently)")

    concl = collections.defaultdict(int)
    for rid, m in by_run.items():
        rc = next((x["run_conclusion"] for x in rows if x["run"] == rid), None)
        concl[rc or "running"] += m
    print("\nMINUTES BY RUN OUTCOME (cancelled = superseded-run waste):")
    for k, m in sorted(concl.items(), key=lambda kv: -kv[1]):
        print(f"  {str(k):<16}{m:>8,} min{100 * m / tot if tot else 0:>7.1f}%")

    retries = sum(1 for r in runs if r.get("run_attempt", 1) > 1)
    print(f"\n  retried runs       : {retries}")

    table(rows, "job", "BY JOB (job-level runtime):", tot, 16)
    table(rows, "event", "BY EVENT:", tot)
    table(rows, "branch", "BY BRANCH:", tot, 8)
    table(rows, "day", "BY DAY:", tot, 12)

    if args.steps and steps:
        print("\nSTEP BREAKDOWN (avg seconds, jobs >2% of total):")
        job_tot = collections.defaultdict(int)
        for x in rows:
            job_tot[x["job"]] += x["billed_min"]
        for job in [j for j, m in sorted(job_tot.items(), key=lambda kv: -kv[1]) if tot and m / tot > 0.02]:
            ss = {k[1]: v for k, v in steps.items() if k[0] == job}
            if not ss:
                continue
            jt = sum(sum(v) / len(v) for v in ss.values())
            print(f"\n  {job}  (avg job {jt:.0f}s)")
            for nm, v in sorted(ss.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))[:8]:
                a = sum(v) / len(v)
                if a >= 1:
                    print(f"    {nm[:52]:<54}{a:>7.1f}s{100 * a / jt if jt else 0:>7.1f}%")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"runs": len(runs), "billable_minutes": tot, "rows": rows}, fh)
        print(f"\nraw rows -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
