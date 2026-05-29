import type { AgentSessionSummary } from "@/api/types";

interface Props {
  sessions: AgentSessionSummary[];
  currentId: number | null;
  onSelect: (id: number) => void;
}

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-700 text-emerald-100",
  ended: "bg-gray-700 text-gray-200",
  capped: "bg-amber-700 text-amber-100",
  error: "bg-rose-700 text-rose-100",
};

export function SessionList({ sessions, currentId, onSelect }: Props) {
  if (sessions.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <div className="p-3 text-xs text-gray-500">No sessions yet.</div>
      </div>
    );
  }
  return (
    <div className="flex-1 overflow-y-auto">
      {sessions.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelect(s.id)}
          className={`w-full border-b border-gray-800 p-3 text-left hover:bg-gray-900 ${
            currentId === s.id ? "bg-gray-900" : ""
          }`}
        >
          <div className="flex items-center justify-between">
            <span
              className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                STATUS_BADGE[s.status] ?? "bg-gray-700 text-gray-200"
              }`}
            >
              {s.status}
            </span>
            <span className="text-[10px] text-gray-500">
              {s.mode === "b1_readonly" ? "B1" : "B2"}
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-400">
            {new Date(s.started_at).toLocaleString()}
          </div>
          <div className="mt-0.5 text-[10px] text-gray-500">
            {s.message_count} msg · ${parseFloat(s.total_cost_usd).toFixed(4)}
          </div>
        </button>
      ))}
    </div>
  );
}
