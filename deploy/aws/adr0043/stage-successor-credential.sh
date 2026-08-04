#!/usr/bin/env bash
# ADR 0043 WS5 successor — Stage B checkpoint B4: owner-controlled credential entry.
#
# Deployed to the governed runtime as /opt/adr0043/bin/stage-successor-credential.
#
# WHY THIS EXISTS. B4 requires staging the dedicated successor credential and
# verifying its fingerprints WITHOUT broker access. Every unattended channel is
# closed to us: §5 prohibits broadening the instance role, so the runtime cannot
# read Parameter Store; `ssm send-command` retains command text in SSM history and
# on disk under /var/lib/amazon/ssm/...; and secrets must never reach shell
# arguments, CI variables, PR bodies or an agent-controlled terminal. What remains
# is an interactive owner session, which is what this script is for. It is the
# narrow secret-entry checkpoint and nothing else.
#
# WHAT IT DOES NOT DO. No broker call. No container. No database. No IAM, network,
# role, volume, scheduler or strategy change. It writes one 0600 root-owned file
# and one non-secret receipt. `verify` writes nothing at all: a failing check
# reports B4_VERIFICATION_FAILED and leaves the staged file exactly as it found it,
# because remediation is not within this checkpoint's authorization.
#
#   stage    prompt for the credential, verify fingerprints, write atomically
#   verify   recompute everything from the staged file and report; no secrets out
#
# The staged file is consumed by `docker run --env-file`, which parses KEY=VALUE
# literally with no shell interpretation. Values are therefore written RAW.
# ⚠ Never `source` this file — raw values are not shell-quoted by design.

set -euo pipefail

# Ranges in glob character classes and `sort` order are locale-sensitive. Pin the
# locale so the accepted-character guard means the same thing on every host.
export LC_ALL=C

# --- governed constants -------------------------------------------------------
# Fingerprints and names are copied from the effective authorization and from
# app/brokers/adr0043_reconcile.py. The fingerprint ALGORITHM is that module's
# _fingerprint(): sha256 hex, truncated to 12. Do not substitute another scheme.
readonly EXPECTED_KEY_FP='ffab8796516a'
readonly EXPECTED_SECRET_FP='c2cab6509f1b'
readonly ENV_KEY='ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY'
readonly ENV_SECRET='ADR0043_SUCCESSOR_CANARY_ALPACA_API_SECRET'
readonly AUTHORIZATION_SHA='9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8'
readonly EXPECTED_INSTANCE='i-0fff7076ad461aa9a'

# NON-SECRET. The account binding is governed by §8 configuration and is
# deliberately NOT staged into the credential file — that file carries secret
# material only. `verify` resolves the §8 value and refuses to agree with
# anything but this account.
readonly EXPECTED_ACCOUNT_ID='PA3E97RWHKQZ'
readonly ENV_ACCOUNT='ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID'
readonly ENV_ACCOUNT_SETTING='WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID'

readonly CREDENTIAL_DIR='/etc/adr0043'
readonly CREDENTIAL_FILE="${CREDENTIAL_DIR}/successor-canary.env"
readonly RECEIPT_DIR='/var/lib/adr0043'
readonly RECEIPT_FILE="${RECEIPT_DIR}/B4_CREDENTIAL_STAGED"

umask 077

die() { printf '%s\n' "$*" >&2; exit 1; }

# sha256 hex truncated to 12 — app/brokers/adr0043_reconcile.py::_fingerprint
# printf is a bash builtin and sha256sum reads stdin, so no credential value ever
# reaches a process argument list.
fp() { printf '%s' "$1" | sha256sum | awk '{print substr($1,1,12)}'; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die 'must run as root (use sudo)'
}

# Refuse to run on the wrong host. An account-identity or resource-identity
# mismatch is a §10 mechanical stop condition; this is the cheap early check.
require_instance() {
  local tok id
  tok="$(curl -fsS -X PUT 'http://169.254.169.254/latest/api/token' \
          -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
  [ -n "$tok" ] || die 'cannot read instance metadata (IMDSv2 unavailable)'
  id="$(curl -fsS -H "X-aws-ec2-metadata-token: $tok" \
          'http://169.254.169.254/latest/meta-data/instance-id' 2>/dev/null || true)"
  [ "$id" = "$EXPECTED_INSTANCE" ] \
    || die "wrong instance: ${id:-<unknown>} != ${EXPECTED_INSTANCE}; nothing staged"
}

# Strict accepted-character validation.
#
# The env-file format is line-oriented KEY=VALUE with NO shell interpretation, so
# the hazard is not injection but silent corruption: a newline splits the entry, a
# '=' moves the key/value boundary, and quotes or backslashes are carried verbatim
# INTO the credential. Shell escaping would be actively wrong here — it would embed
# the escape characters in the value — so the guard is an accepted-character
# allowlist instead, refusing rather than normalising. The explicit cases come
# first so the owner gets an actionable message rather than a generic one.
#
# NUL is covered structurally rather than by a pattern: a bash variable cannot
# hold NUL and `read` discards it, so no NUL can reach this function — and a
# literal `*$'\0'*` case would be a trap, because $'\0' expands to the EMPTY
# string and the pattern would degrade to `**`, rejecting every value.
validate_value() {
  local name="$1" value="$2"
  [ -n "$value" ] || die "${name}: empty; nothing staged"
  case "$value" in
    *$'\n'*|*$'\r'*)          die "${name}: contains a newline or carriage return; nothing staged" ;;
    ' '*|*' '|$'\t'*|*$'\t')  die "${name}: has leading or trailing whitespace; nothing staged" ;;
    *=*)                      die "${name}: contains '='; nothing staged" ;;
    # Separate alternatives, not a bracket class: in a case pattern `[\'\"\\]`
    # loses its quoting to quote removal and the trailing backslash escapes the
    # closing bracket. The backslash alternative must be single-quoted for the
    # same reason — `*\\*` collapses to a literal asterisk.
    *\'*|*\"*|*'\'*)          die "${name}: contains a quote or backslash; nothing staged" ;;
    *[!A-Za-z0-9._~/+-]*)     die "${name}: contains an unaccepted character; nothing staged" ;;
  esac
}

cmd_stage() {
  require_root
  require_instance

  local api_key api_secret key_fp secret_fp tmp
  # Prompt on the controlling terminal with echo disabled. Never an argument,
  # never an environment variable, never stdin from a pipe.
  [ -r /dev/tty ] || die 'no controlling terminal; run this in an interactive session'

  read -r -s -p 'Successor API key: '    api_key    </dev/tty; printf '\n' >/dev/tty
  read -r -s -p 'Successor API secret: ' api_secret </dev/tty; printf '\n' >/dev/tty

  # Scrub on every exit path, including the failures below.
  trap 'unset api_key api_secret' EXIT

  validate_value 'api key'    "$api_key"
  validate_value 'api secret' "$api_secret"

  key_fp="$(fp "$api_key")"
  secret_fp="$(fp "$api_secret")"

  if [ "$key_fp" != "$EXPECTED_KEY_FP" ] || [ "$secret_fp" != "$EXPECTED_SECRET_FP" ]; then
    # Report WHICH side failed, never the value or the computed fingerprint of a
    # wrong secret — a mismatching fingerprint is still derived from key material.
    printf 'FINGERPRINT MISMATCH: key=%s secret=%s; nothing staged.\n' \
      "$([ "$key_fp" = "$EXPECTED_KEY_FP" ] && echo ok || echo BAD)" \
      "$([ "$secret_fp" = "$EXPECTED_SECRET_FP" ] && echo ok || echo BAD)" >&2
    exit 1
  fi

  install -d -o root -g root -m 0700 "$CREDENTIAL_DIR"

  # Atomic: write to a temp file in the SAME directory, fix mode and ownership
  # before it is visible under the real name, then rename.
  tmp="$(mktemp "${CREDENTIAL_DIR}/.successor-canary.XXXXXX")"
  trap 'rm -f "$tmp"; unset api_key api_secret' EXIT
  chown root:root "$tmp"
  chmod 0600 "$tmp"
  # Raw values: docker --env-file does not perform shell interpretation.
  printf '%s=%s\n' "$ENV_KEY"    "$api_key"    >"$tmp"
  printf '%s=%s\n' "$ENV_SECRET" "$api_secret" >>"$tmp"
  mv -f "$tmp" "$CREDENTIAL_FILE"
  trap 'unset api_key api_secret' EXIT

  unset api_key api_secret

  install -d -o root -g root -m 0700 "$RECEIPT_DIR"
  {
    printf 'checkpoint=B4\n'
    printf 'result=B4_PASS\n'
    printf 'credential_file=%s\n'        "$CREDENTIAL_FILE"
    printf 'credential_file_mode=%s\n'   "$(stat -c '%a' "$CREDENTIAL_FILE")"
    printf 'credential_file_owner=%s\n'  "$(stat -c '%U:%G' "$CREDENTIAL_FILE")"
    printf 'credential_names=%s,%s\n'    "$ENV_KEY" "$ENV_SECRET"
    printf 'key_fingerprint=%s\n'        "$key_fp"
    printf 'secret_fingerprint=%s\n'     "$secret_fp"
    printf 'fingerprint_algorithm=%s\n'  'sha256_hex_truncated_12'
    printf 'authorization_sha=%s\n'      "$AUTHORIZATION_SHA"
    printf 'instance_id=%s\n'            "$EXPECTED_INSTANCE"
    printf 'broker_access_performed=%s\n' 'false'
    printf 'container_created=%s\n'      'false'
    printf 'staged_at=%s\n'              "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$RECEIPT_FILE"
  chown root:root "$RECEIPT_FILE"
  chmod 0600 "$RECEIPT_FILE"

  echo 'B4_PASS: successor credential staged and fingerprints verified.'
}

# Recompute from the staged file so continuation depends on the credential itself
# rather than on trusting a receipt that could be stale or hand-written. The
# receipt is supporting evidence; THIS result is authoritative.
#
# `verify` is read-only by construction: it makes no broker request, creates no
# container, and never rewrites or deletes the credential file. A failed check
# leaves remediation to a separate, explicitly authorized action.
cmd_verify() {
  require_root
  require_instance  # instance binding must match the effective authorization

  local mode owner names dups n key_fp secret_fp dirmode key_val secret_val
  local receipt account_resolved account_source rc=0

  [ -f "$CREDENTIAL_FILE" ] || die 'B4_NOT_STAGED: credential file absent'

  mode="$(stat -c '%a' "$CREDENTIAL_FILE")"
  owner="$(stat -c '%U:%G' "$CREDENTIAL_FILE")"
  dirmode="$(stat -c '%a' "$CREDENTIAL_DIR")"
  n="$(grep -c . "$CREDENTIAL_FILE" || true)"
  names="$(cut -d= -f1 "$CREDENTIAL_FILE" | sort | paste -sd, -)"
  dups="$(cut -d= -f1 "$CREDENTIAL_FILE" | sort | uniq -d | paste -sd, -)"

  # Values stay in shell variables and are compared with builtin pattern matching
  # only — they are never passed as an argument to an external process.
  key_val="$(grep "^${ENV_KEY}=" "$CREDENTIAL_FILE" | cut -d= -f2- || true)"
  secret_val="$(grep "^${ENV_SECRET}=" "$CREDENTIAL_FILE" | cut -d= -f2- || true)"
  key_fp="$(fp "$key_val")"
  secret_fp="$(fp "$secret_val")"

  # §8 account binding. Non-secret, and deliberately outside the credential file.
  if [ -n "${!ENV_ACCOUNT:-}" ]; then
    account_resolved="${!ENV_ACCOUNT}"; account_source="$ENV_ACCOUNT"
  elif [ -n "${!ENV_ACCOUNT_SETTING:-}" ]; then
    account_resolved="${!ENV_ACCOUNT_SETTING}"; account_source="$ENV_ACCOUNT_SETTING"
  else
    account_resolved=''; account_source='UNRESOLVED'
  fi

  printf 'credential_file_mode=%s\n'         "$mode"
  printf 'credential_file_owner=%s\n'        "$owner"
  printf 'credential_dir_mode=%s\n'          "$dirmode"
  printf 'credential_line_count=%s\n'        "$n"
  printf 'credential_names=%s\n'             "$names"
  printf 'duplicate_names=%s\n'              "${dups:-none}"
  printf 'key_fingerprint_matches=%s\n'      "$([ "$key_fp"    = "$EXPECTED_KEY_FP" ]    && echo true || echo false)"
  printf 'secret_fingerprint_matches=%s\n'   "$([ "$secret_fp" = "$EXPECTED_SECRET_FP" ] && echo true || echo false)"
  printf 'account_id_source=%s\n'            "$account_source"
  printf 'account_id_matches_authorized=%s\n' "$([ "$account_resolved" = "$EXPECTED_ACCOUNT_ID" ] && echo true || echo false)"
  printf 'broker_access_performed=%s\n'      'false'
  printf 'container_created=%s\n'            'false'

  [ "$mode"  = '600' ]       || { echo 'FAIL: mode is not 0600' >&2; rc=1; }
  [ "$owner" = 'root:root' ] || { echo 'FAIL: owner is not root:root' >&2; rc=1; }
  [ "$(( 8#$dirmode & 8#077 ))" -eq 0 ] \
    || { echo 'FAIL: credential directory is group- or world-accessible' >&2; rc=1; }
  [ "$n"     = '2' ]         || { echo 'FAIL: file does not contain exactly two entries' >&2; rc=1; }
  [ -z "$dups" ]             || { echo 'FAIL: duplicate credential keys present' >&2; rc=1; }
  [ "$names" = "$(printf '%s\n%s\n' "$ENV_KEY" "$ENV_SECRET" | sort | paste -sd, -)" ] \
    || { echo 'FAIL: unexpected credential names present' >&2; rc=1; }
  [ "$key_fp"    = "$EXPECTED_KEY_FP" ]    || { echo 'FAIL: key fingerprint mismatch' >&2; rc=1; }
  [ "$secret_fp" = "$EXPECTED_SECRET_FP" ] || { echo 'FAIL: secret fingerprint mismatch' >&2; rc=1; }

  # The account binding must resolve through §8 configuration and agree with the
  # authorized account. Absent or disagreeing is a stop, never a default.
  [ "$account_resolved" = "$EXPECTED_ACCOUNT_ID" ] \
    || { echo 'FAIL: §8 account binding absent or disagrees with the authorized account' >&2; rc=1; }
  # ...and it must not have been smuggled into the credential file, which carries
  # secret material only.
  ! grep -q "^${ENV_ACCOUNT}=" "$CREDENTIAL_FILE" \
    || { echo 'FAIL: account id present in the credential file' >&2; rc=1; }

  # Receipt cross-check. Supporting evidence only — every assertion above was
  # recomputed independently of it.
  if [ -f "$RECEIPT_FILE" ]; then
    receipt="$(cat "$RECEIPT_FILE")"
    case "$receipt" in
      *"$key_val"*|*"$secret_val"*)
        echo 'FAIL: a credential value appears in the receipt' >&2; rc=1 ;;
    esac
    grep -qx "authorization_sha=${AUTHORIZATION_SHA}" "$RECEIPT_FILE" \
      || { echo 'FAIL: receipt authorization_sha does not match the effective authorization' >&2; rc=1; }
    grep -qx "instance_id=${EXPECTED_INSTANCE}" "$RECEIPT_FILE" \
      || { echo 'FAIL: receipt instance_id does not match the adopted instance' >&2; rc=1; }
    grep -qx 'broker_access_performed=false' "$RECEIPT_FILE" \
      || { echo 'FAIL: receipt does not assert that no broker request was made' >&2; rc=1; }
    grep -qx 'container_created=false' "$RECEIPT_FILE" \
      || { echo 'FAIL: receipt does not assert that no container was created' >&2; rc=1; }
  else
    echo 'FAIL: staging receipt absent' >&2; rc=1
  fi

  if [ "$rc" -eq 0 ]; then
    echo 'B4_VERIFY_PASS'
  else
    echo 'B4_VERIFICATION_FAILED (nothing was rewritten or deleted)' >&2
  fi
  return "$rc"
}

case "${1:-}" in
  stage)  cmd_stage ;;
  verify) cmd_verify ;;
  *)      die "usage: $(basename "$0") {stage|verify}" ;;
esac
