/**
 * Mirrors of backend Pydantic schemas in apps/backend/app/api/v1/schemas/.
 *
 * Decimal fields are serialized by Pydantic v2 as JSON strings, so we type
 * them as `string` here. Convert with `Number(x)` / `parseFloat(x)` only at
 * the rendering edge — never store the parsed number, since it loses
 * precision for prices.
 */

export type OrderSide = "buy" | "sell";

export type OrderType = "market" | "limit" | "stop" | "stop_limit";

export type TimeInForce = "day" | "gtc" | "ioc" | "fok";

export type OrderStatus =
  | "pending_risk"
  | "pending_submit"
  | "submitted"
  | "partially_filled"
  | "filled"
  | "canceled"
  | "expired"
  | "rejected"
  | "replaced";

export const TERMINAL_ORDER_STATUSES: ReadonlySet<OrderStatus> = new Set<OrderStatus>([
  "filled",
  "canceled",
  "expired",
  "rejected",
  "replaced",
]);

export type OrderSourceType =
  | "manual"
  | "strategy"
  | "agent_strategy"
  | "agent_proposal"
  | "pine";

export interface Fill {
  id: number;
  broker_fill_id: string | null;
  qty: string;
  price: string;
  commission: string;
  filled_at: string;
}

export interface RiskCheckSummary {
  id: number;
  decision: "pass" | "reject" | string;
  reason_codes: string[];
  evaluated_at: string;
}

export interface Order {
  id: number | null; // null for ephemeral rejections (e.g. SYMBOL_DENIED)
  broker_order_id: string | null;
  client_order_id: string | null;
  symbol: string;
  side: OrderSide;
  qty: string;
  type: OrderType;
  limit_price: string | null;
  stop_price: string | null;
  tif: TimeInForce;
  extended_hours: boolean;
  status: OrderStatus;
  rejection_reason: string | null;
  source_type: OrderSourceType;
  source_id: string | null;
  created_at: string;
  submitted_at: string | null;
  terminal_at: string | null;
  updated_at: string;
  fills: Fill[];
  risk_check: RiskCheckSummary | null;
}

export interface OrderListResponse {
  items: Order[];
  count: number;
}

export interface OrderCreateRequest {
  symbol: string;
  side: OrderSide;
  qty: string;
  type: OrderType;
  limit_price?: string | null;
  stop_price?: string | null;
  tif: TimeInForce;
  extended_hours?: boolean;
  client_order_id?: string | null;
}

export interface OrderModifyRequest {
  new_qty?: string | null;
  new_limit_price?: string | null;
}

export interface OrderActionResponse {
  order_id: number;
  requested_action: "cancel" | "modify";
  accepted_by_broker: boolean;
}

export interface Position {
  id: number;
  symbol: string;
  qty: string;
  avg_entry_price: string;
  side: "long" | "short" | null;
  market_value: string;
  cost_basis: string;
  unrealized_pl: string;
  unrealized_plpc: string;
  updated_at: string;
}

export interface PositionListResponse {
  items: Position[];
  count: number;
  gross_exposure: string;
  net_exposure: string;
  total_unrealized_pl: string;
}

export interface Account {
  account_id: number;
  mode: "paper" | "live" | string;
  status: string;
  cash: string;
  equity: string;
  last_equity: string;
  buying_power: string;
  portfolio_value: string;
  day_change: string;
  day_change_pct: string;
  daytrade_count: number;
  pattern_day_trader: boolean;
  trading_blocked: boolean;
  account_blocked: boolean;
  updated_at: string;
}

export interface Quote {
  symbol: string;
  bid: string | null;
  ask: string | null;
  last: string | null;
  bid_size: number | null;
  ask_size: number | null;
  ts: string | null;
  source: string;
}
