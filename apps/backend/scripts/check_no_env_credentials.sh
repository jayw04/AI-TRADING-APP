#!/bin/bash
# check_no_env_credentials.sh
#
# P5 §4 invariant (the eighth): no production code path may read broker keys,
# Anthropic keys, or auth secrets from environment variables. The only allowed
# env-var read for these names is in app/security/ (the credential store
# itself) and in alembic/versions/ (the data migration). alembic lives outside
# app/, so the ROOT scope already excludes it.
#
# Mirrors check_strategy_isolation.sh + check_broker_isolation.sh: a grep-level
# invariant that catches drift between PRs.

set -e

ROOT="apps/backend/app"

# The credential names we care about.
NAMES="ALPACA_API_KEY|ALPACA_API_SECRET|ALPACA_PAPER_API_KEY|ALPACA_PAPER_API_SECRET|ALPACA_LIVE_API_KEY|ALPACA_LIVE_API_SECRET|ANTHROPIC_API_KEY|PINE_WEBHOOK_SECRET"

# os.environ.get("NAME"...) or os.environ["NAME"] for these.
PATTERN="os\\.environ\\[?(\\.get)?\\(?[\"'](${NAMES})[\"']"

# Allow-list: the security package (the credential store may read the master
# key + names there). alembic/versions/ is outside $ROOT so already excluded.
VIOLATIONS=$(find "$ROOT" -name "*.py" \
  -not -path "${ROOT}/security/*" \
  -exec grep -lE "$PATTERN" {} \; 2>/dev/null || true)

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: env-var reads of credential names found outside app/security/."
    echo ""
    for f in $VIOLATIONS; do
        echo "  $f:"
        grep -nE "$PATTERN" "$f" | sed 's/^/    /'
    done
    echo ""
    echo "These names must be read via app.security.credential_store.CredentialStore."
    echo "If you genuinely need an env-var fallback, write an ADR first."
    exit 1
fi

echo "Credential env-isolation invariant OK"
exit 0
