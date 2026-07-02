# Daily Reports

Operational daily snapshots of the paper-trading stack — one Markdown file per day
(`YYYY-MM-DD.md`), generated from the **always-on AWS box** (the single armed host,
ADR 0032). Each report has two jobs:

1. **Summarize** every user account — starting capital, current value, gain/loss,
   fills today, open positions, and the active strategy + its schedule.
2. **Surface issues** — a dedicated **⚠ ISSUES & ALERTS** section at the top that
   flags anything an operator should look at *before* it becomes an incident:
   strategies in `ERROR`, orders stuck non-terminal, blocked accounts, empty
   schedules, and stale factor data.

The point is that a clean report reads "no alerts", and a bad day jumps out at the
top instead of hiding inside a wall of numbers.

## How to generate

The generator runs **inside the backend container** (it needs the broker adapters,
the DB, and the factor store), and prints Markdown to stdout. From the repo, over SSH
to the box:

```bash
# on the AWS box (or any host running the stack)
sudo docker exec -i workbench-backend python - < scripts/reports/daily_report.py \
  > reports/$(date +%F).md
```

Or locally against the laptop stack (dev only):

```bash
docker exec -i workbench-backend python - < scripts/reports/daily_report.py \
  > reports/$(date +%F).md
```

## Reading the ISSUES section

| Marker | Meaning |
|---|---|
| 🔴 | Action needed — ERROR state, blocked account, or an order stuck >60 min |
| 🟡 | Watch — order stuck 15–60 min, empty schedule, stale-ish data |
| ✅ | No alerts — nothing flagged |

## Files

- `scripts/reports/daily_report.py` — the generator (tracked in git).
- `reports/README.md` — this file (tracked).
- `reports/YYYY-MM-DD.md` — the daily outputs (git-ignored; regenerable operational
  artifacts, and they contain account numbers).

## Automating (optional)

A `workbench-daily-report` systemd timer on the box can run the generator each
evening after close and email it via SNS, the same pattern as
`deploy/aws/range-report.sh`. Not wired yet — see follow-ups.
