/**
 * Parser for the agent's B2 `Suggestion: / Why: / Confidence:` block.
 *
 * The agent's B2 system prompt instructs it to emit suggestions in this
 * exact format so the UI can render each one as an action card. We do a
 * best-effort regex extraction — if the model deviates from the format
 * the message just renders as regular text. We do NOT enforce structure
 * on the model: too brittle.
 *
 * Strict by design: `Confidence:` must match `low | medium | high`
 * exactly (case-insensitive). Anything else fails the regex and the
 * whole block is skipped.
 */

export type SuggestionConfidence = "low" | "medium" | "high" | "unknown";

export interface ParsedSuggestion {
  suggestion: string;
  why: string;
  confidence: SuggestionConfidence;
}

const SUGGESTION_RE =
  /Suggestion:\s*([^\n]+)\s*\n\s*Why:\s*([\s\S]+?)\s*\n\s*Confidence:\s*(low|medium|high)/gi;

export function parseSuggestions(text: string): ParsedSuggestion[] {
  const out: ParsedSuggestion[] = [];
  // exec with global flag advances lastIndex between calls
  SUGGESTION_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = SUGGESTION_RE.exec(text)) !== null) {
    const conf = (m[3] ?? "").toLowerCase();
    const confidence: SuggestionConfidence =
      conf === "low" || conf === "medium" || conf === "high" ? conf : "unknown";
    out.push({
      suggestion: m[1].trim(),
      why: m[2].trim(),
      confidence,
    });
  }
  return out;
}
