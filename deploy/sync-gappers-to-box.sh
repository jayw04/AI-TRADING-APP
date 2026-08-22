#!/usr/bin/env bash
# Sync the day's pre-market gappers file from this laptop to the AWS paper box.
#
# The gappers scanner (claude-trading-view, driven by TradingView Desktop) is laptop-only; the
# Opportunities-page panel and the SCAN-001 premarket gate on the box read
# /opt/workbench/claude-trading-view/. This publishes *today's* artifact over SSH after the
# scanner runs (~08:30 ET). Runs from a Windows scheduled task ~08:00 CT on trading days.
#
# ── Why this script is strict ──────────────────────────────────────────────────────────────
# It used to fall back to `ls -t … | head -1` — the newest file in the directory — whenever
# today's artifact was missing. On 2026-07-21 the scanner died ("gainers fetch failed after 3
# attempts", exit 1) and that fallback silently republished the 2026-07-20 artifact, which the
# box then scored as an independent forward day. A scanner failure must never be laundered into
# an apparently successful publication.
#
# The rule is now: publish today's artifact, or publish nothing and say so loudly. A stale file
# stays on disk for diagnostics but is never promoted. Every failure path exits non-zero and
# raises an ntfy alert.
#
# Validation performed before anything is copied:
#   1. run manifest  — the scanner's own guard log must record a successful run for the target
#                      date ("[DONE] scan exit 0 -> premarket_gappers_<date>.json"). A "[SKIP]"
#                      line (holiday / weekend / stale feed) is an *expected* no-publication and
#                      exits 0 quietly, so market holidays do not page anyone.
#   2. exact path    — the artifact must be premarket_gappers_<target>.json. No newest-file scan.
#   3. well-formed   — parses as JSON and carries a non-empty `gappers` list (catches truncated
#                      or partially written files).
#   4. embedded date — `scanned_at` converted to America/New_York must fall on the target date,
#                      so a correctly named file containing yesterday's snapshot is rejected.
#   5. time window   — `scanned_at` is not in the future and not older than MAX_ARTIFACT_AGE_MIN,
#                      so a file left over from an earlier run cannot be republished.
#   6. post-copy     — the sha256 on the box must equal the local sha256; publication is only
#                      reported after the bytes are verified in place.
#
# Follow-up (needs a change in the sibling scanner, not here): the artifact carries no scanner
# run ID, so check 1 leans on the guard log rather than a token embedded in the file itself.
# Have premarket_gappers.sh stamp a `run_id` into the JSON and echo it into the log, then match
# them directly.
#
# Usage: sync-gappers-to-box.sh [--date YYYY-MM-DD] [--dry-run]
set -uo pipefail

GAPPERS_DIR="/c/LLM-RAG-APP/claude-trading-view"
SCANNER_LOG="$GAPPERS_DIR/logs/premarket_gapper_guard.log"
LOG="${GAPPER_SYNC_LOG:-$GAPPERS_DIR/sync-gappers.log}"   # overridable so tests don't write the real log
REMOTE_DIR="/opt/workbench/claude-trading-view"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=20 -o ClearAllForwardings=yes"
MAX_ARTIFACT_AGE_MIN="${MAX_ARTIFACT_AGE_MIN:-720}"   # 12h — comfortably covers 08:30 ET → sync

# Scanner [SKIP] reasons that legitimately mean "no artifact is expected today". Deliberately an
# allowlist: an unrecognised skip reason alerts rather than silently clearing the day, because a
# missed alert costs a gate record while a spurious one costs a glance at the log.
SKIP_REASONS="US market holiday|weekend|premarket feed stale|market likely closed"

TARGET_DATE=""
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --date) TARGET_DATE="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Local clock is CT and Git Bash's `TZ=America/New_York date` silently returns UTC on this
# machine, so Eastern dates are computed in Python (zoneinfo) — never by shell TZ conversion.
PYTHON=""
for candidate in "$GAPPERS_DIR/.venv/Scripts/python.exe" python python3; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "$(date '+%F %T') FATAL no python available for validation" | tee -a "$LOG"
  exit 1
fi

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

# Alert on every failure path. Channel from env, else the machine's shared ntfy config.
alert() {
  local title="$1" body="$2"
  if [ "$DRY_RUN" = "1" ]; then log "DRYRUN-ALERT $title: $body"; return; fi
  "$PYTHON" - "$title" "$body" <<'PY' 2>/dev/null || echo "$(date '+%F %T') WARN alert send failed" >>"$LOG"
import json, os, sys, urllib.request

title, body = sys.argv[1], sys.argv[2]
server = os.environ.get("GAPPER_SYNC_NTFY_SERVER")
topic = os.environ.get("GAPPER_SYNC_NTFY_TOPIC")
if not topic:
    for name in ("insider.config.json", "portfolio.config.json", "scanner_b.config.json"):
        path = os.path.join(r"C:\LLM-RAG-APP\claude-trading-view", name)
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            continue
        if cfg.get("ntfy_topic") and "CHANGE-ME" not in str(cfg["ntfy_topic"]):
            server = server or cfg.get("ntfy_server", "https://ntfy.sh")
            topic = cfg["ntfy_topic"]
            break
if not topic:
    sys.exit(1)   # no channel configured — caller logs the WARN
req = urllib.request.Request(
    f"{(server or 'https://ntfy.sh').rstrip('/')}/{topic}",
    data=body.encode("utf-8"),
    headers={"Title": title, "Tags": "rotating_light,chart_with_upwards_trend"},
)
urllib.request.urlopen(req, timeout=15).read()
PY
}

fail() {
  local reason="$1"
  log "FAILED [$reason] target=$TARGET_DATE — nothing published"
  alert "Gapper sync FAILED ($TARGET_DATE)" "$reason
No artifact was published to the box. The SCAN-001 gate will have no record for $TARGET_DATE.
Stale files are retained locally for diagnostics but are never promoted."
  exit 1
}

[ -n "$TARGET_DATE" ] || TARGET_DATE="$("$PYTHON" -c \
  "from datetime import datetime;from zoneinfo import ZoneInfo;print(datetime.now(ZoneInfo('America/New_York')).date().isoformat())")"
if [ -z "$TARGET_DATE" ]; then
  log "FATAL could not determine the Eastern target date"
  exit 1
fi

ARTIFACT="$GAPPERS_DIR/premarket_gappers_${TARGET_DATE}.json"
BASE="$(basename "$ARTIFACT")"

# (1) Run manifest — did the scanner actually run today, and how did it end?
if [ -f "$SCANNER_LOG" ]; then
  if grep -qF "[DONE] scan exit 0 -> $BASE" "$SCANNER_LOG"; then
    :
  elif grep -qE "^$TARGET_DATE .*\[SKIP\].*($SKIP_REASONS)" "$SCANNER_LOG"; then
    # Only *no-scan-expected* reasons clear the day. An unrecognised [SKIP] is NOT accepted —
    # notably "already ran today (…json exists)", which asserts an artifact exists and would
    # otherwise let a deleted/never-landed file pass as a clean non-event.
    skip_line="$(grep -E "^$TARGET_DATE .*\[SKIP\].*($SKIP_REASONS)" "$SCANNER_LOG" | tail -1)"
    log "SKIP  $TARGET_DATE — scanner skipped by design, nothing to publish: $skip_line"
    exit 0
  elif grep -q "^$TARGET_DATE " "$SCANNER_LOG"; then
    # Prefer the explicit error; otherwise quote the last line for the date, so an unrecognised
    # [SKIP] or a run that simply stopped mid-scan still names what was actually observed.
    last_line="$(grep "^$TARGET_DATE .*\[ERROR\]" "$SCANNER_LOG" | tail -1)"
    [ -n "$last_line" ] || last_line="$(grep "^$TARGET_DATE " "$SCANNER_LOG" | tail -1)"
    fail "scanner ran for $TARGET_DATE but recorded no successful completion. Last log line: $last_line"
  else
    fail "no scanner guard-log activity at all for $TARGET_DATE (did the scheduled task fire?)"
  fi
else
  log "WARN scanner guard log not found at $SCANNER_LOG — proceeding on artifact checks alone"
fi

# (2) Exact path only. Deliberately no newest-file fallback.
if [ ! -f "$ARTIFACT" ]; then
  newest="$(ls -t "$GAPPERS_DIR"/premarket_gappers_*.json 2>/dev/null | head -1)"
  fail "no artifact for $TARGET_DATE at $ARTIFACT (newest on disk is ${newest:-none} — NOT published)"
fi

# (3)(4)(5) Content, embedded Eastern date, and freshness window.
validation="$("$PYTHON" - "$ARTIFACT" "$TARGET_DATE" "$MAX_ARTIFACT_AGE_MIN" <<'PY'
import json, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

path, target, max_age_min = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
except (OSError, ValueError) as exc:
    print(f"artifact is not readable JSON: {exc}")
    raise SystemExit(1)

gappers = payload.get("gappers")
if not isinstance(gappers, list) or not gappers:
    print("artifact carries no `gappers` list (truncated or partially written scan)")
    raise SystemExit(1)

raw = payload.get("scanned_at")
if not raw:
    print("artifact has no `scanned_at` stamp — cannot prove when it was captured")
    raise SystemExit(1)
try:
    scanned = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
except ValueError:
    print(f"artifact `scanned_at` is unparseable: {raw!r}")
    raise SystemExit(1)
if scanned.tzinfo is None:
    scanned = scanned.replace(tzinfo=timezone.utc)

scanned_et = scanned.astimezone(ZoneInfo("America/New_York")).date().isoformat()
if scanned_et != target:
    print(f"artifact is named {target} but was captured {scanned_et} ET (scanned_at={raw}) "
          "- a stale snapshot under today's name")
    raise SystemExit(1)

age_min = (datetime.now(timezone.utc) - scanned).total_seconds() / 60
if age_min < -5:
    print(f"artifact `scanned_at` is {abs(age_min):.0f} min in the future (clock skew?)")
    raise SystemExit(1)
if age_min > max_age_min:
    print(f"artifact is {age_min:.0f} min old, beyond the {max_age_min} min window "
          "- leftover from an earlier run")
    raise SystemExit(1)

print(f"ok names={len(gappers)} scanned_at={raw} age_min={age_min:.0f}")
PY
)"
# shellcheck disable=SC2181
if [ $? -ne 0 ]; then fail "$validation"; fi

if [ "$DRY_RUN" = "1" ]; then
  log "DRYRUN would publish $BASE ($validation)"
  exit 0
fi

# (6) Publish, then verify the bytes actually landed.
local_sha="$("$PYTHON" -c \
  "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$ARTIFACT")"

scp $SSH_OPTS "$ARTIFACT" workbench:/tmp/ >/dev/null 2>&1 \
  || fail "scp of $BASE to the box failed"
ssh $SSH_OPTS workbench "sudo cp /tmp/'$BASE' '$REMOTE_DIR/'" \
  || fail "remote copy of $BASE into $REMOTE_DIR failed"

remote_sha="$(ssh $SSH_OPTS workbench "sudo sha256sum '$REMOTE_DIR/$BASE' | cut -d' ' -f1" 2>/dev/null)"
if [ "$remote_sha" != "$local_sha" ]; then
  fail "post-copy verification failed for $BASE (local $local_sha != box ${remote_sha:-missing})"
fi

log "synced $BASE -> box ($validation, sha256 ${local_sha:0:12}… verified)"
