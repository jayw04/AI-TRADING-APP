/**
 * Plain-English copy for backend RiskEngine reason codes.
 *
 * Mirror of app/risk/reason_codes.py::ReasonCode. Unknown codes pass through
 * unchanged so a new backend code is visible (if ugly) until we update this
 * map.
 */

export const RISK_REASON_DESCRIPTIONS: Record<string, string> = {
  OK: "Approved",
  MODE_MISMATCH: "Account is in a different trading mode (paper vs. live).",
  SYMBOL_DENIED: "Symbol is not allowed for trading.",
  SHORT_NOT_ALLOWED: "Shorting is disabled for this account.",
  POSITION_CAP_QTY: "Order would exceed the per-symbol share limit.",
  POSITION_CAP_NOTIONAL: "Order would exceed the per-symbol dollar limit.",
  GROSS_EXPOSURE: "Order would exceed the total exposure limit.",
  HALT_REACHED: "Trading is halted (daily loss cap or operator stop).",
  RATE_LIMIT: "Too many orders sent in the last minute.",
  INVALID_INPUT: "Order has an invalid field (qty / limit / stop price).",
  NO_LIMITS_CONFIGURED: "No risk limits are configured for this account.",
  MARKET_SESSION_CLOSED:
    "Market is closed for this order (outside regular hours, or extended-hours trading not enabled).",
};

export function describeReason(code: string): string {
  return RISK_REASON_DESCRIPTIONS[code] ?? code;
}

export function describeReasons(codes: readonly string[]): string {
  if (codes.length === 0) return "Rejected";
  return codes.map(describeReason).join(" ");
}
