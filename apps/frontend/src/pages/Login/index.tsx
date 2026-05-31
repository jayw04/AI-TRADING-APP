import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as { from?: string } | null)?.from || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await authApi.login(email, password, totp);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setError("Too many login attempts. Wait a few minutes and try again.");
        } else if (err.status === 403) {
          setError("TOTP not set up — contact your admin or run scripts/create_user.py.");
        } else {
          setError("Invalid credentials.");
        }
      } else {
        setError("Login failed. Check the backend is running.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950">
      <form
        onSubmit={handleSubmit}
        className="w-96 space-y-3 rounded-lg border border-neutral-800 bg-neutral-900 p-6"
      >
        <h1 className="text-lg font-semibold text-white">Trading Workbench</h1>
        <p className="text-xs text-neutral-400">Sign in to continue.</p>

        <div>
          <label className="block text-xs text-neutral-400" htmlFor="login-email">
            Email
          </label>
          <input
            id="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
          />
        </div>

        <div>
          <label className="block text-xs text-neutral-400" htmlFor="login-password">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 text-sm text-white"
          />
        </div>

        <div>
          <label className="block text-xs text-neutral-400" htmlFor="login-totp">
            TOTP code
          </label>
          <input
            id="login-totp"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={totp}
            onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
            required
            maxLength={8}
            autoComplete="one-time-code"
            className="mt-1 w-full rounded bg-neutral-800 px-2 py-1 font-mono text-sm text-white"
          />
        </div>

        {error && (
          <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-neutral-700"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <div className="border-t border-neutral-800 pt-3 text-[10px] text-neutral-500">
          First-time setup uses{" "}
          <code className="rounded bg-neutral-800 px-1">scripts/create_user.py</code> on the
          server.
        </div>
      </form>
    </div>
  );
}
