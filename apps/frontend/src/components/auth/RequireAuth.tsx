import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authApi } from "@/api/auth";

type AuthState = "unknown" | "authenticated" | "unauthenticated";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>("unknown");
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then(() => {
        if (!cancelled) setState("authenticated");
      })
      .catch(() => {
        // 401 or network error: fail closed → treat as unauthenticated.
        if (!cancelled) setState("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "unknown") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-950 text-neutral-400">
        Loading…
      </div>
    );
  }
  if (state === "unauthenticated") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}
