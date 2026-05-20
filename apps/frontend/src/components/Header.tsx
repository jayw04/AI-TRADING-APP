export default function Header() {
  return (
    <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-950">
      <div className="text-sm text-neutral-400">P0 — scaffolding</div>
      <span
        role="status"
        aria-label="Trading mode"
        className="inline-flex items-center gap-2 rounded-full bg-paper-500/15 border border-paper-500/40 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-paper-400"
      >
        <span className="size-2 rounded-full bg-paper-400" />
        PAPER
      </span>
    </header>
  );
}
