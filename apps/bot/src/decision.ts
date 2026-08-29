import type { CandidateDecision, CandidateRejectionCode, MarketCandidate, MarketQuote, MarketType } from "@safe-picks/contracts";

export interface DecisionConfig {
  now: Date;
  maxOddsAgeMinutes: number;
  minDataCompleteness: number;
  maxUncertainty: number;
  maxCalibrationError: number;
  maxDistributionShift: number;
  minEdge: number;
}

export const defaultDecisionConfig: Omit<DecisionConfig, "now"> = {
  maxOddsAgeMinutes: 15,
  minDataCompleteness: 0.8,
  maxUncertainty: 0.25,
  maxCalibrationError: 0.1,
  maxDistributionShift: 0.2,
  minEdge: 0.02,
};

const supportedMarkets = new Set<MarketType>([
  "goals_over_under",
  "both_teams_to_score",
  "match_result",
  "double_chance",
  "corners_over_under",
]);

function rejection(code: CandidateRejectionCode, reason: string): CandidateDecision {
  return { status: "rejected", rejectionCode: code, reason };
}

function ageMinutes(observedAt: string, now: Date): number {
  const timestamp = Date.parse(observedAt);
  if (!Number.isFinite(timestamp)) return Number.POSITIVE_INFINITY;
  return Math.max(0, now.getTime() - timestamp) / 60_000;
}

export function deVigProbabilities(quotes: MarketQuote[]): Map<string, number> {
  const valid = quotes.filter((quote) => Number.isFinite(quote.odds) && quote.odds > 1);
  const raw = valid.map((quote) => ({ selection: quote.selection, probability: 1 / quote.odds }));
  const total = raw.reduce((sum, quote) => sum + quote.probability, 0);
  if (total <= 0) return new Map();
  return new Map(raw.map((quote) => [quote.selection, quote.probability / total]));
}

export function expectedValue(probability: number, odds: number): number {
  return probability * odds - 1;
}

function unitInterval(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function candidateRanking(candidate: MarketCandidate, eligible = candidate.status === "eligible"): { qualityPenalty: number; rankingScore: number } {
  const positiveEdge = Math.max(0, candidate.estimatedEdge);
  if (!eligible || candidate.calibrationError === undefined) return { qualityPenalty: positiveEdge, rankingScore: 0 };
  const reliability = unitInterval(candidate.dataCompleteness)
    * (1 - unitInterval(candidate.uncertainty))
    * (1 - unitInterval(candidate.calibrationError))
    * (1 - unitInterval(candidate.distributionShift ?? 0));
  const rankingScore = positiveEdge * reliability;
  return { qualityPenalty: positiveEdge - rankingScore, rankingScore };
}

export function rankingScore(candidate: MarketCandidate): number {
  return candidate.rankingScore !== undefined && Number.isFinite(candidate.rankingScore)
    ? candidate.rankingScore
    : candidateRanking(candidate).rankingScore;
}

export function evaluateCandidate(
  candidate: MarketCandidate,
  marketQuotes: MarketQuote[],
  config: DecisionConfig,
): MarketCandidate {
  let decision: CandidateDecision | undefined;
  if (!supportedMarkets.has(candidate.market)) decision = rejection("UNSUPPORTED_MARKET", "This market is not enabled for the current release.");
  else if (!Number.isFinite(candidate.odds) || candidate.odds <= 1) decision = rejection("INVALID_ODDS", "The available odds are invalid.");
  else if (ageMinutes(candidate.oddsObservedAt, config.now) > config.maxOddsAgeMinutes) decision = rejection("STALE_ODDS", "The odds are older than the configured freshness limit.");
  else if (marketQuotes.length < 2) decision = rejection("MISSING_MARKET_PEERS", "At least two mutually exclusive market prices are required to remove the bookmaker margin.");
  else if (candidate.dataCompleteness < config.minDataCompleteness) decision = rejection("LOW_DATA_COMPLETENESS", "Critical pre-match data is incomplete.");
  else if (candidate.uncertainty > config.maxUncertainty) decision = rejection("HIGH_UNCERTAINTY", "Model uncertainty exceeds the configured limit.");
  else if (candidate.calibrationError === undefined || candidate.calibrationError > config.maxCalibrationError) decision = rejection("UNCALIBRATED_MODEL", "The market model has not met the calibration threshold.");
  else if ((candidate.distributionShift ?? 0) > config.maxDistributionShift) decision = rejection("DISTRIBUTION_SHIFT", "Current match conditions differ too far from the validated operating range.");

  const fairProbabilities = deVigProbabilities(marketQuotes);
  const fairProbability = fairProbabilities.get(candidate.selection);
  if (!decision && fairProbability === undefined) decision = rejection("MISSING_MARKET_PEERS", "No de-vigged market probability exists for this selection.");

  const edge = fairProbability === undefined ? candidate.estimatedEdge : candidate.modelProbability - fairProbability;
  const pricedCandidate = { ...candidate, estimatedEdge: edge };
  const ranking = candidateRanking(pricedCandidate, !decision);
  if (!decision && edge < config.minEdge) decision = rejection("LOW_EDGE", "The calibrated probability does not clear the minimum value edge.");

  if (decision) {
    return { ...pricedCandidate, ...candidateRanking(pricedCandidate, false), status: decision.status, rejectionCode: decision.rejectionCode, reason: decision.reason, fairProbability, fairOdds: fairProbability ? 1 / fairProbability : undefined };
  }

  return { ...pricedCandidate, ...ranking, status: "eligible", rejectionCode: undefined, reason: "Passed eligibility, freshness, calibration, and value gates.", fairProbability, fairOdds: 1 / (fairProbability as number) };
}

export function applyCorrelationFilter(candidates: MarketCandidate[]): MarketCandidate[] {
  const selected: MarketCandidate[] = [];
  const groups = new Set<string>();
  for (const candidate of [...candidates].sort((a, b) => rankingScore(b) - rankingScore(a))) {
    if (candidate.status !== "eligible" || !candidate.correlationGroup || !groups.has(candidate.correlationGroup)) {
      selected.push(candidate);
      if (candidate.status === "eligible" && candidate.correlationGroup) groups.add(candidate.correlationGroup);
      continue;
    }
    selected.push({ ...candidate, status: "rejected", rejectionCode: "CORRELATED_SELECTION", reason: "A stronger candidate already occupies this correlation group." });
  }
  return selected;
}
