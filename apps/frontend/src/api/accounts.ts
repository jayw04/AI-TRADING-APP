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
  // P5 §7: LIVE creation requires a TOTP code (re-verified server-side).
  create: (broker: string, mode: BrokerModeT, label: string, totpCode?: string) =>
    apiFetch<BrokerAccount>("/api/v1/accounts", {
      method: "POST",
      body: JSON.stringify({
        broker,
        mode,
        label,
        ...(totpCode ? { totp_code: totpCode } : {}),
      }),
    }),
};
