import { authApi } from "@/api/auth";

export default function Header() {
  async function handleLogout() {
    try {
      await authApi.logout();
    } catch {
      // Ignore: we redirect to /login regardless so a dead session still clears.
    }
    window.location.href = "/login";
  }

  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-950">
      <div className="text-sm text-neutral-400">Trading Workbench</div>
      <div className="flex items-center gap-4">
        <span className="text-[11px] text-neutral-500">P1 · risk-gated orders</span>
        <button
          type="button"
          onClick={handleLogout}
          className="text-xs text-neutral-400 hover:text-white"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
