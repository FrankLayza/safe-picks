import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { MarketCandidate } from "@safe-picks/contracts";
import { candidateAuditRecord, JsonlDecisionAuditStore, slipAuditRecord } from "../src/audit.js";
import { buildDraft, trimDraft } from "../src/slip.js";

const temporaryDirectories: string[] = [];

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
    odds: 1.8,
    modelProbability: 0.72,
    impliedProbability: 1 / 1.8,
    estimatedEdge: 0.12,
    expectedValue: 0.296,
    rankingScore: 0.08,
    uncertainty: 0.1,
    dataCompleteness: 0.95,
    calibrationError: 0.04,
    distributionShift: 0.02,
    correlationGroups: ["fixture-1", "team:home", "team:away"],
    modelVersion: "poisson-dixon-coles-v1+calibrated",
    oddsObservedAt: "2026-08-23T12:00:00Z",
    status: "eligible",
    reason: "Passed eligibility and value gates.",
    ...overrides,
  };
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

describe("decision audit records", () => {
  it("captures candidate decisions and versioned provenance", () => {
    const record = candidateAuditRecord(candidate({ status: "rejected", rejectionCode: "LOW_EDGE" }), {
      requestId: "request-1",
      source: "forecasting-service",
      generatedAt: "2026-08-23T12:01:00Z",
      sourceManifest: "normalized/odds.json",
      decisionAt: "2026-08-23T12:02:00Z",
    });

    expect(record).toMatchObject({
      eventType: "candidate_decision",
      candidateId: "candidate-1",
      status: "rejected",
      rejectionCode: "LOW_EDGE",
      modelVersion: "poisson-dixon-coles-v1+calibrated",
      provenance: {
        schemaVersion: "decision-audit-v1",
        producer: "safe-picks-bot",
        requestId: "request-1",
        source: "forecasting-service",
        generatedAt: "2026-08-23T12:01:00Z",
        sourceManifest: "normalized/odds.json",
        decisionAt: "2026-08-23T12:02:00Z",
      },
    });
    expect(record.eventId).toEqual(expect.any(String));
    expect(record.provenance.recordedAt).toEqual(expect.any(String));
  });

  it("captures build and trim outcomes in an append-only JSONL file", async () => {
    const directory = await mkdtemp(join(tmpdir(), "safe-picks-audit-"));
    temporaryDirectories.push(directory);
    const path = join(directory, "decisions.jsonl");
    const store = new JsonlDecisionAuditStore(path);
    const first = candidate({
      id: "strong",
      fixtureId: "fixture-strong",
      estimatedEdge: 0.2,
      rankingScore: 0.2,
      correlationGroups: ["fixture-strong", "team:home", "team:away"],
    });
    const second = candidate({
      id: "weak",
      fixtureId: "fixture-weak",
      estimatedEdge: 0.01,
      rankingScore: 0.01,
      correlationGroups: ["fixture-weak", "team:other-home", "team:other-away"],
    });
    const draft = buildDraft([first, second], 3, 2, {
      sourceManifest: "normalized/odds.json",
      sourceGeneratedAt: "2026-08-23T12:01:00Z",
    });
    const trimmed = trimDraft(draft);
    const context = {
      requestId: "request-2",
      source: "forecasting-service" as const,
      generatedAt: "2026-08-23T12:01:00Z",
      sourceManifest: "normalized/odds.json",
    };

    await store.append([slipAuditRecord(draft, context, "build", 2)]);
    await store.append([slipAuditRecord(trimmed, context, "trim", 2)]);

    const records = (await readFile(path, "utf8")).trim().split("\n").map((line) => JSON.parse(line));
    expect(records).toHaveLength(2);
    expect(records[0]).toMatchObject({
      eventType: "slip_decision",
      action: "build",
      status: "draft",
      candidateCount: 2,
      selectedCandidateIds: ["strong", "weak"],
      provenance: { requestId: "request-2", sourceManifest: "normalized/odds.json" },
    });
    expect(records[1]).toMatchObject({
      eventType: "slip_decision",
      action: "trim",
      selectedCandidateIds: ["strong"],
      removedLegs: [{ candidateId: "weak", code: "LOWEST_RISK_ADJUSTED_RANK" }],
    });
  });
});
