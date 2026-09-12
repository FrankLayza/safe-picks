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
  sourceManifest?: string;
  sourceGeneratedAt?: string;
  source?: "development-mock" | "forecasting-service";
}

function getCombinations<T>(items: T[], k: number): T[][] {
  if (k === 0) return [[]];
  if (items.length < k) return [];
  const [first, ...rest] = items;
  const withFirst = getCombinations(rest, k - 1).map((combo) => [first, ...combo]);
  const withoutFirst = getCombinations(rest, k);
  return [...withFirst, ...withoutFirst];
}

export function selectSlipCandidates(
  candidates: MarketCandidate[],
  targetOdds: number,
  maxLegs: number
): MarketCandidate[] {
  // Take top candidates from distinct fixtures to keep combination space focused and fast
  const distinctFixtureMap = new Map<string, MarketCandidate>();
  for (const c of candidates) {
    if (!distinctFixtureMap.has(c.fixtureId)) {
      distinctFixtureMap.set(c.fixtureId, c);
    }
  }
  const pool = Array.from(distinctFixtureMap.values()).slice(0, 12);

  let bestCombo: MarketCandidate[] = [];
  let bestScore = -Infinity;

  const maxK = Math.min(maxLegs, pool.length);
  for (let k = 1; k <= maxK; k++) {
    const combos = getCombinations(pool, k);
    for (const combo of combos) {
      // Check correlation groups
      const seenGroups = new Set<string>();
      let conflict = false;
      for (const item of combo) {
        for (const group of item.correlationGroups ?? [item.fixtureId]) {
          if (seenGroups.has(group)) {
            conflict = true;
            break;
          }
          seenGroups.add(group);
        }
        if (conflict) break;
      }
      if (conflict) continue;

      const combinedOdds = combo.reduce((acc, item) => acc * item.odds, 1);
      const qualityScore = combo.reduce((acc, item) => acc + rankingScore(item), 0);
      const probabilities = combo.map((item) => item.modelProbability);
      const jointProb = conservativeJointProbability(probabilities);

      let score: number;
      if (combinedOdds >= targetOdds) {
        const overshootRatio = (combinedOdds - targetOdds) / targetOdds;
        // Reward reaching target odds, penalize excessive overshoot so slips don't blow up
        score = 10.0 + qualityScore + jointProb - 2.0 * overshootRatio - 0.05 * combo.length;
      } else {
        const underRatio = (targetOdds - combinedOdds) / targetOdds;
        score = qualityScore + jointProb - 3.0 * underRatio;
      }

      if (score > bestScore) {
        bestScore = score;
        bestCombo = combo;
      }
    }
  }

  // Fallback: if no valid combination found (e.g. all conflicts), greedily take up to maxLegs
  if (bestCombo.length === 0 && candidates.length > 0) {
    const fallback: MarketCandidate[] = [];
    const used = new Set<string>();
    for (const c of candidates) {
      if (fallback.length >= maxLegs || used.has(c.fixtureId)) continue;
      fallback.push(c);
      used.add(c.fixtureId);
      const currentOdds = fallback.reduce((acc, item) => acc * item.odds, 1);
      if (currentOdds >= targetOdds) break;
    }
    return fallback;
  }

  return bestCombo.sort((a, b) => rankingScore(b) - rankingScore(a));
}

export function buildDraft(candidates: MarketCandidate[], targetOdds: number, maxLegs: number, context: SlipBuildContext = {}): DraftSlip {
  const ranked = applyCorrelationFilter(candidates)
    .filter((candidate) => candidate.status === "eligible")
    .sort((a, b) => rankingScore(b) - rankingScore(a));

  if (ranked.length === 0) {
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
      sourceManifest: context.sourceManifest,
      sourceGeneratedAt: context.sourceGeneratedAt,
      source: context.source,
      status: "abstain",
      warnings: uniqueWarnings(["No qualifying bet.", abstention.reason, ...(context.sourceWarnings ?? [])]),
    };
  }

  const selected = selectSlipCandidates(ranked, targetOdds, maxLegs);
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
  if (combinedOdds < targetOdds) warnings.push("Target odds were not reached without adding lower-quality fixtures.");

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
    sourceManifest: context.sourceManifest,
    sourceGeneratedAt: context.sourceGeneratedAt,
    source: context.source,
    status: "draft",
    warnings,
  };
}

export function trimDraft(draft: DraftSlip): DraftSlip {
  if (draft.candidates.length <= 1) {
    const warning = "Trim kept the final remaining fixture.";
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
    sourceManifest: draft.sourceManifest,
    sourceGeneratedAt: draft.sourceGeneratedAt,
    source: draft.source,
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
