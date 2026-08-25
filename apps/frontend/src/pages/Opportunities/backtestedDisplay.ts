/**
 * Opportunity listing rule: only names whose evidence status is a completed
 * backtest / validated pattern. Watch and Backtest Pending remain computed
 * on the research plane; they are not listed.
 */
export function isPatternValidatedStatus(status: string): boolean {
  return status.startsWith("Source: MOM-001");
}

export const HIDDEN_UNBACKTESTED =
  "Watch and Backtest Pending names are not listed until they have gone through backtest.";
