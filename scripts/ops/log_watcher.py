#!/usr/bin/env python3
"""Workbench log watcher + operational responder (ADR 0035, ADR 0032 ops).

Runs HOST-SIDE on the paper box every 5 minutes (systemd timer
``workbench-log-watcher``). Each pass:

1. **Scan** — reads each workbench container's logs since the last cursor and
   classifies error/issue lines (structlog ``"level": "error"``, tracebacks,
   curated ``*_failed`` warning events, credential failures). Also runs
   synthetic environment checks: container state, docker healthcheck, disk.
2. **Journal** — appends every NEW issue (fingerprint-deduped) to
   ``/opt/workbench/data/ops/issues.jsonl``. This file is the durable
   "separate error file" an operator (or a future analyzer) can read.
3. **Respond, per ADR 0035**:
   - **Level 1/2 (auto-correct/retry)** — ONLY the synthetic environment
     faults whose fix is provably safe and involves no trading decision:
     a container that is exited/unhealthy → ``docker restart`` (budgeted:
     30-min cooldown, max 2/day per container, else escalate to ORANGE);
     disk ≥90% → ``docker system prune -f`` (dangling only). Every action is
     journaled to ``remediations.jsonl`` AND announced via SNS (YELLOW).
   - **Level 3 (alert + recommend)** — every log-parsed issue. A traceback's
     correct fix cannot be proven mechanically, so the watcher changes
     nothing and emails the sample lines immediately (per-fingerprint
     6-hour alert cooldown so a repeating line cannot storm the inbox).
   - **Level 4 (never auto-correct)** — lines matching risk-control state
     (breaker/halt/daily-loss...) are flagged RED alert-only, explicitly:
     automation may not touch them (ADR 0035 invariant 1).

Stdlib only; uses the docker CLI and ``aws sns publish`` (instance role).
State in ``/opt/workbench/data/ops/watcher_state.json`` (cursor, alert
timestamps, restart budgets). Fail-soft: any scan error becomes its own
alert rather than a crash loop.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

OPS_DIR = os.environ.get("WORKBENCH_OPS_DIR", "/opt/workbench/data/ops")
STATE_PATH = os.path.join(OPS_DIR, "watcher_state.json")
ISSUES_PATH = os.path.join(OPS_DIR, "issues.jsonl")
REMEDIATIONS_PATH = os.path.join(OPS_DIR, "remediations.jsonl")

CONTAINERS = [
    "workbench-backend",
    "workbench-frontend",
    "workbench-mcp",
    "trading-workbench-workbench-mcp-1",
    "trading-workbench-agent-1",
]
# Only the backend is trading-critical; others get gentler handling (no RED).
CRITICAL_CONTAINERS = {"workbench-backend"}

SNS_TOPIC = "arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

ALERT_COOLDOWN_S = 6 * 3600          # one email per fingerprint per 6h
RESTART_COOLDOWN_S = 30 * 60         # min gap between restarts of one container
MAX_RESTARTS_PER_DAY = 2             # then escalate ORANGE and stop acting
DISK_ALERT_PCT = 90
FIRST_RUN_LOOKBACK_MIN = 15
MAX_SAMPLE_CHARS = 700

# --- classification ---------------------------------------------------------
# Level 4 (risk-control state): NEVER auto-corrected, alert-only (ADR 0035).
LEVEL4_RE = re.compile(
    r"breaker|halt|daily_loss|drawdown|risk_check_failed|trading_blocked", re.I
)
# Log lines that are error-severity on their face.
ERROR_PATTERNS = [
    re.compile(r'"level": "error"'),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"CRITICAL"),
    re.compile(r"PermanentAlpacaError|unauthorized", re.I),
]
# Curated warning-severity structlog events worth surfacing between daily reports.
WARN_EVENT_RE = re.compile(
    r'"event": "([a-z0-9_]*(?:_failed|_error|_missing_today|_mismatch)[a-z0-9_]*)"'
)
# Benign noise excluded outright (test markers, our own watcher, expected fallbacks).
BENIGN_RE = re.compile(r"\[TEST\]|log_watcher|healthcheck.*passed", re.I)

_STRUCTLOG_EVENT_RE = re.compile(r'"event": "([^"]+)"')
_NORMALIZE_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27,}|\d[\d.,:TZ+-]*")


def utcnow() -> datetime:
    return datetime.now(UTC)


def sh(cmd: list[str], *, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(OPS_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, STATE_PATH)


def journal(path: str, record: dict) -> None:
    os.makedirs(OPS_DIR, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def sns(subject: str, message: str) -> None:
    code, out = sh([
        "aws", "sns", "publish", "--region", AWS_REGION, "--topic-arn", SNS_TOPIC,
        "--subject", subject[:99], "--message", message,
    ])
    if code != 0:
        print(f"SNS publish failed: {out}", file=sys.stderr)


def fingerprint(line: str) -> str:
    """Stable id for a repeating issue: the structlog event name when present,
    else the line with ids/numbers/timestamps stripped, truncated."""
    m = _STRUCTLOG_EVENT_RE.search(line)
    if m:
        return f"event:{m.group(1)}"
    return "text:" + _NORMALIZE_RE.sub("#", line).strip()[:100]


def classify(line: str) -> dict | None:
    """One log line → issue dict, or None if not an issue."""
    if BENIGN_RE.search(line):
        return None
    level4 = bool(LEVEL4_RE.search(line))
    if any(p.search(line) for p in ERROR_PATTERNS):
        sev = "error"
    else:
        m = WARN_EVENT_RE.search(line)
        if not m and not level4:
            return None
        sev = "warning"
    return {
        "kind": "log",
        "severity": "level4" if level4 else sev,
        "fingerprint": fingerprint(line),
        "sample": line.strip()[:MAX_SAMPLE_CHARS],
    }


# --- scanning ----------------------------------------------------------------

def scan_container_logs(container: str, since_iso: str) -> list[dict]:
    code, out = sh(["docker", "logs", container, "--since", since_iso], timeout=90)
    if code != 0:
        return [{
            "kind": "scan_error", "severity": "warning",
            "fingerprint": f"scan_error:{container}",
            "sample": out.strip()[:MAX_SAMPLE_CHARS], "container": container,
        }]
    issues: dict[str, dict] = {}
    for line in out.splitlines():
        issue = classify(line)
        if issue is None:
            continue
        issue["container"] = container
        prev = issues.get(issue["fingerprint"])
        if prev:
            prev["count"] = prev.get("count", 1) + 1
        else:
            issue["count"] = 1
            issues[issue["fingerprint"]] = issue
    return list(issues.values())


def check_environment() -> list[dict]:
    """Synthetic Level 1/2-eligible checks: container state, health, disk."""
    issues: list[dict] = []
    for c in CONTAINERS:
        code, out = sh(["docker", "inspect", "-f",
                        "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", c])
        state = out.strip() if code == 0 else f"inspect_failed: {out.strip()[:120]}"
        if code != 0 or not state.startswith("running") or "unhealthy" in state:
            issues.append({
                "kind": "container_bad", "severity": "error", "container": c,
                "fingerprint": f"container_bad:{c}", "sample": state,
                "count": 1,
            })
    code, out = sh(["df", "--output=pcent", "/"])
    if code == 0:
        try:
            pct = int(out.splitlines()[-1].strip().rstrip("%"))
            if pct >= DISK_ALERT_PCT:
                issues.append({
                    "kind": "disk_high", "severity": "error",
                    "fingerprint": "disk_high:/", "sample": f"root filesystem at {pct}%",
                    "count": 1, "pct": pct,
                })
        except ValueError:
            pass
    return issues


# --- responding (ADR 0035) ----------------------------------------------------

def _budget_ok(state: dict, key: str) -> tuple[bool, str]:
    now = utcnow()
    budgets = state.setdefault("restart_budgets", {})
    b = budgets.setdefault(key, {"day": now.date().isoformat(), "count": 0, "last": None})
    if b["day"] != now.date().isoformat():
        b.update({"day": now.date().isoformat(), "count": 0})
    if b["last"]:
        last = datetime.fromisoformat(b["last"])
        if (now - last).total_seconds() < RESTART_COOLDOWN_S:
            return False, "cooldown"
    if b["count"] >= MAX_RESTARTS_PER_DAY:
        return False, "daily budget exhausted"
    return True, ""


def _budget_spend(state: dict, key: str) -> None:
    b = state["restart_budgets"][key]
    b["count"] += 1
    b["last"] = utcnow().isoformat()


def remediate(issue: dict, state: dict) -> dict | None:
    """Level 1/2 playbook. Returns a remediation record, or None (alert instead).

    ONLY environment faults are auto-fixed: a fix must be provably operationally
    safe and involve no trading decision (ADR 0035 invariant 1/3). Log-parsed
    issues and anything matching risk-control state always fall through to
    alert-only."""
    if issue.get("severity") == "level4":
        return None  # ADR 0035 Level 4: never auto-correct risk-control state

    if issue["kind"] == "container_bad":
        c = issue["container"]
        ok, why = _budget_ok(state, c)
        if not ok:
            issue["escalation"] = f"auto-restart withheld ({why}) — needs an operator (ORANGE)"
            return None
        code, out = sh(["docker", "restart", c], timeout=180)
        _budget_spend(state, c)
        _, after = sh(["docker", "inspect", "-f",
                       "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", c])
        return {
            "action": "docker_restart", "target": c, "ok": code == 0,
            "before": issue["sample"], "after": after.strip() or out.strip()[:200],
            "level": 1,
        }

    if issue["kind"] == "disk_high":
        code, out = sh(["docker", "system", "prune", "-f"], timeout=300)
        _, df_after = sh(["df", "--output=pcent", "/"])
        return {
            "action": "docker_system_prune", "target": "/", "ok": code == 0,
            "before": issue["sample"],
            "after": f"root at {df_after.splitlines()[-1].strip() if df_after else '?'}",
            "detail": out.strip().splitlines()[-1][:200] if out.strip() else "",
            "level": 1,
        }

    return None  # everything else: Level 3 alert-only


def main() -> int:
    state = load_state()
    now = utcnow()
    since = state.get("cursor") or (now - timedelta(minutes=FIRST_RUN_LOOKBACK_MIN)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    scan_end = now.strftime("%Y-%m-%dT%H:%M:%S")

    issues: list[dict] = []
    for c in CONTAINERS:
        issues.extend(scan_container_logs(c, since))
    issues.extend(check_environment())

    alerts = state.setdefault("alerted", {})  # fingerprint -> last alert iso
    fixed, alerted, suppressed = [], [], []

    for issue in issues:
        issue["ts"] = now.isoformat()
        journal(ISSUES_PATH, issue)

        rem = remediate(issue, state)
        if rem is not None:
            rem["ts"] = now.isoformat()
            rem["issue_fingerprint"] = issue["fingerprint"]
            journal(REMEDIATIONS_PATH, rem)
            fixed.append((issue, rem))
            continue

        last = alerts.get(issue["fingerprint"])
        if last and (now - datetime.fromisoformat(last)).total_seconds() < ALERT_COOLDOWN_S:
            suppressed.append(issue)
            continue
        alerts[issue["fingerprint"]] = now.isoformat()
        alerted.append(issue)

    # --- notify ---
    if fixed:
        lines = ["Watcher AUTO-RECOVERED (ADR 0035 Level 1/2, YELLOW):", ""]
        for issue, rem in fixed:
            lines.append(f"- {issue['fingerprint']}: {rem['action']} on {rem.get('target')} "
                         f"ok={rem['ok']}  before='{rem['before']}' after='{rem['after']}'")
        lines.append("")
        lines.append(f"Audit: {REMEDIATIONS_PATH} (append-only). "
                     "If the same fault recurs past its budget the watcher stops acting and escalates.")
        sns("Workbench watcher: auto-recovered", "\n".join(lines))

    if alerted:
        level4s = [i for i in alerted if i["severity"] == "level4"]
        errors = [i for i in alerted if i["severity"] == "error"]
        warns = [i for i in alerted if i["severity"] == "warning"]
        lines = []
        if level4s:
            lines.append("RED — RISK-CONTROL STATE (ADR 0035 Level 4: automation will NOT touch "
                         "this; operator action required):")
            lines += [f"- [{i['container']}] x{i.get('count', 1)}  {i['sample']}" for i in level4s]
            lines.append("")
        if errors:
            lines.append("ORANGE — errors (alert + recommend; not auto-fixable safely):")
            for i in errors:
                esc = f"  ({i['escalation']})" if i.get("escalation") else ""
                lines.append(f"- [{i.get('container', 'host')}] x{i.get('count', 1)}  {i['sample']}{esc}")
            lines.append("")
        if warns:
            lines.append("YELLOW — warnings:")
            lines += [f"- [{i.get('container', 'host')}] x{i.get('count', 1)}  {i['sample']}" for i in warns]
            lines.append("")
        lines.append(f"Journal: {ISSUES_PATH}. Repeat alerts for the same fingerprint are "
                     f"suppressed for {ALERT_COOLDOWN_S // 3600}h.")
        worst = "RED" if level4s else ("ORANGE" if errors else "YELLOW")
        sns(f"Workbench watcher: {worst} — {len(alerted)} new issue(s)", "\n".join(lines))

    state["cursor"] = scan_end
    state["last_run"] = now.isoformat()
    save_state(state)
    print(json.dumps({
        "scanned_since": since, "issues": len(issues), "auto_fixed": len(fixed),
        "alerted": len(alerted), "suppressed": len(suppressed),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
