#!/bin/sh
# MDQ-001 acquisition-readiness preflight (READ-ONLY operational control).
#
# WHY THIS EXISTS
# ---------------
# 2026-08-24 capture non-event. The 2026-08-23 deploy rewrote the backend
# environment file and dropped the registered account-7 acquisition
# credentials. The free-space leg was checked that morning and PASSED with a
# 16 GiB margin; the 09:25 ET sampler still died three seconds after start
# with "acquisition creds absent". A single-leg check does not establish
# readiness, and the collector's five approved code blobs stayed byte-identical
# throughout -- code-identity conformance does not prove operational readiness.
#
# This reproduces the collector's ACTUAL gate chain, in order:
#
#   1. universe pin
#   2. acquisition credential presence / non-empty
#   3. account-identity latch readiness (fingerprint + broker account)
#   4. free-space floor
#   5. single-instance state
#
# Run before every governed slot, and ALWAYS after any deployment that
# recreates the collector's container.
#
# READ-ONLY: opens no partition, writes no bytes under the capture root,
# mutates nothing. It never repairs; it reports.
#
# SECRETS: a key or secret is NEVER printed. Credentials are reported only as
# SET/ABSENT plus length. The 12-hex key fingerprint IS printed -- the
# collector's own docstring records that form as safe for manifests and logs
# ("reveals nothing recoverable about the key").
#
# EXIT: 0 = every gate ready. 1 = at least one gate would fail-close.
# A non-zero exit is the fail-closed signal, not a broken script. Under
# AWS-RunShellScript that surfaces as STATUS=Failed; read the gate lines.

# Paths are overridable so the control can be exercised in tests. The governed
# universe pin is NOT overridable: weakening it to make the preflight pass
# would defeat the control it implements.
ROOT_HOST=${MDQ_ROOT_HOST:-/opt/workbench/data}
CONTAINER=${MDQ_CONTAINER:-workbench-backend}
DEPLOY_SHA_FILE=${MDQ_DEPLOY_SHA_FILE:-/opt/workbench/app/.deploy_src_sha}
ENV_FILE=${MDQ_ENV_FILE:-/opt/workbench/.env}

UNIVERSE_SHA=0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4

UNIVERSE_HOST=$ROOT_HOST/mdq_config/mdq_phase_a_universe_symbols.json
HOLDOUT_HOST=$ROOT_HOST/mdq_config/mdq_phase_a_holdout.json

fail=0
note() { echo "  $1"; }
gate() { echo; echo "[$1] $2"; }

# sha256 of a file, first field only. GNU sha256sum switches to "escaped
# filename" form and prefixes the WHOLE LINE with a backslash when the path
# contains a backslash or newline; strip it, or a perfectly valid artifact
# reports a false pin mismatch.
sha_of() {
  _line=$(sha256sum "$1")
  _hash=${_line%% *}
  printf '%s' "${_hash#\\}"
}

echo "=== MDQ-001 ACQUISITION-READINESS PREFLIGHT (read-only) ==="
echo "UTC $(date -u +%FT%TZ)"
echo "target slot: 09:25 ET"

# ---------------------------------------------------------------- gate 1 ----
gate 1 "UNIVERSE PIN"
if [ ! -f "$UNIVERSE_HOST" ]; then
  note "RESULT: FAIL - universe artifact absent at $UNIVERSE_HOST"
  fail=1
else
  got=$(sha_of "$UNIVERSE_HOST")
  note "expected $UNIVERSE_SHA"
  note "actual   $got"
  if [ "$got" = "$UNIVERSE_SHA" ]; then
    note "RESULT: PASS"
  else
    note "RESULT: FAIL - pin mismatch"
    fail=1
  fi
fi
if [ -f "$HOLDOUT_HOST" ]; then
  note "holdout artifact present, sha256 $(sha_of "$HOLDOUT_HOST")"
else
  note "WARN: holdout artifact absent - from_config verification is a deployment prerequisite"
fi

# ---------------------------------------------------------------- gate 2 ----
gate 2 "ACQUISITION CREDENTIAL PRESENCE (names/lengths only - never values)"
cred_state=$(docker exec "$CONTAINER" sh -c '
for v in ALPACA_PAPER_6_API_KEY ALPACA_PAPER_6_API_SECRET; do
  eval "val=\$$v"
  if [ -n "$val" ]; then echo "$v SET ${#val}"; else echo "$v ABSENT"; fi
done' 2>&1)
echo "$cred_state" | while read -r line; do note "$line"; done
creds_ok=1
if echo "$cred_state" | grep -q ABSENT; then
  creds_ok=0
fi
if [ "$creds_ok" -eq 1 ]; then
  note "RESULT: PASS"
else
  note "RESULT: FAIL - the collector exits 'acquisition creds absent' before acquiring"
  note "        DO NOT substitute the unnumbered ALPACA_PAPER_* pair. Account 7's"
  note "        entitled acquisition identity is deliberate; substituting it is a"
  note "        governance change, not an operational repair."
  fail=1
fi

# ---------------------------------------------------------------- gate 3 ----
gate 3 "ACCOUNT-IDENTITY LATCH READINESS (fail-closed fingerprint + broker account)"
if [ "$creds_ok" -eq 0 ]; then
  note "RESULT: NOT EVALUABLE - gate 2 failed; the latch cannot be resolved without credentials"
  fail=1
else
  latch=$(docker exec "$CONTAINER" python -c '
import os, sys
sys.path.insert(0, "/app")
from app.research.capture.identity import AcquisitionPins, key_fingerprint, verify_identity
p = AcquisitionPins()
k = os.environ.get(p.cred_env_key); s = os.environ.get(p.cred_env_secret)
print("pinned_fingerprint", p.key_fingerprint)
print("pinned_account", p.account_number)
print("resolved_fingerprint", key_fingerprint(k))
try:
    print("latch PASS", verify_identity(k, s, p))
except Exception as e:
    print("latch FAIL", type(e).__name__, str(e)[:200])
' 2>&1)
  echo "$latch" | while read -r line; do note "$line"; done
  if echo "$latch" | grep -q "latch PASS"; then
    note "RESULT: PASS"
  else
    note "RESULT: FAIL - resolved credential is not the pinned acquisition identity"
    fail=1
  fi
fi

# ---------------------------------------------------------------- gate 4 ----
# Reproduces the DEPLOYED wrapper arithmetic exactly. Do NOT "clean this up"
# into a byte comparison: whole-GiB rounding IS the deployed contract, and
# `df -B1G` rounds UP. Both units are reported so the next reader does not
# reverse-engineer the rounding again.
gate 4 "FREE-SPACE FLOOR  max(10 GiB, size_gb/5), whole GiB, df rounds UP"
size_gb=$(df -B1G --output=size "$ROOT_HOST" | tail -1 | tr -d ' ')
avail_gb=$(df -B1G --output=avail "$ROOT_HOST" | tail -1 | tr -d ' ')
size_b=$(df -B1 --output=size "$ROOT_HOST" | tail -1 | tr -d ' ')
avail_b=$(df -B1 --output=avail "$ROOT_HOST" | tail -1 | tr -d ' ')
floor=$(( size_gb / 5 ))
if [ "$floor" -lt 10 ]; then floor=10; fi
thresh=$(( (floor - 1) * 1073741824 ))
note "guard integers : size_gb=$size_gb avail_gb=$avail_gb floor=$floor"
note "raw bytes      : size=$size_b avail=$avail_b"
note "fails iff       avail_bytes <= $thresh"
if [ "$avail_gb" -lt "$floor" ]; then
  note "RESULT: FAIL - floor breach"
  fail=1
else
  note "RESULT: PASS - margin $(( avail_gb - floor )) GiB"
fi

# ---------------------------------------------------------------- gate 5 ----
gate 5 "SINGLE-INSTANCE STATE"
n=$(pgrep -fc "mdq_collector.py.*sample" 2>/dev/null)
[ -n "$n" ] || n=0
note "running sample collectors: $n"
if [ "$n" -eq 0 ]; then
  note "RESULT: PASS"
else
  note "RESULT: FAIL - a conflicting sampler is already running"
  fail=1
fi

# ------------------------------------------------------------- context ------
echo
echo "=== CONTEXT (not gates) ==="
[ -f "$DEPLOY_SHA_FILE" ] && note "deployed sha : $(cat "$DEPLOY_SHA_FILE")"
[ -f "$ENV_FILE" ] && note "env file     : $(stat -c '%y  %s B' "$ENV_FILE" 2>/dev/null)"
note "backend image: $(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null)"
note "container    : created $(docker inspect --format '{{.Created}}' "$CONTAINER" 2>/dev/null)"
if command -v systemctl >/dev/null 2>&1; then
  echo "  timers:"
  systemctl list-timers --all 2>/dev/null | grep -i mdq | sed 's/^/    /'
fi
if [ -f "$ROOT_HOST/mdq_capture_alerts.log" ]; then
  echo "  recent alerts:"
  tail -3 "$ROOT_HOST/mdq_capture_alerts.log" | sed 's/^/    /'
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "=== READY - all five gates pass ==="
else
  echo "=== NOT READY - at least one gate would fail-close. Do not assume which. ==="
fi
exit "$fail"
