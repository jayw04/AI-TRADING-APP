import { useEffect, useRef, useState } from "react";
import type { AgentSessionDetail } from "@/api/types";
import { MessageList } from "./MessageList";
import { MessageComposer } from "./MessageComposer";

interface Props {
  session: AgentSessionDetail;
  onSend: (text: string) => Promise<void>;
  onEnd: () => Promise<void>;
}

export function ChatPanel({ session, onSend, onEnd }: Props) {
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session.messages.length]);

  const isActive = session.status === "active";

  async function handleSend(text: string) {
    setSending(true);
    try {
      await onSend(text);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-gray-800 bg-gray-950 px-4 py-2">
        <div>
          <div className="text-sm font-semibold text-white">
            Session #{session.id}
            <span className="ml-2 text-xs text-gray-500">
              {session.mode === "b1_readonly" ? "Read-only" : "Interactive"} ·{" "}
              {session.model}
            </span>
          </div>
          {session.status !== "active" && (
            <div className="mt-0.5 text-xs text-amber-400">
              Session {session.status}
              {session.end_reason ? `: ${session.end_reason}` : ""}
            </div>
          )}
        </div>
        {isActive && (
          <button
            type="button"
            onClick={() => void onEnd()}
            className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-600"
          >
            End session
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        <MessageList messages={session.messages} />
      </div>

      {isActive ? (
        <div className="border-t border-gray-800 p-3">
          <MessageComposer onSend={handleSend} disabled={sending} />
        </div>
      ) : (
        <div className="border-t border-gray-800 p-3 text-center text-xs text-gray-500">
          Session is {session.status}. Start a new one to continue.
        </div>
      )}
    </>
  );
}
