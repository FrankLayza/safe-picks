import type { TodayCandidatesResponse } from "@safe-picks/contracts";

export async function getTodayCandidates(baseUrl: string): Promise<TodayCandidatesResponse> {
  const response = await fetch(`${baseUrl}/v1/candidates/today`);
  if (!response.ok) throw new Error(`Forecasting service returned ${response.status}`);
  return (await response.json()) as TodayCandidatesResponse;
}
