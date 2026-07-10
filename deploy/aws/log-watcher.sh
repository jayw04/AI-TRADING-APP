#!/usr/bin/env bash
# Workbench log watcher + ADR 0035 responder (ADR 0032 ops). Every 5 min via the
# workbench-log-watcher systemd timer: scans container logs for errors/issues,
# journals them to /opt/workbench/data/ops/issues.jsonl, auto-fixes ONLY the
# provably-safe environment faults (Level 1/2, budgeted), and SNS-alerts the
# rest immediately. See docs/runbook/log-watcher.md.
set -uo pipefail

exec /usr/bin/python3 /opt/workbench/app/scripts/ops/log_watcher.py
