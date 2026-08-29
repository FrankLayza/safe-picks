import { describe, expect, it } from "vitest";
import type { MarketCandidate } from "@safe-picks/contracts";
import {
  applyCorrelationFilter,
  candidateRanking,
  deVigProbabilities,
  evaluateCandidate,
  expectedValue,
  type DecisionConfig,
} from "../src/decision.js";

const config: DecisionConfig = {
  now: new Date("2026-08-23T12:10:00Z"),
  maxOddsAgeMinutes: 15,
  minDataCompleteness: 0.8,
  maxUncertainty: 0.25,
  maxCalibrationError: 0.1,
  maxDistributionShift: 0.2,
  minEdge: 0.02,
};

function candidate(overrides: Partial<MarketCandidate> = {}): MarketCandidate {
  return {
    id: "candidate-1",
    fixtureId: "fixture-1",
    kickoff: "2026-08-23T18:00:00Z",
    homeTeam: "Home FC",
    awayTeam: "Away FC",
    market: "match_result",
    selection: "Home",
    odds: 2.1,
    modelProbability: 0.52,
    impliedProbability: 1 / 2.1,
    estimatedEdge: 0,
    uncertainty: 0.1,
    dataCompleteness: 0.95,
    calibrationError: 0.04,
    distributionShift: 0.05,
    correlationGroup: "fixture-1-result",
    modelVersion: "test-v1",
    oddsObservedAt: "2026-08-23T12:00:00Z",
    status: "eligible",
    reason: "Unprocessed test candidate",
    ...overrides,
  };
}

describe("market value calculations", () => {
  it("removes the bookmaker margin from mutually exclusive prices", () => {
    const probabilities = deVigProbabilities([
      { selection: "Home", odds: 2.1 },
      { selection: "Draw", odds: 3.4 },
      { selection: "Away", odds: 3.6 },
    ]);

    expect(probabilities.get("Home")).toBeCloseTo((1 / 2.1) / (1 / 2.1 + 1 / 3.4 + 1 / 3.6), 8);
    expect([...probabilities.values()].reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 8);
    expect(expectedValue(0.52, 2.1)).toBeCloseTo(0.092, 8);
  });

  it("penalizes edge for uncertainty and incomplete data", () => {
    const strongData = candidateRanking(candidate({ estimatedEdge: 0.08, dataCompleteness: 0.98, uncertainty: 0.02 }));
    const weakData = candidateRanking(candidate({ estimatedEdge: 0.12, dataCompleteness: 0.81, uncertainty: 0.24, calibrationError: 0.09, distributionShift: 0.19 }));

    expect(strongData.rankingScore).toBeGreaterThan(weakData.rankingScore);
    expect(weakData.qualityPenalty).toBeGreaterThan(strongData.qualityPenalty);
  });
});

describe("candidate eligibility gates", () => {
  const quotes = [
    { selection: "Home", odds: 2.1 },
    { selection: "Draw", odds: 3.4 },
    { selection: "Away", odds: 3.6 },
  ];

  it("accepts a calibrated candidate with sufficient edge", () => {
    const result = evaluateCandidate(candidate(), quotes, config);

    expect(result.status).toBe("eligible");
    expect(result.rejectionCode).toBeUndefined();
    expect(result.fairProbability).toBeDefined();
    expect(result.estimatedEdge).toBeGreaterThan(config.minEdge);
    expect(result.rankingScore).toBeGreaterThan(0);
    expect(result.qualityPenalty).toBeGreaterThan(0);
  });

  it.each([
    ["STALE_ODDS", candidate({ oddsObservedAt: "2026-08-23T11:00:00Z" })],
    ["LOW_DATA_COMPLETENESS", candidate({ dataCompleteness: 0.5 })],
    ["HIGH_UNCERTAINTY", candidate({ uncertainty: 0.4 })],
    ["UNCALIBRATED_MODEL", candidate({ calibrationError: undefined })],
    ["DISTRIBUTION_SHIFT", candidate({ distributionShift: 0.4 })],
  ] as const)("rejects with machine-readable code %s", (code, input) => {
    const result = evaluateCandidate(input, quotes, config);

    expect(result.status).toBe("rejected");
    expect(result.rejectionCode).toBe(code);
    expect(result.reason.length).toBeGreaterThan(0);
  });

  it("rejects when the market margin cannot be removed", () => {
    const result = evaluateCandidate(candidate(), [{ selection: "Home", odds: 2.1 }], config);

    expect(result.rejectionCode).toBe("MISSING_MARKET_PEERS");
  });

  it("rejects candidates below the minimum edge", () => {
    const result = evaluateCandidate(candidate({ modelProbability: 0.4 }), quotes, config);

    expect(result.rejectionCode).toBe("LOW_EDGE");
  });
});

describe("correlation filter", () => {
  it("keeps the strongest candidate and rejects weaker candidates in the same group", () => {
    const results = applyCorrelationFilter([
      candidate({ id: "weaker", estimatedEdge: 0.04 }),
      candidate({ id: "stronger", estimatedEdge: 0.12 }),
      candidate({ id: "independent", fixtureId: "fixture-2", correlationGroup: "fixture-2-goals" }),
    ]);

    expect(results.find(({ id }) => id === "stronger")?.status).toBe("eligible");
    expect(results.find(({ id }) => id === "weaker")?.rejectionCode).toBe("CORRELATED_SELECTION");
    expect(results.find(({ id }) => id === "independent")?.status).toBe("eligible");
  });

  it("uses quality-adjusted rank instead of raw edge", () => {
    const results = applyCorrelationFilter([
      candidate({ id: "higher-edge", estimatedEdge: 0.12, rankingScore: 0.04 }),
      candidate({ id: "better-rank", estimatedEdge: 0.08, rankingScore: 0.07 }),
    ]);

    expect(results.find(({ id }) => id === "better-rank")?.status).toBe("eligible");
    expect(results.find(({ id }) => id === "higher-edge")?.rejectionCode).toBe("CORRELATED_SELECTION");
  });
});
