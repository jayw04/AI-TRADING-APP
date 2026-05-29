import { useState, type KeyboardEvent } from "react";

interface Props {
  onSend: (text: string) => Promise<void>;
  disabled?: boolean;
}

export function MessageComposer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    setText("");
    await onSend(trimmed);
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className="flex items-end gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKey}
        disabled={disabled}
        rows={2}
        placeholder="Ask about positions, strategies, or market data. Enter to send, Shift+Enter for newline."
        className="flex-1 resize-y rounded bg-gray-800 px-3 py-2 text-sm text-white disabled:opacity-50"
      />
      <button
        type="button"
        onClick={() => void handleSend()}
        disabled={disabled || !text.trim()}
        className="rounded bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:bg-gray-700"
      >
        {disabled ? "…" : "Send"}
      </button>
    </div>
  );
}
