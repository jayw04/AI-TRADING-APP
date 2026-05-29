import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageList } from "../MessageList";
import type {
  AgentMessageContentBlock,
  AgentMessageRoleT,
  AgentMessageT,
} from "@/api/types";

function msg(over: Partial<AgentMessageT> = {}): AgentMessageT {
  return {
    id: 1,
    session_id: 1,
    role: "user",
    content: [{ type: "text", text: "hi" }] as AgentMessageContentBlock[],
    input_tokens: null,
    output_tokens: null,
    model: null,
    ts: new Date().toISOString(),
    parent_message_id: null,
    ...over,
  };
}

describe("MessageList", () => {
  it("renders user message text", () => {
    render(<MessageList messages={[msg({ role: "user" as AgentMessageRoleT })]} />);
    expect(screen.getByText("hi")).toBeInTheDocument();
  });

  it("renders assistant text", () => {
    render(
      <MessageList
        messages={[
          msg({
            id: 2,
            role: "assistant",
            content: [{ type: "text", text: "hello back" }],
          }),
        ]}
      />,
    );
    expect(screen.getByText("hello back")).toBeInTheDocument();
  });

  it("extracts and renders a Suggestion card from assistant text", () => {
    const text = `Sure.

Suggestion: Loosen RSI to 35
Why: Strategy hasn't fired in a week.
Confidence: medium`;
    render(
      <MessageList
        messages={[
          msg({
            id: 3,
            role: "assistant",
            content: [{ type: "text", text }],
          }),
        ]}
      />,
    );
    // Suggestion text appears twice by design: once in the muted full
    // message, once highlighted in the SuggestionCard.
    expect(screen.getAllByText(/Loosen RSI to 35/)).toHaveLength(2);
    expect(screen.getByText(/medium confidence/i)).toBeInTheDocument();
  });

  it("renders system message as italic", () => {
    render(
      <MessageList
        messages={[
          msg({
            id: 4,
            role: "system",
            content: [{ type: "text", text: "Session ended" }],
          }),
        ]}
      />,
    );
    const el = screen.getByText("Session ended");
    expect(el.className).toContain("italic");
  });

  it("renders an empty state when no messages", () => {
    render(<MessageList messages={[]} />);
    expect(screen.getByText(/No messages/i)).toBeInTheDocument();
  });

  it("renders an assistant tool_use block inline", () => {
    render(
      <MessageList
        messages={[
          msg({
            id: 5,
            role: "assistant",
            content: [
              {
                type: "tool_use",
                id: "tu_1",
                name: "list_positions",
                input: {},
              } as AgentMessageContentBlock,
            ],
          }),
        ]}
      />,
    );
    expect(screen.getByText("list_positions")).toBeInTheDocument();
  });
});
