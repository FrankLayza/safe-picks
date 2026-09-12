export type MarketType =
  | "goals_over_under"
  | "both_teams_to_score"
  | "match_result"
  | "double_chance"
  | "corners_over_under";

export type CandidateStatus = "eligible" | "rejected" | "abstain";

export type CandidateRejectionCode =
  | "INVALID_ODDS"
  | "STALE_ODDS"
  | "MISSING_MARKET_PEERS"
  | "LOW_DATA_COMPLETENESS"
  | "HIGH_UNCERTAINTY"
  | "UNCALIBRATED_MODEL"
  | "DISTRIBUTION_SHIFT"
  | "LOW_EDGE"
  | "SHORT_PRICE_LOW_VALUE"
  | "CORRELATED_SELECTION"
  | "UNSUPPORTED_MARKET";

export interface CandidateDecision {
  status: CandidateStatus;
  rejectionCode?: CandidateRejectionCode;
  reason: string;
}

export interface MarketQuote {
  selection: string;
  odds: number;
}

export interface MarketCandidate {
  id: string;
  fixtureId: string;
  kickoff: string;
  homeTeam: string;
  awayTeam: string;
  market: MarketType;
  selection: string;
  line?: number;
  odds: number;
  marketQuotes?: MarketQuote[];
  modelProbability: number;
  impliedProbability: number;
  estimatedEdge: number;
  expectedValue?: number;
  qualityPenalty?: number;
  rankingScore?: number;
  fairProbability?: number;
  fairOdds?: number;
  uncertainty: number;
  dataCompleteness: number;
  calibrationError?: number;
  distributionShift?: number;
  correlationGroup?: string;
  correlationGroups?: string[];
  modelVersion: string;
  oddsObservedAt: string;
  status: CandidateStatus;
  reason: string;
  rejectionCode?: CandidateRejectionCode;
}

export interface TodayCandidatesResponse {
  generatedAt: string;
  source: "development-mock" | "forecasting-service";
  status?: "candidates_available" | "abstain";
  abstentionCode?: "NO_ELIGIBLE_CANDIDATES";
  sourceManifest?: string;
  candidates: MarketCandidate[];
  warnings: string[];
  diagnostics?: IngestionQualityReason[];
}

export interface IngestionQualityReason {
  code: string;
  details: Record<string, unknown>;
}

export interface IngestionQualityAudit {
  status: "pass" | "rejected";
  freshness?: Record<string, unknown>;
  missingness?: Record<string, unknown>;
  reasons: IngestionQualityReason[];
}

export interface IngestionQualityResponse {
  status: "pass" | "rejected";
  code?: string;
  message?: string;
  reasons: IngestionQualityReason[];
  audit: IngestionQualityAudit;
}

export interface IngestionQualityRequest {
  snapshot_retrieved_at: string;
  reference_at?: string;
  max_snapshot_age_seconds?: number;
  max_optional_missing_fraction?: number;
  records: Array<Record<string, unknown>>;
}

export interface DraftSlip {
  targetOdds: number;
  maxLegs: number;
  candidates: MarketCandidate[];
  combinedOdds: number;
  estimatedJointProbability: number;
  independenceJointProbability?: number;
  jointProbabilityMethod?: "frechet_lower_bound" | "single_leg" | "empty_slip";
  removedLegs?: SlipRemoval[];
  abstention?: SlipAbstention;
  sourceWarnings?: string[];
  sourceDiagnosticCodes?: string[];
  sourceManifest?: string;
  sourceGeneratedAt?: string;
  source?: "development-mock" | "forecasting-service";
  status: "draft" | "abstain";
  warnings: string[];
}

export type SlipRemovalCode = "LOWEST_RISK_ADJUSTED_RANK";

export type SlipAbstentionCode = "NO_ELIGIBLE_CANDIDATES";

export interface SlipAbstention {
  code: SlipAbstentionCode;
  reason: string;
  candidateCount: number;
  statusCounts: Record<CandidateStatus, number>;
  rejectionCounts: Record<string, number>;
  diagnosticCodes: string[];
}

export interface SlipRemoval {
  candidateId: string;
  fixtureId: string;
  homeTeam: string;
  awayTeam: string;
  market: MarketType;
  selection: string;
  odds: number;
  rankingScore: number;
  estimatedEdge: number;
  uncertainty: number;
  dataCompleteness: number;
  code: SlipRemovalCode;
  reason: string;
}

export interface DecisionAuditProvenance {
  schemaVersion: "decision-audit-v1";
  producer: "safe-picks-bot";
  requestId: string;
  recordedAt: string;
  decisionAt: string;
  source: "development-mock" | "forecasting-service";
  generatedAt?: string;
  sourceManifest?: string;
}

export interface CandidateDecisionAuditRecord {
  eventType: "candidate_decision";
  eventId: string;
  provenance: DecisionAuditProvenance;
  candidateId: string;
  fixtureId: string;
  market: MarketType;
  selection: string;
  status: CandidateStatus;
  rejectionCode?: string;
  reason: string;
  odds: number;
  oddsObservedAt: string;
  modelVersion: string;
  modelProbability: number;
  fairProbability?: number;
  estimatedEdge: number;
  expectedValue?: number;
  rankingScore?: number;
  uncertainty: number;
  dataCompleteness: number;
  calibrationError?: number;
  distributionShift?: number;
  correlationGroups: string[];
}

export interface SlipDecisionAuditRecord {
  eventType: "slip_decision";
  eventId: string;
  provenance: DecisionAuditProvenance;
  action: "build" | "trim";
  status: DraftSlip["status"];
  targetOdds: number;
  maxLegs: number;
  candidateCount: number;
  selectedCandidateIds: string[];
  removedLegs: SlipRemoval[];
  combinedOdds: number;
  estimatedJointProbability: number;
  independenceJointProbability?: number;
  jointProbabilityMethod?: DraftSlip["jointProbabilityMethod"];
  abstentionCode?: SlipAbstentionCode;
  warnings: string[];
  sourceWarnings: string[];
  sourceDiagnosticCodes: string[];
  modelVersions: string[];
}

export type DecisionAuditRecord = CandidateDecisionAuditRecord | SlipDecisionAuditRecord;

// ---------------------------------------------------------------------------
// Paper-trading ledger
// ---------------------------------------------------------------------------

export type PaperTradeStatus = "pending" | "settled_win" | "settled_loss" | "void";

export interface PaperTrade {
  /** Unique identifier for this paper trade record. */
  tradeId: string;
  /** Links back to the slip_decision audit event that generated this trade. */
  slipEventId: string;
  /** Telegram chat ID that owns this trade. */
  chatId: number;
  fixtureId: string;
  kickoff: string;
  homeTeam: string;
  awayTeam: string;
  market: MarketType;
  selection: string;
  /** Decimal odds at decision time. */
  odds: number;
  modelProbability: number;
  estimatedEdge: number;
  expectedValue?: number;
  rankingScore?: number;
  modelVersion: string;
  oddsObservedAt: string;
  /** Stake in units (default 1.0). */
  stake: number;
  status: PaperTradeStatus;
  /** ISO timestamp when the trade was opened. */
  openedAt: string;
  /** ISO timestamp when the trade was settled (win/loss/void). */
  settledAt?: string;
  /** Profit/loss in units. Positive for wins, negative for losses, 0 for void. */
  profitLoss?: number;
}

export interface PaperTradeReport {
  generatedAt: string;
  totalBets: number;
  pendingBets: number;
  settledBets: number;
  wins: number;
  losses: number;
  voids: number;
  winRate: number | null;
  totalStake: number;
  totalReturn: number;
  profitLoss: number;
  roi: number | null;
  avgModelEdge: number | null;
  byMarket: Record<string, { bets: number; wins: number; losses: number; voids: number; profitLoss: number }>;
}
