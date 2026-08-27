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
APP_DIR=${MDQ_APP_DIR:-/opt/workbench/app}
# This script's own directory. Used to locate the attestation helper, which must be version-bound to
# the control rather than supplied by whoever runs it.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# --diagnostic: exercise this implementation against a box that predates the attested deployment.
# ⛔ It is NOT a way to make a governed run pass. It can never print a READY verdict, so it cannot be
# mistaken for one in a transcript, and it is labelled NON-GOVERNING in its own banner.
DIAGNOSTIC=0
for arg in "$@"; do
  case "$arg" in
    --diagnostic) DIAGNOSTIC=1 ;;
  esac
done

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

# ---------------------------------------------------------------- gate 6 ----
# DEPLOYMENT/RUNTIME IDENTITY ATTESTATION.
#
# ⚠⚠ THIS GATE IS GOVERNING AND FAIL-CLOSED. There is deliberately NO environment switch that makes
# it "count": a default-off flag is silent degradation by construction — the repair could deploy
# successfully while someone forgets to set it, and this control would go on declaring READY on five
# gates. The gate is mandatory by VERSION: this script is the six-gate control, full stop.
#
# The prospective boundary is preserved by DEPLOYMENT, not by a flag. Until this version is deployed
# the box still runs the five-gate script, so 2026-08-27 remains the five-gate standard without any
# switch existing anywhere.
#
# To exercise this implementation against a legacy box before deployment, use --diagnostic. That mode
# is loudly labelled NON-GOVERNING and can never print a READY verdict, so it cannot be mistaken for,
# or substituted for, a governed run.
#
# This gate proves the build marker, the deploy manifest and the running runtime RECONCILE.
# ⛔ It does NOT prove the commit was organizationally APPROVED: approval is the separate
# governance authorization that selected the immutable SHA, and a build artifact may never be
# its own sanction. The wording here is load-bearing because a PASS line enters a governed
# operational transcript -- it must not assert a fact it never tested.
#
# This is the gate that answers 2026-08-26. Gates 1-5 read the universe pin, credentials, the identity
# latch, disk and process state — NONE of them reads the deployment self-report, which is exactly why a
# rebuilt runtime with stale declarations sailed through a green preflight.
#
# ⛔ The runtime code is read via `docker cp`, NOT `docker exec`. Running the container's own digest
# implementation would be the suspect attesting to itself: a wrong image carries wrong code AND a
# matching self-description. The daemon streams the bytes out; the host hashes them.
gate 6 "DEPLOYMENT/RUNTIME IDENTITY ATTESTATION"
g6_fail=0
g6_note() { note "$1"; g6_fail=1; }
MARKER_FILE="$APP_DIR/DEPLOYED_BUILD_INFO.json"
RUNTIME_MANIFEST="$APP_DIR/DEPLOYMENT_RUNTIME_MANIFEST.json"
# ⛔⛔ NOT OVERRIDABLE. The helper is VERSION-BOUND to this script: it is this script's own sibling, so
# the attestation implementation ships and moves with the control that depends on it.
#
# An earlier revision made this `${MDQ_ATTEST_HELPER:-...}` "only for tests". That was a hole straight
# through Amendment 8: a governed invocation could point the load-bearing host derivation at arbitrary
# code that simply prints the expected digest. The one source that must not be caller-assertable was
# caller-assertable. Tests exercise the real helper via this same resolution.
ATTEST_HELPER="$SCRIPT_DIR/derive_runtime_code_digest_from_tar.py"
# The helper IMPORTS the canonicalization rather than transcribing it, so it needs `app` importable:
# …/apps/backend/scripts/x.py -> …/apps/backend.
ATTEST_PYTHONPATH=$(dirname "$SCRIPT_DIR")

if [ ! -f "$MARKER_FILE" ]; then
  g6_note "A. build marker      : ABSENT at $MARKER_FILE"
else
  m_commit=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print((d.get('commit') or d.get('deployed_repository_commit') or '').strip().lower())" "$MARKER_FILE" 2>/dev/null)
  m_code=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print((d.get('code_digest') or '').strip().lower())" "$MARKER_FILE" 2>/dev/null)
  note "A. build marker      : commit ${m_commit:-<none>} code_digest ${m_code:-<none>}"
  [ -n "$m_commit" ] || g6_note "   -> marker records no commit"
  case "${m_code}" in sha256:*) : ;; *) g6_note "   -> marker records no code_digest (pre-Amendment-8 archive)" ;; esac
fi

if [ ! -f "$RUNTIME_MANIFEST" ]; then
  g6_note "B. deploy manifest   : ABSENT at $RUNTIME_MANIFEST (deploy step did not record what it made)"
else
  d_commit=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('commit',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  d_code=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('code_digest',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  d_image=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('image_digest',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  d_cid=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('container_id',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  d_bhash=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('build_info_sha256',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  d_created=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('container_created',''))" "$RUNTIME_MANIFEST" 2>/dev/null)
  note "B. deploy manifest   : commit ${d_commit:-<none>} image ${d_image:-<none>}"
  # ⭐ The manifest BINDS the marker by hash, not merely by repeating its fields. Without this, a valid
  # marker from one attempt and a valid manifest from another could be paired and every field-by-field
  # comparison would still agree. The binding makes that pairing detectable.
  if [ -f "$MARKER_FILE" ]; then
    a_bhash=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$MARKER_FILE" 2>/dev/null)
    note "   marker binding    : manifest=${d_bhash:-<none>} actual=${a_bhash:-<none>}"
    if [ -z "$d_bhash" ]; then
      g6_note "   -> manifest does not bind the build marker (build_info_sha256 absent)"
    elif [ "$d_bhash" != "$a_bhash" ]; then
      g6_note "   MISMATCH: the deploy manifest was written against a DIFFERENT build marker"
    fi
  fi
fi

r_cid=$(docker inspect --format '{{.Id}}' "$CONTAINER" 2>/dev/null || echo "")
r_image=$(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null || echo "")
r_created=$(docker inspect --format '{{.Created}}' "$CONTAINER" 2>/dev/null || echo "")
if [ -z "$r_cid" ]; then
  g6_note "C. running container : NOT FOUND ($CONTAINER)"
  r_code=""
elif [ ! -f "$ATTEST_HELPER" ]; then
  g6_note "C. host attestation  : helper absent at $ATTEST_HELPER"
  r_code=""
else
  r_code=$(docker cp "$CONTAINER":/app/app - 2>/dev/null | PYTHONPATH="$ATTEST_PYTHONPATH" python3 "$ATTEST_HELPER" 2>&1) || {
    g6_note "C. host attestation  : FAILED - $r_code"
    r_code=""
  }
  [ -n "$r_code" ] && note "C. running runtime   : container $(echo "$r_cid" | cut -c1-12) image $r_image"
  [ -n "$r_code" ] && note "   host-derived code : $r_code"
fi

# The conjunction. Each clause names what disagreed, because "Gate 6 failed" is not actionable.
if [ -f "$MARKER_FILE" ] && [ -f "$RUNTIME_MANIFEST" ]; then
  [ "$m_commit" = "$d_commit" ] || g6_note "   MISMATCH: build-marker commit $m_commit != deploy-manifest commit $d_commit"
  [ "$m_code" = "$d_code" ]     || g6_note "   MISMATCH: build code_digest != deploy-manifest code_digest"
fi
if [ -n "$r_code" ] && [ -f "$RUNTIME_MANIFEST" ]; then
  [ "$d_code" = "$r_code" ] || g6_note "   MISMATCH: deploy-manifest code_digest != HOST-DERIVED running code"
  [ "$d_image" = "$r_image" ] || g6_note "   MISMATCH: deploy-manifest image != running image (unrecorded rebuild)"
  [ "$d_cid" = "$r_cid" ] || g6_note "   MISMATCH: deploy-manifest container != running container (unrecorded recreation)"
  # The creation timestamp is recorded, so it is reconciled. Container id already catches a
  # recreation; comparing the stamp too is what makes the "full tuple" claim literally true rather
  # than aspirational, and it catches a manifest transplanted from a different container's lifetime.
  if [ -n "$d_created" ] || [ -n "$r_created" ]; then
    [ "$d_created" = "$r_created" ] || g6_note "   MISMATCH: deploy-manifest container_created $d_created != running $r_created"
  fi
fi
# .deploy_src_sha is a CORROBORATING declaration only. It may never again be sufficient by itself --
# on 2026-08-26 it read "unchanged" while the runtime had already moved.
if [ -f "$DEPLOY_SHA_FILE" ] && [ -f "$RUNTIME_MANIFEST" ]; then
  legacy=$(cat "$DEPLOY_SHA_FILE" 2>/dev/null | tr -d '[:space:]')
  if [ "$legacy" != "$d_commit" ]; then
    g6_note "   MISMATCH: legacy .deploy_src_sha $legacy != deploy-manifest commit $d_commit"
  fi
fi

if [ "$g6_fail" -eq 0 ] && [ -n "$r_code" ]; then
  note "RESULT: PASS - build marker == deploy manifest == running runtime"
else
  note "RESULT: FAIL - the deployment tuple does not reconcile"
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
if [ "$DIAGNOSTIC" -eq 1 ]; then
  echo "=== DIAGNOSTIC (NON-GOVERNING) - this invocation CANNOT establish readiness ==="
  if [ "$fail" -eq 0 ]; then
    echo "    all six gates would pass, but a diagnostic run is not readiness evidence"
  else
    echo "    at least one gate would fail-close"
  fi
elif [ "$fail" -eq 0 ]; then
  echo "=== READY - all six gates pass ==="
else
  echo "=== NOT READY - at least one gate would fail-close. Do not assume which. ==="
fi
exit "$fail"
