import { apiFetch } from "./client";

export interface LiveAutodispatchState {
  enabled: boolean;
}

export const liveAutodispatchApi = {
  status: () =>
    apiFetch<LiveAutodispatchState>(`/api/v1/system/live-autodispatch`),

  set: (enabled: boolean, totp_code: string) =>
    apiFetch<LiveAutodispatchState>(`/api/v1/system/live-autodispatch`, {
      method: "POST",
      body: JSON.stringify({ enabled, totp_code }),
    }),
};
