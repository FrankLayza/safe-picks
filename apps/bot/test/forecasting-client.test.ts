import { describe, expect, it, vi } from "vitest";
import { ForecastingServiceError, validateIngestionQuality } from "../src/forecasting-client.js";

describe("forecasting service diagnostics", () => {
  it("preserves machine-readable ingestion rejection details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "ingestion_quality_rejected",
              message: "ingestion quality checks failed",
              reasons: [{ code: "stale_snapshot", details: { age_seconds: 700000 } }],
              audit: { status: "rejected" },
            },
          }),
          { status: 422, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    await expect(
      validateIngestionQuality("http://localhost:8000", {
        snapshot_retrieved_at: "2026-08-23T12:00:00Z",
        records: [],
      }),
    ).rejects.toMatchObject({
      name: "ForecastingServiceError",
      status: 422,
      code: "ingestion_quality_rejected",
      reasons: [{ code: "stale_snapshot" }],
    } satisfies Partial<ForecastingServiceError>);
  });
});
