import { apiFetch } from "./client";
import type {
  BrokerAccount,
  BrokerAccountListResponse,
  BrokerModeT,
} from "./types";

/**
 * Plural accounts API (P5 §1) — lists the user's broker account rows and their
 * broker_mode. Distinct from `account.ts` (singular), which returns the live
 * AccountState snapshot for the active paper account.
 */
export const accountsApi = {
  list: () => apiFetch<BrokerAccountListResponse>("/api/v1/accounts"),
  create: (broker: string, mode: BrokerModeT, label: string) =>
    apiFetch<BrokerAccount>("/api/v1/accounts", {
      method: "POST",
      body: JSON.stringify({ broker, mode, label }),
    }),
};
