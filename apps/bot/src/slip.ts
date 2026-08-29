import type { DraftSlip, MarketCandidate } from "@safe-picks/contracts";
import { applyCorrelationFilter, rankingScore } from "./decision.js";

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
  const estimatedJointProbability = selected.reduce((total, candidate) => total * candidate.modelProbability, 1);
  const warnings = [
    "Model-backed development candidates are not betting advice.",
    "Joint probability is a conservative independence estimate; real legs may be correlated.",
  ];
  if (selected.length === 0) {
    return {
      targetOdds,
      maxLegs,
      candidates: [],
      combinedOdds: 0,
      estimatedJointProbability: 0,
      status: "abstain",
      warnings: ["No qualifying bet.", "No eligible candidates passed the current selection rules."],
    };
  }
  if (combinedOdds < targetOdds) warnings.push("Target odds were not reached without adding lower-quality legs.");

  return { targetOdds, maxLegs, candidates: selected, combinedOdds, estimatedJointProbability, status: "draft", warnings };
}

export function trimDraft(draft: DraftSlip): DraftSlip {
  const candidates = [...draft.candidates].sort((a, b) => rankingScore(b) - rankingScore(a)).slice(0, Math.max(1, draft.maxLegs - 1));
  return buildDraft(candidates, draft.targetOdds, draft.maxLegs);
}
