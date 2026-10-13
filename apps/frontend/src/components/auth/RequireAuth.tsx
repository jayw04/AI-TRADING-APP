import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authApi, type MeResponse } from "@/api/auth";
import { parseMarketId, type MarketId } from "@/markets/registry";
import { SessionProvider, type SessionUser } from "@/markets/session";

type AuthState =
  | { kind: "unknown" }
  | { kind: "unauthenticated" }
  | { kind: "authenticated"; session: SessionUser };

function grantsFrom(me: MeResponse): MarketId[] {
  const out: MarketId[] = [];
  for (const raw of me.markets ?? []) {
    const id = parseMarketId(raw);
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ kind: "unknown" });
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((me) => {
        if (!cancelled) {
          setState({
            kind: "authenticated",
            session: { user_id: me.user_id, markets: grantsFrom(me) },
          });
        }
      })
      .catch(() => {
        // 401 or network error: fail closed → treat as unauthenticated.
        if (!cancelled) setState({ kind: "unauthenticated" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "unknown") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-950 text-neutral-400">
        Loading…
      </div>
    );
  }
  if (state.kind === "unauthenticated") {
    return (
      <Navigate to="/login" state={{ from: `${location.pathname}${location.search}${location.hash}` }} replace />
    );
  }
  return <SessionProvider value={state.session}>{children}</SessionProvider>;
}
