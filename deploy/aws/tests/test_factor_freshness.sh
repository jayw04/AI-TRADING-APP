#!/usr/bin/env bash
# Hermetic behaviour tests for deploy/aws/factor-freshness.sh (the factor-data readiness
# watchdog). No systemd, no Docker, no AWS, no box: `systemctl`, `docker` and `aws` are
# faked, the clock is pinned via WATCHDOG_NOW_EPOCH, and the sealed artifact + store
# report are fixtures on disk.
#
# The property under test is the one the 2026-08-03/04 timeline exposed: a FRESH STORE
# MUST NOT BE ABLE TO HIDE A DEAD PRODUCER. Every producer-liveness case below therefore
# runs with a perfectly clean store report, and must still fail.
#
# Nothing here touches factor_refresh.py, factor-refresh.sh, or any deployment path.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AWSDIR="$(cd "$HERE/.." && pwd)"
SCRIPT="$AWSDIR/factor-freshness.sh"
UNIT="$AWSDIR/systemd/workbench-factor-freshness.service"

PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); return 0; }
# Must return 0. Several guards below read `<condition> && bad ... || ok ...`, so a `bad`
# that exits non-zero would fall through to `ok` and report the SAME check as both failed
# and passed — a real failure printing a PASS line beside it.
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); if [ -n "${2:-}" ]; then printf '        %s\n' "$2"; fi; return 0; }

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "python3 unavailable"; exit 1; }

# ── clock helpers ────────────────────────────────────────────────────────────────────
# Wall-clock in America/New_York -> epoch. zoneinfo resolves the DST offset, so the
# fixtures mean what they say on both sides of a transition.
ep() {
  "$PY" - "$1" <<'PY'
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
print(int(datetime.fromisoformat(sys.argv[1]).replace(tzinfo=ZoneInfo("America/New_York")).timestamp()))
PY
}
usec() { echo $(( $1 * 1000000 )); }
stamp() { TZ=America/New_York date -d "@$1" '+%a %Y-%m-%d %H:%M:%S %Z'; }

# ── fakes ────────────────────────────────────────────────────────────────────────────
BIN="$(mktemp -d)"
cat > "$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
# Fake systemd. Unit state comes from fixture files named by env; anything unset behaves
# like a unit systemd knows nothing about.
case "${1:-}" in
  show-timezone) printf '%s\n' "${FAKE_HOST_TZ:-America/New_York}"; exit 0;;
  is-failed)     printf '%s\n' "${FAKE_IS_FAILED:-active}"; exit 0;;
  show)
    case "${2:-}" in
      *.timer)   [ -n "${FAKE_TIMER_SHOW:-}" ] && [ -f "$FAKE_TIMER_SHOW" ] && cat "$FAKE_TIMER_SHOW";;
      *.service) [ -n "${FAKE_SVC_SHOW:-}" ]   && [ -f "$FAKE_SVC_SHOW" ]   && cat "$FAKE_SVC_SHOW";;
    esac
    exit 0;;
esac
exit 0
EOF
cat > "$BIN/docker" <<'EOF'
#!/usr/bin/env bash
# Fake `docker exec -i ... backend python -`: swallow the inline query on stdin and emit a
# canned store report. The bash classification logic is what is under test here; the
# DuckDB query itself is exercised against the real store on the box.
cat >/dev/null
if [ "${FAKE_STORE_FAIL:-0}" = "1" ]; then echo "Error: No such container" >&2; exit 1; fi
[ -n "${FAKE_STORE_REPORT:-}" ] && [ -f "$FAKE_STORE_REPORT" ] && cat "$FAKE_STORE_REPORT"
exit 0
EOF
cat > "$BIN/aws" <<'EOF'
#!/usr/bin/env bash
# Fake SNS. Records that a publish was attempted so the alert path is observable, and can
# be made to fail so the "publish failed must not downgrade the verdict" case is real.
[ -n "${SNS_LOG:-}" ] && echo "publish $*" >> "$SNS_LOG"
[ "${FAKE_SNS_FAIL:-0}" = "1" ] && exit 1
exit 0
EOF
chmod +x "$BIN/systemctl" "$BIN/docker" "$BIN/aws"

WORK="$(mktemp -d)"
DATA="$WORK/data"; mkdir -p "$DATA"
SEALED="$DATA/_factor_refresh_universe_sealed.json"
CLEAN_STORE="$WORK/store-clean.txt"
SNS_LOG="$WORK/sns.log"

# A store report with nothing wrong with it. Used for EVERY producer-liveness case, so a
# pass there could only come from the store vouching for the producer — which is the exact
# defect this hardening removes.
cat > "$CLEAN_STORE" <<'EOF'
STATUS sep_max=2026-08-03 lastpricedate=2026-08-03 et_today=2026-08-04 tolerance=4d max_lag=4d min_coverage=0.98
METRIC universe=512 covered=511 coverage=0.9980 missing=0 stale=1 lastpricedate_stale=0 frontier=2026-08-03 cutoff=2026-07-30
EOF

seal() {  # <as_of>
  cat > "$SEALED" <<EOF
{"as_of": "$1",
 "universe": ["AAPL", "MSFT", "SPY"],
 "counts": {"total": 3},
 "digests": {"final_refresh_universe": {"sha256": "abc123", "count": 3}},
 "growth": {"state": "COMPARATIVE_GROWTH_CONTROL_ACTIVE"}}
EOF
}

# timer_fixture <file> <load> <unitfilestate> <activestate> <substate> <next> <last> <armed>
# Empty epoch args render as systemd's "n/a". `raw` mode emits microseconds instead of a
# formatted timestamp — systemd does both depending on version, so both are exercised.
timer_fixture() {
  local f="$1" load="$2" ufs="$3" act="$4" sub="$5" next="${6:-}" last="${7:-}" armed="${8:-}" mode="${9:-formatted}"
  {
    echo "LoadState=$load"
    echo "UnitFileState=$ufs"
    echo "ActiveState=$act"
    echo "SubState=$sub"
    if [ "$mode" = "raw" ]; then
      echo "NextElapseUSecRealtime=$( [ -n "$next" ] && usec "$next" || echo 0 )"
      echo "LastTriggerUSec=$( [ -n "$last" ] && usec "$last" || echo 0 )"
      echo "ActiveEnterTimestamp=$( [ -n "$armed" ] && usec "$armed" || echo 0 )"
    else
      echo "NextElapseUSecRealtime=$( [ -n "$next" ] && stamp "$next" || echo "n/a" )"
      echo "LastTriggerUSec=$( [ -n "$last" ] && stamp "$last" || echo "n/a" )"
      echo "ActiveEnterTimestamp=$( [ -n "$armed" ] && stamp "$armed" || echo "n/a" )"
    fi
  } > "$f"
}

# svc_fixture <file> <load> <result> <execmainstatus> <exit-epoch>
svc_fixture() {
  local f="$1" load="$2" result="$3" status="$4" exit_ep="${5:-}"
  {
    echo "LoadState=$load"
    echo "Result=$result"
    echo "ExecMainStatus=$status"
    echo "ExecMainExitTimestamp=$( [ -n "$exit_ep" ] && stamp "$exit_ep" || echo "n/a" )"
  } > "$f"
}

TIMER_F="$WORK/timer.props"
SVC_F="$WORK/svc.props"

# run <NOW_EPOCH> [EXTRA=VAL ...] -> sets OUT / RC
run() {
  local now="$1"; shift
  : > "$SNS_LOG"
  OUT="$(env -u FAKE_STORE_FAIL -u FAKE_SNS_FAIL -u REFRESH_SKIP_DATES \
    SYSTEMCTL_BIN="$BIN/systemctl" WATCHDOG_DOCKER="$BIN/docker" AWS_BIN="$BIN/aws" \
    PYTHON_BIN="$PY" WORKBENCH_DATA_DIR="$DATA" WATCHDOG_NOW_EPOCH="$now" \
    FAKE_TIMER_SHOW="$TIMER_F" FAKE_SVC_SHOW="$SVC_F" FAKE_STORE_REPORT="$CLEAN_STORE" \
    FAKE_IS_FAILED="active" FAKE_HOST_TZ="America/New_York" SNS_LOG="$SNS_LOG" \
    "$@" bash "$SCRIPT" 2>&1)"
  RC=$?
}

has()  { printf '%s\n' "$OUT" | grep -q -- "$1"; }
line() { printf '%s\n' "$OUT" | grep -q "^$1$"; }

# expect <label> <rc> <producer> <sealed> <data> <overall>
expect() {
  local label="$1" want_rc="$2" p="$3" s="$4" d="$5" o="$6" bad_msgs=""
  [ "$RC" = "$want_rc" ] || bad_msgs="rc=$RC want=$want_rc"
  line "PRODUCER_LIVENESS=$p" || bad_msgs="$bad_msgs; PRODUCER_LIVENESS != $p"
  line "SEALED_GENERATION=$s" || bad_msgs="$bad_msgs; SEALED_GENERATION != $s"
  line "DATA_FRESHNESS=$d"    || bad_msgs="$bad_msgs; DATA_FRESHNESS != $d"
  line "OVERALL_READINESS=$o" || bad_msgs="$bad_msgs; OVERALL_READINESS != $o"
  if [ -z "$bad_msgs" ]; then ok "$label"; else
    bad "$label" "$bad_msgs"
    printf '%s\n' "$OUT" | sed -n '1,12p' | sed 's/^/        | /'
  fi
}

# ═════════════════════════════════════════════════════════════════════════════════════
# A canonical healthy Tuesday: watchdog at 07:00 ET, refresh window 06:00 ET the same day.
# ═════════════════════════════════════════════════════════════════════════════════════
NOW=$(ep 2026-08-04T07:00:00)          # Tue
WIN=$(ep 2026-08-04T06:00:00)          # the expected window
TRIG=$(( WIN + 60 ))                   # timer fired
DONE=$(( WIN + 300 ))                  # service completed
NEXT=$(ep 2026-08-05T06:00:00)         # Wed
ARMED=$(ep 2026-07-01T00:00:00)

healthy() {
  timer_fixture "$TIMER_F" loaded enabled active waiting "$NEXT" "$TRIG" "$ARMED" "${1:-formatted}"
  svc_fixture   "$SVC_F"   loaded success 0 "$DONE"
  seal 2026-08-04
}

echo "== factor-data readiness watchdog =="

echo "-- healthy baseline --"
healthy;      run "$NOW"; expect "healthy producer + current seal + fresh data -> PASS (exit 0)" 0 PASS PASS PASS PASS
healthy raw;  run "$NOW"; expect "same, with systemd raw-usec timestamps -> PASS" 0 PASS PASS PASS PASS
healthy
run "$NOW"; [ ! -s "$SNS_LOG" ] && ok "a passing run publishes no alert" || bad "a passing run publishes no alert"

# ═════════════════════════════════════════════════════════════════════════════════════
# PRODUCER LIVENESS. Every case below keeps the CLEAN store report and a CURRENT seal, so
# only the producer can be at fault — the fresh store must not rescue any of them.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- producer liveness (store is clean and the seal is current in every case) --"

healthy; timer_fixture "$TIMER_F" loaded disabled inactive dead "" "$TRIG" "$ARMED"
run "$NOW"; expect "timer DISABLED with fresh data -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_DISABLED" && ok "  names TIMER_DISABLED" || bad "  names TIMER_DISABLED"

healthy; timer_fixture "$TIMER_F" loaded enabled inactive dead "" "$TRIG" "$ARMED"
run "$NOW"; expect "timer INACTIVE with fresh data -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_INACTIVE" && ok "  names TIMER_INACTIVE" || bad "  names TIMER_INACTIVE"

healthy; timer_fixture "$TIMER_F" masked masked inactive dead "" "$TRIG" "$ARMED"
run "$NOW"; expect "timer MASKED with fresh data -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_MASKED" && ok "  names TIMER_MASKED" || bad "  names TIMER_MASKED"

healthy; timer_fixture "$TIMER_F" not-found "" inactive dead "" "" ""
run "$NOW"; expect "timer MISSING -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_MISSING" && ok "  names TIMER_MISSING" || bad "  names TIMER_MISSING"

healthy; : > "$TIMER_F"
run "$NOW"; expect "systemd reports nothing at all for the timer -> FAIL (fail-closed)" 2 FAIL PASS PASS FAIL

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "" "$TRIG" "$ARMED"
run "$NOW"; expect "timer ACTIVE but NO next trigger -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_NO_NEXT_TRIGGER" && ok "  names TIMER_NO_NEXT_TRIGGER" || bad "  names TIMER_NO_NEXT_TRIGGER"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$(( NOW - 3600 ))" "$TRIG" "$ARMED"
run "$NOW"; expect "next trigger in the PAST -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_NEXT_TRIGGER_IN_PAST" && ok "  names TIMER_NEXT_TRIGGER_IN_PAST" || bad "  names TIMER_NEXT_TRIGGER_IN_PAST"

# systemd spells "never" as UINT64_MAX in raw mode, which overflows 64-bit shell
# arithmetic into a NEGATIVE epoch. That must read as "no next trigger", never as a
# trigger in the distant past.
healthy raw
sed -i 's/^NextElapseUSecRealtime=.*/NextElapseUSecRealtime=18446744073709551615/' "$TIMER_F"
run "$NOW"; expect "next elapse reported as UINT64_MAX (never) -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_NO_NEXT_TRIGGER" && ok "  UINT64_MAX reads as NO next trigger, not a past one" \
  || bad "  UINT64_MAX reads as NO next trigger, not a past one"
has "TIMER_NEXT_TRIGGER_IN_PAST" && bad "  UINT64_MAX must not read as a past trigger" \
  || ok "  UINT64_MAX must not read as a past trigger"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$(ep 2026-08-20T06:00:00)" "$TRIG" "$ARMED"
run "$NOW"; expect "next trigger implausibly far out -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_NEXT_TRIGGER_IMPLAUSIBLE" && ok "  names TIMER_NEXT_TRIGGER_IMPLAUSIBLE" || bad "  names TIMER_NEXT_TRIGGER_IMPLAUSIBLE"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$(ep 2026-08-05T18:00:00)" "$TRIG" "$ARMED"
run "$NOW"; expect "next trigger at the wrong hour -> FAIL" 2 FAIL PASS PASS FAIL
has "TIMER_NEXT_TRIGGER_OFF_SCHEDULE" && ok "  names TIMER_NEXT_TRIGGER_OFF_SCHEDULE" || bad "  names TIMER_NEXT_TRIGGER_OFF_SCHEDULE"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$NEXT" "$(ep 2026-08-03T06:00:00)" "$ARMED"
run "$NOW"; expect "last trigger PRECEDES the expected window (overdue) -> FAIL" 2 FAIL PASS PASS FAIL
has "PRODUCER_OVERDUE" && ok "  names PRODUCER_OVERDUE" || bad "  names PRODUCER_OVERDUE"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$NEXT" "" "$ARMED"
run "$NOW"; expect "timer has NEVER triggered -> FAIL" 2 FAIL PASS PASS FAIL
has "LAST_TRIGGER_MISSING" && ok "  names LAST_TRIGGER_MISSING" || bad "  names LAST_TRIGGER_MISSING"

healthy; timer_fixture "$TIMER_F" loaded enabled active waiting "$NEXT" "" "$(( WIN + 1800 ))"
run "$NOW"; expect "timer armed AFTER the window and never fired -> FAIL" 2 FAIL PASS PASS FAIL
has "WINDOW_MISSED_TIMER_ARMED_LATE" && ok "  distinguishes an armed-late miss from 'never fired'" \
  || bad "  distinguishes an armed-late miss from 'never fired'"

healthy; svc_fixture "$SVC_F" loaded success 0 ""
run "$NOW"; expect "last expected service run ABSENT -> FAIL" 2 FAIL PASS PASS FAIL
has "SERVICE_NO_COMPLETION" && ok "  names SERVICE_NO_COMPLETION" || bad "  names SERVICE_NO_COMPLETION"

healthy; svc_fixture "$SVC_F" loaded success 0 "$(ep 2026-08-03T06:05:00)"
run "$NOW"; expect "service last completed BEFORE the expected window -> FAIL" 2 FAIL PASS PASS FAIL

healthy; svc_fixture "$SVC_F" not-found "" "" ""
run "$NOW"; expect "service unit MISSING -> FAIL" 2 FAIL PASS PASS FAIL
has "SERVICE_MISSING" && ok "  names SERVICE_MISSING" || bad "  names SERVICE_MISSING"

healthy; svc_fixture "$SVC_F" loaded exit-code 1 "$DONE"
run "$NOW" FAKE_IS_FAILED=failed; expect "last service run FAILED -> FAIL" 2 FAIL PASS PASS FAIL
has "SERVICE_FAILED" && ok "  names SERVICE_FAILED" || bad "  names SERVICE_FAILED"

healthy; svc_fixture "$SVC_F" loaded success 1 "$DONE"
run "$NOW"; expect "service Result=success but non-zero exit status -> FAIL" 2 FAIL PASS PASS FAIL

# host timezone: OnCalendar carries no timezone, so a host in the wrong zone fires the
# window at a different wall-clock time than the schedule claims.
healthy
run "$NOW" FAKE_HOST_TZ=UTC; expect "host timezone != pinned schedule timezone -> FAIL" 2 FAIL PASS PASS FAIL
has "SCHEDULE_TZ_MISMATCH" && ok "  names SCHEDULE_TZ_MISMATCH" || bad "  names SCHEDULE_TZ_MISMATCH"

# ═════════════════════════════════════════════════════════════════════════════════════
# SEALED GENERATION — the #606 contract.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- sealed refresh progression --"

healthy; rm -f "$SEALED"
run "$NOW"; expect "sealed artifact MISSING -> FAIL" 2 PASS FAIL PASS FAIL
has "SEALED_ARTIFACT_MISSING" && ok "  names SEALED_ARTIFACT_MISSING" || bad "  names SEALED_ARTIFACT_MISSING"

healthy; seal 2026-08-03
run "$NOW"; expect "seal STALE relative to the expected window -> FAIL" 2 PASS FAIL PASS FAIL
has "SEALED_GENERATION_STALE" && ok "  names SEALED_GENERATION_STALE" || bad "  names SEALED_GENERATION_STALE"
line "SEALED_STALE_CAUSE=PRODUCER_RAN_OK_SEAL_DID_NOT_ADVANCE" \
  && ok "  a successful run that did not advance the seal is named as a #606 contract break" \
  || bad "  a successful run that did not advance the seal is named as a #606 contract break"

# THE case the instruction singles out: a failed refresh correctly leaves the seal alone.
healthy; seal 2026-08-03; svc_fixture "$SVC_F" loaded exit-code 1 "$DONE"
run "$NOW" FAKE_IS_FAILED=failed
expect "failed refresh leaves the seal unchanged -> FAIL (readiness), producer also FAIL" 2 FAIL FAIL PASS FAIL
line "SEALED_STALE_CAUSE=PRODUCER_RAN_AND_FAILED" \
  && ok "  cause is PRODUCER_RAN_AND_FAILED" || bad "  cause is PRODUCER_RAN_AND_FAILED"
has "is CORRECT behaviour" && ok "  states that leaving the seal unchanged is CORRECT" \
  || bad "  states that leaving the seal unchanged is CORRECT"
has "NOT corrupt" && ok "  explicitly does NOT call the unchanged artifact corrupt" \
  || bad "  explicitly does NOT call the unchanged artifact corrupt"
if printf '%s\n' "$OUT" | grep -qi "corrupt" && ! printf '%s\n' "$OUT" | grep -q "NOT corrupt"; then
  bad "  no unqualified 'corrupt' label on an unchanged artifact"
else
  ok "  no unqualified 'corrupt' label on an unchanged artifact"
fi

healthy; seal 2026-08-03; timer_fixture "$TIMER_F" loaded disabled inactive dead "" "$(ep 2026-08-03T06:00:00)" "$ARMED"
run "$NOW"; expect "producer never ran and the seal did not advance -> FAIL" 2 FAIL FAIL PASS FAIL
line "SEALED_STALE_CAUSE=PRODUCER_DID_NOT_RUN" && ok "  cause is PRODUCER_DID_NOT_RUN" \
  || bad "  cause is PRODUCER_DID_NOT_RUN"

# malformed is a DIFFERENT condition from unchanged
healthy; printf '%s' '{"as_of": ' > "$SEALED"
run "$NOW"; expect "sealed artifact MALFORMED -> FAIL" 2 PASS FAIL PASS FAIL
has "SEALED_ARTIFACT_UNREADABLE" && ok "  malformed JSON is reported as UNREADABLE, not as 'did not advance'" \
  || bad "  malformed JSON is reported as UNREADABLE, not as 'did not advance'"
has "SEALED_GENERATION_STALE" && bad "  malformed must not also claim staleness" \
  || ok "  malformed must not also claim staleness"

healthy; printf '%s' '{"universe": ["AAPL"]}' > "$SEALED"
run "$NOW"; expect "sealed artifact without a governed as_of -> FAIL" 2 PASS FAIL PASS FAIL

# the seal is NOT required to move on every invocation — only after the expected window
healthy; seal 2026-08-04
run "$(( WIN + 600 ))"   # 06:10, inside the grace period: the expected window is MONDAY
expect "inside the grace period the prior window governs -> PASS (seal need not move yet)" 0 PASS PASS PASS PASS

# repeated failure: armed timer, failing service, seal behind even the PRIOR window
healthy; seal 2026-07-31; svc_fixture "$SVC_F" loaded exit-code 1 "$DONE"
run "$NOW" FAKE_IS_FAILED=failed
has "SERVICE_REPEATEDLY_FAILING" && ok "timer active but the service is repeatedly failing -> named" \
  || bad "timer active but the service is repeatedly failing -> named"

# ═════════════════════════════════════════════════════════════════════════════════════
# DATA FRESHNESS — independent of the two above.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- data freshness --"

STALE_STORE="$WORK/store-pernname.txt"
cat > "$STALE_STORE" <<'EOF'
STATUS sep_max=2026-08-03 lastpricedate=2026-08-03 et_today=2026-08-04 tolerance=4d max_lag=4d min_coverage=0.98
METRIC universe=512 covered=300 coverage=0.5859 missing=12 stale=200 lastpricedate_stale=0 frontier=2026-08-03 cutoff=2026-07-30
PROBLEM DATA_PER_NAME_COVERAGE: per-name coverage 0.5859 < 0.98 (12 missing, 200 stale beyond 4d of the 2026-08-03 frontier); e.g. AAL,AAP,ABBV
EOF
healthy; run "$NOW" FAKE_STORE_REPORT="$STALE_STORE"
expect "seal advanced but per-name freshness fails -> FAIL on DATA only" 2 PASS PASS FAIL FAIL
has "DATA_PER_NAME_COVERAGE" && ok "  stale-name attribution is carried through" \
  || bad "  stale-name attribution is carried through"

FRONTIER_STORE="$WORK/store-frontier.txt"
cat > "$FRONTIER_STORE" <<'EOF'
STATUS sep_max=2026-07-20 lastpricedate=2026-07-10 et_today=2026-08-04 tolerance=4d max_lag=4d min_coverage=0.98
PROBLEM DATA_SEP_FRONTIER_STALE: sep max 2026-07-20 is 15d old (>4d) - factor books are ranking on old data
PROBLEM DATA_LOCKSTEP_BROKEN: tickers.lastpricedate 2026-07-10 BEHIND sep 2026-07-20
EOF
healthy; run "$NOW" FAKE_STORE_REPORT="$FRONTIER_STORE"
expect "SEP frontier stale + lockstep broken -> FAIL on DATA only" 2 PASS PASS FAIL FAIL

healthy; run "$NOW" FAKE_STORE_FAIL=1
expect "store unreadable -> FAIL (never assumed fresh)" 2 PASS PASS FAIL FAIL
has "DATA_STORE_UNREADABLE" && ok "  names DATA_STORE_UNREADABLE" || bad "  names DATA_STORE_UNREADABLE"

# ═════════════════════════════════════════════════════════════════════════════════════
# CALENDAR: weekends, holidays, timezone, daylight saving.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- calendar --"

# Saturday 07:00: the expected window is FRIDAY's, and the next trigger is MONDAY. A
# clean Friday state must not be reported as a missed weekend refresh.
SAT=$(ep 2026-08-08T07:00:00)
FRI_WIN=$(ep 2026-08-07T06:00:00)
MON_NEXT=$(ep 2026-08-10T06:00:00)
timer_fixture "$TIMER_F" loaded enabled active waiting "$MON_NEXT" "$(( FRI_WIN + 60 ))" "$ARMED"
svc_fixture   "$SVC_F"   loaded success 0 "$(( FRI_WIN + 300 ))"
seal 2026-08-07
run "$SAT"; expect "SATURDAY with Friday's refresh sealed -> PASS (no weekend false positive)" 0 PASS PASS PASS PASS
has "expected_refresh_window=2026-08-07 06:00" && ok "  expected window is Friday's, not Saturday's" \
  || bad "  expected window is Friday's, not Saturday's"

SUN=$(ep 2026-08-09T07:00:00)
run "$SUN"; expect "SUNDAY with Friday's refresh sealed -> PASS" 0 PASS PASS PASS PASS

# Monday morning must require MONDAY's refresh, not accept Friday's. The timer is
# otherwise healthy and pointing at Tuesday, so the only producer faults available are the
# genuine ones: the Monday window was neither triggered nor served.
MON=$(ep 2026-08-10T07:00:00)
TUE_NEXT=$(ep 2026-08-11T06:00:00)
timer_fixture "$TIMER_F" loaded enabled active waiting "$TUE_NEXT" "$(( FRI_WIN + 60 ))" "$ARMED"
run "$MON"; expect "MONDAY still holding Friday's seal -> FAIL" 2 FAIL FAIL PASS FAIL
has "PRODUCER_OVERDUE" && ok "  the missed Monday window is named as overdue" \
  || bad "  the missed Monday window is named as overdue"

# Holiday suppression. The pinned OnCalendar has no holiday calendar, so this is OFF by
# default; it is honoured only when a suppressed date is declared explicitly — and then
# the same fixture, unchanged, must come back clean.
run "$MON" REFRESH_SKIP_DATES=2026-08-10
expect "Monday declared a suppressed refresh date -> PASS (Friday's seal governs)" 0 PASS PASS PASS PASS
has "expected_refresh_window=2026-08-07 06:00" && ok "  a suppressed date falls back to the prior window" \
  || bad "  a suppressed date falls back to the prior window"

# Daylight saving. US DST begins Sun 2026-03-08 and ends Sun 2026-11-01, so the wall-clock
# window is 06:00 EST on one side and 06:00 EDT on the other — a fixed UTC offset would
# get one of them wrong.
EST_NOW=$(ep 2026-03-06T07:00:00)      # Friday, EST
EST_WIN=$(ep 2026-03-06T06:00:00)
EDT_NEXT=$(ep 2026-03-09T06:00:00)     # Monday, already EDT
timer_fixture "$TIMER_F" loaded enabled active waiting "$EDT_NEXT" "$(( EST_WIN + 60 ))" "$ARMED"
svc_fixture   "$SVC_F"   loaded success 0 "$(( EST_WIN + 300 ))"
seal 2026-03-06
run "$EST_NOW"; expect "EST side of the spring transition -> PASS" 0 PASS PASS PASS PASS
has "expected_refresh_window=2026-03-06 06:00 EST" && ok "  expected window resolves in EST" \
  || bad "  expected window resolves in EST"
has "next_trigger_local_hhmm=06:00" && ok "  a next trigger across the transition still reads 06:00 local" \
  || bad "  a next trigger across the transition still reads 06:00 local"

EDT_NOW=$(ep 2026-03-09T07:00:00)      # Monday after the spring-forward
EDT_WIN=$(ep 2026-03-09T06:00:00)
timer_fixture "$TIMER_F" loaded enabled active waiting "$(ep 2026-03-10T06:00:00)" "$(( EDT_WIN + 60 ))" "$ARMED"
svc_fixture   "$SVC_F"   loaded success 0 "$(( EDT_WIN + 300 ))"
seal 2026-03-09
run "$EDT_NOW"; expect "EDT side of the spring transition -> PASS" 0 PASS PASS PASS PASS
has "expected_refresh_window=2026-03-09 06:00 EDT" && ok "  expected window resolves in EDT" \
  || bad "  expected window resolves in EDT"

# The spring-forward loses an hour, so Friday 07:00 EST -> Monday 06:00 EDT is 70h, not
# 71h. Both are inside the plausibility ceiling; what matters is that the check reads the
# local wall clock rather than a fixed offset, so it does not fire spuriously.
timer_fixture "$TIMER_F" loaded enabled active waiting "$EDT_NEXT" "$(( EST_WIN + 60 ))" "$ARMED"
svc_fixture   "$SVC_F"   loaded success 0 "$(( EST_WIN + 300 ))"
seal 2026-03-06
run "$EST_NOW"
has "TIMER_NEXT_TRIGGER_OFF_SCHEDULE" && bad "  DST transition must not read as an off-schedule trigger" \
  || ok "  DST transition must not read as an off-schedule trigger"

FALL_NOW=$(ep 2026-11-02T07:00:00)     # Monday after the fall-back, EST
FALL_WIN=$(ep 2026-11-02T06:00:00)
timer_fixture "$TIMER_F" loaded enabled active waiting "$(ep 2026-11-03T06:00:00)" "$(( FALL_WIN + 60 ))" "$ARMED"
svc_fixture   "$SVC_F"   loaded success 0 "$(( FALL_WIN + 300 ))"
seal 2026-11-02
run "$FALL_NOW"; expect "autumn transition (EDT -> EST) -> PASS" 0 PASS PASS PASS PASS
has "expected_refresh_window=2026-11-02 06:00 EST" && ok "  expected window resolves in EST after fall-back" \
  || bad "  expected window resolves in EST after fall-back"

# ═════════════════════════════════════════════════════════════════════════════════════
# DISPATCH INTERLOCK — the failure signal must survive to the unit result.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- dispatch interlock --"

healthy; timer_fixture "$TIMER_F" loaded disabled inactive dead "" "$TRIG" "$ARMED"
run "$NOW"
[ "$RC" = 2 ] && ok "a readiness failure exits 2" || bad "a readiness failure exits 2" "rc=$RC"
[ "$RC" != 1 ] && ok "a readiness failure never exits 1 (the unit's SuccessExitStatus absorbs 1)" \
  || bad "a readiness failure never exits 1"
grep -q "publish" "$SNS_LOG" && ok "a readiness failure publishes an SNS alert" \
  || bad "a readiness failure publishes an SNS alert"

run "$NOW" FAKE_SNS_FAIL=1
[ "$RC" = 2 ] && ok "a failed SNS publish does NOT downgrade the verdict" \
  || bad "a failed SNS publish does NOT downgrade the verdict" "rc=$RC"
has "SNS publish FAILED" && ok "  a failed publish is reported" || bad "  a failed publish is reported"

if [ -f "$UNIT" ]; then
  SES="$(sed -n 's/^SuccessExitStatus=//p' "$UNIT")"
  case " $SES " in
    *" 2 "*) bad "the unit's SuccessExitStatus must not absorb exit 2 (found: '$SES')";;
    *)       ok "the shipped unit's SuccessExitStatus ('${SES:-none}') does not absorb exit 2";;
  esac
else
  bad "unit file missing at $UNIT"
fi

# ═════════════════════════════════════════════════════════════════════════════════════
# READINESS ARTIFACT PUBLICATION — the step that turns detection into a veto.
#
# The in-app gate reads this file AT DISPATCH and refuses to enter a factor book when it
# is absent, unreadable, stale or not PASS. So the watchdog's obligation is no longer
# "alert someone": it is "leave a correct, readable verdict on disk, every run". The
# schema itself is bound to its reader by
# apps/backend/tests/deploy/test_factor_readiness_artifact_contract.py; what is tested
# here is that the SCRIPT publishes at all, publishes in both directions, and reports it
# when it cannot.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- readiness artifact publication --"

READY_ART="$DATA/_factor_readiness.json"
# read <jq-ish field> from the artifact
art() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get(sys.argv[2]))" "$READY_ART" "$1" 2>/dev/null; }

healthy; rm -f "$READY_ART"; run "$NOW"
expect "a healthy run still exits 0 with publication enabled" 0 PASS PASS PASS PASS
[ -f "$READY_ART" ] && ok "  a healthy run PUBLISHES the verdict" || bad "  a healthy run PUBLISHES the verdict"
line "READINESS_ARTIFACT=PUBLISHED" && ok "  reports READINESS_ARTIFACT=PUBLISHED" || bad "  reports READINESS_ARTIFACT=PUBLISHED"
[ "$(art overall_readiness)" = "PASS" ] && ok "  the published verdict is PASS" \
  || bad "  the published verdict is PASS" "got: $(art overall_readiness)"
"$PY" -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" "$READY_ART" 2>/dev/null \
  && ok "  the published document is valid JSON" || bad "  the published document is valid JSON"
[ "$(art problem_count)" = "0" ] && ok "  a passing verdict carries no problems" \
  || bad "  a passing verdict carries no problems"

# The timestamp the consumer ages out against must come from THIS run, not from the file's
# mtime and not from a previous verdict.
WANT_TS="$("$PY" -c "
import datetime,sys
print(datetime.datetime.fromtimestamp(int(sys.argv[1]),datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$NOW")"
[ "$(art evaluated_at_utc)" = "$WANT_TS" ] && ok "  evaluated_at_utc is this run's evaluation instant" \
  || bad "  evaluated_at_utc is this run's evaluation instant" "got $(art evaluated_at_utc) want $WANT_TS"

# ⚠ The case that is easiest to get wrong: a FAIL verdict must be WRITTEN. Skipping the
# write "because we already failed" leaves the previous PASS on disk for up to 26h — the
# watchdog would then be actively vouching for a box it just declared not ready.
healthy; timer_fixture "$TIMER_F" loaded disabled inactive dead "" "$TRIG" "$ARMED"
run "$NOW"; expect "a producer-liveness failure -> FAIL, and still publishes" 2 FAIL PASS PASS FAIL
line "READINESS_ARTIFACT=PUBLISHED" && ok "  a FAILING run publishes too" || bad "  a FAILING run publishes too"
[ "$(art overall_readiness)" = "FAIL" ] && ok "  the published verdict is FAIL (it is what BLOCKS dispatch)" \
  || bad "  the published verdict is FAIL" "got: $(art overall_readiness)"
[ "$(art problem_count)" -gt 0 ] 2>/dev/null && ok "  the published document carries the problems" \
  || bad "  the published document carries the problems"
"$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if any('TIMER_DISABLED' in p['detail'] for p in d['problems']) else 1)" "$READY_ART" \
  && ok "  the operator can read WHY from the artifact alone" || bad "  the operator can read WHY from the artifact alone"

# A previous PASS must not survive a later FAIL.
healthy; run "$NOW"                                   # publishes PASS
timer_fixture "$TIMER_F" loaded disabled inactive dead "" "$TRIG" "$ARMED"
run "$NOW"                                            # publishes FAIL over it
[ "$(art overall_readiness)" = "FAIL" ] && ok "  a later FAIL replaces an earlier PASS" \
  || bad "  a later FAIL replaces an earlier PASS"

# Atomic write: nothing partial, nothing left behind.
healthy; run "$NOW"
RESIDUE="$(find "$DATA" -name '_factor_readiness.json.*' 2>/dev/null | wc -l)"
[ "$RESIDUE" = "0" ] && ok "  no temp residue beside the artifact" \
  || bad "  no temp residue beside the artifact" "$RESIDUE leftover file(s)"

# Publication failure on an otherwise-ready box. Data fine, veto unarmed: exit 2 and alert,
# because the books will halt once the previous verdict ages past 26h.
healthy; run "$NOW" READINESS_ARTIFACT_PATH="$WORK/no-such-dir/_factor_readiness.json"
[ "$RC" = 2 ] && ok "an unpublishable verdict exits 2 even when readiness PASSes" \
  || bad "an unpublishable verdict exits 2 even when readiness PASSes" "rc=$RC"
line "READINESS_ARTIFACT=FAILED" && ok "  reports READINESS_ARTIFACT=FAILED" || bad "  reports READINESS_ARTIFACT=FAILED"
line "OVERALL_READINESS=PASS" && ok "  does NOT misreport the factor data as stale" \
  || bad "  does NOT misreport the factor data as stale"
has "READINESS_ARTIFACT_NOT_PUBLISHED" && ok "  names READINESS_ARTIFACT_NOT_PUBLISHED" \
  || bad "  names READINESS_ARTIFACT_NOT_PUBLISHED"
grep -q "publish" "$SNS_LOG" && ok "  alerts on an unarmed veto" || bad "  alerts on an unarmed veto"
grep -q "NOT PUBLISHED" "$SNS_LOG" && ok "  the alert subject distinguishes it from stale data" \
  || bad "  the alert subject distinguishes it from stale data"
[ ! -e "$WORK/no-such-dir" ] && ok "  a missing data directory is NOT created (an unmounted volume must not look mounted)" \
  || bad "  a missing data directory is NOT created"

# ═════════════════════════════════════════════════════════════════════════════════════
# SCOPE GUARDS — this PR must not create a deployment dependency.
# ═════════════════════════════════════════════════════════════════════════════════════
echo "-- scope guards --"
grep -q "factor_refresh.py" "$SCRIPT" && ! grep -qE '^\s*#.*factor_refresh\.py' "$SCRIPT" \
  && bad "the watchdog must not invoke apps/backend/scripts/factor_refresh.py" \
  || ok "the watchdog does not invoke factor_refresh.py (mentioned in comments only)"
grep -qE '(docker compose|docker-compose)' "$SCRIPT" \
  && bad "the watchdog must not run docker compose (no deploy/restart side effects)" \
  || ok "the watchdog runs no compose command (no deploy/restart side effects)"
# Enumerate the systemctl subcommands the watchdog actually invokes and require every one
# of them to be read-only. Stronger than grepping for forbidden words, and it cannot be
# tripped by prose: a future `systemctl restart` shows up here as an unexpected subcommand.
SUBCMDS="$(grep -oE '"\$SYSTEMCTL" [a-z-]+' "$SCRIPT" | awk '{print $2}' | sort -u)"
UNEXPECTED="$(printf '%s\n' "$SUBCMDS" | grep -vE '^(show|is-failed|show-timezone)$')"
if [ -z "$UNEXPECTED" ]; then
  ok "every systemctl subcommand is read-only ($(printf '%s' "$SUBCMDS" | tr '\n' ' '))"
else
  bad "the watchdog must not mutate systemd units" "unexpected: $(printf '%s' "$UNEXPECTED" | tr '\n' ' ')"
fi
# Nor may it reach the broker, the app database, or any HTTP endpoint.
grep -qEi '\b(alpaca|sqlite3|curl|wget)\b' "$SCRIPT" \
  && bad "the watchdog must not touch the broker, the app database, or the network" \
  || ok "the watchdog touches no broker, app database, or HTTP endpoint"
grep -q "_factor_refresh_universe_sealed.json" "$SCRIPT" \
  && ok "the sealed artifact name is exactly _factor_refresh_universe_sealed.json" \
  || bad "the sealed artifact name is exactly _factor_refresh_universe_sealed.json"

echo
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
