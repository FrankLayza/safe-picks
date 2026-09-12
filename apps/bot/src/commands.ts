import type { PaperTradeStatus } from "@safe-picks/contracts";

export interface SafeBetsArgs {
  targetOdds: number;
  maxLegs: number;
}

export function parseSafeBetsArgs(text: string | undefined): SafeBetsArgs {
  const [, target = "3.00", legs = "3"] = text?.trim().split(/\s+/) ?? [];
  const targetOdds = Number(target);
  const maxLegs = Number(legs);
  if (!Number.isFinite(targetOdds) || targetOdds < 1 || !Number.isInteger(maxLegs) || maxLegs < 1 || maxLegs > 8) {
    throw new Error("Usage: /safe_bets <target odds> <max fixtures>\nExample: /safe_bets 3.00 3");
  }
  return { targetOdds, maxLegs };
}

export type SettleScope = { kind: "all"; outcome: PaperTradeStatus } | { kind: "id"; tradeId: string; outcome: PaperTradeStatus };

const OUTCOME_MAP: Record<string, PaperTradeStatus> = {
  win: "settled_win",
  won: "settled_win",
  loss: "settled_loss",
  lost: "settled_loss",
  void: "void",
  vd: "void",
};

/**
 * Parse /settle arguments.
 *
 * Supported forms:
 *   /settle win          → settle all pending for this chat as settled_win
 *   /settle loss
 *   /settle void
 *   /settle <tradeId> win|loss|void  → settle a single trade by ID
 */
export function parseSettleArgs(text: string | undefined): SettleScope {
  const parts = text?.trim().split(/\s+/) ?? [];
  // parts[0] is "/settle", parts[1] is outcome or tradeId, parts[2] is optional outcome
  const [, second, third] = parts;

  if (!second) {
    throw new Error("Usage: /settle win|loss|void  or  /settle <tradeId> win|loss|void");
  }

  // Two-argument form: /settle win|loss|void
  const directOutcome = OUTCOME_MAP[second.toLowerCase()];
  if (directOutcome) return { kind: "all", outcome: directOutcome };

  // Three-argument form: /settle <tradeId> win|loss|void
  if (third) {
    const outcome = OUTCOME_MAP[third.toLowerCase()];
    if (outcome) return { kind: "id", tradeId: second, outcome };
  }

  throw new Error("Unknown outcome. Use: /settle win|loss|void");
}
