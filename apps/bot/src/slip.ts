import type { DraftSlip, MarketCandidate, SlipRemoval } from "@safe-picks/contracts";
import { applyCorrelationFilter, rankingScore } from "./decision.js";

export function independenceJointProbability(probabilities: number[]): number {
  return probabilities.reduce((total, probability) => total * probability, 1);
}

export function conservativeJointProbability(probabilities: number[]): number {
  if (probabilities.length === 0) return 0;
  const bounded = probabilities.map((probability) => Math.max(0, Math.min(1, probability)));
  return Math.max(0, bounded.reduce((total, probability) => total + probability, 0) - (bounded.length - 1));
}

export function buildDraft(candidates: MarketCandidate[], targetOdds: number, maxLegs: number): DraftSlip {
  const selected: MarketCandidate[] = [];
  const usedFixtures = new Set<string>();
  const ranked = applyCorrelationFilter(candidates)
    .filter((candidate) => candidate.status === "eligible")
    .sort((a, b) => rankingScore(b) - rankingScore(a));

  for (const candidate of ranked) {
    if (selected.length >= maxLegs || usedFixtures.has(candidate.fixtureId)) continue;
    selected.push(candidate);
    usedFixtures.add(candidate.fixtureId);
  }

  const combinedOdds = selected.reduce((total, candidate) => total * candidate.odds, 1);
  const probabilities = selected.map((candidate) => candidate.modelProbability);
  const estimatedJointProbability = conservativeJointProbability(probabilities);
  const independenceProbability = independenceJointProbability(probabilities);
  const warnings = [
    "Model-backed development candidates are not betting advice.",
    "Joint probability uses the Frechet lower bound for unknown dependence; it is not a profitability estimate.",
    `Independence reference: ${(independenceProbability * 100).toFixed(1)}%.`,
  ];
  if (selected.length === 0) {
    return {
      targetOdds,
      maxLegs,
      candidates: [],
      combinedOdds: 0,
      estimatedJointProbability: 0,
      independenceJointProbability: 0,
      jointProbabilityMethod: "empty_slip",
      status: "abstain",
      warnings: ["No qualifying bet.", "No eligible candidates passed the current selection rules."],
    };
  }
  if (combinedOdds < targetOdds) warnings.push("Target odds were not reached without adding lower-quality legs.");

  return {
    targetOdds,
    maxLegs,
    candidates: selected,
    combinedOdds,
    estimatedJointProbability,
    independenceJointProbability: independenceProbability,
    jointProbabilityMethod: selected.length === 1 ? "single_leg" : "frechet_lower_bound",
    status: "draft",
    warnings,
  };
}

export function trimDraft(draft: DraftSlip): DraftSlip {
  if (draft.candidates.length <= 1) {
    const warning = "Trim kept the final remaining leg.";
    return {
      ...draft,
      warnings: draft.warnings.includes(warning) ? draft.warnings : [...draft.warnings, warning],
    };
  }
  const ordered = [...draft.candidates].sort((a, b) => {
    const scoreDifference = rankingScore(a) - rankingScore(b);
    return scoreDifference === 0 ? a.id.localeCompare(b.id) : scoreDifference;
  });
  const removed = ordered[0];
  const candidates = draft.candidates.filter((candidate) => candidate.id !== removed.id);
  const removal = trimRemoval(removed);
  const rebuilt = buildDraft(candidates, draft.targetOdds, draft.maxLegs);
  return {
    ...rebuilt,
    removedLegs: [...(draft.removedLegs ?? []), removal],
  };
}

function trimRemoval(candidate: MarketCandidate): SlipRemoval {
  const score = rankingScore(candidate);
  return {
    candidateId: candidate.id,
    fixtureId: candidate.fixtureId,
    homeTeam: candidate.homeTeam,
    awayTeam: candidate.awayTeam,
    market: candidate.market,
    selection: candidate.selection,
    odds: candidate.odds,
    rankingScore: score,
    estimatedEdge: candidate.estimatedEdge,
    uncertainty: candidate.uncertainty,
    dataCompleteness: candidate.dataCompleteness,
    code: "LOWEST_RISK_ADJUSTED_RANK",
    reason: `Removed ${candidate.selection} from ${candidate.homeTeam} vs ${candidate.awayTeam}: lowest risk-adjusted rank ${(score * 100).toFixed(1)}% (edge ${(candidate.estimatedEdge * 100).toFixed(1)}%, uncertainty ${(candidate.uncertainty * 100).toFixed(1)}%, completeness ${(candidate.dataCompleteness * 100).toFixed(1)}%).`,
  };
}
