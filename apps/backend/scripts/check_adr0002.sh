#!/usr/bin/env bash
# check_adr0002.sh
#
# ADR 0002 CI invariant: SINGLE ORDER ENTRY POINT.
#
# "Every order — regardless of which caller initiated it — flows through a
# single OrderRouter module on the backend. There are no exceptions, including
# for the agent." (ADR 0002, Decision)
#
# This is the invariant CLAUDE.md, the risk-engine skill, ADR 0020 and ADR 0021
# have all named `check_adr0002.sh` as enforcing. Until this script landed, the
# only static enforcement was `tests/test_adr_0002_invariant.py`, which runs
# under `pytest` — and `pytest` in this repo is FULL-runs-only
# (`if: github.event_name != 'pull_request'` in .github/workflows/ci.yml). So
# ADR 0002 was the one architectural invariant with NO pull-request-visible
# check, while its twelve siblings all ran on every PR. This script closes that.
#
# ---------------------------------------------------------------------------
# What is actually being defended
# ---------------------------------------------------------------------------
#
# The runtime guard is the `_router_token` tripwire: AlpacaAdapter's mutating
# methods (submit_order / cancel_order / replace_order) take a keyword-only
# `_router_token` and refuse to run without the exact value, and the router is
# meant to be the only module that knows it. That guard is only as good as two
# properties, so this script checks BOTH:
#
#   LEG 1 — no module outside the router originates a broker order call.
#   LEG 2 — no module outside the router/adapter seam knows the router token.
#
# Leg 2 is the one nothing checked before. Leg 1 alone is insufficient: a file
# that has acquired an allowlist entry for some benign reason can later add a
# genuine bypass, and whole-file exemptions are how that happens. Leg 2 means a
# bypass must ALSO smuggle the token out of the router, which cannot be done
# quietly.
#
# ---------------------------------------------------------------------------
# Why receiver-aware matching, not a bare `.submit_order(` grep
# ---------------------------------------------------------------------------
#
# `StrategyContext.submit_order(...)` is the SANCTIONED path — it is bound to
# `OrderRouter.submit`, so `self.ctx.submit_order(...)` in a strategy template
# is ADR 0002 being obeyed, not violated. A bare `.submit_order(` grep cannot
# tell that apart from `adapter.submit_order(...)`, so the previous check
# exempted fourteen whole files to stay green — and a whole-file exemption
# disables the check for that file permanently. (It also went red the moment an
# untracked strategy, `strategies_user/momentum_top5_rotation.py`, used the
# perfectly legitimate context path.)
#
# This script classifies by RECEIVER instead: a call whose receiver is `ctx` or
# ends in `.ctx` is the context pass-through and is fine anywhere. Everything
# else is a direct broker call and is fine only in the router. That removes the
# need for eleven of those fourteen exemptions, so the allowlist below is short
# enough to actually audit.
#
# Known limit, stated rather than hidden: someone could name a broker adapter
# variable `ctx` and slip past leg 1. Leg 2 and the runtime `_router_token`
# tripwire are what stop that — a static grep is a tripwire, not a proof.
#
# If this check fails, the fix is NOT to add the file to an allowlist. It is to
# route the new code path through OrderRouter.submit(). Per ADR 0002: "If the
# router blocks it for a reason that needs overriding, the right answer is to
# make the override an explicit input to the router, not to bypass it."

set -euo pipefail

# Overridable so the negative tests can point the script at a fixture tree.
# Defaults to apps/backend/ when invoked normally.
ROOT="${ADR0002_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../" && pwd)}"

if [ ! -d "$ROOT" ]; then
  echo "ADR 0002 check: root '$ROOT' does not exist."
  exit 1
fi

MUTATORS='submit_order|cancel_order|replace_order'

# A dotted receiver followed by one of the mutators: `adapter.submit_order(`,
# `self.ctx.submit_order(`, `running.instance.ctx.cancel_order(`. Requiring a
# receiver is also what excludes `def submit_order(` definitions — no dot, no
# match — so definitions need no special-casing.
CALL_RE="[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)*\.($MUTATORS)[[:space:]]*\("

# The sanctioned StrategyContext / BacktestContext pass-through.
CTX_RE="(^|\.)ctx\.($MUTATORS)[[:space:]]*\("

# The router token in any form.
TOKEN_RE='ROUTER_TOKEN|_router_token'

# LEG 1 — files permitted to make a direct broker order call.
#   app/orders/router.py            the router: the one legitimate caller
#   app/brokers/alpaca/adapter.py   method bodies; calls the Alpaca SDK client
#   app/brokers/base.py             BrokerAdapter Protocol declarations
#   tests/brokers/...test_adapter.py  tripwire tests MUST call them to prove
#                                     they refuse without the token
#   tests/test_adr_0002_invariant.py  carries the patterns as fixture data
ALLOW_CALL=(
  "app/orders/router.py"
  "app/brokers/alpaca/adapter.py"
  "app/brokers/base.py"
  "tests/brokers/alpaca/test_adapter.py"
  "tests/test_adr_0002_invariant.py"
)

# LEG 2 — files permitted to know the router token. Deliberately even shorter:
# this is the router/adapter seam plus the tests that prove the seam holds.
ALLOW_TOKEN=(
  "app/orders/router.py"
  "app/orders/__init__.py"
  "app/brokers/alpaca/adapter.py"
  "app/brokers/base.py"
  "tests/brokers/alpaca/test_adapter.py"
  "tests/test_adr_0002_invariant.py"
)

in_list() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

FAIL=0

# Scan from inside $ROOT so paths come back as ./app/... — this keeps a Windows
# drive letter out of the output, which matters because the parsing below splits
# grep's `path:lineno:match` on ':'. Two grep processes total, not two per file:
# the per-file version took ~82s on Windows, which is too slow for a check that
# runs on every pull request.
cd "$ROOT"

SCOPE=(--include='*.py'
  --exclude-dir='.venv' --exclude-dir='__pycache__' --exclude-dir='node_modules')

# LEG 1 — direct broker order calls outside the router.
while IFS= read -r line; do
  [ -z "$line" ] && continue
  rel="${line%%:*}"
  rel="${rel#./}"
  rest="${line#*:}"          # lineno:match
  lineno="${rest%%:*}"
  match="${rest#*:}"

  in_list "$rel" "${ALLOW_CALL[@]}" && continue
  # The context pass-through dispatches through OrderRouter. Not a bypass.
  printf '%s' "$match" | grep -Eq "$CTX_RE" && continue

  echo "ADR 0002 VIOLATION (direct broker order call outside OrderRouter): $rel:$lineno: $match"
  FAIL=1
done < <(grep -REno "${SCOPE[@]}" "$CALL_RE" . || true)

# LEG 2 — router-token containment.
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  rel="${rel#./}"
  in_list "$rel" "${ALLOW_TOKEN[@]}" && continue
  echo "ADR 0002 VIOLATION (router-token leak): $rel references the OrderRouter token"
  FAIL=1
done < <(grep -REl "${SCOPE[@]}" "$TOKEN_RE" . || true)

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "ADR 0002 check FAILED — single order entry point violated."
  echo
  echo "Every order must reach the broker through OrderRouter.submit(), which is"
  echo "the single place pre-trade risk checks fire, the Order row is persisted"
  echo "before the broker is called, and the audit row is written with"
  echo "actor_type in {user, strategy, agent}."
  echo
  echo "Do NOT resolve this by adding the file to ALLOW_CALL or ALLOW_TOKEN."
  echo "Route the code path through OrderRouter. If the router blocks it for a"
  echo "reason that needs overriding, make the override an explicit input to the"
  echo "router (ADR 0002, Consequences)."
  echo
  echo "Strategies reach the router via the context: self.ctx.submit_order(...)."
  exit 1
fi

echo "ADR 0002 single-order-entry-point check passed."
exit 0
