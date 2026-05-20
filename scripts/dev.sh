#!/usr/bin/env bash
# Bring up the Trading Workbench dev stack (backend + mcp-server + frontend).
#
#   ./scripts/dev.sh            # build (if needed) and run in foreground
#   ./scripts/dev.sh -d         # detached
#   ./scripts/dev.sh down       # stop and remove
#   ./scripts/dev.sh logs -f    # tail combined logs
#
# Any args are passed through to `docker compose`.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> Created .env from .env.example. Edit it with real Alpaca creds when you reach P1."
fi

if [ "${1:-}" = "down" ] || [ "${1:-}" = "logs" ] || [ "${1:-}" = "ps" ]; then
  exec docker compose "$@"
fi

exec docker compose up --build "$@"
