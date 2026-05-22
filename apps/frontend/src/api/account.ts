import { apiFetch } from "./client";
import type { Account } from "./types";

export const accountApi = {
  get(): Promise<Account> {
    return apiFetch<Account>("/api/v1/account");
  },
};

// Back-compat for callers that imported the function form.
export function getAccount(): Promise<Account> {
  return accountApi.get();
}

export type { Account };
