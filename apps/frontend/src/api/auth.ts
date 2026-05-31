import { apiFetch } from "./client";

export interface LoginResponse {
  user_id: number;
  email: string;
  display_name: string | null;
}

export interface MeResponse {
  user_id: number;
  email: string;
  display_name: string | null;
  session_id: number | null;
}

export const authApi = {
  login: (email: string, password: string, totp_code: string) =>
    apiFetch<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, totp_code }),
    }),

  logout: () =>
    apiFetch<{ ok: boolean }>("/api/v1/auth/logout", {
      method: "POST",
      body: "{}",
    }),

  me: () => apiFetch<MeResponse>("/api/v1/auth/me"),
};
