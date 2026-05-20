import { apiFetch } from "./client";

export interface Account {
  id: number;
  mode: "paper" | "live";
  status: string;
}

export function getAccount(): Promise<Account> {
  return apiFetch<Account>("/api/v1/account");
}
