import { apiFetch } from "./client";
import type {
  Order,
  OrderActionResponse,
  OrderCreateRequest,
  OrderListResponse,
  OrderModifyRequest,
} from "./types";

export type OrderListFilter = "open" | "history" | "all";

export const ordersApi = {
  list(filter: OrderListFilter = "all", symbol?: string): Promise<OrderListResponse> {
    const params = new URLSearchParams();
    if (filter !== "all") params.set("status", filter);
    if (symbol) params.set("symbol", symbol);
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
