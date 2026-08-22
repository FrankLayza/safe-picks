export interface SafeBetsArgs {
  targetOdds: number;
  maxLegs: number;
}

export function parseSafeBetsArgs(text: string | undefined): SafeBetsArgs {
  const [, target = "3.00", legs = "3"] = text?.trim().split(/\s+/) ?? [];
  const targetOdds = Number(target);
  const maxLegs = Number(legs);
  if (!Number.isFinite(targetOdds) || targetOdds < 1 || !Number.isInteger(maxLegs) || maxLegs < 1 || maxLegs > 8) {
    throw new Error("Usage: /safe_bets <target odds> <max legs>\nExample: /safe_bets 3.00 3");
  }
  return { targetOdds, maxLegs };
}
