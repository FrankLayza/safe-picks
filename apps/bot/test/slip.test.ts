import { describe, expect, it } from "vitest";
import type { MarketCandidate } from "@safe-picks/contracts";
import { parseSafeBetsArgs } from "../src/commands.js";
import { formatSlip } from "../src/format.js";
import { buildDraft, conservativeJointProbability, independenceJointProbability, trimDraft } from "../src/slip.js";

function candidate(overrides: Partial<MarketCandidate> = {}): MarketCandidate {
  return {
    id: "candidate-1",
    fixtureId: "fixture-1",
    kickoff: "2026-08-23T18:00:00Z",
    homeTeam: "Home FC",
    awayTeam: "Away FC",
    market: "goals_over_under",
    selection: "Over 1.5 goals",
    line: 1.5,
    odds: 1.5,
    modelProbability: 0.75,
    impliedProbability: 2 / 3,
    estimatedEdge: 0.08,
    uncertainty: 0.1,
    dataCompleteness: 0.95,
    calibrationError: 0.04,
    distributionShift: 0.05,
    modelVersion: "test-v1",
    oddsObservedAt: "2026-08-23T12:00:00Z",
    status: "eligible",
    reason: "Test candidate",
    ...overrides,
  };
}

describe("safe bets command parsing", () => {
  it("uses documented defaults", () => {
    expect(parseSafeBetsArgs("/safe_bets")).toEqual({ targetOdds: 3, maxLegs: 3 });
  });

  it("parses target odds and maximum legs", () => {
    expect(parseSafeBetsArgs("/safe_bets 4.25 5")).toEqual({ targetOdds: 4.25, maxLegs: 5 });
  });

  it("rejects invalid odds and leg counts", () => {
    expect(() => parseSafeBetsArgs("/safe_bets 0.9 3")).toThrow("Usage:");
    expect(() => parseSafeBetsArgs("/safe_bets 3 9")).toThrow("Usage:");
    expect(() => parseSafeBetsArgs("/safe_bets 3 2.5")).toThrow("Usage:");
  });
});

describe("draft selection", () => {
  it("uses a conservative Frechet lower bound and exposes the independence reference", () => {
    expect(independenceJointProbability([0.8, 0.7])).toBeCloseTo(0.56);
    expect(conservativeJointProbability([0.8, 0.7])).toBeCloseTo(0.5);

    const draft = buildDraft([
      candidate({ id: "one", fixtureId: "fixture-one", modelProbability: 0.8 }),
      candidate({ id: "two", fixtureId: "fixture-two", modelProbability: 0.7 }),
    ], 2, 2);

    expect(draft.estimatedJointProbability).toBeCloseTo(0.5);
    expect(draft.independenceJointProbability).toBeCloseTo(0.56);
    expect(draft.jointProbabilityMethod).toBe("frechet_lower_bound");
  });

  it("ranks eligible candidates by edge and ignores rejected candidates", () => {
    const draft = buildDraft([
      candidate({ id: "low", fixtureId: "fixture-low", estimatedEdge: 0.02 }),
      candidate({ id: "high", fixtureId: "fixture-high", estimatedEdge: 0.12 }),
      candidate({ id: "rejected", fixtureId: "fixture-rejected", estimatedEdge: 0.5, status: "rejected" }),
    ], 2, 2);

    expect(draft.candidates.map(({ id }) => id)).toEqual(["high", "low"]);
  });

  it("prefers quality-adjusted ranking over a larger raw edge", () => {
    const draft = buildDraft([
      candidate({ id: "raw-edge", fixtureId: "fixture-raw", estimatedEdge: 0.14, rankingScore: 0.04 }),
      candidate({ id: "reliable", fixtureId: "fixture-reliable", estimatedEdge: 0.09, rankingScore: 0.07 }),
    ], 2, 2);

    expect(draft.candidates.map(({ id }) => id)).toEqual(["reliable", "raw-edge"]);
  });

  it("selects at most one candidate from each fixture", () => {
    const draft = buildDraft([
      candidate({ id: "fixture-1-high", estimatedEdge: 0.2 }),
      candidate({ id: "fixture-1-low", estimatedEdge: 0.1 }),
      candidate({ id: "fixture-2", fixtureId: "fixture-2", estimatedEdge: 0.05 }),
    ], 2, 3);

    expect(draft.candidates.map(({ id }) => id)).toEqual(["fixture-1-high", "fixture-2"]);
  });

  it("abstains when no candidate is eligible", () => {
    const draft = buildDraft([candidate({ status: "abstain" })], 2, 3);

    expect(draft.status).toBe("abstain");
    expect(draft.candidates).toHaveLength(0);
    expect(draft.warnings).toContain("No qualifying bet.");
    expect(draft.estimatedJointProbability).toBe(0);
    expect(draft.jointProbabilityMethod).toBe("empty_slip");
  });
});

describe("draft trimming", () => {
  it("removes the lowest-edge leg and preserves the stronger legs", () => {
    const draft = buildDraft([
      candidate({ id: "strong", fixtureId: "fixture-strong", estimatedEdge: 0.2 }),
      candidate({ id: "medium", fixtureId: "fixture-medium", estimatedEdge: 0.1 }),
      candidate({ id: "weak", fixtureId: "fixture-weak", estimatedEdge: 0.01 }),
    ], 3, 3);

    const trimmed = trimDraft(draft);
    expect(trimmed.candidates.map(({ id }) => id)).toEqual(["strong", "medium"]);
    expect(trimmed.removedLegs).toHaveLength(1);
    expect(trimmed.removedLegs?.[0]).toMatchObject({
      candidateId: "weak",
      code: "LOWEST_RISK_ADJUSTED_RANK",
      estimatedEdge: 0.01,
    });
    expect(trimmed.removedLegs?.[0].reason).toContain("lowest risk-adjusted rank");
    expect(formatSlip(trimmed)).toContain("Removed legs");
    expect(formatSlip(trimmed)).toContain("[LOWEST_RISK_ADJUSTED_RANK]");
  });

  it("removes one current leg per command and preserves cumulative explanations", () => {
    const draft = buildDraft([
      candidate({ id: "strong", fixtureId: "fixture-strong", rankingScore: 0.2 }),
      candidate({ id: "medium", fixtureId: "fixture-medium", rankingScore: 0.1 }),
      candidate({ id: "weak", fixtureId: "fixture-weak", rankingScore: 0.01 }),
    ], 3, 3);

    const once = trimDraft(draft);
    const twice = trimDraft(once);
    const final = trimDraft(twice);

    expect(once.candidates.map(({ id }) => id)).toEqual(["strong", "medium"]);
    expect(twice.candidates.map(({ id }) => id)).toEqual(["strong"]);
    expect(twice.removedLegs?.map(({ candidateId }) => candidateId)).toEqual(["weak", "medium"]);
    expect(final.candidates.map(({ id }) => id)).toEqual(["strong"]);
    expect(final.removedLegs).toHaveLength(2);
    expect(final.warnings).toContain("Trim kept the final remaining leg.");
  });
});
