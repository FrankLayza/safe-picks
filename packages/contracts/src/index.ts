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
  qualityPenalty?: number;
  rankingScore?: number;
  fairProbability?: number;
  fairOdds?: number;
  uncertainty: number;
  dataCompleteness: number;
  calibrationError?: number;
  distributionShift?: number;
  correlationGroup?: string;
  modelVersion: string;
  oddsObservedAt: string;
  status: CandidateStatus;
  reason: string;
  rejectionCode?: CandidateRejectionCode;
}

export interface TodayCandidatesResponse {
  generatedAt: string;
  source: "development-mock" | "forecasting-service";
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
  status: "draft" | "abstain";
  warnings: string[];
}
