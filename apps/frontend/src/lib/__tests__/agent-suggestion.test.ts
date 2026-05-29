import { describe, it, expect } from "vitest";
import { parseSuggestions } from "../agent-suggestion";

describe("parseSuggestions", () => {
  it("parses a single suggestion block", () => {
    const text = `Looking at your positions, here's a thought:

Suggestion: Loosen RSI entry threshold from 30 to 35
Why: The strategy hasn't fired in 5 sessions; current threshold is too tight for the regime.
Confidence: medium`;
    const result = parseSuggestions(text);
    expect(result).toHaveLength(1);
    expect(result[0].suggestion).toContain("Loosen RSI");
    expect(result[0].why).toContain("hasn't fired");
    expect(result[0].confidence).toBe("medium");
  });

  it("returns empty array when no suggestion present", () => {
    expect(parseSuggestions("Just an informational answer.")).toEqual([]);
  });

  it("parses multiple suggestions in one message", () => {
    const text = `Suggestion: A
Why: because A
Confidence: low

Suggestion: B
Why: because B
Confidence: high`;
    const result = parseSuggestions(text);
    expect(result).toHaveLength(2);
    expect(result[0].confidence).toBe("low");
    expect(result[1].confidence).toBe("high");
  });

  it("treats Confidence as case-insensitive", () => {
    const text = `Suggestion: X
Why: x
Confidence: HIGH`;
    expect(parseSuggestions(text)[0].confidence).toBe("high");
  });

  it("rejects unrecognized confidence values (strict regex)", () => {
    const text = `Suggestion: X
Why: x
Confidence: maybe`;
    expect(parseSuggestions(text)).toEqual([]);
  });

  it("is safe to call multiple times (no leaked regex state)", () => {
    const text = `Suggestion: A
Why: y
Confidence: low`;
    expect(parseSuggestions(text)).toHaveLength(1);
    expect(parseSuggestions(text)).toHaveLength(1);
    expect(parseSuggestions(text)).toHaveLength(1);
  });
});
