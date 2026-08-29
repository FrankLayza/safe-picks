import type { DraftSlip, MarketCandidate } from "@safe-picks/contracts";

function percent(value: number): string { return `${(value * 100).toFixed(1)}%`; }

export function formatCandidate(candidate: MarketCandidate): string {
  return `${candidate.homeTeam} vs ${candidate.awayTeam}\n${candidate.market}: ${candidate.selection} @ ${candidate.odds.toFixed(2)}\nModel: ${percent(candidate.modelProbability)} | Edge: ${percent(candidate.estimatedEdge)} | EV: ${percent(candidate.expectedValue ?? 0)} | Rank: ${percent(candidate.rankingScore ?? 0)}\nReason: ${candidate.reason}`;
}

export function formatSlip(draft: DraftSlip): string {
  const legs = draft.candidates.length === 0
    ? "No qualifying bet."
    : draft.candidates.map((candidate, index) => `${index + 1}. ${formatCandidate(candidate)}`).join("\n\n");
  const title = draft.status === "abstain" ? "No qualifying bet" : "Filtered picks";
  return `${title}\n\n${legs}\n\nCombined odds: ${draft.combinedOdds.toFixed(2)}\nEstimated joint probability: ${percent(draft.estimatedJointProbability)}\n\n${draft.warnings.join("\n")}`;
}
