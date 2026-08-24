import type { IngestionQualityRequest, IngestionQualityResponse, TodayCandidatesResponse } from "@safe-picks/contracts";
import { applyCorrelationFilter, defaultDecisionConfig, evaluateCandidate } from "./decision.js";

export class ForecastingServiceError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly reasons: Array<{ code: string; details: Record<string, unknown> }> = [],
    readonly audit?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ForecastingServiceError";
  }
}

async function parseServiceError(response: Response): Promise<ForecastingServiceError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const error = payload && typeof payload === "object" && "error" in payload ? payload.error : undefined;
  if (error && typeof error === "object") {
    const value = error as Record<string, unknown>;
    return new ForecastingServiceError(
      typeof value.message === "string" ? value.message : `Forecasting service returned ${response.status}`,
      response.status,
      typeof value.code === "string" ? value.code : "FORECASTING_SERVICE_ERROR",
      Array.isArray(value.reasons) ? value.reasons as Array<{ code: string; details: Record<string, unknown> }> : [],
      value.audit && typeof value.audit === "object" ? value.audit as Record<string, unknown> : undefined,
    );
  }
  return new ForecastingServiceError(`Forecasting service returned ${response.status}`, response.status, "FORECASTING_SERVICE_ERROR");
}

export async function getTodayCandidates(baseUrl: string): Promise<TodayCandidatesResponse> {
  const response = await fetch(`${baseUrl}/v1/candidates/today`);
  if (!response.ok) throw await parseServiceError(response);
  const payload = (await response.json()) as TodayCandidatesResponse;
  const config = {
    ...defaultDecisionConfig,
    now: new Date(),
    maxOddsAgeMinutes: Number(process.env.ODDS_MAX_AGE_MINUTES ?? defaultDecisionConfig.maxOddsAgeMinutes),
  };
  const evaluated = payload.candidates.map((candidate) => evaluateCandidate(candidate, candidate.marketQuotes ?? [], config));
  return { ...payload, candidates: applyCorrelationFilter(evaluated) };
}

export async function validateIngestionQuality(
  baseUrl: string,
  payload: IngestionQualityRequest,
): Promise<IngestionQualityResponse> {
  const response = await fetch(`${baseUrl}/v1/ingestion/quality`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await parseServiceError(response);
  return (await response.json()) as IngestionQualityResponse;
}
