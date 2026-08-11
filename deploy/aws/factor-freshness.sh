#!/usr/bin/env bash
# Factor-data READINESS watchdog -> SNS (the scheduled control over factor-refresh).
# Runs on the EC2 paper box via a systemd timer, weekdays 07:00 ET — after the 06:00 ET
# factor-refresh and BEFORE the open (factor books rank on this store; Monday rebalances
# fire ~10:30 ET, hours before the 16:35 daily report would surface a problem).
#
# ─────────────────────────────────────────────────────────────────────────────────────
# WHY THIS WAS HARDENED (2026-08-03/04)
#
# The previous watchdog measured the STORE and inferred the PRODUCER from it. That is an
# incomplete condition, and the incomplete part is the one that failed:
#
#   2026-08-03 07:00 ET  watchdog clean; producer still operational
#   2026-08-03 09:46 ET  workbench-factor-refresh.timer deliberately stopped + disabled
#   2026-08-04 07:00 ET  watchdog alerted only once the DATA had begun to drift
#
# Nothing executed incorrectly. A recently refreshed store simply cannot distinguish a
# live producer from a dead one, so a disabled timer stays invisible for as many days as
# the freshness tolerance allows. The governing contract is therefore three-part:
#
#   factor data readiness = producer liveness PASS
#                       AND sealed refresh progression PASS
#                       AND data freshness PASS
#
# Any ONE failing makes readiness fail. The three are measured INDEPENDENTLY and reported
# separately: a fresh store may never vouch for a dead producer, and a live producer may
# never vouch for a fresh store.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# SEALED-ARTIFACT CONTRACT (established by #606)
#
#   _factor_refresh_universe_sealed.json advances ONLY after staging verification passes
#   AND the store swap completes.
#
# So a failed refresh that leaves the sealed artifact unchanged is CORRECT producer
# behaviour, not corruption — the seal is deliberately not advanced by a run nobody
# accepted. It is still a READINESS failure, because the expected successful generation
# did not occur. This watchdog therefore never labels an unchanged artifact "corrupt";
# it reports WHICH of these happened:
#
#   PRODUCER_DID_NOT_RUN                  no trigger since the expected window
#   PRODUCER_RAN_AND_FAILED               triggered, service result != success
#   PRODUCER_RAN_OK_SEAL_DID_NOT_ADVANCE  service succeeded but the seal did not move
#                                         (a genuine break of the #606 contract)
#   (seal advanced, freshness failed)     SEALED_GENERATION=PASS, DATA_FRESHNESS=FAIL
#
# "Unreadable/malformed JSON" is a separate, explicitly distinct condition. It is never
# used for the merely-unchanged case.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# ADVANCEMENT RULE
#
# The seal is NOT required to change on every watchdog invocation. It is required to
# correspond to the most recent EXPECTED SUCCESSFUL refresh window — Mon-Fri 06:00 in the
# schedule timezone, plus a grace period for an authorized retry. Weekends, suppressed
# dates, host timezone and daylight-saving transitions are computed from the pinned
# schedule (below), never from file age: the artifact carries a governed `as_of`, so age
# on disk is not consulted for the advancement decision (it is still RECORDED).
#
# ─────────────────────────────────────────────────────────────────────────────────────
# EXIT CODES / INTERLOCK
#
#   0  OVERALL_READINESS=PASS *and* the readiness artifact was published
#   2  OVERALL_READINESS=FAIL — producer liveness, sealed generation, or data freshness
#   2  the readiness artifact could not be published (the veto is then unarmed)
#
# 2, deliberately, and never 1: workbench-factor-freshness.service declares
# `SuccessExitStatus=0 1`, so an exit of 1 is recorded by systemd as a SUCCESS and would
# be absorbed. A readiness failure must survive to the unit result. Every failure path
# below is fail-CLOSED: anything this watchdog cannot determine is a FAIL, because an
# unknown readiness state must not be allowed to look like a ready one.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# THE PUBLISHED ARTIFACT IS THE INTERLOCK (added 2026-08-08; #615 + #621)
#
# Until this section existed, everything above was DETECTION: a unit result and an SNS
# alert. `readiness FAIL -> non-zero + alert -> [MISSING] -> dispatch proceeds`. The box
# could observe a dead producer and still rebalance a factor book.
#
# The missing step is a durable verdict the application can read AT dispatch. Section 5
# writes `_factor_readiness.json` into the shared data volume; the in-app gate
# (`app/strategies/factor_readiness.py`, at all three dispatch sites) requires it and
# blocks the strategy from being entered when it is absent, unreadable, stale (>26h) or
# does not read exactly `"PASS"`.
#
# ⚠ THAT MAKES THIS SCRIPT LOAD-BEARING FOR TRADING, NOT MERELY FOR ALERTING. Three
# consequences, all deliberate:
#
#   * Publication happens on EVERY run, PASS or FAIL. A FAIL verdict must be WRITTEN —
#     an absent artifact and a FAIL artifact both block, but only the written one tells
#     the operator why. Never "skip the write because we already failed".
#   * The write is atomic (temp + rename in the same directory). A reader that catches a
#     half-written document sees `unreadable`, which under the consumer's contract is a
#     halt — so open-truncate-write here would self-inflict an outage on every publish.
#   * The two field names the consumer reads — `evaluated_at_utc` and `overall_readiness`
#     (uppercase, exact) — are a CONTRACT. Renaming either halts the factor books rather
#     than warning. `tests/deploy/test_factor_readiness_artifact_contract.py` binds this
#     writer to that reader so the drift cannot ship.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# HOST-SIDE BY DESIGN. Producer liveness is a systemd fact and is read on the host. The
# only container work is reading the live DuckDB store, via an inline query — this script
# does NOT depend on apps/backend/scripts/factor_refresh.py, which is baked into the image
# rather than bind-mounted and is not present in the deployed image.
#
# No secrets: aws uses the instance role. Deliberately alert-only on failure (no daily
# "clean" email): the CEE and daily reports already prove the SNS path daily.
set -uo pipefail

# ── pinned identity ──────────────────────────────────────────────────────────────────
TIMER_UNIT="${REFRESH_TIMER_UNIT:-workbench-factor-refresh.timer}"
SERVICE_UNIT="${REFRESH_SERVICE_UNIT:-workbench-factor-refresh.service}"
SEALED_BASENAME="_factor_refresh_universe_sealed.json"   # exact, per #606

# ── the pinned refresh schedule ──────────────────────────────────────────────────────
# Mirrors deploy/aws/systemd/workbench-factor-refresh.timer: `OnCalendar=Mon-Fri 06:00`.
# That OnCalendar carries NO timezone, so systemd evaluates it in the HOST's local time —
# which is why the host timezone is itself checked below. If the unit's schedule changes,
# these must change with it.
REFRESH_TZ="${REFRESH_SCHEDULE_TZ:-America/New_York}"
REFRESH_HOUR="${REFRESH_SCHEDULE_HOUR:-6}"
REFRESH_MINUTE="${REFRESH_SCHEDULE_MINUTE:-0}"
REFRESH_WEEKDAYS="${REFRESH_SCHEDULE_WEEKDAYS:-0,1,2,3,4}"   # 0=Mon … 6=Sun
# How long after the window a refresh is still authorized to be running or retrying. The
# watchdog fires at 07:00, 60 min after the window; 45 min leaves the job time to finish
# (it stops/starts the backend) without tolerating a silently missed window.
REFRESH_GRACE_MINUTES="${REFRESH_GRACE_MINUTES:-45}"
# Holiday suppression. EMPTY BY DEFAULT AND DELIBERATELY SO: the pinned OnCalendar is
# plain `Mon-Fri` with no holiday calendar, so the producer is expected to run on market
# holidays too. Set this (comma-separated ISO dates) if and only if the timer's schedule
# gains suppression — otherwise the watchdog would excuse a window the producer really
# was expected to serve.
REFRESH_SKIP_DATES="${REFRESH_SKIP_DATES:-}"
# A next trigger further out than this is not plausible for a weekday schedule (the
# longest legitimate gap is Fri -> Mon).
MAX_NEXT_TRIGGER_HOURS="${MAX_NEXT_TRIGGER_HOURS:-96}"

# ── freshness thresholds (unchanged semantics) ───────────────────────────────────────
TOLERANCE="${FRESH_TOLERANCE_DAYS:-4}"        # sep frontier vs ET today
MAX_LAG_DAYS="${FRESH_MAX_LAG_DAYS:-4}"       # per-name lag vs the store's own frontier
MIN_COVERAGE="${FRESH_MIN_COVERAGE:-0.98}"    # fraction of the universe that must be current
STALE_NAME_SAMPLE="${STALE_NAME_SAMPLE:-12}"  # how many stale names to attribute in the alert

# ── environment seams (production defaults; the test harness overrides these) ────────
REGION="${AWS_REGION:-us-east-1}"
TOPIC="${SNS_TOPIC_ARN:-arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms}"
SYSTEMCTL="${SYSTEMCTL_BIN:-systemctl}"
PYTHON="${PYTHON_BIN:-python3}"
AWS_BIN="${AWS_BIN:-aws}"
DATADIR="${WORKBENCH_DATA_DIR:-/opt/workbench/data}"           # host side
CONTAINER_DATADIR="${WORKBENCH_CONTAINER_DATA_DIR:-/app/data}"  # same volume, in-container
BACKEND_CONTAINER="${BACKEND_CONTAINER:-workbench-backend}"
STORE_PATH="${FACTOR_STORE_PATH:-$CONTAINER_DATADIR/factor_data.duckdb}"
CONTAINER_APP_DB="${WORKBENCH_CONTAINER_APP_DB:-$CONTAINER_DATADIR/workbench.sqlite}"
SUBJECT_PREFIX="${FRESHNESS_SUBJECT_PREFIX:-}"   # e.g. "[TEST] " for manual alert-path tests
NOW_EPOCH="${WATCHDOG_NOW_EPOCH:-$(date +%s)}"   # clock seam: DST / weekend tests pin this
# Pinning the clock also pins the timestamp stamped into the published artifact, which is
# what the consumer ages out against. Recorded in the artifact so an operator can see that
# a verdict came from a pinned-clock run rather than from the wall clock.
CLOCK_SOURCE="wall"; [ -n "${WATCHDOG_NOW_EPOCH:-}" ] && CLOCK_SOURCE="pinned"
DOCKER="${WATCHDOG_DOCKER:-}"
if [ -z "$DOCKER" ]; then
  DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
fi

SEALED_PATH="$DATADIR/$SEALED_BASENAME"
CONTAINER_SEALED="$CONTAINER_DATADIR/$SEALED_BASENAME"

# The dispatch-time verdict the application reads. Host-side path; the container sees the
# same volume at $CONTAINER_DATADIR, which is how the in-app gate at
# `resolve_store_path().parent / "_factor_readiness.json"` reaches it. The BASENAME IS
# PART OF THE CONTRACT — the consumer derives the path itself and does not take it from
# configuration, so a rename here silently unarms the veto (absent -> blocked) rather
# than pointing the reader somewhere new.
READINESS_BASENAME="_factor_readiness.json"
READINESS_PATH="${READINESS_ARTIFACT_PATH:-$DATADIR/$READINESS_BASENAME}"

# The refresh pipeline's own adjudication of symbols that are legitimately unavailable —
# a delisted security (PROVIDER_EXHAUSTED) or one the provider never covered
# (PROVIDER_NOT_COVERED). Written under ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001 and
# already fail-closed for the refresh itself; consulted here so this watchdog is not
# STRICTER than the adjudication the rest of the system performs.
EXHAUSTION_BASENAME="_factor_exhaustion_evidence.json"
CONTAINER_EXHAUSTION="$CONTAINER_DATADIR/$EXHAUSTION_BASENAME"

# The SHARED adjudication implementation. Until 2026-08-11 this watchdog carried its own
# reading of the evidence artifact above and reached a DIFFERENT verdict from the refresh
# verifier's: it published coverage 1.0000 / PASS from the same file, store and universe
# that aborted the refresh at 0.9784. One implementation, consumed by both, is the only
# structural fix.
#
# ⚠ It is resolved from THIS SCRIPT'S OWN checked-out tree and piped into the container as
# source — never imported from the running image. The image is built and deployed on its
# own cadence and routinely predates the host tree; an import would make this watchdog
# fail, or silently adjudicate differently, exactly when the two drift. A readiness
# watchdog must never become the reason to deploy, and must never be the last component
# to learn the rules changed. There is deliberately NO import fallback.
WATCHDOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADJUDICATION_PATH="${FACTOR_ADJUDICATION_PATH:-$WATCHDOG_DIR/../../apps/backend/scripts/factor_adjudication.py}"

# Read ONCE, then hash and pipe THE SAME BYTES. Hashing the path and separately re-reading
# it to pipe would leave a window in which the artifact names an implementation that is not
# the one that ran — which is the whole property the recorded hash exists to establish.
ADJUDICATION_SRC=""
ADJUDICATION_SHA256=""
ADJUDICATION_AVAILABLE=0
if [ -r "$ADJUDICATION_PATH" ]; then
  ADJUDICATION_SRC="$(cat "$ADJUDICATION_PATH" 2>/dev/null)" || ADJUDICATION_SRC=""
fi
if [ -n "$ADJUDICATION_SRC" ]; then
  # `<<<` appends exactly one newline, and the pipe below feeds the container through
  # the same construct from the same variable - so the bytes hashed ARE the bytes
  # executed, and the recorded hash cannot name an implementation that did not run.
  ADJUDICATION_SHA256="$(sha256sum <<< "$ADJUDICATION_SRC" | cut -d' ' -f1)"
  ADJUDICATION_AVAILABLE=1
fi

EXIT_READY=0
EXIT_NOT_READY=2

# Three independent problem ledgers. They are never merged before the verdict: the whole
# point of the hardening is that these conditions cannot substitute for one another.
P_PRODUCER=(); P_SEALED=(); P_DATA=()

# FAIL CLOSED on a missing adjudication implementation. No implementation means no
# adjudication, and an unadjudicated store cannot be declared ready. Never degrade to
# "assume fresh", and never fall back to an image-resident copy whose provenance we
# cannot state. Appended here rather than at resolution time because the ledgers above
# are initialised after the configuration block and would otherwise erase it.
if [ "$ADJUDICATION_AVAILABLE" -ne 1 ]; then
  P_DATA+=("DATA_ADJUDICATION_HELPER_UNAVAILABLE: the shared adjudication implementation at '$ADJUDICATION_PATH' is missing or unreadable, so per-name freshness could NOT be adjudicated - freshness is UNKNOWN, which is treated as a failure rather than assumed fresh. Restore it from the checkout; do NOT substitute an image-resident copy.")
fi
# A FOURTH ledger, deliberately outside the readiness conjunction. Failing to publish the
# artifact is not a statement about the factor data — it is a statement about the
# interlock itself, and conflating the two would let "the veto is unarmed" be reported as
# "the data is stale". It still exits 2 and still alerts.
P_PUBLISH=()
FACTS=()
SEALED_STALE_CAUSE="N/A"

fact(){ FACTS+=("$1"); }

# ── helpers ──────────────────────────────────────────────────────────────────────────

# prop <systemctl-show-output> <PropertyName> -> first value, "" if absent
prop() { printf '%s\n' "${1:-}" | sed -n "s/^$2=//p" | head -n1; }

# to_epoch <systemd timestamp | usec-since-epoch> -> seconds, "" when absent/unset.
# systemd renders *USec properties either as microseconds or as a formatted timestamp
# depending on version and property; accept both rather than pin one.
# In raw mode systemd spells "never" as UINT64_MAX rather than 0, and that value overflows
# 64-bit shell arithmetic into a negative epoch — which would read as a trigger in the
# distant past instead of as no trigger at all. Anything outside a sane range is absent.
to_epoch() {
  local v="${1:-}" e
  case "$v" in ""|0|"n/a"|"infinity"|"-") echo ""; return 0;; esac
  if printf '%s' "$v" | grep -qE '^[0-9]+$'; then
    if [ "${#v}" -gt 18 ]; then echo ""; return 0; fi   # >= ~year 33658 in usec: never
    e=$(( v / 1000000 ))
  else
    e="$(date -d "$v" +%s 2>/dev/null)" || { echo ""; return 0; }
  fi
  [ -n "$e" ] || { echo ""; return 0; }
  # 0 .. 2100-01-01. Outside that, systemd is not reporting a real instant.
  if [ "$e" -le 0 ] || [ "$e" -gt 4102444800 ]; then echo ""; return 0; fi
  echo "$e"
}

human() {  # epoch -> readable, in the schedule timezone
  local e="${1:-}"
  [ -n "$e" ] || { echo "none"; return 0; }
  TZ="$REFRESH_TZ" date -d "@$e" '+%Y-%m-%d %H:%M %Z' 2>/dev/null || echo "epoch:$e"
}

# local_hhmm <epoch> -> HH:MM in the schedule timezone (DST-correct: evaluated in the
# zone, never derived from a fixed offset).
local_hhmm() {
  REFRESH_TZ="$REFRESH_TZ" CLASSIFY_EPOCH="$1" "$PYTHON" - <<'PY' 2>/dev/null
import os
from datetime import datetime
from zoneinfo import ZoneInfo
t = datetime.fromtimestamp(int(os.environ["CLASSIFY_EPOCH"]), ZoneInfo(os.environ["REFRESH_TZ"]))
print(f"{t:%H:%M}")
PY
}

# ═════════════════════════════════════════════════════════════════════════════════════
# 0) THE EXPECTED REFRESH WINDOW
#
# Calendar reasoning is done in python because DST is not shell arithmetic: the offset
# between the schedule timezone and UTC changes underneath the schedule, so "06:00 local"
# is not a fixed number of seconds from anything. zoneinfo resolves it exactly.
# ═════════════════════════════════════════════════════════════════════════════════════
SCHEDULE="$(
  REFRESH_TZ="$REFRESH_TZ" REFRESH_HOUR="$REFRESH_HOUR" REFRESH_MINUTE="$REFRESH_MINUTE" \
  REFRESH_WEEKDAYS="$REFRESH_WEEKDAYS" REFRESH_GRACE_MINUTES="$REFRESH_GRACE_MINUTES" \
  REFRESH_SKIP_DATES="$REFRESH_SKIP_DATES" NOW_EPOCH="$NOW_EPOCH" \
  "$PYTHON" - <<'PY' 2>/dev/null
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

tz = ZoneInfo(os.environ["REFRESH_TZ"])
now = datetime.fromtimestamp(int(os.environ["NOW_EPOCH"]), tz)
hour, minute = int(os.environ["REFRESH_HOUR"]), int(os.environ["REFRESH_MINUTE"])
grace = timedelta(minutes=int(os.environ["REFRESH_GRACE_MINUTES"]))
days = {int(x) for x in os.environ["REFRESH_WEEKDAYS"].split(",") if x.strip()}
skip = {s.strip() for s in os.environ.get("REFRESH_SKIP_DATES", "").split(",") if s.strip()}


def window(d):
    # 06:00 exists on every US DST transition day (transitions are at 02:00), so this is
    # never ambiguous or non-existent for the pinned schedule. fold=0 pins the choice
    # anyway, so a schedule moved into a repeated hour still resolves deterministically.
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz, fold=0)


def is_refresh_day(d):
    return d.weekday() in days and d.isoformat() not in skip


def walk(start, step, want_future):
    d = start
    for _ in range(15):
        if is_refresh_day(d):
            w = window(d)
            if (w > now) if want_future else (w + grace <= now):
                return w
        d += timedelta(days=step)
    return None


expected = walk(now.date(), -1, False)
prior = walk(expected.date() - timedelta(days=1), -1, False) if expected else None
nxt = walk(now.date(), 1, True)

print(f"NOW_LOCAL={now:%Y-%m-%d %H:%M %Z}")
print(f"NOW_DATE={now.date().isoformat()}")
print(f"TODAY_IS_REFRESH_DAY={'yes' if is_refresh_day(now.date()) else 'no'}")
if expected:
    print(f"EXPECTED_DATE={expected.date().isoformat()}")
    print(f"EXPECTED_EPOCH={int(expected.timestamp())}")
    print(f"EXPECTED_LOCAL={expected:%Y-%m-%d %H:%M %Z}")
if prior:
    print(f"PRIOR_DATE={prior.date().isoformat()}")
if nxt:
    print(f"NEXT_WINDOW_LOCAL={nxt:%Y-%m-%d %H:%M %Z}")
PY
)"

EXPECTED_DATE="$(prop "$SCHEDULE" EXPECTED_DATE)"
EXPECTED_EPOCH="$(prop "$SCHEDULE" EXPECTED_EPOCH)"
EXPECTED_LOCAL="$(prop "$SCHEDULE" EXPECTED_LOCAL)"
PRIOR_DATE="$(prop "$SCHEDULE" PRIOR_DATE)"
NOW_LOCAL="$(prop "$SCHEDULE" NOW_LOCAL)"
TODAY_IS_REFRESH_DAY="$(prop "$SCHEDULE" TODAY_IS_REFRESH_DAY)"
NEXT_WINDOW_LOCAL="$(prop "$SCHEDULE" NEXT_WINDOW_LOCAL)"
DATE_ET="$(prop "$SCHEDULE" NOW_DATE)"
[ -n "$DATE_ET" ] || DATE_ET="$(TZ="$REFRESH_TZ" date '+%Y-%m-%d')"

if [ -z "$EXPECTED_DATE" ] || [ -z "$EXPECTED_EPOCH" ]; then
  # Fail closed: with no expected window the seal cannot be assessed at all, and an
  # unassessable readiness state must never present as a ready one.
  P_SEALED+=("SCHEDULE_UNRESOLVED: could not compute the expected refresh window from the pinned schedule (weekdays[$REFRESH_WEEKDAYS] @ ${REFRESH_HOUR}:$(printf '%02d' "$REFRESH_MINUTE") $REFRESH_TZ) - is python3/tzdata present on the host?")
  P_PRODUCER+=("SCHEDULE_UNRESOLVED: producer liveness cannot be judged without an expected window")
fi

fact "watchdog_now=${NOW_LOCAL:-unknown} (today_is_refresh_day=${TODAY_IS_REFRESH_DAY:-unknown})"
fact "pinned_schedule=weekdays[$REFRESH_WEEKDAYS] ${REFRESH_HOUR}:$(printf '%02d' "$REFRESH_MINUTE") $REFRESH_TZ (+${REFRESH_GRACE_MINUTES}m grace, skip_dates=${REFRESH_SKIP_DATES:-none})"
fact "expected_refresh_window=${EXPECTED_LOCAL:-UNRESOLVED} (prior window ${PRIOR_DATE:-unknown}; next ${NEXT_WINDOW_LOCAL:-unknown})"

# ═════════════════════════════════════════════════════════════════════════════════════
# 1) PRODUCER LIVENESS — is the thing that refreshes the store actually alive?
#
# Read from systemd directly. NEVER inferred from store dates: that inference is exactly
# what let a timer disabled at 09:46 on 08-03 stay invisible until the data drifted.
# ═════════════════════════════════════════════════════════════════════════════════════
TIMER_SHOW="$("$SYSTEMCTL" show "$TIMER_UNIT" 2>/dev/null)"
SVC_SHOW="$("$SYSTEMCTL" show "$SERVICE_UNIT" 2>/dev/null)"

T_LOAD="$(prop "$TIMER_SHOW" LoadState)"
T_FILE="$(prop "$TIMER_SHOW" UnitFileState)"
T_ACTIVE="$(prop "$TIMER_SHOW" ActiveState)"
T_SUB="$(prop "$TIMER_SHOW" SubState)"
T_NEXT_EPOCH="$(to_epoch "$(prop "$TIMER_SHOW" NextElapseUSecRealtime)")"
T_LAST_EPOCH="$(to_epoch "$(prop "$TIMER_SHOW" LastTriggerUSec)")"
T_ARMED_EPOCH="$(to_epoch "$(prop "$TIMER_SHOW" ActiveEnterTimestamp)")"

S_LOAD="$(prop "$SVC_SHOW" LoadState)"
S_RESULT="$(prop "$SVC_SHOW" Result)"
S_STATUS="$(prop "$SVC_SHOW" ExecMainStatus)"
S_EXIT_EPOCH="$(to_epoch "$(prop "$SVC_SHOW" ExecMainExitTimestamp)")"
S_IS_FAILED="$("$SYSTEMCTL" is-failed "$SERVICE_UNIT" 2>/dev/null)"

# One place decides "the last run was not a success", so every consumer below agrees.
service_unhealthy() {
  [ "$S_IS_FAILED" = "failed" ] && return 0
  [ -n "$S_RESULT" ] && [ "$S_RESULT" != "success" ] && return 0
  [ -n "$S_STATUS" ] && [ "$S_STATUS" != "0" ] && return 0
  return 1
}

fact "timer=$TIMER_UNIT load=${T_LOAD:-unknown} file=${T_FILE:-unknown} active=${T_ACTIVE:-unknown}/${T_SUB:-unknown}"
fact "timer_last_trigger=$(human "$T_LAST_EPOCH") timer_next_trigger=$(human "$T_NEXT_EPOCH")"
fact "service=$SERVICE_UNIT result=${S_RESULT:-unknown} exit_status=${S_STATUS:-unknown} is-failed=${S_IS_FAILED:-unknown}"
fact "service_last_completion=$(human "$S_EXIT_EPOCH")"

# -- existence / load ------------------------------------------------------------------
TIMER_USABLE=1
if [ -z "$TIMER_SHOW" ] || [ -z "$T_LOAD" ] || [ "$T_LOAD" = "not-found" ]; then
  TIMER_USABLE=0
  P_PRODUCER+=("TIMER_MISSING: $TIMER_UNIT does not exist on this host (LoadState=${T_LOAD:-<none>}) - nothing is scheduled to refresh the factor store")
elif [ "$T_LOAD" = "masked" ] || [ "$T_FILE" = "masked" ]; then
  TIMER_USABLE=0
  P_PRODUCER+=("TIMER_MASKED: $TIMER_UNIT is MASKED (LoadState=$T_LOAD UnitFileState=$T_FILE) - it cannot be started even manually; unmask before anything else")
elif [ "$T_LOAD" != "loaded" ]; then
  P_PRODUCER+=("TIMER_NOT_LOADED: $TIMER_UNIT LoadState=$T_LOAD (expected 'loaded') - the unit file is present but systemd could not load it; check the unit syntax")
fi

if [ "$TIMER_USABLE" -eq 1 ]; then
  # -- enabled ---------------------------------------------------------------------
  case "$T_FILE" in
    enabled|enabled-runtime) : ;;
    disabled)
      P_PRODUCER+=("TIMER_DISABLED: $TIMER_UNIT is DISABLED - it is not installed into timers.target and will not be armed after a reboot (this is the 2026-08-03 09:46 ET state)")
      ;;
    "")
      P_PRODUCER+=("TIMER_ENABLEMENT_UNKNOWN: $TIMER_UNIT reports no UnitFileState - enablement cannot be confirmed, so it is treated as NOT enabled")
      ;;
    *)
      P_PRODUCER+=("TIMER_NOT_ENABLED: $TIMER_UNIT UnitFileState=$T_FILE (expected 'enabled')")
      ;;
  esac

  # -- active ----------------------------------------------------------------------
  if [ "$T_ACTIVE" != "active" ]; then
    P_PRODUCER+=("TIMER_INACTIVE: $TIMER_UNIT ActiveState=${T_ACTIVE:-<none>}/${T_SUB:-<none>} (expected active/waiting) - the timer is not armed, so no refresh will fire regardless of whether it is enabled")
  fi

  # -- next trigger exists, is in the future, and matches the pinned schedule -------
  if [ -z "$T_NEXT_EPOCH" ]; then
    P_PRODUCER+=("TIMER_NO_NEXT_TRIGGER: $TIMER_UNIT (ActiveState=${T_ACTIVE:-<none>}) has NO next elapse - nothing is scheduled; an armed timer with no next trigger will never fire again")
  elif [ "$T_NEXT_EPOCH" -le "$NOW_EPOCH" ]; then
    P_PRODUCER+=("TIMER_NEXT_TRIGGER_IN_PAST: $TIMER_UNIT next elapse $(human "$T_NEXT_EPOCH") is not in the future - the timer is stuck rather than waiting")
  else
    AHEAD_H=$(( (T_NEXT_EPOCH - NOW_EPOCH) / 3600 ))
    if [ "$AHEAD_H" -gt "$MAX_NEXT_TRIGGER_HOURS" ]; then
      P_PRODUCER+=("TIMER_NEXT_TRIGGER_IMPLAUSIBLE: next elapse $(human "$T_NEXT_EPOCH") is ${AHEAD_H}h away, beyond the ${MAX_NEXT_TRIGGER_HOURS}h ceiling for a weekday schedule - the OnCalendar spec no longer matches the pinned schedule")
    fi
    NEXT_HHMM="$(local_hhmm "$T_NEXT_EPOCH")"
    WANT_HHMM="$(printf '%02d:%02d' "$REFRESH_HOUR" "$REFRESH_MINUTE")"
    if [ -n "$NEXT_HHMM" ] && [ "$NEXT_HHMM" != "$WANT_HHMM" ]; then
      P_PRODUCER+=("TIMER_NEXT_TRIGGER_OFF_SCHEDULE: next elapse fires at $NEXT_HHMM $REFRESH_TZ, not the pinned $WANT_HHMM - the unit's OnCalendar has drifted from the schedule this watchdog is pinned to")
    fi
    fact "next_trigger_local_hhmm=${NEXT_HHMM:-unknown} (pinned $WANT_HHMM, ${AHEAD_H}h ahead)"
  fi

  # -- the LAST EXPECTED trigger actually occurred ---------------------------------
  if [ -n "$EXPECTED_EPOCH" ]; then
    if [ -z "$T_LAST_EPOCH" ]; then
      if [ -n "$T_ARMED_EPOCH" ] && [ "$T_ARMED_EPOCH" -gt "$EXPECTED_EPOCH" ]; then
        P_PRODUCER+=("WINDOW_MISSED_TIMER_ARMED_LATE: $TIMER_UNIT has never triggered and was armed at $(human "$T_ARMED_EPOCH"), AFTER the $EXPECTED_LOCAL window - Persistent=false means a missed window is not caught up, so that refresh did not happen")
      else
        P_PRODUCER+=("LAST_TRIGGER_MISSING: $TIMER_UNIT has no recorded trigger at all - it has never fired, so the $EXPECTED_LOCAL window was not served")
      fi
    elif [ "$T_LAST_EPOCH" -lt "$EXPECTED_EPOCH" ]; then
      OVERDUE_H=$(( (NOW_EPOCH - T_LAST_EPOCH) / 3600 ))
      P_PRODUCER+=("PRODUCER_OVERDUE: last trigger $(human "$T_LAST_EPOCH") is ${OVERDUE_H}h old and precedes the expected $EXPECTED_LOCAL window - the producer skipped its window")
    fi
  fi

fi

# -- the corresponding service execution completed successfully -----------------------
# Outside the timer block on purpose: when the timer is missing or masked the verdict is
# already FAIL, but the service's own state is still the evidence an operator needs first.
if [ -z "$SVC_SHOW" ] || [ -z "$S_LOAD" ] || [ "$S_LOAD" = "not-found" ]; then
  P_PRODUCER+=("SERVICE_MISSING: $SERVICE_UNIT does not exist (LoadState=${S_LOAD:-<none>}) - the timer, if it fires, has nothing to run")
else
  if service_unhealthy; then
    P_PRODUCER+=("SERVICE_FAILED: $SERVICE_UNIT last run FAILED (Result=${S_RESULT:-unknown} ExecMainStatus=${S_STATUS:-unknown} is-failed=${S_IS_FAILED:-unknown}) - the live store was left on its previous day (staging verify-abort or ingest error); see: journalctl -u ${SERVICE_UNIT%.service}")
  fi
  if [ -n "$EXPECTED_EPOCH" ]; then
    if [ -z "$S_EXIT_EPOCH" ]; then
      P_PRODUCER+=("SERVICE_NO_COMPLETION: $SERVICE_UNIT has no recorded completion - the $EXPECTED_LOCAL refresh never finished (or never started)")
    elif [ "$S_EXIT_EPOCH" -lt "$EXPECTED_EPOCH" ]; then
      P_PRODUCER+=("SERVICE_NO_COMPLETION: $SERVICE_UNIT last completed $(human "$S_EXIT_EPOCH"), BEFORE the expected $EXPECTED_LOCAL window - no execution corresponds to the window that was due")
    fi
  fi
fi

# ── host timezone ────────────────────────────────────────────────────────────────────
# `OnCalendar=Mon-Fri 06:00` carries no timezone, so systemd evaluates it in the host's
# local time. If the host is not the timezone this watchdog is pinned to, "06:00 ET" is a
# claim about a window that does not exist, and every window computation above is
# measuring the wrong hour. That is a producer-liveness defect, not a cosmetic one.
HOST_TZ="$("$SYSTEMCTL" show-timezone 2>/dev/null)"
[ -n "$HOST_TZ" ] || HOST_TZ="$(cat /etc/timezone 2>/dev/null)"
if [ -n "$HOST_TZ" ] && [ "$HOST_TZ" != "$REFRESH_TZ" ]; then
  P_PRODUCER+=("SCHEDULE_TZ_MISMATCH: host timezone is '$HOST_TZ' but the refresh OnCalendar carries no timezone and this watchdog is pinned to '$REFRESH_TZ' - the ${REFRESH_HOUR}:$(printf '%02d' "$REFRESH_MINUTE") window does not fire when the schedule claims it does")
fi
fact "host_timezone=${HOST_TZ:-unknown} (schedule pinned to $REFRESH_TZ)"

# ═════════════════════════════════════════════════════════════════════════════════════
# 2) SEALED REFRESH PROGRESSION
#
# #606: the seal advances only after verification passes AND the swap completes, so it is
# the only artifact that attests to a SUCCESSFUL generation. Read its governed `as_of` —
# not its file age — and require it to correspond to the expected window.
# ═════════════════════════════════════════════════════════════════════════════════════
SEALED_AS_OF=""
fact "sealed_artifact_path=$SEALED_PATH"

if [ ! -f "$SEALED_PATH" ]; then
  fact "sealed_artifact_exists=no"
  P_SEALED+=("SEALED_ARTIFACT_MISSING: $SEALED_PATH does not exist - nothing attests that any refresh has ever completed successfully on this host. (Expected on a host where the #606 producer has not yet completed a successful refresh.)")
else
  fact "sealed_artifact_exists=yes"
  SEALED_MTIME="$(stat -c %Y "$SEALED_PATH" 2>/dev/null || echo "")"
  SEALED_DIGEST="$(sha256sum "$SEALED_PATH" 2>/dev/null | cut -d' ' -f1)"
  SEALED_BYTES="$(stat -c %s "$SEALED_PATH" 2>/dev/null || echo "")"
  fact "sealed_artifact_mtime=$(human "$SEALED_MTIME")"
  fact "sealed_artifact_sha256=${SEALED_DIGEST:-unreadable} bytes=${SEALED_BYTES:-unknown}"

  SEALED_FIELDS="$(SEALED_PATH="$SEALED_PATH" "$PYTHON" - <<'PY' 2>/dev/null
import json, os, sys

try:
    doc = json.loads(open(os.environ["SEALED_PATH"], encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001 - any parse failure is one condition
    print(f"PARSE_ERROR={type(exc).__name__}")
    sys.exit(0)
if not isinstance(doc, dict):
    print("PARSE_ERROR=not-a-json-object")
    sys.exit(0)
as_of = doc.get("as_of")
if not isinstance(as_of, str) or not as_of.strip():
    print("PARSE_ERROR=missing-as_of")
    sys.exit(0)
print(f"AS_OF={as_of.strip()}")
counts = doc.get("counts") or {}
if isinstance(counts, dict) and counts.get("total") is not None:
    print(f"COUNT={counts['total']}")
dig = ((doc.get("digests") or {}).get("final_refresh_universe") or {}).get("sha256")
if dig:
    print(f"UNIVERSE_SHA256={dig}")
state = (doc.get("growth") or {}).get("state")
if state:
    print(f"GROWTH_STATE={state}")
PY
)"
  SEALED_PARSE_ERROR="$(prop "$SEALED_FIELDS" PARSE_ERROR)"
  SEALED_AS_OF="$(prop "$SEALED_FIELDS" AS_OF)"

  if [ -n "$SEALED_PARSE_ERROR" ] || [ -z "$SEALED_AS_OF" ]; then
    # A DISTINCT condition from "did not advance". Only a genuinely unreadable document
    # lands here; an unchanged-but-valid seal never does.
    P_SEALED+=("SEALED_ARTIFACT_UNREADABLE: $SEALED_PATH could not be parsed for its governed generation (${SEALED_PARSE_ERROR:-no as_of field}) - this is a MALFORMED artifact, which is a different condition from an artifact that simply did not advance")
  else
    fact "sealed_generation_as_of=$SEALED_AS_OF"
    fact "sealed_universe_count=$(prop "$SEALED_FIELDS" COUNT) sha256=$(prop "$SEALED_FIELDS" UNIVERSE_SHA256) growth=$(prop "$SEALED_FIELDS" GROWTH_STATE)"
  fi
fi

# -- the advancement rule -------------------------------------------------------------
# systemd keeps no separate "last SUCCESSFUL execution" stamp for a oneshot: ExecMainExit-
# Timestamp is simply the last execution, and Result says whether it succeeded. So the
# record names both, and points at the seal's as_of as the authoritative last successful
# generation when the most recent execution was not one.
if service_unhealthy; then
  fact "last_successful_service_execution=unknown (the last execution at $(human "$S_EXIT_EPOCH") FAILED); last SUCCESSFUL generation is the seal's as_of=${SEALED_AS_OF:-none}"
else
  fact "last_successful_service_execution=$(human "$S_EXIT_EPOCH")"
fi
fact "expected_latest_successful_generation=${EXPECTED_DATE:-UNRESOLVED}"
if [ -n "$SEALED_AS_OF" ] && [ -n "$EXPECTED_DATE" ]; then
  # Both are YYYY-MM-DD, which compares correctly as a string.
  if [ "$SEALED_AS_OF" \< "$EXPECTED_DATE" ]; then
    # Classify WHY from the producer evidence gathered above. An unchanged seal is
    # correct #606 behaviour after a failed refresh — reported as a readiness failure,
    # never as corruption.
    if [ -n "$EXPECTED_EPOCH" ] && { [ -z "$T_LAST_EPOCH" ] || [ "$T_LAST_EPOCH" -lt "$EXPECTED_EPOCH" ]; }; then
      SEALED_STALE_CAUSE="PRODUCER_DID_NOT_RUN"
      WHY="the producer did not run: no trigger at or after the expected window. The artifact is intact and unchanged, which is correct - there was no successful generation to seal"
    elif service_unhealthy; then
      SEALED_STALE_CAUSE="PRODUCER_RAN_AND_FAILED"
      WHY="the producer RAN and FAILED. Leaving the seal unchanged is CORRECT behaviour (#606: the seal advances only after verification passes AND the swap completes) - the artifact is NOT corrupt; the successful generation is what is missing"
    elif [ -n "$EXPECTED_EPOCH" ] && [ -n "$S_EXIT_EPOCH" ] && [ "$S_EXIT_EPOCH" -ge "$EXPECTED_EPOCH" ]; then
      SEALED_STALE_CAUSE="PRODUCER_RAN_OK_SEAL_DID_NOT_ADVANCE"
      WHY="the producer ran and reported SUCCESS but the seal did not advance - this breaks the #606 contract (a completed swap must be followed by the seal) and needs investigation on the box"
    else
      SEALED_STALE_CAUSE="INDETERMINATE"
      WHY="the cause could not be attributed from systemd state - treated as NOT READY until it is established"
    fi
    P_SEALED+=("SEALED_GENERATION_STALE: sealed as_of=$SEALED_AS_OF is behind the expected $EXPECTED_DATE window - $WHY")
  else
    fact "sealed_generation=CURRENT (as_of=$SEALED_AS_OF >= expected $EXPECTED_DATE)"
  fi
fi

# ── timer active but the service is repeatedly failing ───────────────────────────────
# Distinguished from a single failure by evidence, not by a counter systemd does not keep
# for oneshots: the seal records the last SUCCESSFUL generation, so a seal two or more
# expected windows behind while the timer is armed and the service is failing means the
# producer is firing and failing repeatedly, not once.
if [ "$T_ACTIVE" = "active" ] && [ -n "$PRIOR_DATE" ] && [ -n "$SEALED_AS_OF" ] \
   && service_unhealthy && [ "$SEALED_AS_OF" \< "$PRIOR_DATE" ]; then
  P_PRODUCER+=("SERVICE_REPEATEDLY_FAILING: $TIMER_UNIT is armed and firing, but $SERVICE_UNIT is failing and the last SUCCESSFUL sealed generation ($SEALED_AS_OF) predates even the prior window ($PRIOR_DATE) - at least two consecutive refreshes have failed; restarting the timer will not fix this")
fi

# ═════════════════════════════════════════════════════════════════════════════════════
# 3) DATA FRESHNESS — the live store itself. Independent of everything above.
#
# Inline query only. This must NOT import apps/backend/scripts/factor_refresh.py: that
# module is baked into the image, the deployed image predates it, and this watchdog must
# never become a reason to deploy it as a side effect.
# ═════════════════════════════════════════════════════════════════════════════════════
# The shared adjudication implementation is PIPED IN AHEAD of the driver, from the
# host tree, and the driver runs against those definitions. Never imported from the
# image: the image is built on its own cadence and routinely predates the host tree.
STORE_REPORT="$( { cat <<< "$ADJUDICATION_SRC"; cat <<'PY'
import datetime, json, os, zoneinfo

import duckdb

tol = int(os.environ["TOLERANCE"])
max_lag = int(os.environ["MAX_LAG_DAYS"])
min_cov = float(os.environ["MIN_COVERAGE"])
sample = int(os.environ["STALE_SAMPLE"])
# Clock seam, mirroring the shell's WATCHDOG_NOW_EPOCH. Without it this block reads the
# wall clock while its tests pin a frontier, so they rot silently as time passes rather
# than failing on a real regression.
_pinned = os.environ.get("ET_TODAY", "").strip()
et_today = (
    datetime.date.fromisoformat(_pinned)
    if _pinned
    else datetime.datetime.now(zoneinfo.ZoneInfo(os.environ["REFRESH_TZ"])).date()
)


def d(v):
    return v.date() if hasattr(v, "date") else v


c = duckdb.connect(os.environ["STORE_PATH"], read_only=True)
sep = d(c.execute("SELECT max(date) FROM sep").fetchone()[0])
lpd = d(c.execute("SELECT max(lastpricedate) FROM tickers").fetchone()[0])
print(f"STATUS sep_max={sep} lastpricedate={lpd} et_today={et_today} "
      f"tolerance={tol}d max_lag={max_lag}d min_coverage={min_cov}")

if sep is None:
    print("PROBLEM DATA_SEP_EMPTY: live sep table is EMPTY")
else:
    age = (et_today - sep).days
    if age > tol:
        print(f"PROBLEM DATA_SEP_FRONTIER_STALE: sep max {sep} is {age}d old (>{tol}d) "
              "- factor books are ranking on old data")
    if lpd is not None and lpd < sep:
        print(f"PROBLEM DATA_LOCKSTEP_BROKEN: tickers.lastpricedate {lpd} BEHIND sep {sep} "
              "- the PIT universe resolves EMPTY and every factor book silently HOLDs "
              "(2026-07-06 incident class)")

    # Per-name freshness over the SEALED universe. max(date) over the whole table is not a
    # freshness measure: one current ticker keeps it green while the rest of the pool is
    # frozen, which is how 301/500 names sat at 2026-07-06 with every gate green.
    try:
        universe = sorted({
            str(s).strip().upper()
            for s in json.loads(
                open(os.environ["SEALED_PATH"], encoding="utf-8").read()
            )["universe"]
            if str(s).strip()
        })
    except Exception as exc:  # noqa: BLE001
        universe = []
        print("PROBLEM DATA_PER_NAME_UNAVAILABLE: the sealed universe could not be read "
              f"in-container ({type(exc).__name__}), so per-name freshness was NOT "
              "assessed - treated as a failure rather than assumed fresh")

    if universe:
        cutoff = sep - datetime.timedelta(days=max_lag)
        ph = ",".join("?" * len(universe))
        sep_rows = c.execute(
            f"SELECT ticker, max(date) FROM sep WHERE ticker IN ({ph}) GROUP BY ticker",  # noqa: S608
            universe,
        ).fetchall()
        try:
            lpd_rows = c.execute(
                f"SELECT ticker, lastpricedate FROM tickers WHERE ticker IN ({ph})",  # noqa: S608
                universe,
            ).fetchall()
        except Exception:  # noqa: BLE001 - tickers table absent
            lpd_rows = []
        smax = {t: d(v) for t, v in sep_rows if v is not None}
        lmax = {t: d(v) for t, v in lpd_rows if v is not None}

        # EFFECTIVE freshness is the earlier of the two. A name with current prices but a
        # lagging lastpricedate is dropped from the ranking pool outright - strictly worse
        # than being ranked on old data - so it must not read as healthy here.
        effective = {}
        for t in universe:
            parts = [x for x in (smax.get(t), lmax.get(t)) if x is not None]
            effective[t] = min(parts) if parts else None
        non_fresh = sorted(
            t for t in universe if effective[t] is None or effective[t] < cutoff
        )

        evidence, ev_note, ev_status = load_evidence(os.environ["EXHAUSTION_PATH"])
        if ev_status in ("unreadable", "malformed"):
            # A broken control is a finding even on a run where nothing is stale.
            print("PROBLEM DATA_EXHAUSTION_EVIDENCE_UNREADABLE: "
                  f"{os.environ['EXHAUSTION_PATH']} could not be used ({ev_note}), so no "
                  "symbol was attributed and an adjudicated delisting will read as a "
                  "freshness failure - repair the evidence artifact rather than relaxing "
                  "the freshness threshold")
        # Held/registered facts are RECOMPUTED from the app DB, never taken from the
        # evidence file: a stale or crafted artifact must not be able to declare a held
        # name unheld and so write it off. Unreadable is a failure, not an empty set -
        # empty would be LAXER than the refresh verifier, and the two must not diverge.
        try:
            operational = operational_facts(os.environ["APP_DB"], universe)
        except Exception as exc:  # noqa: BLE001
            operational = None
            print("PROBLEM DATA_OPERATIONAL_FACTS_UNAVAILABLE: held/registered facts could "
                  f"not be read from the app DB ({type(exc).__name__}), so adjudication "
                  "could not verify that an attributed name is neither held nor registered "
                  "- treated as a failure rather than adjudicated without them")

        if operational is not None:
            # The watchdog assesses ONE store, so the live and stage frontiers are the same
            # value: there is no pending swap to disprove.
            result = adjudicate(
                universe,
                stage_effective=effective,
                live_effective=effective,
                non_fresh=non_fresh,
                cutoff=cutoff,
                evidence=evidence,
                operational=operational,
            )
            coverage = gating_coverage(result)
            print(f"METRIC universe={result['universe_size']} "
                  f"assessable={result['assessable_count']} "
                  f"attributed={result['attributed_count']} covered={result['covered']} "
                  f"coverage={coverage:.4f} raw_coverage={result['raw_coverage']:.4f} "
                  f"unexplained={result['failed_or_unexplained_count']} "
                  f"ceiling={result['exemption_ceiling']} frontier={sep} cutoff={cutoff}")
            print(f"NOTE DATA_ADJUDICATION_EVIDENCE: {ev_note}")
            for note in result["notes"]:
                print(f"NOTE {note}")
            for problem in result["problems"]:
                print(f"PROBLEM {problem}")
            if coverage < min_cov:
                bad = result["failed_or_unexplained_symbols"]
                print(f"PROBLEM DATA_PER_NAME_COVERAGE: per-name coverage {coverage:.4f} < "
                      f"{min_cov} over {result['assessable_count']} assessable names "
                      f"({result['failed_or_unexplained_count']} unadjudicated) of the "
                      f"{sep} frontier; e.g. {','.join(bad[:sample])}")
            if result["failed_or_unexplained_symbols"]:
                bad = result["failed_or_unexplained_symbols"]
                print(f"PROBLEM DATA_UNADJUDICATED_STALE: {len(bad)} universe tickers are "
                      "stale with no accepted evidence - a name with a stale "
                      "tickers.lastpricedate is EXCLUDED from the ranking pool outright "
                      f"(worse than ranking on old data); e.g. {','.join(bad[:sample])}")
c.close()
PY
} | $DOCKER exec -i \
  -e TOLERANCE="$TOLERANCE" \
  -e MAX_LAG_DAYS="$MAX_LAG_DAYS" \
  -e MIN_COVERAGE="$MIN_COVERAGE" \
  -e STALE_SAMPLE="$STALE_NAME_SAMPLE" \
  -e SEALED_PATH="$CONTAINER_SEALED" \
  -e EXHAUSTION_PATH="$CONTAINER_EXHAUSTION" \
  -e STORE_PATH="$STORE_PATH" \
  -e APP_DB="$CONTAINER_APP_DB" \
  -e ET_TODAY="${WATCHDOG_ET_TODAY:-}" \
  -e REFRESH_TZ="$REFRESH_TZ" \
  "$BACKEND_CONTAINER" python - 2>/dev/null )"
STORE_RC=$?

if [ "$STORE_RC" -ne 0 ] || [ -z "$STORE_REPORT" ]; then
  P_DATA+=("DATA_STORE_UNREADABLE: could not read the live factor store from '$BACKEND_CONTAINER' (container down, or duckdb open failed) - freshness is UNKNOWN, which is treated as a failure rather than assumed fresh")
else
  while IFS= read -r line; do
    case "$line" in
      PROBLEM*) P_DATA+=("${line#PROBLEM }");;
      # The adjudicated populations, lifted out for publication. A verdict that reports
      # only PASS/FAIL leaves an operator unable to tell a legitimately-attributed pool
      # from one that is quietly missing data, which is the question this whole change is
      # about. Parsed rather than recomputed: these are the figures that actually decided
      # the run, not a second calculation that could disagree with them.
      METRIC*)
        for kv in ${line#METRIC }; do
          case "$kv" in
            universe=*)      M_UNIVERSE="${kv#universe=}";;
            assessable=*)    M_ASSESSABLE="${kv#assessable=}";;
            attributed=*)    M_ATTRIBUTED="${kv#attributed=}";;
            covered=*)       M_COVERED="${kv#covered=}";;
            coverage=*)      M_GATING="${kv#coverage=}";;
            raw_coverage=*)  M_RAW="${kv#raw_coverage=}";;
            unexplained=*)   M_UNEXPLAINED="${kv#unexplained=}";;
          esac
        done;;
    esac
  done <<< "$STORE_REPORT"
fi

# ═════════════════════════════════════════════════════════════════════════════════════
# 4) VERDICT — three independent conditions; readiness is their conjunction.
# ═════════════════════════════════════════════════════════════════════════════════════
verdict() { if [ "$1" -eq 0 ]; then echo PASS; else echo FAIL; fi; }
PRODUCER_LIVENESS="$(verdict "${#P_PRODUCER[@]}")"
SEALED_GENERATION="$(verdict "${#P_SEALED[@]}")"
DATA_FRESHNESS="$(verdict "${#P_DATA[@]}")"
if [ "$PRODUCER_LIVENESS" = PASS ] && [ "$SEALED_GENERATION" = PASS ] && [ "$DATA_FRESHNESS" = PASS ]; then
  OVERALL_READINESS=PASS
else
  OVERALL_READINESS=FAIL
fi

# ═════════════════════════════════════════════════════════════════════════════════════
# 5) PUBLISH THE VERDICT — the step that turns detection into a veto.
#
# Written on every run, PASS or FAIL, atomically. The document is generated by python
# rather than assembled as a shell string on purpose: the problem details below are
# operator prose containing quotes, brackets and '=' signs, and hand-rolled JSON quoting
# is exactly how a writer starts emitting documents its reader classifies as UNREADABLE —
# which, under the consumer's fail-closed contract, is a trading halt.
# ═════════════════════════════════════════════════════════════════════════════════════
# One "<component>\t<detail>" line per problem. Tab-separated because the details are
# free prose that already contains every other plausible separator; they never contain a
# newline or a tab, so this round-trips exactly.
PROBLEMS_BLOB=""
blob_add() {  # <component> <problem>...
  local component="$1" problem line; shift
  for problem in "$@"; do
    printf -v line '%s\t%s\n' "$component" "$problem"
    PROBLEMS_BLOB="${PROBLEMS_BLOB}${line}"
  done
}
blob_add producer_liveness ${P_PRODUCER[@]+"${P_PRODUCER[@]}"}
blob_add sealed_generation ${P_SEALED[@]+"${P_SEALED[@]}"}
blob_add data_freshness    ${P_DATA[@]+"${P_DATA[@]}"}

PUBLISH_OUT="$(
  READINESS_PATH="$READINESS_PATH" \
  EVALUATED_EPOCH="$NOW_EPOCH" \
  CLOCK_SOURCE="$CLOCK_SOURCE" \
  OVERALL="$OVERALL_READINESS" \
  V_PRODUCER="$PRODUCER_LIVENESS" \
  V_SEALED="$SEALED_GENERATION" \
  V_DATA="$DATA_FRESHNESS" \
  V_CAUSE="$SEALED_STALE_CAUSE" \
  SEALED_AS_OF="$SEALED_AS_OF" \
  EXPECTED_DATE="$EXPECTED_DATE" \
  TIMER_UNIT="$TIMER_UNIT" \
  SERVICE_UNIT="$SERVICE_UNIT" \
  SCHEDULE_TZ="$REFRESH_TZ" \
  PROBLEMS_BLOB="$PROBLEMS_BLOB" \
  ADJUDICATION_SHA256="$ADJUDICATION_SHA256" \
  ADJUDICATION_PATH="$ADJUDICATION_PATH" \
  M_UNIVERSE="${M_UNIVERSE:-}" \
  M_ASSESSABLE="${M_ASSESSABLE:-}" \
  M_ATTRIBUTED="${M_ATTRIBUTED:-}" \
  M_COVERED="${M_COVERED:-}" \
  M_GATING="${M_GATING:-}" \
  M_RAW="${M_RAW:-}" \
  M_UNEXPLAINED="${M_UNEXPLAINED:-}" \
  "$PYTHON" - <<'PY' 2>&1
import contextlib
import hashlib
import json
import os
import tempfile
# `timezone.utc`, NOT `datetime.UTC`: this block runs under the HOST's python3, not the
# container's. The alias was added in 3.11, and a host on an older interpreter would fail
# to publish on every run — which, once the gate requires the artifact, is a trading halt
# caused by a stylistic import. Nothing else here needs more than python 3.9.
from datetime import datetime, timezone
from pathlib import Path

dest = Path(os.environ["READINESS_PATH"])

problems = []
for line in os.environ.get("PROBLEMS_BLOB", "").splitlines():
    if not line.strip():
        continue
    component, _, detail = line.partition("\t")
    problems.append({"component": component, "detail": detail})


def opt(name):
    value = os.environ.get(name, "").strip()
    return value or None


def num(name, cast=float):
    """A metric the store query reported, or None if it never got that far.

    None is meaningful and is preserved rather than defaulted to zero: it says the
    per-name assessment did not run, which is a different state from 'nothing was
    covered'. Zero would read as a measured catastrophe instead of an absent
    measurement."""
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return cast(value)
    except ValueError:
        return None


doc = {
    "schema_version": 1,
    "artifact": "factor_readiness",
    # ── CONTRACT FIELDS ───────────────────────────────────────────────────────────
    # app/strategies/factor_readiness.py reads exactly these two. `evaluated_at_utc`
    # must parse via datetime.fromisoformat (after Z -> +00:00) and is aged out at 26h;
    # `overall_readiness` is compared, uppercased, against the literal "PASS". Anything
    # else BLOCKS factor-consuming dispatch. Do not rename, reformat or drop them.
    "evaluated_at_utc": datetime.fromtimestamp(
        int(os.environ["EVALUATED_EPOCH"]), timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "overall_readiness": os.environ["OVERALL"].upper(),
    # ── evidence: why the verdict is what it is ───────────────────────────────────
    "components": {
        "producer_liveness": os.environ["V_PRODUCER"].upper(),
        "sealed_generation": os.environ["V_SEALED"].upper(),
        "data_freshness": os.environ["V_DATA"].upper(),
    },
    "sealed_stale_cause": os.environ.get("V_CAUSE") or "N/A",
    "sealed_generation_as_of": opt("SEALED_AS_OF"),
    "expected_refresh_window_date": opt("EXPECTED_DATE"),
    "problem_count": len(problems),
    "problems": problems,
    "producer": {
        "timer_unit": os.environ["TIMER_UNIT"],
        "service_unit": os.environ["SERVICE_UNIT"],
        "schedule_tz": os.environ["SCHEDULE_TZ"],
    },
    # WHICH adjudication implementation produced this verdict. The refresh verifier and
    # this watchdog consume ONE shared module; recording its hash is what lets an
    # operator prove after the fact that a given PASS came from the reviewed rules and
    # not from a drifted copy. A null hash means the helper was unavailable, in which
    # case data_freshness is FAIL by construction — a verdict with no named
    # implementation behind it is never a PASS.
    # The two coverage figures, side by side and never conflated. `gating_coverage` is
    # the ONLY one any threshold is applied to; `raw_coverage` is observability. An
    # ATTRIBUTED symbol is not 'fresh' — it is removed from the assessable population
    # because the provider has been governably determined unable or inapplicable to
    # supply the observation. So gating_coverage=1.0000 never means 'all names are
    # current'; read it with attributed_count and raw_coverage beside it.
    "coverage": {
        "gating_coverage": num("M_GATING"),
        "gating_coverage_definition": (
            "covered / assessable, assessable = universe - validly attributed"
        ),
        "raw_coverage": num("M_RAW"),
        "raw_coverage_use": "observability only; no gate may threshold it",
        "universe_count": num("M_UNIVERSE", int),
        "assessable_count": num("M_ASSESSABLE", int),
        "attributed_count": num("M_ATTRIBUTED", int),
        "covered_count": num("M_COVERED", int),
        "unexplained_count": num("M_UNEXPLAINED", int),
    },
    "adjudication": {
        "implementation": os.environ.get("ADJUDICATION_PATH") or None,
        "sha256": opt("ADJUDICATION_SHA256"),
        "sourced_from": "host tree, piped into the container as source",
        "image_import": False,
    },
    "clock_source": os.environ.get("CLOCK_SOURCE", "wall"),
}

payload = json.dumps(doc, indent=2, sort_keys=False) + "\n"

# ATOMIC BY CONSTRUCTION: a fresh temp file in the SAME directory (so rename cannot cross
# a filesystem boundary and degrade into copy-then-truncate), fsynced, then renamed over
# the destination. A concurrent reader observes either the whole previous document or the
# whole new one — never a prefix. The destination is NEVER opened for writing.
fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name + ".", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    # The watchdog runs as root on the host; the reader is the backend container. 0644 so
    # a future non-root container user can still read the verdict it is gated on.
    os.chmod(tmp, 0o644)
    os.replace(tmp, dest)
except BaseException:
    with contextlib.suppress(OSError):
        os.unlink(tmp)
    raise
# Durability of the rename itself, so a power loss cannot resurrect the previous verdict.
with contextlib.suppress(OSError):
    dir_fd = os.open(str(dest.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

print(f"sha256={hashlib.sha256(payload.encode('utf-8')).hexdigest()} bytes={len(payload)}")
PY
)"
PUBLISH_RC=$?

if [ "$PUBLISH_RC" -eq 0 ]; then
  READINESS_ARTIFACT=PUBLISHED
  fact "readiness_artifact=$READINESS_PATH published verdict=$OVERALL_READINESS ${PUBLISH_OUT}"
else
  READINESS_ARTIFACT=FAILED
  # Fail LOUD, not silently: with no artifact the in-app gate blocks factor dispatch once
  # the previous verdict ages past 26h, so this is an operator-action condition even when
  # the factor data itself is perfectly current.
  P_PUBLISH+=("READINESS_ARTIFACT_NOT_PUBLISHED: could not write $READINESS_PATH - the dispatch-time veto has no verdict to read for today, so factor-consuming strategies will be BLOCKED once the previous verdict ages out (26h). Is $DATADIR mounted and writable? Writer said: $(printf '%s' "$PUBLISH_OUT" | tr '\n' ' ' | tail -c 400)")
  fact "readiness_artifact=$READINESS_PATH NOT PUBLISHED (writer exit $PUBLISH_RC)"
fi

TOTAL=$(( ${#P_PRODUCER[@]} + ${#P_SEALED[@]} + ${#P_DATA[@]} + ${#P_PUBLISH[@]} ))

# Machine-readable first, so a consumer greps a line rather than parsing prose.
SUMMARY="PRODUCER_LIVENESS=$PRODUCER_LIVENESS
SEALED_GENERATION=$SEALED_GENERATION
DATA_FRESHNESS=$DATA_FRESHNESS
OVERALL_READINESS=$OVERALL_READINESS
READINESS_ARTIFACT=$READINESS_ARTIFACT
SEALED_STALE_CAUSE=$SEALED_STALE_CAUSE"

section() {  # <title> <verdict> [problem ...]
  local title="$1" v="$2"; shift 2
  printf '\n%s: %s\n' "$title" "$v"
  if [ "$#" -gt 0 ]; then printf -- '  - %s\n' "$@"; fi
}

DETAIL="$(
  section "PRODUCER LIVENESS" "$PRODUCER_LIVENESS" ${P_PRODUCER[@]+"${P_PRODUCER[@]}"}
  section "SEALED GENERATION" "$SEALED_GENERATION" ${P_SEALED[@]+"${P_SEALED[@]}"}
  section "DATA FRESHNESS"    "$DATA_FRESHNESS"    ${P_DATA[@]+"${P_DATA[@]}"}
  section "READINESS ARTIFACT" "$READINESS_ARTIFACT" ${P_PUBLISH[@]+"${P_PUBLISH[@]}"}
  printf '\nEvidence:\n'
  printf -- '  %s\n' ${FACTS[@]+"${FACTS[@]}"}
  printf '\nStore report:\n%s\n' "${STORE_REPORT:-unavailable}"
)"

printf '%s\n' "$SUMMARY"
printf '%s\n' "$DETAIL"

if [ "$OVERALL_READINESS" = PASS ] && [ "$READINESS_ARTIFACT" = PUBLISHED ]; then
  exit "$EXIT_READY"
fi

# A publication failure on an otherwise-ready box is a DIFFERENT operational condition
# from stale factor data, and the alert must not misreport one as the other: the data is
# fine, the veto is unarmed.
if [ "$OVERALL_READINESS" = PASS ]; then
  HEADLINE="READY BUT THE INTERLOCK VERDICT WAS NOT PUBLISHED"
else
  HEADLINE="NOT READY (${TOTAL} issue(s))"
fi

BODY="${SUBJECT_PREFIX}Factor-data readiness ${DATE_ET} - ${HEADLINE}.

${SUMMARY}
${DETAIL}

Contract: readiness = producer liveness AND sealed refresh progression AND data freshness.
Any one failing must block factor-consuming dispatch. A fresh store does NOT vouch for a
live producer (2026-08-03: the timer was disabled at 09:46 ET and the store stayed clean
until the next day). A failed refresh that leaves ${SEALED_BASENAME} unchanged is CORRECT
producer behaviour per #606 - the artifact is not corrupt; the successful generation is
what is missing.

Interlock: this run's verdict is published to ${READINESS_PATH} and read AT DISPATCH by
the in-app gate. A FAIL verdict, a verdict older than 26h, and an absent or unreadable
artifact all BLOCK the factor books (momentum / sector / low-vol / combined) from being
entered at all - they do not merely spoil the resulting orders. Expect that block to be
visible as 'strategy_dispatch_blocked_factor_not_ready' in the backend log.

Runbook: the factor books (momentum / sector / low-vol / combined) RANK on
data/factor_data.duckdb. Producer: ${TIMER_UNIT} -> ${SERVICE_UNIT}
(journalctl -u ${SERVICE_UNIT%.service}). Rollback copy: factor_data.prev.duckdb.
See deploy/aws/factor-refresh.sh and docs/runbook/aws-migration.md."

SUBJECT="${SUBJECT_PREFIX}FACTOR READINESS ${DATE_ET} - ${HEADLINE}"
if "$AWS_BIN" sns publish --region "$REGION" --topic-arn "$TOPIC" \
     --subject "$SUBJECT" --message "$BODY" >/dev/null 2>&1; then
  echo "published: $SUBJECT"
else
  echo "SNS publish FAILED - readiness is still NOT READY"
fi
# Non-zero regardless of whether the alert got out: the exit code is the interlock, and a
# failed publish must never downgrade a readiness failure to a pass.
exit "$EXIT_NOT_READY"
