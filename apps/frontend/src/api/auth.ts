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

export interface LoginConfig {
  totp_required: boolean;
}

export const authApi = {
  // totp_code is omitted from the body when not provided so a password-only
  // login works when the backend has WORKBENCH_LOGIN_TOTP_REQUIRED=false.
  login: (email: string, password: string, totp_code?: string) =>
    apiFetch<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(
        totp_code ? { email, password, totp_code } : { email, password },
      ),
    }),

  loginConfig: () => apiFetch<LoginConfig>("/api/v1/auth/login-config"),

  logout: () =>
    apiFetch<{ ok: boolean }>("/api/v1/auth/logout", {
      method: "POST",
      body: "{}",
    }),

  me: () => apiFetch<MeResponse>("/api/v1/auth/me"),
};
