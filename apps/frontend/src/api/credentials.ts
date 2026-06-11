import { apiFetch } from "./client";

export interface CredentialMetadata {
  kind: string;
  has_value: boolean;
  created_at: string | null;
  updated_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export const credentialsApi = {
  list: () =>
    apiFetch<CredentialMetadata[]>("/api/v1/users/me/credentials/"),

  set: (kind: string, value: string) =>
    apiFetch<void>(`/api/v1/users/me/credentials/${kind}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),

  revoke: (kind: string) =>
    apiFetch<void>(`/api/v1/users/me/credentials/${kind}`, {
      method: "DELETE",
    }),
};

// Mirror of the backend CredentialKind enum, minus TOTP_SECRET (the auth flow
// owns that; the credentials endpoint refuses it). Labels are human-facing.
export const CREDENTIAL_KINDS: { kind: string; label: string }[] = [
  { kind: "alpaca_paper_key", label: "Alpaca Paper — API Key" },
  { kind: "alpaca_paper_secret", label: "Alpaca Paper — API Secret" },
  { kind: "alpaca_live_key", label: "Alpaca Live — API Key" },
  { kind: "alpaca_live_secret", label: "Alpaca Live — API Secret" },
  { kind: "anthropic_api_key", label: "Anthropic — API Key" },
  { kind: "pine_webhook_secret", label: "TradingView Pine — Webhook Secret" },
  // P5.5 §3: bearer token the workbench-mcp server presents to the backend.
  { kind: "workbench_mcp_key", label: "Workbench MCP — Bearer Key" },
  // P6 §1a: bearer token the agent service presents to the backend HTTP API.
  { kind: "agent_api_key", label: "Agent — API Key" },
];
