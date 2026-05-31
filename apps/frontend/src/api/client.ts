// P5 §3: default to a same-origin (relative) base so the session cookie flows.
// In dev, Vite proxies /api → backend; in prod the reverse proxy is same-origin.
// VITE_API_BASE can still point at an absolute origin for cross-origin setups.
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API error ${status}`);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    // Send/receive the session cookie (harmless same-origin; required if a
    // cross-origin VITE_API_BASE is configured).
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiBase(): string {
  return API_BASE;
}
