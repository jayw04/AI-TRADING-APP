#!/usr/bin/env bash
# Explicit market-data feed pinning (Strategy proposals v1.4.1 §3.1/§3.4).
#
# Alpaca's data layer resolves the "best available" feed when none is named, so a
# subscription entitlement (Algo Trader Plus) can silently switch an implicit IEX
# path to SIP with no code change. Governed paths must therefore:
#
#   1. pass an explicit, non-None `feed=` to every Alpaca data request/stream
#      constructor (checked by AST, so multi-line calls are handled); and
#   2. never read a feed default from the environment (the retired
#      ALPACA_DATA_FEED knob must not reappear).
#
# Which feed a governed path names (iex vs sip) is a §3.3 migration/governance
# question, NOT this check's concern — this check only forbids implicitness.
# Exploratory notebooks are out of scope; anything under the scanned trees is not.
#
# Disabling this requires an ADR. Prefer a clean checkout (ADR 0051 check pattern).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"

"$PYTHON" - <<'PY'
import ast
import sys
from pathlib import Path

SCAN_TREES = [
    "apps/backend/app",
    "apps/backend/scripts",
    "scripts/research",
]

# Alpaca data request/stream constructors that accept a feed. Matched by bare
# name so aliased imports are still caught.
FEED_CONSTRUCTORS = {
    "StockBarsRequest",
    "StockQuotesRequest",
    "StockTradesRequest",
    "StockLatestQuoteRequest",
    "StockLatestTradeRequest",
    "StockLatestBarRequest",
    "StockSnapshotRequest",
    "StockDataStream",
    "OptionBarsRequest",
    "OptionTradesRequest",
    "OptionChainRequest",
    "OptionSnapshotRequest",
    "OptionLatestQuoteRequest",
    "OptionDataStream",
}

# Env-driven feed defaults are forbidden in any form.
FORBIDDEN_LITERALS = ("ALPACA_DATA_FEED", "alpaca_data_feed")

offenders: list[str] = []

def call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None

for tree in SCAN_TREES:
    base = Path(tree)
    if not base.exists():
        continue
    for path in sorted(base.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lit in FORBIDDEN_LITERALS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if lit in line:
                    offenders.append(
                        f"{path}:{lineno}: env-driven feed default "
                        f"('{lit}') — feed must be pinned in code"
                    )
        try:
            module = ast.parse(text)
        except SyntaxError as exc:
            offenders.append(f"{path}: unparseable ({exc})")
            continue
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node)
            if name not in FEED_CONSTRUCTORS:
                continue
            feed_kw = next((k for k in node.keywords if k.arg == "feed"), None)
            if feed_kw is None:
                offenders.append(
                    f"{path}:{node.lineno}: {name}(...) without explicit feed= "
                    f"— provider/entitlement default forbidden"
                )
            elif isinstance(feed_kw.value, ast.Constant) and feed_kw.value.value is None:
                offenders.append(
                    f"{path}:{node.lineno}: {name}(feed=None) — explicit non-None "
                    f"feed required"
                )

if offenders:
    print("MARKET-DATA FEED-PINNING VIOLATION (Strategy proposals v1.4.1 §3.1/§3.4):",
          file=sys.stderr)
    for o in offenders:
        print(f"  {o}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Every governed Alpaca data request/stream must name feed= explicitly;",
          file=sys.stderr)
    print("no environment or entitlement may choose feed semantics.", file=sys.stderr)
    sys.exit(1)

print("Market-data feed pinning OK")
PY

# The retired knob must not reappear in env templates either.
if grep -nE '^[[:space:]]*ALPACA_DATA_FEED=' .env.example 2>/dev/null; then
  echo "MARKET-DATA FEED-PINNING VIOLATION: .env.example re-advertises the retired" >&2
  echo "ALPACA_DATA_FEED knob (feed is pinned in code; see header of this script)." >&2
  exit 1
fi

echo "Feed-pinning invariant OK"
