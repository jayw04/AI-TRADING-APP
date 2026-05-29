import { apiFetch } from "./client";
import type {
  AgentBudget,
  AgentSessionDetail,
  AgentSessionListResponse,
  AgentSessionMode,
  AgentSessionStatusT,
  AgentSessionSummary,
  AppendMessageResponseT,
} from "./types";

export const agentApi = {
  startSession: (mode: AgentSessionMode = "b2_interactive", model?: string) =>
    apiFetch<AgentSessionSummary>("/api/v1/agent/sessions", {
      method: "POST",
      body: JSON.stringify(model ? { mode, model } : { mode }),
    }),

  listSessions: (params: { status?: AgentSessionStatusT; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.limit) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<AgentSessionListResponse>(`/api/v1/agent/sessions${suffix}`);
  },

  getSession: (id: number) =>
    apiFetch<AgentSessionDetail>(`/api/v1/agent/sessions/${id}`),

  appendMessage: (id: number, text: string) =>
    apiFetch<AppendMessageResponseT>(`/api/v1/agent/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  endSession: (id: number, reason = "user_end") =>
    apiFetch<AgentSessionSummary>(`/api/v1/agent/sessions/${id}/end`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  getBudget: () => apiFetch<AgentBudget>("/api/v1/agent/budget"),
};
