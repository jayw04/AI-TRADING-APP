#!/usr/bin/env bash
# Research-plane broker-capability limit (ADR 0051 Decision 3).
#
# Phase 1A (in-process): research-plane *code* must not import the Alpaca *trading*
# SDK or hold broker-mutation capability tokens. (The shared backend process still
# carries credentials the *core* needs; this check denies research *code* the
# capability, not the process.)
#
# Phase 2 (separate deployable): this script will additionally assert the research
# worker image/env ships no Alpaca trading SDK and no broker credentials. That
# block is gated on apps/research-worker/ existing.
#
# Disabling this requires an ADR. Prefer a clean checkout (ADR 0051 Decision 7).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

# Trading SDK / trading client imports — market-data-only paths are not the concern;
# alpaca.trading* is the mutation surface.
TRADING_SDK_PATTERN='(from|import)[[:space:]]+alpaca\.trading|from[[:space:]]+alpaca[[:space:]]+import[[:space:]].*TradingClient|TradingClient\('

SEARCH_PATHS=(
  "apps/backend/app/research"
  "apps/backend/app/factor_data"
  "apps/backend/app/altdata"
)

OFFENDERS=""
for p in "${SEARCH_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$TRADING_SDK_PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

if [[ -n "${OFFENDERS//[$'\n']/}" ]]; then
  echo "RESEARCH-PLANE BROKER-CAPABILITY VIOLATION — research-plane code imports the" >&2
  echo "Alpaca trading SDK (ADR 0051 Decision 3):" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Research-plane code is structurally denied broker mutation. Market data may be" >&2
  echo "read via core read-models / factor stores; never via alpaca.trading*." >&2
  exit 1
fi

# MDQ acquisition package HTTP boundary (MDQ-001 registration §7 control 1
# hardening, 2026-08-15): app/research/capture performs raw HTTP for exactly ONE
# purpose — the read-only GET /v2/account identity latch. Because raw HTTP could
# otherwise grow into trading capability, the boundary is structural: no
# mutating HTTP verbs, and no /v2/ endpoint literal other than /v2/account.
CAPTURE_DIR="apps/backend/app/research/capture"
if [[ -d "$CAPTURE_DIR" ]]; then
  CAP_HITS=""
  HIT=$(grep -rEn '(httpx|requests)\.(post|put|delete|patch)\(|\.request\([[:space:]]*["'"'"'](POST|PUT|DELETE|PATCH)' \
        "$CAPTURE_DIR" --include='*.py' || true)
  [[ -n "$HIT" ]] && CAP_HITS+="$HIT"$'\n'
  HIT=$(grep -rEn '/v2/[a-zA-Z_/]+' "$CAPTURE_DIR" --include='*.py' | grep -v '/v2/account' || true)
  [[ -n "$HIT" ]] && CAP_HITS+="$HIT"$'\n'
  if [[ -n "${CAP_HITS//[$'\n']/}" ]]; then
    echo "MDQ CAPTURE HTTP-BOUNDARY VIOLATION — app/research/capture may only" >&2
    echo "GET /v2/account (identity latch) plus market-data SDK calls; no mutating" >&2
    echo "HTTP verbs or other /v2/ trading endpoints (ADR 0051 / MDQ-001 §7):" >&2
    echo "$CAP_HITS" >&2
    exit 1
  fi
  echo "MDQ capture HTTP boundary OK"
fi

# Phase 2 deployable (when present): no trading SDK in its dependency lock / no
# broker credential env keys in its compose/env templates.
WORKER_DIR="apps/research-worker"
if [[ -d "$WORKER_DIR" ]]; then
  WORKER_HITS=""
  if [[ -f "$WORKER_DIR/pyproject.toml" ]]; then
    HIT=$(grep -nE 'alpaca-py|alpaca\.trading' "$WORKER_DIR/pyproject.toml" || true)
    [[ -n "$HIT" ]] && WORKER_HITS+="$WORKER_DIR/pyproject.toml:"$'\n'"$HIT"$'\n'
  fi
  for f in "$WORKER_DIR"/.env* "$WORKER_DIR"/docker-compose*.yml "$WORKER_DIR"/**/*.env.example; do
    [[ -e "$f" ]] || continue
    HIT=$(grep -nE 'ALPACA_(API_KEY|SECRET_KEY|KEY_ID)|APCA_API_KEY' "$f" || true)
    [[ -n "$HIT" ]] && WORKER_HITS+="$f:"$'\n'"$HIT"$'\n'
  done
  if [[ -n "${WORKER_HITS}" ]]; then
    echo "RESEARCH-WORKER BROKER-CAPABILITY VIOLATION — Phase-2 research deployable" >&2
    echo "must not ship Alpaca trading SDK or broker credentials (ADR 0051):" >&2
    echo "$WORKER_HITS" >&2
    exit 1
  fi
  echo "Research-worker Phase-2 broker-capability check OK"
fi

echo "Research-plane no-broker-capability OK"
