import { apiFetch } from "./client";
import type {
  Order,
  OrderActionResponse,
  OrderCreateRequest,
  OrderListResponse,
  OrderModifyRequest,
  OrderSourceType,
} from "./types";

export type OrderListFilter = "open" | "history" | "all";

export interface OrderListOptions {
  filter?: OrderListFilter;
  symbol?: string;
  // P4 §5: server-side scoping by source. ``source_id`` requires
  // ``source_type`` (the backend rejects with 400 otherwise).
  source_type?: OrderSourceType;
  source_id?: string;
  limit?: number;
}

export const ordersApi = {
  list(opts: OrderListOptions = {}): Promise<OrderListResponse> {
    const params = new URLSearchParams();
    const filter = opts.filter ?? "all";
    if (filter !== "all") params.set("status", filter);
    if (opts.symbol) params.set("symbol", opts.symbol);
    if (opts.source_type) params.set("source_type", opts.source_type);
    if (opts.source_id !== undefined) params.set("source_id", opts.source_id);
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return apiFetch<OrderListResponse>(`/api/v1/orders${qs ? `?${qs}` : ""}`);
  },

  get(id: number): Promise<Order> {
    return apiFetch<Order>(`/api/v1/orders/${id}`);
  },

  create(body: OrderCreateRequest): Promise<Order> {
    return apiFetch<Order>("/api/v1/orders", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  cancel(id: number): Promise<OrderActionResponse> {
    return apiFetch<OrderActionResponse>(`/api/v1/orders/${id}`, {
      method: "DELETE",
    });
  },

  modify(id: number, body: OrderModifyRequest): Promise<OrderActionResponse> {
    return apiFetch<OrderActionResponse>(`/api/v1/orders/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
};
