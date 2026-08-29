import { randomUUID } from "node:crypto";
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import type {
  CandidateDecisionAuditRecord,
  DecisionAuditProvenance,
  DecisionAuditRecord,
  DraftSlip,
  MarketCandidate,
  SlipDecisionAuditRecord,
} from "@safe-picks/contracts";

export interface AuditContext {
  requestId: string;
  decisionAt?: string;
  source: DecisionAuditProvenance["source"];
  generatedAt?: string;
  sourceManifest?: string;
}

export function newAuditRequestId(): string {
  return randomUUID();
}

export function candidateAuditRecord(
  candidate: MarketCandidate,
  context: AuditContext,
): CandidateDecisionAuditRecord {
  const provenance = provenanceFor(context);
  return {
    eventType: "candidate_decision",
    eventId: randomUUID(),
    provenance,
    candidateId: candidate.id,
    fixtureId: candidate.fixtureId,
    market: candidate.market,
    selection: candidate.selection,
    status: candidate.status,
    rejectionCode: candidate.rejectionCode,
    reason: candidate.reason,
    odds: candidate.odds,
    oddsObservedAt: candidate.oddsObservedAt,
    modelVersion: candidate.modelVersion,
    modelProbability: candidate.modelProbability,
    fairProbability: candidate.fairProbability,
    estimatedEdge: candidate.estimatedEdge,
    expectedValue: candidate.expectedValue,
    rankingScore: candidate.rankingScore,
    uncertainty: candidate.uncertainty,
    dataCompleteness: candidate.dataCompleteness,
    calibrationError: candidate.calibrationError,
    distributionShift: candidate.distributionShift,
    correlationGroups: [...(candidate.correlationGroups ?? [])],
  };
}

export function slipAuditRecord(
  draft: DraftSlip,
  context: AuditContext,
  action: SlipDecisionAuditRecord["action"],
  candidateCount: number,
): SlipDecisionAuditRecord {
  const provenance = provenanceFor({
    ...context,
    generatedAt: context.generatedAt ?? draft.sourceGeneratedAt,
    sourceManifest: context.sourceManifest ?? draft.sourceManifest,
  });
  return {
    eventType: "slip_decision",
    eventId: randomUUID(),
    provenance,
    action,
    status: draft.status,
    targetOdds: draft.targetOdds,
    maxLegs: draft.maxLegs,
    candidateCount,
    selectedCandidateIds: draft.candidates.map((candidate) => candidate.id),
    removedLegs: [...(draft.removedLegs ?? [])],
    combinedOdds: draft.combinedOdds,
    estimatedJointProbability: draft.estimatedJointProbability,
    independenceJointProbability: draft.independenceJointProbability,
    jointProbabilityMethod: draft.jointProbabilityMethod,
    abstentionCode: draft.abstention?.code,
    warnings: [...draft.warnings],
    sourceWarnings: [...(draft.sourceWarnings ?? [])],
    sourceDiagnosticCodes: [...(draft.sourceDiagnosticCodes ?? [])],
    modelVersions: [...new Set(draft.candidates.map((candidate) => candidate.modelVersion))].sort(),
  };
}

export class JsonlDecisionAuditStore {
  private pending: Promise<void> = Promise.resolve();

  constructor(private readonly filePath: string) {}

  append(records: DecisionAuditRecord[]): Promise<void> {
    if (records.length === 0) return this.pending;
    const content = `${records.map((record) => JSON.stringify(record)).join("\n")}\n`;
    this.pending = this.pending
      .catch(() => undefined)
      .then(async () => {
        await mkdir(dirname(this.filePath), { recursive: true });
        await appendFile(this.filePath, content, { encoding: "utf8" });
      });
    return this.pending;
  }
}

function provenanceFor(context: AuditContext): DecisionAuditProvenance {
  const decisionAt = context.decisionAt ?? new Date().toISOString();
  return {
    schemaVersion: "decision-audit-v1",
    producer: "safe-picks-bot",
    requestId: context.requestId,
    recordedAt: new Date().toISOString(),
    decisionAt,
    source: context.source,
    generatedAt: context.generatedAt,
    sourceManifest: context.sourceManifest,
  };
}
