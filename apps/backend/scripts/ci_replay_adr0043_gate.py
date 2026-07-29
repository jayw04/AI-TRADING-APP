#!/usr/bin/env python3
"""Replay the ADR 0043 gate predicate against real historical pull requests.

Acceptance evidence for GITHUB-OPS-001 PR 1 (ADR-0043 path gating). Answers two
questions the unit tests cannot:

  1. SAFETY  — is there any historical PR where backend FULL ran but the gate would
               have skipped? That set must be EMPTY. A non-empty result means a
               loss-control regression could reach main under a green result.
  2. SAVING  — what share of historical PRs would actually skip the gate? The step's
               total cost is NOT its avoidable cost; most PRs legitimately need it.

Usage:
  python apps/backend/scripts/ci_replay_adr0043_gate.py                # 120 most recent closed PRs
  python apps/backend/scripts/ci_replay_adr0043_gate.py --sample 200
  python apps/backend/scripts/ci_replay_adr0043_gate.py --markdown report.md

Requires the `gh` CLI, authenticated. Exits non-zero if any safety violation is found,
so it can run as a gate rather than only as a report.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ci_classify_changes import (  # noqa: E402
    classify,
    requires_adr0043_by_backend_attribution,
)

REPO = "jayw04/AI-TRADING-APP"
# Cost inputs measured from the July 2026 Actions data (see scripts/ci_usage_report.py).
LIGHT_RUNS_PER_MONTH = 582
STEP_SECONDS = 96.2
BASELINE_MINUTES = 8007

# Categories the replay must demonstrate coverage of. Each maps to a path predicate.
CATEGORIES: dict[str, callable] = {
    "backend app": lambda f: f.startswith("apps/backend/app/"),
    "backend tests": lambda f: f.startswith("apps/backend/tests/"),
    "risk / order path": lambda f: "app/risk/" in f or "order_router" in f,
    "migrations": lambda f: "alembic" in f,
    "workflow": lambda f: f.startswith(".github/"),
    "frontend": lambda f: f.startswith("apps/frontend/"),
    "docs": lambda f: f.startswith(("docs/", "Docs/")),
    "auxiliary projects": lambda f: f.startswith(("apps/mcp-", "apps/agent/")),
}


def gh(path: str) -> list[dict]:
    p = subprocess.run(["gh", "api", path, "--paginate"], capture_output=True)
    if p.returncode:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=120, help="Number of most-recent closed PRs")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--markdown", type=str, default="", help="Write a markdown report here")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args(argv)

    prs = [pr for pg in gh(f"repos/{args.repo}/pulls?state=closed&per_page=100&sort=updated&direction=desc")
           for pr in pg][: args.sample]
    if not prs:
        print("ERROR: no PRs returned (is `gh` authenticated?)", file=sys.stderr)
        return 2

    def files_for(pr):
        pgs = gh(f"repos/{args.repo}/pulls/{pr['number']}/files?per_page=100")
        return pr, [f["filename"] for pg in pgs for f in pg]

    rows = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for pr, fs in ex.map(files_for, prs):
            if not fs:
                continue
            rows.append({
                "number": pr["number"], "title": pr["title"][:60], "files": fs,
                "backend_full": classify(fs)["backend"],
                "gate": requires_adr0043_by_backend_attribution(fs),
            })

    run = [r for r in rows if r["gate"]]
    skip = [r for r in rows if not r["gate"]]
    violations = [r for r in rows if r["backend_full"] and not r["gate"]]
    skip_share = len(skip) / len(rows) if rows else 0.0
    saved_min = skip_share * LIGHT_RUNS_PER_MONTH * STEP_SECONDS / 60

    out = []
    out.append(f"# ADR 0043 gate replay — {len(rows)} historical PRs ({args.repo})\n")
    out.append("Predicate: `requires_adr0043_by_backend_attribution` "
               "(conservative backend attribution, not a precise risk-path classifier).\n")
    out.append("## Safety\n")
    out.append(f"- PRs where backend FULL ran but the gate would skip: **{len(violations)}** (must be 0)\n")
    for v in violations[:10]:
        out.append(f"  - !! #{v['number']} {v['title']}\n")
    out.append("\n## Selection\n")
    out.append(f"- gate WOULD RUN: **{len(run)}** ({100 * len(run) / len(rows):.1f}%) — legitimate required execution\n")
    out.append(f"- gate WOULD SKIP: **{len(skip)}** ({100 * skip_share:.1f}%) — the avoidable portion\n")
    out.append(f"- projected saving: **~{saved_min:.0f} runner-min/month** "
               f"({100 * saved_min / BASELINE_MINUTES:.1f}% of the {BASELINE_MINUTES:,}-min baseline)\n")
    out.append(f"- step total cost was {LIGHT_RUNS_PER_MONTH * STEP_SECONDS / 60:.0f} min/month; "
               f"the difference is required execution, **not** remaining waste\n")
    out.append("\n## Category coverage\n\n| Category | PRs | Gate runs on |\n|---|---|---|\n")
    for name, fn in CATEGORIES.items():
        m = [r for r in rows if any(fn(f) for f in r["files"])]
        if m:
            out.append(f"| {name} | {len(m)} | {sum(1 for r in m if r['gate'])} |\n")
    out.append("\n## Sample of skipped PRs\n\n")
    for r in skip[:15]:
        tops = sorted({f.split("/")[0] for f in r["files"]})
        out.append(f"- #{r['number']} {r['title']} — `{', '.join(tops)}`\n")

    text = "".join(out)
    print(text)
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
        print(f"\nreport -> {args.markdown}")

    if violations:
        print(f"\nFAIL: {len(violations)} safety violation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
