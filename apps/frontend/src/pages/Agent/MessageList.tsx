import { useState } from "react";
import type {
  AgentMessageContentBlock,
  AgentMessageT,
} from "@/api/types";
import { parseSuggestions, type ParsedSuggestion } from "@/lib/agent-suggestion";

export function MessageList({ messages }: { messages: AgentMessageT[] }) {
  if (messages.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-gray-500">
        No messages yet.
      </div>
    );
  }
  return (
    <>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </>
  );
}

function MessageBubble({ message }: { message: AgentMessageT }) {
  if (message.role === "system") {
    return (
      <div className="text-center text-xs italic text-gray-500">
        {message.content.map((b) => b.text ?? "").join(" ")}
      </div>
    );
  }
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-gray-700 px-3 py-2 text-sm text-white">
          {message.content.map((b, i) => (
            <span key={i}>{b.text}</span>
          ))}
        </div>
      </div>
    );
  }
  if (message.role === "tool_use") {
    const block = message.content[0] as AgentMessageContentBlock | undefined;
    if (!block) return null;
    return <ToolUseInlineCard block={block} />;
  }
  if (message.role === "tool_result") {
    return <ToolResultCard message={message} />;
  }
  // assistant
  return <AssistantBubble message={message} />;
}

function AssistantBubble({ message }: { message: AgentMessageT }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {message.content.map((b, i) => {
          if (b.type === "text" && b.text) {
            return <AssistantTextBlock key={i} text={b.text} />;
          }
          if (b.type === "tool_use") {
            return <ToolUseInlineCard key={i} block={b} />;
          }
          return null;
        })}
      </div>
    </div>
  );
}

function AssistantTextBlock({ text }: { text: string }) {
  const suggestions = parseSuggestions(text);
  if (suggestions.length === 0) {
    return (
      <div className="whitespace-pre-wrap rounded-lg bg-blue-900/40 px-3 py-2 text-sm text-blue-100">
        {text}
      </div>
    );
  }
  // Render the original text muted, then the parsed cards in full color.
  return (
    <div className="space-y-2">
      <div className="whitespace-pre-wrap rounded-lg bg-blue-900/40 px-3 py-2 text-sm text-blue-100 opacity-80">
        {text}
      </div>
      {suggestions.map((s, i) => (
        <SuggestionCard key={i} suggestion={s} />
      ))}
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: ParsedSuggestion }) {
  const conf = suggestion.confidence;
  const confColor =
    conf === "high"
      ? "bg-emerald-700"
      : conf === "medium"
        ? "bg-amber-700"
        : conf === "low"
          ? "bg-gray-700"
          : "bg-gray-800";
  return (
    <div className="rounded-lg border border-amber-700 bg-amber-900/20 p-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase text-amber-300">
          Suggestion
        </div>
        <span
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white ${confColor}`}
        >
          {conf} confidence
        </span>
      </div>
      <div className="mt-1 text-sm text-amber-100">{suggestion.suggestion}</div>
      <div className="mt-1 text-xs italic text-amber-200/80">
        {suggestion.why}
      </div>
    </div>
  );
}

function ToolUseInlineCard({ block }: { block: AgentMessageContentBlock }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800/60 p-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-gray-300">
          🔧 <span className="font-mono">{block.name as string}</span>
        </span>
        <span className="text-gray-500">{open ? "▼" : "▶"}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto text-[10px] text-gray-400">
          {JSON.stringify(block.input, null, 2)}
        </pre>
      )}
    </div>
  );
}

function ToolResultCard({ message }: { message: AgentMessageT }) {
  const [open, setOpen] = useState(false);
  const block = message.content[0] as AgentMessageContentBlock | undefined;
  if (!block) return null;
  const content =
    typeof block.content === "string"
      ? block.content
      : JSON.stringify(block.content);
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800/40 p-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-gray-400">✓ tool result</span>
        <span className="text-gray-500">{open ? "▼" : "▶"}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-[10px] text-gray-400">
          {content.slice(0, 4000)}
          {content.length > 4000 ? "…(truncated)" : ""}
        </pre>
      )}
    </div>
  );
}
