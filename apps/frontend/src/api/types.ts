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

// ===== Strategies =====

export type StrategyType = "python" | "pine" | "agent";
export type StrategyStatus = "idle" | "backtest" | "paper" | "live" | "halted" | "error";

export const ACTIVE_STRATEGY_STATUSES: ReadonlyArray<StrategyStatus> = ["paper", "live"];

// P4 §7: optional UI-form schema declared on the strategy class. Lives in
// code, not the DB — surfaced fresh on the detail endpoint. ``null`` means
// the strategy didn't declare one; the Params tab falls back to JSON.
export type ParamFieldType = "integer" | "number" | "string" | "boolean" | "enum";

export interface ParamFieldSpec {
  type: ParamFieldType;
  default?: number | string | boolean;
  description?: string;
  min?: number;
  max?: number;
  step?: number;
  max_length?: number;
  choices?: string[]; // for enum
}

export type ParamsSchema = Record<string, ParamFieldSpec>;

export interface Strategy {
  id: number;
  name: string;
  version: string;
  type: StrategyType;
  status: StrategyStatus;
  code_path: string | null;
  params: Record<string, unknown>;
  symbols: string[];
  schedule: string;
  risk_limits_id: number | null;
  error_text: string | null;
  // P4 §7. Populated only on detail endpoint responses.
  params_schema?: ParamsSchema | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyListResponse {
  items: Strategy[];
  count: number;
}

export interface StrategyCreateRequest {
  name: string;
  version?: string;
  type?: StrategyType;
  code_path?: string;
  params?: Record<string, unknown>;
  symbols?: string[];
  schedule?: string;
  risk_limits_id?: number | null;
}

export interface StrategyUpdateRequest {
  params?: Record<string, unknown>;
  symbols?: string[];
  schedule?: string;
  risk_limits_id?: number | null;
  version?: string;
}

export interface StrategyActionResponse {
  strategy_id: number;
  action: "start" | "stop";
  new_status: StrategyStatus;
  run_id: number | null;
}

// ===== Strategy runs =====

export interface StrategyRun {
  id: number;
  strategy_id: number;
  started_at: string;
  ended_at: string | null;
  status: StrategyStatus;
  error_text: string | null;
}

export interface StrategyRunListResponse {
  items: StrategyRun[];
  count: number;
}

// ===== Signals =====

export type SignalTypeT = "entry" | "exit" | "flat" | "info" | "agent_action" | "pine_alert";

export interface Signal {
  id: number;
  strategy_id: number | null;
  symbol: string;
  type: SignalTypeT;
  payload: Record<string, unknown>;
  received_at: string;
  processed_at: string | null;
}

export interface SignalListResponse {
  items: Signal[];
  count: number;
}

// ===== Backtests =====

export interface BacktestRequest {
  start: string;                            // ISO datetime
  end: string;
  label?: string;
  initial_equity?: string;                  // Decimal as string
  slippage_bps?: number;
  commission_per_share?: number;
  timeframe?: string;
  params?: Record<string, unknown>;
  symbols?: string[];
}

export interface BacktestMetricsT {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trade_count: number;
  avg_win: number;
  avg_loss: number;
  avg_trade_duration_seconds: number;
  starting_equity: number;
  ending_equity: number;
}

export interface BacktestTradeT {
  symbol: string;
  side: "long" | "short";
  entry_ts: string;
  entry_price: number;
  exit_ts: string | null;
  exit_price: number | null;
  qty: number;
  pnl: number | null;
  duration_seconds: number | null;
  exit_reason: string | null;
}

export interface EquityPointT {
  t: string;
  equity: number;
}

export interface BacktestResult {
  id: number;
  strategy_id: number;
  label: string;
  params: Record<string, unknown>;
  metrics: BacktestMetricsT;
  equity_curve: EquityPointT[];
  trades: BacktestTradeT[];
  range_start: string;
  range_end: string;
  created_at: string;
}

export interface BacktestSummary {
  id: number;
  strategy_id: number;
  label: string;
  metrics: BacktestMetricsT;
  range_start: string;
  range_end: string;
  created_at: string;
}

export interface BacktestListResponse {
  items: BacktestSummary[];
  count: number;
}

// ===== Backtest jobs (P4 §2) =====

export type BacktestJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface BacktestJob {
  id: number;
  user_id: number;
  strategy_id: number;
  result_id: number | null;
  status: BacktestJobStatus;
  label: string;
  percent_complete: number;
  current_ts: string | null;
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_text: string | null;
}

export interface BacktestJobSubmittedResponse {
  job_id: number;
  strategy_id: number;
  status: BacktestJobStatus;
  submitted_at: string;
}
