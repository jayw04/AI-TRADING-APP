import { createContext, useContext, type ReactNode } from "react";
import { MARKET_IDS, type MarketId } from "./registry";

export interface SessionUser {
  user_id: number;
  markets: readonly MarketId[];
}

const SessionContext = createContext<SessionUser | null>(null);

export function SessionProvider({ value, children }: { value: SessionUser; children: ReactNode }) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useOptionalSession(): SessionUser | null {
  return useContext(SessionContext);
}

/**
 * Markets this session may open. Tests render the app without a session and keep both markets;
 * the backend is the access check. A real session with an empty grant list sees neither market.
 */
export function useGrantedMarkets(): readonly MarketId[] {
  const session = useContext(SessionContext);
  if (!session) return MARKET_IDS;
  return session.markets;
}
