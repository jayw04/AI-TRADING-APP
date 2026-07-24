"""Daily operational health check for account 4 / momentum-daily (id=11).

Read-only. Runs INSIDE the backend container against the live DB, same
pattern as daily_report.py:

    ssh -o ClearAllForwardings=yes workbench \
        'sudo docker exec -i workbench-backend python -' \
        < scripts/reports/acct4_daily_check.py

Prints one PASS/WARN/CRIT line per checklist item and a final verdict.
Companion runbook: docs/runbook/account4_momentum_daily_daily_ops.md
"""

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DB_PATH = "file:/app/data/workbench.sqlite?mode=ro"
FACTOR_DB = "/app/data/factor_data.duckdb"
ACCOUNT_ID = 4
USER_ID = 4
STRATEGY_ID = 11

EXPECTED_STATUS = "PAPER"
EXPECTED_SCHEDULE = "50 15 * * mon-fri"
EXPECTED_VERSION = "0.2.0"
EXPECTED_REGIME_MODE = "graduated"
EXPECTED_MAX_DAILY_LOSS = 2000
EXPECTED_MAX_POSITION_NOTIONAL = 25000
EXPECTED_MAX_GROSS = 100000
EXPECTED_ALLOW_SHORT = 0
MAX_NAMES = 5  # entry_rank
EQUAL_WEIGHT_REL_TOL = 0.35  # relative deviation from equal weight before we flag

TERMINAL_ORDER_STATUSES = ("FILLED", "CANCELED", "REJECTED", "EXPIRED")
DATA_HEALTH_SIGNAL_REASONS = (
    "factor_unavailable_hold",
    "regime_stale_degraded_gross",
    "regime_stale_blind_flat",
)

ET = ZoneInfo("America/New_York")
now_utc = datetime.now(timezone.utc)
now_et = now_utc.astimezone(ET)
today_et = now_et.date()
today_utc = now_utc.strftime("%Y-%m-%d")
is_weekday = now_et.weekday() < 5
post_eval = is_weekday and (now_et.hour, now_et.minute) >= (16, 5)


def prev_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:  # holidays not modeled; runbook covers them
        d -= timedelta(days=1)
    return d


results = []


def check(name, ok, detail, warn=False):
    level = "PASS" if ok else ("WARN" if warn else "CRIT")
    results.append((level, name, detail))


db = sqlite3.connect(DB_PATH, uri=True)
db.row_factory = sqlite3.Row

# ---------------- A. registration / pins ----------------
s = db.execute(
    "SELECT status, schedule, version, params_json FROM strategies WHERE id=?",
    (STRATEGY_ID,),
).fetchone()
if s is None:
    check("strategy_exists", False, f"strategy id={STRATEGY_ID} NOT FOUND")
else:
    check(
        "strategy_status",
        s["status"] == EXPECTED_STATUS,
        f"status={s['status']} (expect {EXPECTED_STATUS})",
    )
    check(
        "strategy_schedule",
        s["schedule"] == EXPECTED_SCHEDULE,
        f"schedule={s['schedule']!r} (expect {EXPECTED_SCHEDULE!r})",
    )
    check(
        "strategy_version",
        s["version"] == EXPECTED_VERSION,
        f"version={s['version']} (expect {EXPECTED_VERSION})",
    )
    params = json.loads(s["params_json"] or "{}")
    check(
        "regime_mode_pinned",
        params.get("regime_mode") == EXPECTED_REGIME_MODE,
        f"regime_mode={params.get('regime_mode')!r} (expect {EXPECTED_REGIME_MODE!r}; "
        "ABSENT would silently fall back to class defaults)",
    )

run = db.execute(
    "SELECT id, status, started_at, ended_at, error_text FROM strategy_runs "
    "WHERE strategy_id=? ORDER BY id DESC LIMIT 1",
    (STRATEGY_ID,),
).fetchone()
if run is None:
    check("active_run", False, "no strategy_runs rows at all")
else:
    ok = run["status"] == EXPECTED_STATUS and run["ended_at"] is None
    check(
        "active_run",
        ok,
        f"run {run['id']} status={run['status']} started={run['started_at']} "
        f"ended={run['ended_at']} err={run['error_text'] or '-'}",
    )

# ---------------- B. data freshness ----------------
try:
    import duckdb

    fdb = duckdb.connect(FACTOR_DB, read_only=True)
    sep_max = fdb.execute("SELECT max(date) FROM sep").fetchone()[0]
    last_ingest = fdb.execute(
        "SELECT max(started_at) FROM ingest_runs WHERE status='ok'"
    ).fetchone()[0]
    failed_today = fdb.execute(
        "SELECT count(*) FROM ingest_runs WHERE status<>'ok' AND started_at >= ?",
        [now_et.strftime("%Y-%m-%d")],
    ).fetchone()[0]
    fdb.close()

    # Sharadar SEP publishes T-1: after the morning refresh, expect data through
    # the PREVIOUS trading day. One extra day behind = WARN (holiday/pub delay),
    # more = CRIT (the factor_data_staleness_gap failure mode). Anchor to the
    # last weekday refresh: weekends and pre-refresh mornings judge against the
    # ingest that has actually had a chance to run.
    ref_day = today_et
    if not is_weekday or (now_et.hour, now_et.minute) < (6, 30):
        ref_day = prev_trading_day(today_et)
    expect_through = prev_trading_day(ref_day)
    tolerated = prev_trading_day(expect_through)
    if sep_max is None:
        check("factor_data_fresh", False, "sep table EMPTY")
    elif sep_max >= expect_through:
        check("factor_data_fresh", True, f"sep through {sep_max} (expect ≥ {expect_through})")
    elif sep_max >= tolerated:
        check(
            "factor_data_fresh", False,
            f"sep through {sep_max}, expected ≥ {expect_through} — 1 day behind "
            "(holiday? publication delay?)", warn=True,
        )
    else:
        check(
            "factor_data_fresh", False,
            f"sep through {sep_max}, expected ≥ {expect_through} — STALE; "
            "momentum-daily will degrade gross / go flat on stale regime data",
        )
    ingest_ran_today = last_ingest is not None and last_ingest.date() == today_et
    check(
        "factor_ingest_ran_today",
        (not is_weekday) or ingest_ran_today,
        f"last ok ingest={last_ingest}; failed rows today={failed_today}",
        warn=True,
    )
    check("factor_ingest_no_failures", failed_today == 0,
          f"{failed_today} non-ok ingest_runs today", warn=True)
except Exception as exc:  # noqa: BLE001
    check("factor_data_fresh", False, f"could not read {FACTOR_DB}: {exc}")

# ---------------- C. eval + rebalance correctness ----------------
state = {
    r["key"]: (r["value"], r["updated_at"])
    for r in db.execute(
        "SELECT key, value, updated_at FROM strategy_state WHERE strategy_id=?",
        (STRATEGY_ID,),
    )
}


def state_val(key):
    raw = state.get(key, (None, None))[0]
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


last_eval = state_val("last_eval_date")
if post_eval:
    check(
        "eval_ran_today",
        last_eval == str(today_et),
        f"last_eval_date={last_eval!r} (expect {today_et}) — if missing, the 15:50 ET "
        "dispatch did not reach on_bar: check engine logs + session gate "
        "(or today is a market holiday — holidays are not modeled here)",
    )
else:
    check("eval_ran_today", True,
          f"skipped (weekend or before 16:05 ET); last_eval_date={last_eval!r}")

lifecycle = state_val("rebalance_lifecycle") or {}
if lifecycle:
    incomplete = (
        lifecycle.get("attempted_at")
        and not lifecycle.get("completed_at")
        and str(lifecycle.get("signal_date")) <= str(today_et)
    )
    check(
        "rebalance_lifecycle",
        not incomplete,
        f"{lifecycle} — attempted but never completed = orders may have been cut short",
    )
else:
    check("rebalance_lifecycle", True, "no lifecycle state yet (no rebalance attempted)")

regime = state_val("prev_regime")
sig_today = db.execute(
    "SELECT id, type, payload_json, received_at FROM signals "
    "WHERE strategy_id=? AND received_at >= ? ORDER BY id",
    (STRATEGY_ID, today_utc),
).fetchall()
reasons_today = []
for r in sig_today:
    try:
        reasons_today.append(json.loads(r["payload_json"] or "{}").get("reason"))
    except (TypeError, ValueError):
        pass
data_health_hits = [x for x in reasons_today if x in DATA_HEALTH_SIGNAL_REASONS]
check(
    "no_data_degradation_signals",
    not data_health_hits,
    f"today's signal reasons={reasons_today or 'none'}; regime state={regime}",
    warn=all(h == "regime_stale_degraded_gross" for h in data_health_hits),
)

# ---------------- D. orders / book ----------------
placeholders = ",".join("?" for _ in TERMINAL_ORDER_STATUSES)
stuck = db.execute(
    f"SELECT o.id, sy.ticker, o.side, o.qty, o.status, o.created_at FROM orders o "
    f"LEFT JOIN symbols sy ON sy.id=o.symbol_id "
    f"WHERE o.account_id=? AND o.status NOT IN ({placeholders})",
    (ACCOUNT_ID, *TERMINAL_ORDER_STATUSES),
).fetchall()
old_stuck = []
for o in stuck:
    created = datetime.fromisoformat(o["created_at"]).replace(tzinfo=timezone.utc)
    if now_utc - created > timedelta(minutes=15):
        old_stuck.append(dict(o))
check(
    "no_stuck_orders",
    not old_stuck,
    f"{len(old_stuck)} non-terminal >15min: {old_stuck or 'none'} "
    f"({len(stuck)} non-terminal total)",
)

rej = db.execute(
    "SELECT o.id, sy.ticker, o.side, o.qty, o.rejection_reason FROM orders o "
    "LEFT JOIN symbols sy ON sy.id=o.symbol_id "
    "WHERE o.account_id=? AND o.status='REJECTED' AND o.created_at >= ?",
    (ACCOUNT_ID, today_utc),
).fetchall()
check(
    "no_rejections_today",
    not rej,
    f"{len(rej)} rejected today: {[dict(r) for r in rej] or 'none'}",
    warn=True,
)

pos = db.execute(
    "SELECT sy.ticker, p.qty, p.side, p.market_value FROM positions p "
    "LEFT JOIN symbols sy ON sy.id=p.symbol_id WHERE p.account_id=?",
    (ACCOUNT_ID,),
).fetchall()
gross = sum(abs(p["market_value"] or 0) for p in pos)
shorts = [dict(p) for p in pos if (p["qty"] or 0) < 0 or p["side"] == "short"]
oversized = [dict(p) for p in pos if abs(p["market_value"] or 0) > EXPECTED_MAX_POSITION_NOTIONAL]
book = {p["ticker"]: round(p["market_value"] or 0) for p in pos}
check("no_shorts", not shorts, f"shorts={shorts or 'none'}; book(mv)={book}")
check(
    "position_count",
    len(pos) <= MAX_NAMES,
    f"{len(pos)} names (max {MAX_NAMES}); gross=${gross:,.0f} (cap ${EXPECTED_MAX_GROSS:,})",
)
check("per_position_notional", not oversized,
      f"over ${EXPECTED_MAX_POSITION_NOTIONAL:,}: {oversized or 'none'}")
check("gross_exposure", gross <= EXPECTED_MAX_GROSS, f"gross=${gross:,.0f}")

# Equal-weight shape: every held name should sit near gross/k. A large skew
# means a partial rebalance (some legs filled, some didn't) — cross-check
# against rebalance_lifecycle + stuck/rejected orders above.
if len(pos) >= 2 and gross > 0:
    target_w = 1.0 / len(pos)
    weights = {p["ticker"]: abs(p["market_value"] or 0) / gross for p in pos}
    skewed = {t: round(w, 3) for t, w in weights.items()
              if abs(w - target_w) / target_w > EQUAL_WEIGHT_REL_TOL}
    check("equal_weight_shape", not skewed,
          f"names off equal-weight by >{EQUAL_WEIGHT_REL_TOL:.0%}: {skewed or 'none'} "
          f"(target w={target_w:.3f})", warn=True)
else:
    check("equal_weight_shape", True, f"{len(pos)} position(s) — nothing to compare")

# ---------------- E. account / risk ----------------
acct = db.execute(
    "SELECT circuit_breaker_tripped_at FROM accounts WHERE id=?", (ACCOUNT_ID,)
).fetchone()
check(
    "breaker_clear",
    acct is not None and acct["circuit_breaker_tripped_at"] is None,
    f"circuit_breaker_tripped_at={acct['circuit_breaker_tripped_at'] if acct else 'ACCOUNT MISSING'}",
)

st = db.execute(
    "SELECT equity, last_equity, day_change, updated_at FROM accounts_state "
    "WHERE account_id=?",
    (ACCOUNT_ID,),
).fetchone()
if st is None:
    check("account_state", False, "no accounts_state row")
else:
    dc = st["day_change"] or 0
    detail = (
        f"equity={st['equity']} last_equity={st['last_equity']} "
        f"day_change={dc} (cap -{EXPECTED_MAX_DAILY_LOSS})"
    )
    if dc <= -EXPECTED_MAX_DAILY_LOSS:
        check("daily_loss_headroom", False, detail + " — CAP BREACHED")
    elif dc <= -EXPECTED_MAX_DAILY_LOSS * 0.5:
        check("daily_loss_headroom", False, detail + " — >50% of cap consumed", warn=True)
    else:
        check("daily_loss_headroom", True, detail)
    upd = datetime.fromisoformat(st["updated_at"]).replace(tzinfo=timezone.utc)
    age_min = (now_utc - upd).total_seconds() / 60
    stale = is_weekday and 9 <= now_et.hour < 16 and age_min > 30
    check("state_sync_fresh", not stale,
          f"accounts_state.updated_at {age_min:.0f}min ago", warn=True)

rl = db.execute(
    "SELECT max_daily_loss, max_position_notional, max_gross_exposure, allow_short "
    "FROM risk_limits WHERE user_id=? AND scope_type='GLOBAL'",
    (USER_ID,),
).fetchone()
rl_ok = rl is not None and (
    rl["max_daily_loss"] == EXPECTED_MAX_DAILY_LOSS
    and rl["max_position_notional"] == EXPECTED_MAX_POSITION_NOTIONAL
    and rl["max_gross_exposure"] == EXPECTED_MAX_GROSS
    and rl["allow_short"] == EXPECTED_ALLOW_SHORT
)
check("risk_limits_unchanged", rl_ok, dict(rl) if rl else "NO GLOBAL risk_limits ROW")

# ---------------- report ----------------
tail = db.execute(
    "SELECT id, ts, action, target_id FROM audit_log WHERE user_id=? "
    "ORDER BY id DESC LIMIT 5",
    (USER_ID,),
).fetchall()

print(f"=== ACCOUNT 4 / momentum-daily (id=11) DAILY CHECK — {now_et:%Y-%m-%d %H:%M ET} ===")
worst = "PASS"
for level, name, detail in results:
    icon = {"PASS": "✅", "WARN": "🟡", "CRIT": "🔴"}[level]
    print(f"{icon} {level:4} {name:28} {detail}")
    if level == "CRIT" or (level == "WARN" and worst != "CRIT"):
        worst = level
print("--- today's strategy signals ---")
for r in sig_today:
    print(f"  #{r['id']} {r['received_at']} {r['type']} {r['payload_json'][:140]}")
if not sig_today:
    print("  (none)")
print("--- audit tail (user 4) ---")
for r in tail:
    print(f"  #{r['id']} {r['ts']} {r['action']} target={r['target_id']}")
print(f"=== VERDICT: {worst} ===")
