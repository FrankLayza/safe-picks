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

export interface SlipBuildContext {
  sourceWarnings?: string[];
  diagnosticCodes?: string[];
}

export function buildDraft(candidates: MarketCandidate[], targetOdds: number, maxLegs: number, context: SlipBuildContext = {}): DraftSlip {
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
  const warnings = uniqueWarnings([
    "Model-backed development candidates are not betting advice.",
    "Joint probability uses the Frechet lower bound for unknown dependence; it is not a profitability estimate.",
    `Independence reference: ${(independenceProbability * 100).toFixed(1)}%.`,
    ...(context.sourceWarnings ?? []),
  ]);
  if (selected.length === 0) {
    const abstention = buildAbstention(candidates, context.diagnosticCodes ?? []);
    return {
      targetOdds,
      maxLegs,
      candidates: [],
      combinedOdds: 0,
      estimatedJointProbability: 0,
      independenceJointProbability: 0,
      jointProbabilityMethod: "empty_slip",
      abstention,
      sourceWarnings: context.sourceWarnings ?? [],
      sourceDiagnosticCodes: context.diagnosticCodes ?? [],
      status: "abstain",
      warnings: uniqueWarnings(["No qualifying bet.", abstention.reason, ...(context.sourceWarnings ?? [])]),
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
    sourceWarnings: context.sourceWarnings ?? [],
    sourceDiagnosticCodes: context.diagnosticCodes ?? [],
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
  const rebuilt = buildDraft(candidates, draft.targetOdds, draft.maxLegs, {
    sourceWarnings: draft.sourceWarnings,
    diagnosticCodes: draft.sourceDiagnosticCodes,
  });
  return {
    ...rebuilt,
    removedLegs: [...(draft.removedLegs ?? []), removal],
  };
}

function buildAbstention(candidates: MarketCandidate[], diagnosticCodes: string[]): NonNullable<DraftSlip["abstention"]> {
  const statusCounts = { eligible: 0, rejected: 0, abstain: 0 };
  const rejectionCounts: Record<string, number> = {};
  for (const candidate of candidates) {
    statusCounts[candidate.status] += 1;
    const code = candidate.rejectionCode ?? (candidate.status === "abstain" ? "MODEL_ABSTAINED" : "UNSPECIFIED_REJECTION");
    if (candidate.status !== "eligible") rejectionCounts[code] = (rejectionCounts[code] ?? 0) + 1;
  }
  const reason = candidates.length === 0
    ? "The forecasting service returned no candidate that could be evaluated."
    : `All ${candidates.length} candidates were rejected or abstained by the current eligibility rules.`;
  return {
    code: "NO_ELIGIBLE_CANDIDATES",
    reason,
    candidateCount: candidates.length,
    statusCounts,
    rejectionCounts,
    diagnosticCodes: [...new Set(diagnosticCodes)].sort(),
  };
}

function uniqueWarnings(warnings: string[]): string[] {
  return [...new Set(warnings.filter(Boolean))];
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
