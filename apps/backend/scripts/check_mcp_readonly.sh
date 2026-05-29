#!/usr/bin/env bash
# MCP server read-only tripwire (P3 §2): tools registered with the MCP
# server must not have names implying mutation.
#
# P3 ships only read tools. Mutation (submit/cancel/start/stop/create/
# update/delete/etc.) is reserved for P6's B3 autonomous-agent surface.
# Adding a mutating tool before then must be a deliberate, design-
# reviewed change — not an accident.
#
# The check is grep-based and scans Python files under
# apps/mcp-server/src/workbench_mcp/ for tool name="..." declarations.
# Coverage limits:
#   * AST-level reasoning would catch creative naming bypasses; that's a
#     P4 polish. Today's failure mode is *accidental* mutation, not
#     adversarial.
#   * Read-only endpoints can still cause writes server-side
#     (e.g. /opportunities aggregator hits the cache). The tripwire
#     gates the *tool name*, not the tool's network effects.
set -euo pipefail

MUTATION_PATTERNS='(submit|cancel|start|stop|create|update|delete|modify|set|write|post|put|patch)_'
SEARCH_DIR="apps/mcp-server/src/workbench_mcp"

if [[ ! -d "$SEARCH_DIR" ]]; then
  echo "MCP source dir not found: $SEARCH_DIR" >&2
  exit 2
fi

# Find name= "..." declarations in Python files (anywhere in the source
# tree, including server.py's @server.tool(name=...) decorators).
OFFENDERS=$(grep -rEn 'name\s*=\s*"[^"]+"' "$SEARCH_DIR" --include='*.py' \
  | grep -iE "name\s*=\s*\"${MUTATION_PATTERNS}" \
  || true)

if [[ -n "$OFFENDERS" ]]; then
  echo "MCP READ-ONLY VIOLATION — tool name implies mutation:" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "P3 ships read-only tools only. B3 (autonomous trading) is P6." >&2
  exit 1
fi
echo "MCP read-only OK"
