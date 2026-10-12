#!/usr/bin/env bash
# PU-1 presentation-gate tripwire (Personal-Use Data Presentation Rule).
#
# Three structural properties, so the rule is enforced by mechanism rather than reviewer diligence:
#
#   A. The licensing package is a LEAF: app/licensing imports no order-path module.
#   B. The order path never imports app.licensing (labeling/export only; it must not be able to
#      influence what is submitted).
#   C. No document/chart/deck rendering library is imported anywhere outside app/licensing. Any
#      future presentation exporter must therefore be added through (and reviewed against) the
#      gated seam in app/licensing/output.py, not bolted on beside it. If you need such a library,
#      route the export through app.licensing.export_for_external_use and amend this allowlist in
#      the same reviewed change.
#
# Run from the repository root (same convention as check_altdata_order_path_isolation.sh).
set -euo pipefail

ORDER_PATH_IMPORT='(from|import)[[:space:]]+app\.(orders|risk|brokers|services\.order_router)([.[:space:]]|$)'
LICENSING_IMPORT='(from|import)[[:space:]]+app\.licensing([.[:space:]]|$)|from[[:space:]]+app[[:space:]]+import[[:space:]]+licensing'
RENDER_LIBS='(pptx|docx|reportlab|weasyprint|fpdf|fpdf2|xhtml2pdf|pdfkit|matplotlib|plotly|kaleido|openpyxl|xlsxwriter)'
RENDER_IMPORT="^[[:space:]]*(from|import)[[:space:]]+${RENDER_LIBS}([.[:space:]]|\$)"

FAIL=0

if [[ -d apps/backend/app/licensing ]]; then
  HIT=$(grep -rEn "$ORDER_PATH_IMPORT" apps/backend/app/licensing --include='*.py' || true)
  if [[ -n "$HIT" ]]; then
    echo "PU-1 VIOLATION (A): app/licensing imports the order path:" >&2
    echo "$HIT" >&2
    FAIL=1
  fi
fi

for p in apps/backend/app/orders apps/backend/app/risk apps/backend/app/brokers \
         apps/backend/app/services/order_router.py; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$LICENSING_IMPORT" "$p" --include='*.py' || true)
  if [[ -n "$HIT" ]]; then
    echo "PU-1 VIOLATION (B): order path imports app.licensing:" >&2
    echo "$HIT" >&2
    FAIL=1
  fi
done

for root in apps/backend/app apps/backend/scripts scripts apps/agent apps/mcp-server apps/mcp-workbench; do
  [[ -d "$root" ]] || continue
  HIT=$(grep -rEn "$RENDER_IMPORT" "$root" --include='*.py' \
        | grep -v "^apps/backend/app/licensing/" | grep -v "/tests/" || true)
  if [[ -n "$HIT" ]]; then
    echo "PU-1 VIOLATION (C): presentation/chart rendering library imported outside the gated seam:" >&2
    echo "$HIT" >&2
    FAIL=1
  fi
done

if [[ "$FAIL" -ne 0 ]]; then
  echo "" >&2
  echo "Personal-use data may not reach a presentation path. Route exports through" >&2
  echo "app.licensing.export_for_external_use (reason code PU1_PERSONAL_SCOPE_BLOCKED); there is no override." >&2
  exit 1
fi
echo "PU-1 presentation-gate invariant OK"
