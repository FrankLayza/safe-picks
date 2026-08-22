import type { TodayCandidatesResponse } from "@safe-picks/contracts";
import { applyCorrelationFilter, defaultDecisionConfig, evaluateCandidate } from "./decision.js";

export async function getTodayCandidates(baseUrl: string): Promise<TodayCandidatesResponse> {
  const response = await fetch(`${baseUrl}/v1/candidates/today`);
  if (!response.ok) throw new Error(`Forecasting service returned ${response.status}`);
  const payload = (await response.json()) as TodayCandidatesResponse;
  const config = {
    ...defaultDecisionConfig,
    now: new Date(),
    maxOddsAgeMinutes: Number(process.env.ODDS_MAX_AGE_MINUTES ?? defaultDecisionConfig.maxOddsAgeMinutes),
  };
  const evaluated = payload.candidates.map((candidate) => evaluateCandidate(candidate, candidate.marketQuotes ?? [], config));
  return { ...payload, candidates: applyCorrelationFilter(evaluated) };
}
